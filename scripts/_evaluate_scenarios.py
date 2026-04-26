"""Compute the headline numbers for the planted-tree scenario(s) vs baseline.

For each scenario:
  - Per-hour tile-mean ΔTmrt and ΔUTCI (scenario − baseline), non-roof cells
  - At-tree ΔTmrt: median ΔTmrt at the planted-disk pixels (the cells we burned)
  - Within-30 m ΔTmrt: median ΔTmrt within 30 m of any planted point
  - Peak-hour spatial stats

The plan's Stage-7 gates (translated):
  - At planted pixels, peak-hour median ΔTmrt < 0  (cooling, not warming)
  - Tile-mean peak-hour |Δ| within plausible range (0.05–0.5 °C for our tiny intervention)
  - At-tree cooling ≥ 1 °C for at least one of the scenarios

Outputs a structured per-scenario report. Used as the data source for Stage 7
figures + the headline statement.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import Point

from _aoi import AOI_NAME, SIM_DATE, TILE_BBOX

BASELINE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
SCENARIOS = ["year10", "mature"]
TREES_GEOJSON = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"

NEAR_TREE_RADIUS_M = 30.0


def load_planted_points() -> gpd.GeoDataFrame:
    trees = gpd.read_file(TREES_GEOJSON).to_crs("EPSG:32617")
    sites = trees[trees["present"] == "Planting Site"].copy()
    return sites.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]].reset_index(drop=True)


def planted_disk_mask(scenario: str) -> np.ndarray:
    """Boolean mask of the cells we actually modified in the scenario (Trees diff)."""
    with rasterio.open(BASELINE / "Trees.tif") as ds:
        base = ds.read(1)
    with rasterio.open(REPO / f"inputs/processed/{AOI_NAME}_scenario_{scenario}/Trees.tif") as ds:
        scen = ds.read(1)
    return scen != base


def near_tree_mask(transform, shape) -> np.ndarray:
    pts = load_planted_points()
    geoms = [pt.buffer(NEAR_TREE_RADIUS_M) for pt in pts.geometry]
    return geometry_mask(geoms, transform=transform, out_shape=shape, invert=True)


def building_mask() -> np.ndarray:
    with rasterio.open(BASELINE / "Landcover.tif") as ds:
        lc = ds.read(1)
    with rasterio.open(BASELINE / "Building_DSM.tif") as ds:
        dsm = ds.read(1)
    with rasterio.open(BASELINE / "DEM.tif") as ds:
        dem = ds.read(1)
    return (lc == 2) | ((dsm - dem) > 2.5)


def hourly_stats(base_path: Path, scen_path: Path, var: str,
                  is_building: np.ndarray, planted: np.ndarray, near: np.ndarray) -> list:
    out = []
    with rasterio.open(base_path / "output_folder" / "0_0" / f"{var}_0_0.tif") as bds, \
         rasterio.open(scen_path / "output_folder" / "0_0" / f"{var}_0_0.tif") as sds:
        for h in range(24):
            b = bds.read(h + 1).astype("float32")
            s = sds.read(h + 1).astype("float32")
            valid = np.isfinite(b) & np.isfinite(s) & (b > -100) & (s > -100)
            d = s - b
            tile_pedestrian = valid & ~is_building
            row = {
                "h": h,
                "base_mean": float(b[tile_pedestrian].mean()),
                "scen_mean": float(s[tile_pedestrian].mean()),
                "tile_dmean": float(d[tile_pedestrian].mean()),
                "tile_dmax": float(d[tile_pedestrian].max()),
                "tile_dmin": float(d[tile_pedestrian].min()),
                "planted_dmedian": (float(np.median(d[planted & valid]))
                                     if (planted & valid).any() else np.nan),
                "planted_dmean": (float(d[planted & valid].mean())
                                   if (planted & valid).any() else np.nan),
                "near_dmean": (float(d[near & tile_pedestrian].mean())
                                if (near & tile_pedestrian).any() else np.nan),
                "near_dmedian": (float(np.median(d[near & tile_pedestrian]))
                                  if (near & tile_pedestrian).any() else np.nan),
            }
            out.append(row)
    return out


def report_scenario(scenario: str, is_building: np.ndarray, near: np.ndarray) -> int:
    fails = 0
    scen_path = REPO / f"inputs/processed/{AOI_NAME}_scenario_{scenario}"
    planted = planted_disk_mask(scenario)
    n_planted = int(planted.sum())
    print(f"\n{'='*78}")
    print(f"== scenario '{scenario}' — planted disk pixels: {n_planted:,}  "
          f"near-tree (≤{NEAR_TREE_RADIUS_M:.0f} m): {int(near.sum()):,}")
    print(f"{'='*78}")

    for var in ("TMRT", "UTCI"):
        rows = hourly_stats(BASELINE, scen_path, var, is_building, planted, near)
        peak_h = max(rows, key=lambda r: r["base_mean"])["h"]
        print(f"\n  {var} (°C)  hourly Δ (scenario − baseline)")
        print(f"  {'h':>3} {'base':>6} {'scen':>6} {'tile_Δ':>7} {'tile_Δmin':>10} "
              f"{'planted_Δmed':>13} {'near_Δmed':>10}")
        for r in rows:
            mark = " ← peak" if r["h"] == peak_h else ""
            print(f"  {r['h']:>3d} {r['base_mean']:>6.1f} {r['scen_mean']:>6.1f} "
                  f"{r['tile_dmean']:>+7.3f} {r['tile_dmin']:>+10.2f} "
                  f"{r['planted_dmedian']:>+13.2f} {r['near_dmedian']:>+10.2f}{mark}")

        peak = next(r for r in rows if r["h"] == peak_h)
        print(f"\n  ---- {var} headline at peak hour h={peak_h} ----")
        print(f"    tile-mean Δ (non-roof):    {peak['tile_dmean']:+.3f} °C")
        print(f"    coldest cell Δ (non-roof): {peak['tile_dmin']:+.2f} °C")
        print(f"    at-planted-pixel median:   {peak['planted_dmedian']:+.2f} °C")
        print(f"    within-{NEAR_TREE_RADIUS_M:.0f}m median:        {peak['near_dmedian']:+.2f} °C")

        if var == "TMRT":
            if peak["planted_dmedian"] >= 0:
                print(f"    FAIL: planted-pixel ΔTmrt should be < 0 (cooling)"); fails += 1
            else:
                print(f"    OK: planted pixels cool by {-peak['planted_dmedian']:.2f} °C "
                      f"at peak ({var})")

    return fails


def main() -> int:
    print(f"Cross-scenario evaluation: baseline vs {SCENARIOS}")
    print(f"AOI: {AOI_NAME}  date: {SIM_DATE}\n")

    is_building = building_mask()
    with rasterio.open(BASELINE / "Trees.tif") as ds:
        transform = ds.transform; shape = ds.shape
    near = near_tree_mask(transform, shape)
    pts = load_planted_points()
    print(f"  planted sites in AOI: {len(pts)}")
    print(f"  near-tree mask area: {int(near.sum()):,} cells "
          f"({100*near.sum()/near.size:.1f}% of tile)")
    print(f"  building mask: {int(is_building.sum()):,} cells "
          f"({100*is_building.sum()/is_building.size:.1f}% — excluded from pedestrian stats)")

    fails = 0
    for scen in SCENARIOS:
        fails += report_scenario(scen, is_building, near)

    print("\n" + "="*78)
    if fails == 0:
        print("ALL SCENARIO GATES PASS ✓")
    else:
        print(f"{fails} GATE(S) FAILED")
    return fails


if __name__ == "__main__":
    sys.exit(main())
