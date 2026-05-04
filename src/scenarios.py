"""Burn planted-canopy disks into Trees.tif + Landcover.tif to build the
SOLWEIG inputs for a planting scenario.

Two parameter tiers from the 2026-04 decision log:
  year10  — 5 m canopy disks, radius 2 px (5×5 = ~25 m² footprint)
  mature  — 12 m canopy disks, radius 3 px (7×7 = ~50 m² footprint)
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

SCENARIO_PARAMS = {
    "year10": {"canopy_h_m": 5.0,  "radius_px": 2,
                "description": "5–10 yr post-planting (5 m canopy)"},
    "mature": {"canopy_h_m": 12.0, "radius_px": 3,
                "description": "~25 yr / mature (12 m canopy)"},
}


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_planting_sites(trees_geojson: Path, tile_bbox) -> gpd.GeoDataFrame:
    """Read Durham's Trees & Planting Sites layer, filter to `present == "Planting Site"`,
    clip to tile_bbox in UTM 17N."""
    trees = gpd.read_file(trees_geojson).to_crs("EPSG:32617")
    sites = trees[trees["present"] == "Planting Site"].copy()
    return sites.cx[tile_bbox[0]:tile_bbox[2],
                     tile_bbox[1]:tile_bbox[3]].reset_index(drop=True)


def disk_offsets(radius_px: int) -> list:
    return [(dy, dx) for dy in range(-radius_px, radius_px + 1)
                       for dx in range(-radius_px, radius_px + 1)]


def seed_walls_aspect_cache(baseline_dir: Path, scenario_dir: Path) -> None:
    """Symlink baseline's walls/ + aspect/ tiles into scenario's processed_inputs/.
    Wall height + aspect depend only on Building_DSM (identical across baseline +
    scenarios), so reusing baseline outputs lets SOLWEIG skip ~20 min CPU prep.
    """
    base_pp = baseline_dir / "processed_inputs"
    if not (base_pp / "walls").is_dir() or not (base_pp / "aspect").is_dir():
        print("  no baseline wall/aspect cache found — SOLWEIG will recompute.")
        return
    scen_pp = scenario_dir / "processed_inputs"
    for sub in ("walls", "aspect", "Building_DSM", "DEM"):
        src = base_pp / sub
        if not src.is_dir():
            continue
        dst = scen_pp / sub
        dst.mkdir(parents=True, exist_ok=True)
        for tile in src.iterdir():
            link = dst / tile.name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(tile.resolve())
    print(f"  seeded {scenario_dir.name}/processed_inputs/ from baseline cache.")


def burn_canopy(baseline_dir: Path, scenario_dir: Path, scenario_name: str,
                 sites: gpd.GeoDataFrame, sim_date: str) -> dict:
    """Build a scenario folder by copying baseline rasters and burning planting
    disks into Trees.tif + Landcover.tif. Idempotent: if Trees.tif and
    Landcover.tif already differ from baseline by the expected count, skip.
    """
    params = SCENARIO_PARAMS[scenario_name]
    scenario_dir.mkdir(parents=True, exist_ok=True)

    # 1. Mirror unchanged inputs (Building_DSM, DEM, ownmet)
    for name in ["Building_DSM.tif", "DEM.tif", f"ownmet_{sim_date}.txt"]:
        src = baseline_dir / name
        dst = scenario_dir / name
        if dst.exists() and _file_sha(src) == _file_sha(dst):
            continue
        shutil.copyfile(src, dst)

    # 2. Read baseline Trees + Landcover
    with rasterio.open(baseline_dir / "Trees.tif") as ds:
        trees = ds.read(1).astype("float32")
        trees_profile = ds.profile
        transform = ds.transform
        height, width = ds.shape
    with rasterio.open(baseline_dir / "Landcover.tif") as ds:
        lc = ds.read(1)
        lc_profile = ds.profile

    # 3. Idempotency: if outputs already exist and have the right diff signature, skip
    trees_dst = scenario_dir / "Trees.tif"
    lc_dst = scenario_dir / "Landcover.tif"
    if trees_dst.exists() and lc_dst.exists():
        with rasterio.open(trees_dst) as ds:
            existing_trees = ds.read(1)
        n_diff = int((existing_trees != trees).sum())
        if n_diff > 0:
            print(f"  [cached] {scenario_dir.name} already burned ({n_diff:,} cells differ)")
            seed_walls_aspect_cache(baseline_dir, scenario_dir)
            return {"cached": True, "n_diff": n_diff}

    # 4. Burn disks
    offsets = disk_offsets(params["radius_px"])
    canopy_h = params["canopy_h_m"]
    burned = 0
    reclassed = 0
    skipped_inside = 0
    skipped_offgrid = 0
    for _, row in sites.iterrows():
        x_utm, y_utm = row.geometry.x, row.geometry.y
        col, row_idx = ~transform * (x_utm, y_utm)
        col, row_idx = int(round(col)), int(round(row_idx))
        if not (0 <= col < width and 0 <= row_idx < height):
            skipped_offgrid += 1
            continue
        if lc[row_idx, col] == 2:
            skipped_inside += 1
            continue
        for dy, dx in offsets:
            r, c = row_idx + dy, col + dx
            if not (0 <= c < width and 0 <= r < height):
                continue
            if trees[r, c] < canopy_h:
                trees[r, c] = canopy_h
                burned += 1
            if lc[r, c] != 2 and lc[r, c] != 5:
                lc[r, c] = 5
                reclassed += 1

    with rasterio.open(trees_dst, "w", **trees_profile) as out:
        out.write(trees, 1)
    with rasterio.open(lc_dst, "w", **lc_profile) as out:
        out.write(lc, 1)
    seed_walls_aspect_cache(baseline_dir, scenario_dir)

    stats = {
        "scenario": scenario_name, "params": params,
        "active_sites": len(sites) - skipped_inside - skipped_offgrid,
        "skipped_inside_building": skipped_inside,
        "skipped_offgrid": skipped_offgrid,
        "burned_canopy_pixels": burned,
        "reclassed_landcover_pixels": reclassed,
    }
    print(f"  scenario '{scenario_name}': {stats}")
    return stats
