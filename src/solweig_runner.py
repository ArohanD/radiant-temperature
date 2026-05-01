"""Wrapper around solweig_gpu.thermal_comfort with idempotency + wall-cache reuse.

Two key behaviors that scripts/04 + 06 had built in:
 1. **Skip-if-complete** — if the expected per-tile TMRT and UTCI files already
    exist, don't re-run. Falls back to a wipe-and-retry if outputs are partial.
 2. **Wall+aspect cache hit** — monkey-patch
    solweig_gpu.walls_aspect.run_parallel_processing so it skips the (single-threaded,
    ~20 min) wall+aspect preprocess when its outputs are already on disk. The
    scenario builder symlinks baseline's wall/aspect tiles into the scenario's
    processed_inputs/, so this turns the SOLWEIG run into a pure GPU-bound op.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import numpy as np
import rasterio


def _expected_tile_keys(base: Path) -> list:
    dsm_tiles = sorted((base / "processed_inputs" / "Building_DSM").glob("*.tif"))
    return [p.stem.replace("Building_DSM_", "") for p in dsm_tiles]


def outputs_complete(base: Path) -> tuple:
    out = base / "output_folder"
    keys = _expected_tile_keys(base)
    if not out.exists() or not keys:
        return False, []
    missing = []
    for k in keys:
        for prefix in ("TMRT", "UTCI"):
            tile = out / k / f"{prefix}_{k}.tif"
            if not tile.exists():
                missing.append(str(tile.relative_to(base)))
    return (len(missing) == 0), missing


def patch_skip_walls_if_cached() -> None:
    """Monkey-patch solweig_gpu.walls_aspect.run_parallel_processing so it skips
    the wall+aspect preprocess when its outputs are already present. Idempotent."""
    import solweig_gpu.walls_aspect as wa
    if getattr(wa.run_parallel_processing, "_skip_if_cached_wrap", False):
        return
    original = wa.run_parallel_processing

    def run_with_skip(dem_folder, wall_folder, aspect_folder):
        dem_tiles = [f for f in os.listdir(dem_folder) if f.endswith(".tif")]
        if not dem_tiles:
            return original(dem_folder, wall_folder, aspect_folder)
        os.makedirs(wall_folder, exist_ok=True)
        os.makedirs(aspect_folder, exist_ok=True)
        all_cached = True
        for t in dem_tiles:
            key = t[len("Building_DSM_"):-len(".tif")] if t.startswith("Building_DSM_") else t[:-4]
            wall_tile = os.path.join(wall_folder, f"walls_{key}.tif")
            aspect_tile = os.path.join(aspect_folder, f"aspect_{key}.tif")
            if not (os.path.exists(wall_tile) and os.path.exists(aspect_tile)):
                all_cached = False
                break
        if all_cached:
            print(f"[wall+aspect cache hit] skipping recomputation "
                  f"({len(dem_tiles)} tiles already cached)")
            return
        return original(dem_folder, wall_folder, aspect_folder)

    run_with_skip._skip_if_cached_wrap = True
    wa.run_parallel_processing = run_with_skip


def preflight(base: Path, sim_date: str) -> dict:
    needed = ["Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif",
              f"ownmet_{sim_date}.txt"]
    for n in needed:
        p = base / n
        if not p.exists():
            raise FileNotFoundError(f"missing {p}")
    with rasterio.open(base / "Building_DSM.tif") as ds:
        dsm = ds.read(1)
    with rasterio.open(base / "DEM.tif") as ds:
        dem = ds.read(1)
    valid = (dsm != -9999) & (dem != -9999)
    h = (dsm - dem)[valid]
    if h.size and h.max() >= 250:
        raise ValueError(f"max DSM-DEM height {h.max():.0f} m >= 250 m gate")
    with rasterio.open(base / "Landcover.tif") as ds:
        lc = ds.read(1)
    if not set(int(v) for v in np.unique(lc)).issubset({0, 1, 2, 5, 6, 7}):
        raise ValueError(f"Landcover has unexpected codes")
    return {"dsm_max_h": float(h.max()) if h.size else 0.0,
             "trees_canopy_cells": int((rasterio.open(base / "Trees.tif").read(1) > 0).sum())}


def run(base: Path, sim_date: str, *, tile_size: int = 1000, tile_overlap: int = 100,
        force: bool = False) -> dict:
    """Fire SOLWEIG against the rasters in `base`. Idempotent unless `force=True`.

    Outputs land at `base/output_folder/<key>/{TMRT,UTCI,SVF,Shadow}_<key>.tif`.
    """
    if not force:
        complete, missing = outputs_complete(base)
        if complete:
            print(f"  [skip] {base.name} already has complete TMRT+UTCI outputs.")
            return {"skipped": True, "base": str(base)}
        if (base / "output_folder").exists() and missing:
            print(f"  output_folder is INCOMPLETE — missing {len(missing)} file(s). "
                  f"Wiping and re-running.")
            shutil.rmtree(base / "output_folder")

    preflight(base, sim_date)
    patch_skip_walls_if_cached()
    from solweig_gpu import thermal_comfort
    t0 = time.monotonic()
    thermal_comfort(
        base_path=str(base),
        selected_date_str=sim_date,
        building_dsm_filename="Building_DSM.tif",
        dem_filename="DEM.tif",
        trees_filename="Trees.tif",
        landcover_filename="Landcover.tif",
        tile_size=tile_size,
        overlap=tile_overlap,
        use_own_met=True,
        own_met_file=str(base / f"ownmet_{sim_date}.txt"),
        save_tmrt=True,
        save_svf=True,
        save_shadow=True,
    )
    elapsed = time.monotonic() - t0
    print(f"  thermal_comfort() finished in {elapsed/60:.1f} min")
    return {"skipped": False, "elapsed_s": elapsed, "base": str(base)}
