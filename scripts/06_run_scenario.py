"""Stage 6 — run SOLWEIG against each scenario directory built in Stage 5.

Iterates over every `inputs/processed/{AOI_NAME}_scenario_*/` directory, fires
`thermal_comfort()` against each, and writes outputs under each scenario's own
`output_folder/`. Total wallclock ~2 × baseline (≈ 75 min for two scenarios).

Logs to `outputs/{AOI_NAME}_scenario_run.log` for live monitoring:

    tail -f outputs/durham_downtown_scenario_run.log
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

from _aoi import AOI_NAME, SIM_DATE

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


def run_one(base: Path) -> int:
    name = base.name.replace(f"{AOI_NAME}_scenario_", "")
    _log(f"running scenario '{name}' in {base}", header=True)
    preflight(base)

    if (base / "output_folder").exists():
        _log(f"  WARN: {base/'output_folder'} already exists — skipping. "
             f"Delete it to re-run.")
        return 0

    from solweig_gpu import thermal_comfort
    t_start = time.monotonic()
    thermal_comfort(
        base_path=str(base),
        selected_date_str=SIM_DATE,
        building_dsm_filename="Building_DSM.tif",
        dem_filename="DEM.tif",
        trees_filename="Trees.tif",
        landcover_filename="Landcover.tif",
        tile_size=1600,  # > raster shape so it stays a single tile (see 04_run_baseline.py)
        overlap=100,
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
