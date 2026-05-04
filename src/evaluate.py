"""Physical sanity checks and headline statistics for SOLWEIG outputs.

The two entry points used by the analysis notebook are:
  baseline_checks(prefix)        — physics gates on the baseline run.
  scenario_headline(prefix, name) — peak-hour ΔTmrt / ΔUTCI vs baseline at
                                     planted-pixel and within-30 m masks.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask

from src.aoi import (AOI_CENTER_LAT, AOI_CENTER_LON, OUTPUT_PREFIX, SIM_DATE,
                     TILE_BBOX, UTC_OFFSET, baseline_dir, scenario_dir)

REPO = Path(__file__).resolve().parent.parent
TREES_GEOJSON = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
NEAR_TREE_RADIUS_M = 30.0


def _valid_mask(a: np.ndarray) -> np.ndarray:
    m = np.isfinite(a)
    m &= a > -100
    m &= a < 1000
    return m


def _building_mask(base: Path) -> np.ndarray:
    with rasterio.open(base / "Landcover.tif") as ds:
        lc = ds.read(1)
    with rasterio.open(base / "Building_DSM.tif") as ds:
        dsm = ds.read(1)
    with rasterio.open(base / "DEM.tif") as ds:
        dem = ds.read(1)
    return (lc == 2) | ((dsm - dem) > 2.5)


def _solar_position(lat: float, lon: float, date_str: str, hour_local: int,
                     utc_offset: int) -> tuple:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    doy = dt.timetuple().tm_yday
    hour_utc = hour_local - utc_offset
    g = math.radians(360 / 365.25 * (doy - 81))
    eot_min = 9.87 * math.sin(2 * g) - 7.53 * math.cos(g) - 1.5 * math.sin(g)
    decl = math.radians(23.45) * math.sin(math.radians(360 / 365 * (doy - 81)))
    solar_time = hour_utc + lon / 15.0 + eot_min / 60.0
    H = math.radians(15.0 * (solar_time - 12.0))
    L = math.radians(lat)
    sin_alt = math.sin(L) * math.sin(decl) + math.cos(L) * math.cos(decl) * math.cos(H)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    cos_az = (math.sin(decl) - sin_alt * math.sin(L)) / (math.cos(math.asin(sin_alt)) * math.cos(L))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))
    if H > 0:
        az = 360 - az
    return alt, az


def _merged_raster(output_folder: Path, prefix: str) -> Path:
    tiles = sorted(output_folder.glob(f"*/{prefix}_*.tif"))
    if not tiles:
        raise FileNotFoundError(f"no {prefix} tiles under {output_folder}")
    if len(tiles) == 1:
        return tiles[0]
    merged = output_folder / f"{prefix}_merged.tif"
    if merged.exists():
        return merged
    from rasterio.merge import merge as rio_merge
    handles = [rasterio.open(p) for p in tiles]
    nodata_val = handles[0].nodata
    arr, transform = rio_merge(handles, nodata=nodata_val)
    profile = handles[0].profile.copy()
    for h in handles:
        h.close()
    profile.update(height=arr.shape[1], width=arr.shape[2], transform=transform,
                    count=arr.shape[0], compress="lzw", nodata=nodata_val)
    with rasterio.open(merged, "w", **profile) as out:
        out.write(arr)
    return merged


def _peak_hour(tmrt_path: Path, is_building: np.ndarray) -> int:
    means = []
    with rasterio.open(tmrt_path) as ds:
        for h in range(ds.count):
            b = ds.read(h + 1).astype("float32")
            v = b[(b > -100) & np.isfinite(b) & ~is_building]
            means.append(float(v.mean()) if v.size else float("-inf"))
    return int(np.argmax(means))


def baseline_checks(prefix: str = OUTPUT_PREFIX) -> dict:
    """Physical-plausibility gates on the baseline outputs. Returns a result dict
    with peak hour, per-class mean Tmrt at peak, shadow direction, SVF percentiles,
    and a list of failed gate names.
    """
    base = baseline_dir(prefix)
    out = base / "output_folder" / "0_0"
    if not out.exists():
        # Multi-tile mode — pick the first tile for shadow / SVF spot checks
        candidates = sorted((base / "output_folder").glob("*/"))
        out = candidates[0] if candidates else base / "output_folder" / "0_0"

    tmrt_path = _merged_raster(base / "output_folder", "TMRT")
    utci_path = _merged_raster(base / "output_folder", "UTCI")

    with rasterio.open(base / "Landcover.tif") as ds:
        lc = ds.read(1)
    is_building = _building_mask(base)

    peak_h = _peak_hour(tmrt_path, is_building)
    fails = []

    with rasterio.open(tmrt_path) as ds:
        peak_band = ds.read(peak_h + 1).astype("float32")
        pre_dawn = ds.read(4).astype("float32")
    per_class = {}
    for code, name in [(1, "paved"), (2, "building"), (5, "grass"), (6, "soil"), (7, "water")]:
        m = _valid_mask(peak_band) & (lc == code)
        if m.any():
            per_class[name] = float(peak_band[m].mean())
    if "paved" in per_class and "grass" in per_class:
        if per_class["paved"] - per_class["grass"] < 2.0:
            fails.append("paved_should_be_hotter_than_grass")

    pre_std = float(pre_dawn[_valid_mask(pre_dawn) & ~is_building].std())
    if pre_std > 3.0:
        fails.append("pre_dawn_uniformity")

    alt, az = _solar_position(AOI_CENTER_LAT, AOI_CENTER_LON, SIM_DATE, peak_h, UTC_OFFSET)
    shadow_az = (az + 180) % 360

    with rasterio.open(utci_path) as ds:
        utci_peak = ds.read(peak_h + 1).astype("float32")
    valid = _valid_mask(utci_peak) & ~is_building
    utci_summary = {
        "mean": float(utci_peak[valid].mean()),
        "p50": float(np.percentile(utci_peak[valid], 50)),
        "p99": float(np.percentile(utci_peak[valid], 99)),
        "extreme_pct": float(100 * (utci_peak[valid] > 46).mean()),
    }

    return {
        "peak_hour": peak_h,
        "tmrt_per_class_at_peak": per_class,
        "pre_dawn_std": pre_std,
        "solar_altitude_at_peak": alt,
        "solar_azimuth_at_peak": az,
        "shadow_azimuth_at_peak": shadow_az,
        "utci_at_peak": utci_summary,
        "failed_gates": fails,
    }


def _planted_disk_mask(base: Path, scenario_path: Path) -> np.ndarray:
    with rasterio.open(base / "Trees.tif") as ds:
        b = ds.read(1)
    with rasterio.open(scenario_path / "Trees.tif") as ds:
        s = ds.read(1)
    return s != b


def _near_tree_mask(base: Path) -> np.ndarray:
    with rasterio.open(base / "Trees.tif") as ds:
        transform = ds.transform
        shape = ds.shape
    trees = gpd.read_file(TREES_GEOJSON).to_crs("EPSG:32617")
    sites = trees[trees["present"] == "Planting Site"].copy()
    sites = sites.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]]
    geoms = [pt.buffer(NEAR_TREE_RADIUS_M) for pt in sites.geometry]
    return geometry_mask(geoms, transform=transform, out_shape=shape, invert=True)


def scenario_headline(prefix: str = OUTPUT_PREFIX, scenario: str = "mature") -> dict:
    """Compute peak-hour ΔTmrt / ΔUTCI statistics for a single scenario vs the
    baseline."""
    base = baseline_dir(prefix)
    scen = scenario_dir(scenario, prefix)
    is_building = _building_mask(base)
    base_tmrt = _merged_raster(base / "output_folder", "TMRT")
    scen_tmrt = _merged_raster(scen / "output_folder", "TMRT")
    base_utci = _merged_raster(base / "output_folder", "UTCI")
    scen_utci = _merged_raster(scen / "output_folder", "UTCI")
    peak_h = _peak_hour(base_tmrt, is_building)

    planted = _planted_disk_mask(base, scen)
    near = _near_tree_mask(base) & ~is_building

    with rasterio.open(base_tmrt) as ds: bt = ds.read(peak_h + 1).astype("float32")
    with rasterio.open(scen_tmrt) as ds: st = ds.read(peak_h + 1).astype("float32")
    with rasterio.open(base_utci) as ds: bu = ds.read(peak_h + 1).astype("float32")
    with rasterio.open(scen_utci) as ds: su = ds.read(peak_h + 1).astype("float32")

    valid_t = np.isfinite(bt) & np.isfinite(st) & ~is_building
    valid_u = np.isfinite(bu) & np.isfinite(su) & ~is_building
    dtmrt = st - bt
    dutci = su - bu

    out = {
        "scenario": scenario,
        "peak_hour": peak_h,
        "tile_dtmrt_mean": float(dtmrt[valid_t].mean()),
        "tile_dutci_mean": float(dutci[valid_u].mean()),
        "planted_pixels": int(planted.sum()),
    }
    if (planted & valid_t).any():
        out["planted_dtmrt_median"] = float(np.median(dtmrt[planted & valid_t]))
        out["planted_dtmrt_min"] = float(dtmrt[planted & valid_t].min())
    if (planted & valid_u).any():
        out["planted_dutci_median"] = float(np.median(dutci[planted & valid_u]))
        # Bröde et al. 2012 UTCI heat-stress category boundaries.
        # A "category drop" is a planted pixel whose scenario UTCI sits in a
        # lower heat-stress band than its baseline UTCI.
        utci_bins = np.array([-40, 9, 26, 32, 38, 46, 90])
        b_cat = np.digitize(bu[planted & valid_u], utci_bins)
        s_cat = np.digitize(su[planted & valid_u], utci_bins)
        out["who_category_drop_pct"] = float(100 * (s_cat < b_cat).mean())
    if (near & valid_t).any():
        out["near_dtmrt_median"] = float(np.median(dtmrt[near & valid_t]))
    return out


def write_diff_geotiffs(prefix: str = OUTPUT_PREFIX) -> dict:
    """Write peak-hour ΔTmrt and ΔUTCI GeoTIFFs for both scenarios into
    outputs/{prefix}/diffs/. Used by the inspector."""
    base = baseline_dir(prefix)
    diff_dir = REPO / f"outputs/{prefix}/diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    base_tmrt = _merged_raster(base / "output_folder", "TMRT")
    base_utci = _merged_raster(base / "output_folder", "UTCI")
    is_building = _building_mask(base)
    peak_h = _peak_hour(base_tmrt, is_building)

    written = {}
    for scen in ("year10", "mature"):
        scen_dir = scenario_dir(scen, prefix)
        if not (scen_dir / "output_folder").exists():
            continue
        scen_tmrt = _merged_raster(scen_dir / "output_folder", "TMRT")
        scen_utci = _merged_raster(scen_dir / "output_folder", "UTCI")
        with rasterio.open(base_tmrt) as ds: bt = ds.read(peak_h + 1).astype("float32")
        with rasterio.open(scen_tmrt) as ds: st = ds.read(peak_h + 1).astype("float32")
        with rasterio.open(base_utci) as ds: bu = ds.read(peak_h + 1).astype("float32")
        with rasterio.open(scen_utci) as ds: su = ds.read(peak_h + 1).astype("float32")
        dt = np.where(is_building, np.nan, st - bt).astype("float32")
        du = np.where(is_building, np.nan, su - bu).astype("float32")
        with rasterio.open(base_tmrt) as ds:
            profile = ds.profile.copy()
        profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
        for arr, suffix in ((dt, "dtmrt"), (du, "dutci")):
            dst = diff_dir / f"{suffix}_peak_{scen}.tif"
            with rasterio.open(dst, "w", **profile) as out:
                out.write(arr, 1)
            written[(scen, suffix)] = dst
    return {"peak_hour": peak_h, "written": written}
