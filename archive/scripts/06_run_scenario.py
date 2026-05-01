"""Stage 6 — run SOLWEIG against each scenario directory built in Stage 5.

Iterates over every `inputs/processed/{AOI_NAME}_scenario_*/` directory, fires
`thermal_comfort()` against each, and writes outputs under each scenario's own
`output_folder/`. Total wallclock ~2 × baseline (≈ 75 min for two scenarios).

Logs to `outputs/{AOI_NAME}_scenario_run.log` for live monitoring:

    tail -f outputs/{AOI_NAME}_scenario_run.log
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import numpy as np
import rasterio

from _aoi import AOI_NAME, SIM_DATE, TILE_SIZE, TILE_OVERLAP

LOG_FILE = REPO / f"outputs/{AOI_NAME}_scenario_run.log"
_T0 = time.monotonic()


class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, data):
        for s in self.streams: s.write(data); s.flush()
    def flush(self):
        for s in self.streams: s.flush()


def _log(msg: str = "", *, header: bool = False) -> None:
    elapsed = time.monotonic() - _T0
    mins, secs = divmod(int(elapsed), 60)
    stamp = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{stamp}  +{mins:02d}m{secs:02d}s] "
    if header:
        bar = "=" * (80 - len(prefix))
        print(f"{prefix}{bar}\n{prefix}== {msg}\n{prefix}{bar}")
    else:
        print(f"{prefix}{msg}")


def find_scenarios() -> list[Path]:
    parent = REPO / "inputs/processed"
    out = sorted(parent.glob(f"{AOI_NAME}_scenario_*/"))
    return [p for p in out if p.is_dir()]


def preflight(base: Path) -> None:
    needed = ["Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif",
              f"ownmet_{SIM_DATE}.txt"]
    for n in needed:
        p = base / n
        if not p.exists():
            raise SystemExit(f"  MISSING: {p}")
    with rasterio.open(base / "Trees.tif") as ds:
        t = ds.read(1)
    n_canopy = int((t > 0).sum())
    _log(f"  Trees CDSM: {n_canopy:,} canopy cells  max={t.max():.1f}m  "
         f"mean(nonzero)={t[t>0].mean():.1f}m")
    with rasterio.open(base / "Landcover.tif") as ds:
        lc = ds.read(1)
    vals, counts = np.unique(lc, return_counts=True)
    pct = {int(v): f"{100*c/lc.size:.1f}%" for v, c in zip(vals, counts)}
    _log(f"  Landcover distribution: {pct}")


def _patch_skip_walls_if_cached() -> None:
    """Monkey-patch solweig_gpu.walls_aspect.run_parallel_processing so it skips
    the (single-threaded, ~20 min) wall+aspect preprocess when its outputs are
    already on disk. Stage 5 seeds the scenario cache from baseline (symlinks).
    Without this, solweig-gpu unconditionally recomputes — wasted on a paid GPU
    pod where wall-height keeps the GPU idle for the entire CPU stage.
    Idempotent: re-importing/re-applying is safe.
    """
    import os
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
                  f"({len(dem_tiles)} tiles already present in {wall_folder})")
            return
        return original(dem_folder, wall_folder, aspect_folder)

    run_with_skip._skip_if_cached_wrap = True
    wa.run_parallel_processing = run_with_skip


def _scenario_outputs_complete(base: Path) -> tuple[bool, list[str]]:
    """True iff every expected per-tile TMRT and UTCI output exists. Compares
    against the Building_DSM tile set produced earlier in the same run, so it
    works for any tile_size. Returns (complete, missing_paths)."""
    out = base / "output_folder"
    dsm_tiles = sorted((base / "processed_inputs" / "Building_DSM").glob("*.tif"))
    if not out.exists() or not dsm_tiles:
        return False, []
    keys = [p.stem.replace("Building_DSM_", "") for p in dsm_tiles]
    missing = []
    for k in keys:
        for prefix in ("TMRT", "UTCI"):
            tile = out / k / f"{prefix}_{k}.tif"
            if not tile.exists():
                missing.append(str(tile.relative_to(base)))
    return (len(missing) == 0), missing


def run_one(base: Path) -> int:
    name = base.name.replace(f"{AOI_NAME}_scenario_", "")
    _log(f"running scenario '{name}' in {base}", header=True)
    preflight(base)

    if (base / "output_folder").exists():
        complete, missing = _scenario_outputs_complete(base)
        if complete:
            _log(f"  output_folder is complete — skipping (delete it to re-run).")
            return 0
        # Partial / corrupted prior run: wipe and re-do. Better than letting
        # Stage 7 read a half-written tile and produce nonsense ΔTmrt.
        import shutil
        _log(f"  output_folder is INCOMPLETE — missing {len(missing)} tile file(s) "
             f"(e.g., {missing[:3]}). Wiping and re-running.")
        shutil.rmtree(base / "output_folder")

    _patch_skip_walls_if_cached()
    from solweig_gpu import thermal_comfort
    t_start = time.monotonic()
    thermal_comfort(
        base_path=str(base),
        selected_date_str=SIM_DATE,
        building_dsm_filename="Building_DSM.tif",
        dem_filename="DEM.tif",
        trees_filename="Trees.tif",
        landcover_filename="Landcover.tif",
        # MUST match baseline's tile_size for the wall+aspect cache to align
        # (Stage 5 symlinks). Both pull from _aoi.TILE_SIZE.
        tile_size=TILE_SIZE,
        overlap=TILE_OVERLAP,
        use_own_met=True,
        own_met_file=str(base / f"ownmet_{SIM_DATE}.txt"),
        save_tmrt=True,
        save_svf=True,
        save_shadow=True,
    )
    elapsed = time.monotonic() - t_start
    _log(f"  scenario '{name}' finished in {elapsed/60:.1f} min")
    return 0


def main() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fp = LOG_FILE.open("w")
    sys.stdout = Tee(sys.__stdout__, log_fp)
    sys.stderr = Tee(sys.__stderr__, log_fp)

    _log(f"== Stage 6: scenario SOLWEIG runs for {AOI_NAME} on {SIM_DATE} ==")
    _log(f"logging to {LOG_FILE}")
    _log(f"monitor with:  tail -f {LOG_FILE}")

    scenarios = find_scenarios()
    if not scenarios:
        raise SystemExit(f"  no scenario directories found under "
                         f"inputs/processed/{AOI_NAME}_scenario_*/")
    _log(f"found {len(scenarios)} scenario(s): "
         f"{', '.join(s.name for s in scenarios)}")
    _log(f"expected wallclock per scenario ~38 min (CPU only)")

    for base in scenarios:
        run_one(base)

    _log("")
    _log(f"DONE. {len(scenarios)} scenario(s) complete.  "
         f"total wallclock {(time.monotonic()-_T0)/60:.1f} min")


if __name__ == "__main__":
    main()
