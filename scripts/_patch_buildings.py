"""Build the SOLWEIG-ready Building_DSM and Landcover from raw LiDAR + Overture.

This implements the canonical UMEP/Lindberg recipe for `Building_DSM` (= ground +
buildings only, no vegetation) by using authoritative building footprints to gate
which LiDAR returns count as "building":

    Building_DSM[cell] =
        if cell ∈ Overture footprint:
            max( LiDAR_first_return[cell],          # measured roof, if available
                 DEM[cell] + Overture_height )      # estimated roof, fallback
        else:
            DEM[cell]                                # flat ground, no trees

This matches the UMEP LiDAR Processing tutorial (which states it's "loosely based
upon the method presented in Lindberg and Grimmond (2011)") — it specifies that
Building_DSM be built from ground returns + unclassified returns clipped to
building polygons. We use Overture footprints as the polygon source.

The previous "max(LiDAR, Overture)" approach was wrong: PDAL first-return max
included tree canopies and other non-building tall objects, which SOLWEIG would
treat as opaque buildings (full SVF blocking, building albedo/emissivity, no
canopy porosity) — and double-count them against Trees.tif.

Landcover follows the same authoritative-footprint principle:
    Landcover[cell] = MULC reclass everywhere; cells inside Overture footprints
    are forced to UMEP class 2 (building).

Reads inputs from inputs/processed/{AOI_NAME}_baseline/:
  - Building_DSM.preMS.tif   (raw LiDAR first-return max — used only inside footprints)
  - DEM.tif                   (bare-earth, hole-filled)
  - MULC_aligned.tif          (raw EnviroAtlas classes, reprojected)
  - Overture buildings GeoJSON (downloaded by fetch step below)

Writes:
  - Building_DSM.tif          (SOLWEIG-ready: ground + buildings only)
  - Landcover.tif             (SOLWEIG-ready: UMEP codes 1, 2, 5, 6, 7)
  - Landcover.preMS.tif       (backup of MULC-only landcover for inspection)
  - .dsm_built marker         (idempotency)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

from _aoi import AOI_NAME, PROCESSING_BBOX

OUT = REPO / f"inputs/processed/{AOI_NAME}_baseline"
# AOI-namespaced so different AOIs get fresh footprint pulls
GEOJSON = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
MARKER = OUT / ".dsm_built"


def fetch_overture_if_missing() -> None:
    if GEOJSON.exists():
        print(f"  [cached] {GEOJSON}")
        return
    GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
    lon_min, lat_min = t.transform(PROCESSING_BBOX[0], PROCESSING_BBOX[1])
    lon_max, lat_max = t.transform(PROCESSING_BBOX[2], PROCESSING_BBOX[3])
    bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    # Resolve overturemaps from PATH (works on pod / system python). Fall back
    # to the laptop conda env's bin if PATH lookup fails.
    overture_bin = shutil.which("overturemaps") or str(REPO / "env/bin/overturemaps")
    print(f"  downloading Overture buildings for bbox {bbox} …")
    print(f"  using {overture_bin}")
    subprocess.check_call([
        overture_bin,
        "download", "--bbox", bbox,
        "-f", "geojson", "--type", "building",
        "-o", str(GEOJSON),
    ])


def reclass_mulc(mulc: np.ndarray) -> np.ndarray:
    """EnviroAtlas MULC 9-class → UMEP 5-class. No height disambiguation here —
    the building/paved split comes from Overture footprints in the next step."""
    lc = np.zeros_like(mulc, dtype="uint8")
    lc[mulc == 10] = 7                                  # water
    lc[mulc == 20] = 1                                  # impervious → paved
    lc[mulc == 30] = 6                                  # bare soil
    lc[(mulc == 40) | (mulc == 70) | (mulc == 80)] = 5  # trees / grass / ag → grass
    lc[(mulc == 91) | (mulc == 92)] = 7                 # wetlands → water
    lc[lc == 0] = 5                                     # unclassified → grass
    return lc


def main() -> None:
    if MARKER.exists():
        print(f"  DSM/Landcover already built (marker: {MARKER}). Delete .dsm_built to re-run.")
        return

    fetch_overture_if_missing()

    print("== reading raw inputs ==")
    dsm_raw_path = OUT / "Building_DSM.preMS.tif"
    dem_path = OUT / "DEM.tif"
    mulc_path = OUT / "MULC_aligned.tif"
    if not dsm_raw_path.exists():
        # Bootstrap: 03_build_rasters.py wrote a single Building_DSM.tif. Promote
        # it to .preMS.tif so future runs treat it as the immutable raw LiDAR DSM.
        shutil.copyfile(OUT / "Building_DSM.tif", dsm_raw_path)
        print(f"  bootstrapped {dsm_raw_path} ← Building_DSM.tif")

    with rasterio.open(dsm_raw_path) as ds:
        lidar_dsm = ds.read(1).astype("float32")
        profile_dsm = ds.profile
        transform = ds.transform
        out_shape = ds.shape
    with rasterio.open(dem_path) as ds:
        dem = ds.read(1).astype("float32")
    with rasterio.open(mulc_path) as ds:
        mulc = ds.read(1)
        profile_mulc = ds.profile

    print("== loading Overture buildings ==")
    bldgs = gpd.read_file(GEOJSON).to_crs("EPSG:32617")
    bldgs = bldgs.cx[PROCESSING_BBOX[0]:PROCESSING_BBOX[2],
                     PROCESSING_BBOX[1]:PROCESSING_BBOX[3]]
    bldgs = bldgs[bldgs.geometry.notna() & ~bldgs.geometry.is_empty].copy()
    n_total = len(bldgs)
    n_with_h = bldgs["height"].notna().sum()
    print(f"  {n_total} buildings in AOI ({n_with_h} have Overture height = "
          f"{100*n_with_h/n_total:.0f}%)")

    print("== rasterizing footprints ==")
    bldgs_with_h = bldgs[bldgs["height"].notna()].copy()
    heights_raster = rasterize(
        ((g, float(h)) for g, h in zip(bldgs_with_h.geometry, bldgs_with_h["height"])),
        out_shape=out_shape, transform=transform,
        fill=0.0, dtype="float32",
    )
    footprint_mask = rasterize(
        ((g, 1) for g in bldgs.geometry),
        out_shape=out_shape, transform=transform,
        fill=0, dtype="uint8",
    ).astype(bool)
    n_f_px = int(footprint_mask.sum())
    print(f"  footprint pixels: {n_f_px:,} ({100*n_f_px/footprint_mask.size:.1f}% of tile)")

    print("== building SOLWEIG Building_DSM (ground + buildings only) ==")
    # Cap LiDAR's contribution at 150 m above ground. Durham's tallest building
    # is the Hill Building / Truist Center at ~91 m; 150 m gives generous headroom
    # for antennas/parapets while filtering out the 1000 m+ first-return spikes
    # (birds, aircraft, glints) that survive even inside building footprints.
    LIDAR_HEIGHT_CAP_M = 150.0

    valid_dem = dem != -9999
    valid_lidar = (lidar_dsm != -9999) & valid_dem
    lidar_capped = np.where(valid_lidar,
                            np.minimum(lidar_dsm, dem + LIDAR_HEIGHT_CAP_M),
                            -9999.0).astype("float32")

    # Default: flat ground everywhere (no trees, no noise spikes).
    new_dsm = np.where(valid_dem, dem, -9999.0).astype("float32")

    # Inside footprints, three cases:
    #   Overture has a height + LiDAR has a measurement → max of the two (capped LiDAR).
    #   Overture has a height, LiDAR is nodata           → Overture roof.
    #   No Overture height, LiDAR has a measurement      → capped LiDAR alone.
    #   No Overture height, no LiDAR                     → leave at DEM (no info).
    overture_roof = dem + heights_raster
    have_overture = heights_raster > 0
    inside = footprint_mask & valid_dem

    case_both = inside & have_overture & valid_lidar
    new_dsm[case_both] = np.maximum(lidar_capped[case_both], overture_roof[case_both])

    case_overture_only = inside & have_overture & ~valid_lidar
    new_dsm[case_overture_only] = overture_roof[case_overture_only]

    case_lidar_only = inside & ~have_overture & valid_lidar
    new_dsm[case_lidar_only] = lidar_capped[case_lidar_only]

    n_both = int(case_both.sum())
    n_oo = int(case_overture_only.sum())
    n_lo = int(case_lidar_only.sum())
    n_neither = int((inside & ~have_overture & ~valid_lidar).sum())
    print(f"  footprint cell sources: both={n_both:,}  overture-only={n_oo:,}  "
          f"lidar-only={n_lo:,}  neither(=DEM)={n_neither:,}")

    h_in_fp = (new_dsm - dem)[inside]
    if h_in_fp.size:
        print(f"  in-footprint heights: median={np.median(h_in_fp):.1f}m  "
              f"p99={np.percentile(h_in_fp, 99):.1f}m  max={h_in_fp.max():.1f}m")
    n_capped = int((valid_lidar & (lidar_dsm > dem + LIDAR_HEIGHT_CAP_M)).sum())
    if n_capped:
        print(f"  LiDAR cells capped at {LIDAR_HEIGHT_CAP_M:.0f}m AGL (noise filter): {n_capped:,}")

    print("== building SOLWEIG Landcover ==")
    lc_mulc_only = reclass_mulc(mulc)
    new_lc = lc_mulc_only.copy()
    new_lc[footprint_mask] = 2  # all footprint cells → building
    n_reclassed = ((new_lc == 2) & (lc_mulc_only != 2)).sum()
    print(f"  cells reclassed to building by Overture: {n_reclassed:,}")

    print("== writing outputs ==")
    dsm_path = OUT / "Building_DSM.tif"
    lc_path = OUT / "Landcover.tif"
    lc_pre_path = OUT / "Landcover.preMS.tif"

    profile_dsm.update(dtype="float32", count=1, nodata=-9999)
    with rasterio.open(dsm_path, "w", **profile_dsm) as out:
        out.write(new_dsm, 1)
    print(f"  wrote {dsm_path}")

    p_lc = profile_mulc.copy()
    p_lc.update(dtype="uint8", count=1, nodata=0, compress="lzw")
    with rasterio.open(lc_path, "w", **p_lc) as out:
        out.write(new_lc, 1)
    print(f"  wrote {lc_path}")
    with rasterio.open(lc_pre_path, "w", **p_lc) as out:
        out.write(lc_mulc_only, 1)
    print(f"  wrote {lc_pre_path}  (MULC-only landcover for comparison)")

    print("\n== post-build sanity ==")
    valid_out = (new_dsm != -9999) & valid_dem
    diff = (new_dsm - dem)[valid_out]
    print(f"  (DSM − DEM) p99={np.percentile(diff, 99):.2f}m  "
          f"max={diff.max():.2f}m  (gate: max < 250 for downtown Durham)")
    vals, counts = np.unique(new_lc, return_counts=True)
    pct = {int(v): f"{100*c/new_lc.size:.1f}%" for v, c in zip(vals, counts)}
    print(f"  Landcover distribution: {pct}")

    MARKER.touch()
    print(f"\n  marked complete: {MARKER}")


if __name__ == "__main__":
    main()
