#!/bin/bash
# Chain Stages 3 → 7 for the current AOI in _aoi.py. Used for overnight runs
# after pivoting to a new AOI.  Logs to outputs/{AOI_NAME}_pipeline.log.
#
# Usage: bash scripts/run_full_pipeline.sh
# Background:  nohup bash scripts/run_full_pipeline.sh &
#
# Each stage's failure aborts the chain (set -e).

set -euo pipefail
cd "$(dirname "$0")/.."

AOI_NAME=$(./env/bin/python -c "import sys; sys.path.insert(0,'scripts'); from _aoi import AOI_NAME; print(AOI_NAME)")
LOG="outputs/${AOI_NAME}_pipeline.log"
mkdir -p outputs

ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

say "================================================================"
say "Full pipeline run for AOI: $AOI_NAME"
say "logged to $LOG"
say "monitor with:   tail -f $LOG"
say "================================================================"

run_stage() {
  local desc="$1"; shift
  say ""
  say ">>>>> $desc"
  say ">>>>> command: $*"
  if "$@" >> "$LOG" 2>&1; then
    say "<<<<< $desc finished OK"
  else
    say "!!!!! $desc FAILED — aborting pipeline"
    exit 1
  fi
}

T0=$(date +%s)

run_stage "Stage 3 — build raster inputs"        ./env/bin/python scripts/03_build_rasters.py
run_stage "Stage 3.5 — Overture patch"           ./env/bin/python scripts/_patch_buildings.py
run_stage "Stage 4 — baseline SOLWEIG"           ./env/bin/python scripts/04_run_baseline.py
run_stage "Stage 5 — build scenarios"            ./env/bin/python scripts/05_build_scenario.py
run_stage "Stage 6 — scenario SOLWEIG runs"      ./env/bin/python scripts/06_run_scenario.py
run_stage "Stage 7 — figures + headline"         ./env/bin/python scripts/07_make_figures.py
run_stage "post — regenerate web inspector"      ./env/bin/python scripts/_inspect_web.py

T1=$(date +%s)
say ""
say "================================================================"
say "PIPELINE DONE in $(( (T1 - T0) / 60 )) min wall clock"
say "================================================================"
