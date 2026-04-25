"""Patch the LiDAR-derived Building_DSM + Landcover with current Overture building
footprints. This catches buildings that were built after the 2015 NC LiDAR was flown.

Source: Overture Maps buildings (combines OpenStreetMap + Microsoft ML + others).
About 73% of Durham buildings have a height attribute in Overture; the remaining
27% have a footprint only.

Strategy at each footprint pixel:
  new_DSM       = max(existing LiDAR DSM, DEM + Overture_height)   if height present
                = existing LiDAR DSM                                if height absent (no bump)
  new_Landcover = 2  (building)                                     for every footprint

The previous version applied a 12m default when Overture had no height. Counting
showed only 15 buildings (1.8%) actually fell into the "no Overture + no LiDAR
support" pocket where a default could possibly help, and they all turned out to be
real short structures (sheds, garages) where 12m was inflating LiDAR's correct ~1m
measurement. Dropping the default avoids that distortion. Footprints without heights
still get reclassed to building in Landcover — outlines update, heights don't.

Operates in-place on inputs/processed/{AOI_NAME}_baseline/. Backs up the originals
to *.preMS.tif on first run.
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
GEOJSON = REPO / "inputs/raw/durham/overture/buildings.geojson"
MARKER = OUT / ".overture_patched"


def fetch_overture_if_missing() -> None:
    if GEOJSON.exists():
        print(f"  [cached] {GEOJSON}")
        return
    GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    # Convert PROCESSING_BBOX to lat/lon for Overture CLI
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
    lon_min, lat_min = t.transform(PROCESSING_BBOX[0], PROCESSING_BBOX[1])
    lon_max, lat_max = t.transform(PROCESSING_BBOX[2], PROCESSING_BBOX[3])
    bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    print(f"  downloading Overture buildings for bbox {bbox} …")
    subprocess.check_call([
        str(REPO / "env/bin/overturemaps"),
        "download", "--bbox", bbox,
        "-f", "geojson", "--type", "building",
        "-o", str(GEOJSON),
    ])


def main() -> None:
    if MARKER.exists():
        print(f"  Overture patch already applied (marker: {MARKER}). Delete .overture_patched to re-run.")
        return

    fetch_overture_if_missing()

    print("== reading existing rasters ==")
    dsm_path = OUT / "Building_DSM.tif"
    dem_path = OUT / "DEM.tif"
    lc_path = OUT / "Landcover.tif"

    # Backup originals (first run only)
    for p in (dsm_path, lc_path):
        bak = p.with_suffix(".preMS.tif")
        if not bak.exists():
            shutil.copyfile(p, bak)
            print(f"  backup: {bak}")

    with rasterio.open(dsm_path) as ds:
        dsm = ds.read(1).astype("float32")
        profile_dsm = ds.profile
        transform = ds.transform
        out_shape = ds.shape
    with rasterio.open(dem_path) as ds:
        dem = ds.read(1).astype("float32")
    with rasterio.open(lc_path) as ds:
        lc = ds.read(1)
        profile_lc = ds.profile

    print("== loading Overture buildings ==")
    bldgs = gpd.read_file(GEOJSON).to_crs("EPSG:32617")
    bldgs = bldgs.cx[PROCESSING_BBOX[0]:PROCESSING_BBOX[2],
                     PROCESSING_BBOX[1]:PROCESSING_BBOX[3]]
    bldgs = bldgs[bldgs.geometry.notna() & ~bldgs.geometry.is_empty].copy()
    n_total = len(bldgs)
    n_with_h = bldgs["height"].notna().sum()
    print(f"  {n_total} buildings in AOI ({n_with_h} have Overture height = {100*n_with_h/n_total:.0f}%)")

    print("== rasterizing footprints ==")
    # Two rasters: a height raster (only buildings with measured Overture heights)
    # and a footprint mask (every building, for landcover reclass).
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
    n_h_px = int((heights_raster > 0).sum())
    n_f_px = int(footprint_mask.sum())
    print(f"  height-bearing footprint pixels: {n_h_px:,} ({100*n_h_px/heights_raster.size:.1f}% of tile)")
    print(f"  total footprint pixels:          {n_f_px:,} ({100*n_f_px/heights_raster.size:.1f}% of tile)")

    print("== applying patch ==")
    # New DSM: bump only where Overture has a real height. Existing LiDAR DSM stays
    # untouched everywhere else — no defaults inflating short structures.
    overture_roof_elev = np.where(heights_raster > 0, dem + heights_raster, dsm)
    new_dsm = np.maximum(dsm, overture_roof_elev).astype("float32")

    delta = new_dsm - dsm
    bumped = (delta > 0.5).sum()
    print(f"  pixels bumped up: {bumped:,}  "
          f"(mean bump where bumped = {delta[delta>0.5].mean() if bumped else 0:.1f}m)")

    # New Landcover: every Overture footprint pixel → building (UMEP=2), heights or not.
    new_lc = lc.copy()
    new_lc[footprint_mask] = 2
    n_reclassed = ((new_lc == 2) & (lc != 2)).sum()
    print(f"  Landcover cells re-classed to building: {n_reclassed:,}")

    print("== writing back ==")
    with rasterio.open(dsm_path, "w", **profile_dsm) as out:
        out.write(new_dsm, 1)
    print(f"  wrote {dsm_path}")
    with rasterio.open(lc_path, "w", **profile_lc) as out:
        out.write(new_lc, 1)
    print(f"  wrote {lc_path}")

    # Verify the gate still holds after the patch
    print("\n== post-patch sanity ==")
    valid = (new_dsm != -9999) & (dem != -9999)
    diff = (new_dsm - dem)[valid]
    p99 = float(np.percentile(diff, 99))
    print(f"  (DSM − DEM) p99 after patch: {p99:.2f}m  (gate: 3 < p99 < 50)")
    vals, counts = np.unique(new_lc, return_counts=True)
    pct = {int(v): f"{100*c/new_lc.size:.1f}%" for v, c in zip(vals, counts)}
    print(f"  Landcover distribution: {pct}")

    MARKER.touch()
    print(f"\n  marked complete: {MARKER}")


if __name__ == "__main__":
    main()
