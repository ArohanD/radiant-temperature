"""LiDAR DSM, DEM, MULC reproject, and the Overture-gated building patch.

Pipeline (in execution order):
  fetch_overture()        — Overture buildings GeoJSON for the AOI bbox.
  pull_lidar_dsm()        — first-return DSM via PDAL from NC Phase 3 EPT.
  build_dem()             — Class=2 ground returns + gdal_fillnodata gap-fill.
  build_landcover_raw()   — reproject EnviroAtlas MULC, snap to PROCESSING_BBOX.
  build_trees_and_landcover() — derive Trees CDSM + UMEP-coded Landcover from
                                 DSM/DEM/MULC. Note: Landcover here has no
                                 building class (UMEP 2) yet; the Overture
                                 footprint patch step assigns it.
  patch_with_overture()   — canonical Lindberg/Grimmond recipe: Building_DSM is
                            ground+buildings only, gated by Overture footprints.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize

EPT_URL = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/6209/ept.json"
LIDAR_HEIGHT_CAP_M = 150.0  # filter LiDAR noise (birds, antennas) above buildings


# ----------------------------------------------------------------- Overture

def fetch_overture(aoi_name: str, processing_bbox: tuple, dst: Path) -> Path:
    """Download Overture Foundation building footprints (GeoJSON) for the AOI bbox.
    Idempotent: returns the cached path if it already exists."""
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    t = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
    lon_min, lat_min = t.transform(processing_bbox[0], processing_bbox[1])
    lon_max, lat_max = t.transform(processing_bbox[2], processing_bbox[3])
    bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    overture_bin = shutil.which("overturemaps")
    if overture_bin is None:
        raise RuntimeError("overturemaps CLI not on PATH — `pip install overturemaps`.")
    print(f"  downloading Overture buildings for bbox {bbox} …")
    subprocess.check_call([
        overture_bin, "download", "--bbox", bbox,
        "-f", "geojson", "--type", "building", "-o", str(dst),
    ])
    return dst


# ------------------------------------------------------------------- PDAL

def _proc_bbox_in(bbox, crs: str):
    t = Transformer.from_crs("EPSG:32617", crs, always_xy=True)
    xmin, ymin = t.transform(bbox[0], bbox[1])
    xmax, ymax = t.transform(bbox[2], bbox[3])
    return (xmin, ymin, xmax, ymax)


def _bounds_str(bbox) -> str:
    return f"([{bbox[0]}, {bbox[2]}], [{bbox[1]}, {bbox[3]}])"


def _run_pdal(pipe: dict, label: str) -> None:
    print(f"  [{label}] running PDAL pipeline …")
    import pdal
    p = pdal.Pipeline(json.dumps(pipe))
    n = p.execute()
    print(f"  [{label}] processed {n:,} points")


def pull_lidar_dsm(processing_bbox: tuple, dst: Path) -> Path:
    """First-return DSM at 1 m, in EPSG:32617. Idempotent."""
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    bbox_native = _proc_bbox_in(processing_bbox, "EPSG:6346")
    pipe = {"pipeline": [
        {"type": "readers.ept", "filename": EPT_URL,
         "bounds": _bounds_str(bbox_native)},
        {"type": "filters.range", "limits": "ReturnNumber[1:1]"},
        {"type": "filters.reprojection", "in_srs": "EPSG:6346", "out_srs": "EPSG:32617"},
        {"type": "writers.gdal", "filename": str(dst),
         "resolution": 1.0, "output_type": "max", "data_type": "float32",
         "bounds": _bounds_str(processing_bbox)},
    ]}
    _run_pdal(pipe, "DSM")
    return dst


def build_dem(processing_bbox: tuple, dst: Path) -> Path:
    """DEM from Class=2 ground returns + gdal_fillnodata gap-fill. Idempotent."""
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    raw = dst.parent / "DEM_raw.tif"
    bbox_native = _proc_bbox_in(processing_bbox, "EPSG:6346")
    pipe = {"pipeline": [
        {"type": "readers.ept", "filename": EPT_URL,
         "bounds": _bounds_str(bbox_native)},
        {"type": "filters.range", "limits": "Classification[2:2]"},
        {"type": "filters.reprojection", "in_srs": "EPSG:6346", "out_srs": "EPSG:32617"},
        {"type": "writers.gdal", "filename": str(raw),
         "resolution": 1.0, "output_type": "idw", "data_type": "float32",
         "bounds": _bounds_str(processing_bbox)},
    ]}
    _run_pdal(pipe, "DEM")
    print(f"  [DEM] filling nodata holes with gdal_fillnodata.py …")
    subprocess.check_call(["gdal_fillnodata.py", "-md", "100", "-si", "0",
                            str(raw), str(dst)])
    return dst


# ------------------------------------------------------------- MULC + Trees

def build_landcover_raw(mulc_src: Path, processing_bbox: tuple, dst: Path) -> Path:
    """Reproject MULC (native EPSG:26917) → EPSG:32617, snap to processing_bbox, 1 m."""
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    cmd = [
        "gdalwarp", "-t_srs", "EPSG:32617", "-tr", "1", "1",
        "-te", *map(str, processing_bbox), "-r", "near",
        "-tap", "-of", "GTiff", "-overwrite",
        str(mulc_src), str(dst),
    ]
    subprocess.check_call(cmd)
    return dst


def reclass_mulc(mulc: np.ndarray) -> np.ndarray:
    """EnviroAtlas MULC 9-class → UMEP 5-class. Building (UMEP 2) is NOT assigned
    here — the Overture footprint patch step does that."""
    lc = np.zeros_like(mulc, dtype="uint8")
    lc[mulc == 10] = 7                                  # water
    lc[mulc == 20] = 1                                  # impervious → paved
    lc[mulc == 30] = 6                                  # bare soil
    lc[(mulc == 40) | (mulc == 70) | (mulc == 80)] = 5  # trees / grass / ag → grass
    lc[(mulc == 91) | (mulc == 92)] = 7                 # wetlands → water
    lc[lc == 0] = 5                                     # unclassified → grass
    return lc


def build_trees_and_landcover(dsm_path: Path, dem_path: Path, mulc_path: Path,
                               trees_dst: Path, landcover_dst: Path) -> tuple[Path, Path]:
    """Trees CDSM (canopy heights on MULC tree pixels) + raw UMEP Landcover
    (no buildings yet). Idempotent if both outputs exist."""
    if trees_dst.exists() and landcover_dst.exists():
        print(f"  [cached] {trees_dst.name}, {landcover_dst.name}")
        return trees_dst, landcover_dst

    with rasterio.open(dsm_path) as ds_dsm, \
         rasterio.open(dem_path) as ds_dem, \
         rasterio.open(mulc_path) as ds_mulc:
        dsm = ds_dsm.read(1).astype("float32")
        dem = ds_dem.read(1).astype("float32")
        mulc = ds_mulc.read(1)
        ref_profile = ds_dsm.profile

    valid = (dsm != -9999) & (dem != -9999)
    height = np.where(valid, dsm - dem, 0.0).astype("float32")
    height = np.clip(height, 0, 100)

    lc = reclass_mulc(mulc)
    vals, counts = np.unique(lc, return_counts=True)
    print(f"  Landcover UMEP code distribution: "
          f"{ {int(v): f'{100*c/lc.size:.1f}%' for v, c in zip(vals, counts)} }")

    trees_arr = np.zeros_like(dsm, dtype="float32")
    tree_mask = (mulc == 40) & (height > 0)
    trees_arr[tree_mask] = height[tree_mask]
    n_tall = int((trees_arr > 40).sum())
    trees_arr[trees_arr > 40] = 0
    if tree_mask.any():
        print(f"  Trees CDSM: {tree_mask.sum():,} canopy pixels  "
              f"max h={trees_arr.max():.2f}m  ({n_tall} cells >40m zeroed as noise)")

    p_lc = ref_profile.copy()
    p_lc.update(dtype="uint8", count=1, nodata=0, compress="lzw")
    with rasterio.open(landcover_dst, "w", **p_lc) as out:
        out.write(lc, 1)

    p_t = ref_profile.copy()
    p_t.update(dtype="float32", count=1, nodata=0, compress="lzw")
    with rasterio.open(trees_dst, "w", **p_t) as out:
        out.write(trees_arr, 1)
    return trees_dst, landcover_dst


# --------------------------------------------------------- Overture patch

def patch_with_overture(base_dir: Path, overture_geojson: Path,
                         processing_bbox: tuple) -> dict:
    """Canonical UMEP/Lindberg recipe for Building_DSM: ground+buildings only,
    gated by Overture footprints.

      Building_DSM[cell] =
        if cell ∈ Overture footprint:
            max(LiDAR_first_return[cell], DEM + Overture_height)
        else:
            DEM[cell]                              (flat ground; no trees)

    Reads from base_dir:
      - Building_DSM.preMS.tif  (raw LiDAR first-return max)
      - DEM.tif
      - Landcover.preMS.tif      (MULC-only landcover, written by build_trees_and_landcover)

    Writes:
      - Building_DSM.tif         (ground + buildings only)
      - Landcover.tif            (UMEP codes; footprint cells set to class 2)
      - .dsm_built marker        (idempotency)

    Returns a stats dict (footprint pixels, source breakdown, etc.).
    """
    marker = base_dir / ".dsm_built"
    dsm_path = base_dir / "Building_DSM.tif"
    lc_path = base_dir / "Landcover.tif"
    if marker.exists() and dsm_path.exists() and lc_path.exists():
        print(f"  [cached] DSM/Landcover already patched (marker present).")
        return {"cached": True}

    import geopandas as gpd

    print("== reading raw inputs ==")
    dsm_raw_path = base_dir / "Building_DSM.preMS.tif"
    dem_path = base_dir / "DEM.tif"
    lc_pre_path = base_dir / "Landcover.preMS.tif"
    if not dsm_raw_path.exists():
        # Bootstrap: promote Building_DSM.tif to .preMS.tif
        shutil.copyfile(dsm_path, dsm_raw_path)
        print(f"  bootstrapped {dsm_raw_path.name} ← Building_DSM.tif")

    with rasterio.open(dsm_raw_path) as ds:
        lidar_dsm = ds.read(1).astype("float32")
        profile_dsm = ds.profile
        transform = ds.transform
        out_shape = ds.shape
    with rasterio.open(dem_path) as ds:
        dem = ds.read(1).astype("float32")
    with rasterio.open(lc_pre_path) as ds:
        mulc_lc = ds.read(1)
        profile_lc = ds.profile

    print("== loading Overture buildings ==")
    bldgs = gpd.read_file(overture_geojson).to_crs("EPSG:32617")
    bldgs = bldgs.cx[processing_bbox[0]:processing_bbox[2],
                     processing_bbox[1]:processing_bbox[3]]
    bldgs = bldgs[bldgs.geometry.notna() & ~bldgs.geometry.is_empty].copy()
    n_total = len(bldgs)
    n_with_h = int(bldgs["height"].notna().sum())
    print(f"  {n_total} buildings ({n_with_h} have Overture height)")

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

    valid_dem = dem != -9999
    valid_lidar = (lidar_dsm != -9999) & valid_dem
    lidar_capped = np.where(valid_lidar,
                            np.minimum(lidar_dsm, dem + LIDAR_HEIGHT_CAP_M),
                            -9999.0).astype("float32")
    new_dsm = np.where(valid_dem, dem, -9999.0).astype("float32")

    overture_roof = dem + heights_raster
    have_overture = heights_raster > 0
    inside = footprint_mask & valid_dem

    case_both = inside & have_overture & valid_lidar
    new_dsm[case_both] = np.maximum(lidar_capped[case_both], overture_roof[case_both])
    case_oo = inside & have_overture & ~valid_lidar
    new_dsm[case_oo] = overture_roof[case_oo]
    case_lo = inside & ~have_overture & valid_lidar
    new_dsm[case_lo] = lidar_capped[case_lo]

    # Landcover: stamp footprint cells as building (UMEP 2)
    new_lc = mulc_lc.copy()
    new_lc[footprint_mask] = 2

    profile_dsm.update(dtype="float32", count=1, nodata=-9999)
    with rasterio.open(dsm_path, "w", **profile_dsm) as out:
        out.write(new_dsm, 1)
    profile_lc.update(dtype="uint8", count=1, nodata=0, compress="lzw")
    with rasterio.open(lc_path, "w", **profile_lc) as out:
        out.write(new_lc, 1)

    diff = (new_dsm - dem)[(new_dsm != -9999) & valid_dem]
    stats = {
        "buildings_total": n_total,
        "buildings_with_height": n_with_h,
        "footprint_cells": int(footprint_mask.sum()),
        "case_both": int(case_both.sum()),
        "case_overture_only": int(case_oo.sum()),
        "case_lidar_only": int(case_lo.sum()),
        "max_height_m": float(diff.max()) if diff.size else 0.0,
        "p99_height_m": float(np.percentile(diff, 99)) if diff.size else 0.0,
    }
    marker.touch()
    print(f"  patch stats: {stats}")
    return stats


def assert_aligned(*paths: Path) -> None:
    sets = []
    for p in paths:
        with rasterio.open(p) as ds:
            sets.append((p.name, ds.shape, ds.transform, str(ds.crs)))
    for s in sets[1:]:
        assert s[1] == sets[0][1], f"{s[0]} shape mismatch with {sets[0][0]}"
        assert s[2] == sets[0][2], f"{s[0]} transform mismatch"
        assert s[3] == sets[0][3], f"{s[0]} crs mismatch"
