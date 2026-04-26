"""Stage 5 — build the SOLWEIG inputs for the planting scenarios.

Burns Durham's planned tree-planting sites into copies of the baseline rasters,
producing two scenario directories that Stage 6 will run SOLWEIG against.

Two parameter tiers, per the 2026-04-26 decision (see decision_log.md):

  year10  — 5 m canopy disks, radius 2 px (5×5 = ~25 m² footprint)
            Realistic ~5–10 years post-planting for a Willow Oak / Red Maple
            archetype (NC Extension growth rates).

  mature  — 12 m canopy disks, radius 3 px (7×7 = ~50 m² footprint)
            Approximate ~25-year canopy for the same archetype. Honest upper
            bound for "what does Durham's plan deliver at maturity".

Source data: Durham Open Data Portal "Trees & Planting Sites" layer
(`https://webgis2.durhamnc.gov/.../FeatureServer/11`), filter
`present == "Planting Site"`. 22 such sites fall inside our TILE_BBOX.

For each site:
  - Trees CDSM:  set the disk to max(existing, canopy_h_m). `max` so we never
                 shrink existing canopy if a site falls under one.
  - Landcover:   set non-building cells in the disk to UMEP 5 (grass / under-tree).
                 Building cells (UMEP 2) are left alone — you can't plant a
                 tree on top of a roof. If the site itself sits inside a
                 building footprint, it's reported and skipped (likely data
                 mismatch).

Writes:
  inputs/processed/{AOI_NAME}_scenario_year10/
  inputs/processed/{AOI_NAME}_scenario_mature/
    ├── Building_DSM.tif    (copy of baseline — unchanged)
    ├── DEM.tif             (copy of baseline — unchanged)
    ├── Trees.tif           (modified)
    ├── Landcover.tif       (modified)
    └── ownmet_*.txt        (copy of baseline — unchanged)
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import geopandas as gpd
import numpy as np
import rasterio

from _aoi import AOI_NAME, SIM_DATE, TILE_BBOX

BASELINE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
TREES_GEOJSON = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"

SCENARIOS = {
    "year10": {"canopy_h_m": 5.0,  "radius_px": 2,  # 5×5 disk
               "description": "5–10 yr post-planting (5 m canopy, ~25 m² each)"},
    "mature": {"canopy_h_m": 12.0, "radius_px": 3,  # 7×7 disk
               "description": "~25 yr / mature (12 m canopy, ~50 m² each)"},
}

# Files that should be byte-identical to baseline in every scenario
COPY_FROM_BASELINE = ["Building_DSM.tif", "DEM.tif", f"ownmet_{SIM_DATE}.txt"]


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_planting_sites() -> gpd.GeoDataFrame:
    print("== loading planting sites ==")
    if not TREES_GEOJSON.exists():
        raise SystemExit(f"  MISSING: {TREES_GEOJSON} — run 02_download_data.py first")
    trees = gpd.read_file(TREES_GEOJSON).to_crs("EPSG:32617")
    sites = trees[trees["present"] == "Planting Site"].copy()
    sites_in_aoi = sites.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]]
    print(f"  citywide planting sites: {len(sites):,}")
    print(f"  inside TILE_BBOX:        {len(sites_in_aoi)}")
    if len(sites_in_aoi) == 0:
        raise SystemExit("  FAIL: no planting sites inside TILE_BBOX")
    return sites_in_aoi.reset_index(drop=True)


def disk_offsets(radius_px: int) -> list[tuple[int, int]]:
    """Pixel offsets for a (2r+1)×(2r+1) square footprint. Square (vs circle)
    keeps the per-site footprint area exactly equal to the documented value
    (5×5 = 25 m², 7×7 = 49 m²) — at 1 m pixel resolution the difference between
    a square and a discretized circle is cosmetic anyway."""
    return [(dy, dx) for dy in range(-radius_px, radius_px + 1)
                       for dx in range(-radius_px, radius_px + 1)]


def burn_scenario(scenario_name: str, params: dict, sites: gpd.GeoDataFrame) -> None:
    print(f"\n== building scenario '{scenario_name}': {params['description']} ==")
    out_dir = REPO / f"inputs/processed/{AOI_NAME}_scenario_{scenario_name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Mirror the unchanged inputs
    for name in COPY_FROM_BASELINE:
        src = BASELINE / name
        dst = out_dir / name
        shutil.copyfile(src, dst)
        if _file_sha(src) != _file_sha(dst):
            raise SystemExit(f"  FAIL: copy mismatch for {name}")
    print(f"  copied {len(COPY_FROM_BASELINE)} inputs (verified byte-identical)")

    # Read baseline Trees + Landcover into memory for modification
    with rasterio.open(BASELINE / "Trees.tif") as ds:
        trees = ds.read(1).astype("float32")
        trees_profile = ds.profile
        transform = ds.transform
        height, width = ds.shape
    with rasterio.open(BASELINE / "Landcover.tif") as ds:
        lc = ds.read(1)
        lc_profile = ds.profile

    # Convert each site's UTM coords to pixel coords
    offsets = disk_offsets(params["radius_px"])
    canopy_h = params["canopy_h_m"]

    burned_tree_pixels = 0
    reclassed_lc_pixels = 0
    sites_inside_building = 0
    sites_outside_grid = 0

    for _, row in sites.iterrows():
        x_utm, y_utm = row.geometry.x, row.geometry.y
        col, row_idx = ~transform * (x_utm, y_utm)
        col, row_idx = int(round(col)), int(round(row_idx))
        if not (0 <= col < width and 0 <= row_idx < height):
            sites_outside_grid += 1
            continue
        if lc[row_idx, col] == 2:
            sites_inside_building += 1
            continue
        for dy, dx in offsets:
            r, c = row_idx + dy, col + dx
            if not (0 <= c < width and 0 <= r < height):
                continue
            # Trees: take max so existing canopy isn't shrunk
            if trees[r, c] < canopy_h:
                trees[r, c] = canopy_h
                burned_tree_pixels += 1
            # Landcover: don't reclassify roofs to grass
            if lc[r, c] != 2 and lc[r, c] != 5:
                lc[r, c] = 5
                reclassed_lc_pixels += 1

    n_active = len(sites) - sites_inside_building - sites_outside_grid
    expected_max = n_active * len(offsets)
    print(f"  active sites: {n_active}/{len(sites)}  "
          f"(skipped: {sites_inside_building} on building, "
          f"{sites_outside_grid} off-grid)")
    print(f"  disk size: {2*params['radius_px']+1}×{2*params['radius_px']+1} = "
          f"{len(offsets)} pixels per site (~{len(offsets)} m²)")
    print(f"  burned canopy pixels: {burned_tree_pixels:,}  "
          f"(<= {expected_max:,} = active × disk)")
    print(f"  landcover cells reclassed to grass: {reclassed_lc_pixels:,}")

    # Write the modified rasters
    trees_dst = out_dir / "Trees.tif"
    lc_dst = out_dir / "Landcover.tif"
    with rasterio.open(trees_dst, "w", **trees_profile) as out:
        out.write(trees, 1)
    with rasterio.open(lc_dst, "w", **lc_profile) as out:
        out.write(lc, 1)

    # Diff stats vs baseline
    with rasterio.open(BASELINE / "Trees.tif") as ds:
        base_trees = ds.read(1)
    with rasterio.open(BASELINE / "Landcover.tif") as ds:
        base_lc = ds.read(1)
    n_tree_diff = int((trees != base_trees).sum())
    n_lc_diff = int((lc != base_lc).sum())
    print(f"  written: {trees_dst.name}, {lc_dst.name}")
    print(f"  Δ vs baseline: Trees {n_tree_diff:,} cells, Landcover {n_lc_diff:,} cells")
    if n_tree_diff != burned_tree_pixels or n_lc_diff != reclassed_lc_pixels:
        raise SystemExit(f"  FAIL: written diff ({n_tree_diff}/{n_lc_diff}) != "
                         f"in-memory diff ({burned_tree_pixels}/{reclassed_lc_pixels})")


def main() -> None:
    print(f"== Stage 5: scenario inputs for {AOI_NAME} ==")
    sites = load_planting_sites()
    for name, params in SCENARIOS.items():
        burn_scenario(name, params, sites)
    print(f"\n== done. Two scenario folders ready for Stage 6: ==")
    for name in SCENARIOS:
        print(f"  inputs/processed/{AOI_NAME}_scenario_{name}/")


if __name__ == "__main__":
    main()
