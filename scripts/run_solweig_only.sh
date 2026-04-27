#!/bin/bash
# Resume the pipeline from Stage 4 (assumes Stage 3 + Overture patch are done).
# Used after a Stage-4+ failure where the input rasters are already built, or
# on a remote GPU pod where Stages 1-3 ran on the laptop.
#
# Picks Python via $PYTHON (default `python` on PATH). Set this to use a
# specific interpreter:
#     PYTHON=./env/bin/python bash scripts/run_solweig_only.sh   # laptop conda
#     bash scripts/run_solweig_only.sh                           # pod / system
set -euo pipefail
cd "$(dirname "$0")/.."

AOI_NAME=$(${PYTHON:-python} -c "import sys; sys.path.insert(0,'scripts'); from _aoi import AOI_NAME; print(AOI_NAME)")
LOG="outputs/${AOI_NAME}_pipeline.log"
mkdir -p outputs

ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

say ""
say "================================================================"
say "RESUMING pipeline from Stage 4 for AOI: $AOI_NAME"
say "================================================================"

run_stage() {
  local desc="$1"; shift
  say ""
  say ">>>>> $desc"
  say ">>>>> command: $*"
  if "$@" >> "$LOG" 2>&1; then
    say "<<<<< $desc finished OK"
  else
    say "!!!!! $desc FAILED — aborting"
    exit 1
  fi
}

T0=$(date +%s)
run_stage "Stage 4 — baseline SOLWEIG"           ${PYTHON:-python} scripts/04_run_baseline.py
run_stage "Stage 5 — build scenarios"            ${PYTHON:-python} scripts/05_build_scenario.py
run_stage "Stage 6 — scenario SOLWEIG runs"      ${PYTHON:-python} scripts/06_run_scenario.py
run_stage "Stage 7 — figures + headline"         ${PYTHON:-python} scripts/07_make_figures.py
run_stage "post — regenerate web inspector"      ${PYTHON:-python} scripts/_inspect_web.py
T1=$(date +%s)

say ""
say "================================================================"
say "RESUMED PIPELINE DONE in $(( (T1 - T0) / 60 )) min wall clock"
say "================================================================"
