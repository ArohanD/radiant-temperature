"""Stage 3 — build the 4 co-registered rasters + UMEP met file for SOLWEIG.

Pipeline:
  1. PDAL: pull NC Phase 3 EPT (NOAA dataset 6209) at PROCESSING_BBOX, derive
     Building_DSM (first returns, max @1m) and DEM (Class 2 ground, idw @1m).
     EPT is in EPSG:6346 NAD83(2011) UTM 17N + EPSG:5703 NAVD88, METERS — no
     US Survey Feet conversion needed for this source. Reproject to EPSG:32617
     during the PDAL pipeline.
  2. Reproject EnviroAtlas MULC (EPSG:26917) → EPSG:32617 + snap to PROCESSING_BBOX.
  3. Trees.tif (CDSM): (DSM − DEM) where MULC class == 40 (trees), zero elsewhere.
  4. Landcover.tif: reclass MULC → UMEP codes {1, 2, 5, 6, 7}. Impervious (MULC=20)
     splits to building (UMEP=2) when DSM−DEM > 2.5m, else paved (UMEP=1).
  5. Final: assert all 4 rasters share shape/transform/CRS.
  6. HRRR met fetch via _lib.fetch_hrrr_point → write ownmet_<date>.txt.

Output: inputs/processed/{AOI_NAME}_baseline/{Building_DSM,DEM,Trees,Landcover}.tif
        + ownmet_<SIM_DATE>.txt
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env, fetch_hrrr_point, write_umep_met
setup_geo_env()  # MUST be before any GDAL/PDAL/rasterio import

import numpy as np
import rasterio
from pyproj import Transformer

from _aoi import (
    AOI_NAME, SIM_DATE, UTC_OFFSET,
    AOI_CENTER_LAT, AOI_CENTER_LON,
    PROCESSING_BBOX,
)

EPT_URL = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/6209/ept.json"

OUT = REPO / f"inputs/processed/{AOI_NAME}_baseline"
RAW_MULC = REPO / "inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif"


def proc_bbox_in(crs: str) -> tuple[float, float, float, float]:
    t = Transformer.from_crs("EPSG:32617", crs, always_xy=True)
    xmin, ymin = t.transform(PROCESSING_BBOX[0], PROCESSING_BBOX[1])
    xmax, ymax = t.transform(PROCESSING_BBOX[2], PROCESSING_BBOX[3])
    return (xmin, ymin, xmax, ymax)


def _bounds_str(bbox: tuple) -> str:
    """PDAL bounds format: ([xmin, xmax], [ymin, ymax])."""
    return f"([{bbox[0]}, {bbox[2]}], [{bbox[1]}, {bbox[3]}])"


def _run_pdal(pipe: dict, label: str) -> None:
    print(f"  [{label}] running PDAL pipeline …")
    import pdal
    p = pdal.Pipeline(json.dumps(pipe))
    n = p.execute()
    print(f"  [{label}] processed {n:,} points")


def build_dsm() -> Path:
    dst = OUT / "Building_DSM.tif"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    bbox_native = proc_bbox_in("EPSG:6346")
    pipe = {"pipeline": [
        {"type": "readers.ept", "filename": EPT_URL,
         "bounds": _bounds_str(bbox_native)},
        {"type": "filters.range", "limits": "ReturnNumber[1:1]"},
        {"type": "filters.reprojection", "in_srs": "EPSG:6346", "out_srs": "EPSG:32617"},
        {"type": "writers.gdal", "filename": str(dst),
         "resolution": 1.0, "output_type": "max", "data_type": "float32",
         "bounds": _bounds_str(PROCESSING_BBOX)},
    ]}
    _run_pdal(pipe, "DSM")
    return dst


def build_dem() -> Path:
    """Build DEM from Class=2 ground returns, then fill gaps under buildings/canopy.

    Ground points are sparser than first returns (~30% nodata in urban tiles).
    Without filling, DSM-DEM at hole pixels reads as DSM+9999, which both inflates
    canopy heights and falsely classes parking lots as buildings via the impervious
    height disambiguation downstream.
    """
    dst = OUT / "DEM.tif"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    raw = OUT / "DEM_raw.tif"
    bbox_native = proc_bbox_in("EPSG:6346")
    pipe = {"pipeline": [
        {"type": "readers.ept", "filename": EPT_URL,
         "bounds": _bounds_str(bbox_native)},
        {"type": "filters.range", "limits": "Classification[2:2]"},
        {"type": "filters.reprojection", "in_srs": "EPSG:6346", "out_srs": "EPSG:32617"},
        {"type": "writers.gdal", "filename": str(raw),
         "resolution": 1.0, "output_type": "idw", "data_type": "float32",
         "bounds": _bounds_str(PROCESSING_BBOX)},
    ]}
    _run_pdal(pipe, "DEM")
    # Fill nodata holes via GDAL inverse-distance interpolation. 100-pixel search
    # radius is more than enough for downtown blocks; smoothing iter=0 keeps it sharp.
    print(f"  [DEM] filling nodata holes with gdal_fillnodata.py …")
    subprocess.check_call([
        "gdal_fillnodata.py", "-md", "100", "-si", "0",
        str(raw), str(dst),
    ])
    return dst


def build_mulc_aligned() -> Path:
    """Reproject MULC (native EPSG:26917) → EPSG:32617, snap to PROCESSING_BBOX, 1m."""
    dst = OUT / "MULC_aligned.tif"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    cmd = [
        "gdalwarp",
        "-t_srs", "EPSG:32617",
        "-tr", "1", "1",
        "-te", *map(str, PROCESSING_BBOX),
        "-r", "near",
        "-tap", "-of", "GTiff", "-overwrite",
        str(RAW_MULC), str(dst),
    ]
    subprocess.check_call(cmd)
    return dst


def build_landcover_and_trees(dsm_path: Path, dem_path: Path, mulc_path: Path) -> tuple[Path, Path]:
    landcover = OUT / "Landcover.tif"
    trees = OUT / "Trees.tif"

    with rasterio.open(dsm_path) as ds_dsm, \
         rasterio.open(dem_path) as ds_dem, \
         rasterio.open(mulc_path) as ds_mulc:
        dsm = ds_dsm.read(1).astype("float32")
        dem = ds_dem.read(1).astype("float32")
        mulc = ds_mulc.read(1)
        ref_profile = ds_dsm.profile

    # Mask -9999 nodata before any arithmetic. Even after gdal_fillnodata, edge
    # cells can still hold the fill value where the search radius was insufficient.
    valid = (dsm != -9999) & (dem != -9999)
    height = np.where(valid, dsm - dem, 0.0).astype("float32")
    height = np.clip(height, 0, 100)  # cap at 100m — anything above is a LiDAR artifact

    # Reclass MULC → UMEP codes. Impervious (MULC=20) splits by height: building if
    # DSM-DEM > 2.5m, else paved. Without this, every road and rooftop reads as the
    # same class and SOLWEIG can't tell streets from buildings.
    lc = np.zeros_like(mulc, dtype="uint8")
    lc[mulc == 10] = 7                              # water
    lc[mulc == 20] = 1                              # impervious default → paved
    lc[(mulc == 20) & (height > 2.5)] = 2           # impervious + tall → building
    lc[mulc == 30] = 6                              # bare soil
    lc[(mulc == 40) | (mulc == 70) | (mulc == 80)] = 5  # trees / grass / ag → grass
    lc[(mulc == 91) | (mulc == 92)] = 7             # wetlands → water
    lc[lc == 0] = 5                                 # unclassified → grass (safe default)

    vals, counts = np.unique(lc, return_counts=True)
    pct = {int(v): f"{100*c/lc.size:.1f}%" for v, c in zip(vals, counts)}
    print(f"  Landcover UMEP code distribution: {pct}")

    # Trees CDSM: canopy heights only on MULC tree pixels, zero elsewhere.
    trees_arr = np.zeros_like(dsm, dtype="float32")
    tree_mask = (mulc == 40) & (height > 0)
    trees_arr[tree_mask] = height[tree_mask]
    if tree_mask.any():
        print(f"  Trees CDSM: {tree_mask.sum():,} canopy pixels  "
              f"max h={trees_arr.max():.2f}m  mean h={trees_arr[tree_mask].mean():.2f}m")
    else:
        print(f"  WARN: no tree pixels in AOI")

    p_lc = ref_profile.copy()
    p_lc.update(dtype="uint8", count=1, nodata=0, compress="lzw")
    with rasterio.open(landcover, "w", **p_lc) as out:
        out.write(lc, 1)
    print(f"  wrote {landcover}")

    p_t = ref_profile.copy()
    p_t.update(dtype="float32", count=1, nodata=0, compress="lzw")
    with rasterio.open(trees, "w", **p_t) as out:
        out.write(trees_arr, 1)
    print(f"  wrote {trees}")

    return landcover, trees


def assert_aligned(*paths: Path) -> None:
    sets = []
    for p in paths:
        with rasterio.open(p) as ds:
            sets.append((p.name, ds.shape, ds.transform, str(ds.crs)))
    print(f"  {sets[0][0]}: shape={sets[0][1]}, crs={sets[0][3]}")
    for s in sets[1:]:
        print(f"  {s[0]}: shape={s[1]}, crs={s[3]}")
        assert s[1] == sets[0][1], f"{s[0]} shape mismatch with {sets[0][0]}"
        assert s[2] == sets[0][2], f"{s[0]} transform mismatch with {sets[0][0]}"
        assert s[3] == sets[0][3], f"{s[0]} crs mismatch with {sets[0][0]}"
    print("  all 4 rasters identically aligned ✓")


def vertical_units_check(dsm_path: Path, dem_path: Path) -> None:
    with rasterio.open(dsm_path) as d:
        dsm = d.read(1)
    with rasterio.open(dem_path) as d:
        dem = d.read(1)
    valid = (dsm != -9999) & (dem != -9999)
    diff = (dsm - dem)[valid]
    p99 = float(np.percentile(diff, 99))
    n_valid = int(valid.sum())
    n_total = int(valid.size)
    print(f"  valid pixels: {n_valid:,}/{n_total:,} ({100*n_valid/n_total:.1f}%)")
    print(f"  (DSM − DEM) 99th percentile (valid only): {p99:.2f}m  (gate: 3 < p99 < 50)")
    if p99 > 200:
        raise SystemExit(f"  FAIL: p99 = {p99:.1f}m > 200m — feet→m conversion missed!")
    if p99 < 3:
        raise SystemExit(f"  FAIL: p99 = {p99:.1f}m < 3m — DSM ≈ DEM, no buildings/trees")
    if not (3 <= p99 <= 50):
        print(f"  WARN: p99 outside expected [3, 50]m range, but not catastrophic")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if SIM_DATE is None:
        raise SystemExit("SIM_DATE not set in _aoi.py — run 02_download_data.py first.")

    print("== 1. PDAL DSM (first returns from NC Phase 3 EPT) ==")
    dsm = build_dsm()

    print("\n== 2. PDAL DEM (ground returns) ==")
    dem = build_dem()

    print("\n== 3. Reproject MULC + align to PROCESSING_BBOX ==")
    mulc = build_mulc_aligned()

    print("\n== 4. Build Landcover (UMEP codes) + Trees (CDSM) ==")
    landcover, trees = build_landcover_and_trees(dsm, dem, mulc)

    print("\n== 5. Verify alignment + vertical units ==")
    assert_aligned(dsm, dem, trees, landcover)
    vertical_units_check(dsm, dem)

    print("\n== 6. Fetch HRRR met + write UMEP own-met file ==")
    df = fetch_hrrr_point(AOI_CENTER_LAT, AOI_CENTER_LON, SIM_DATE, UTC_OFFSET)
    print(df[["hour", "Ta_C", "RH_pct", "Wind_ms", "press_kPa", "Kdn_Wm2", "ldown_Wm2", "rain_mmh"]]
          .to_string(index=False, float_format=lambda x: f"{x:7.2f}"))
    write_umep_met(df, OUT / f"ownmet_{SIM_DATE}.txt", SIM_DATE)


if __name__ == "__main__":
    main()
