#!/bin/bash
# Pull SOLWEIG outputs from a RunPod pod into an isolated, timestamped tree
# under outputs/pod_runs/. Designed to be safe to run while the laptop's own
# pipeline is still writing to inputs/processed/{AOI}_baseline/, _scenario_*,
# figures/{AOI}/, and outputs/{AOI}_scenario_diffs/. Nothing in this script
# touches those laptop-owned paths.
#
# Edit POD_HOST / POD_PORT below if RunPod reassigned them after a restart.
#
# Usage (from repo root):
#   bash scripts/_pull_from_pod.sh
#
# Result: outputs/pod_runs/{AOI}_<timestamp>/ contains
#     figures/                       (PNGs + headline.txt)
#     scenario_diffs/                (dtmrt_peak_*.tif)
#     baseline/output_folder/        (TMRT/UTCI/SVF/Shadow per tile + merged)
#     scenario_year10/output_folder/
#     scenario_mature/output_folder/
#     ... matching the pod's layout, isolated from the laptop pipeline

set -euo pipefail
cd "$(dirname "$0")/.."

POD_HOST="69.30.85.195"
POD_PORT="22101"
POD_USER="root"
SSH_KEY="$HOME/.ssh/runpod_hayti"
POD_REPO="/workspace/radiant-temperature"

AOI=$(./env/bin/python -c "import sys; sys.path.insert(0,'scripts'); from _aoi import AOI_NAME; print(AOI_NAME)")
STAMP=$(date +%Y%m%d_%H%M%S)
DEST="outputs/pod_runs/${AOI}_${STAMP}"

mkdir -p "$DEST"

echo "Pulling from: $POD_USER@$POD_HOST:$POD_PORT"
echo "Saving to:    $DEST  (isolated — does not touch any active laptop pipeline path)"
echo

RSH="ssh -i $SSH_KEY -p $POD_PORT -o StrictHostKeyChecking=accept-new"

# Each rsync is its own block so a partial failure on one doesn't kill the rest.
# Trailing slashes on sources matter: SRC/ means "the contents of SRC", SRC means "SRC itself".

echo ">>> figures/"
mkdir -p "$DEST/figures"
rsync -avz -e "$RSH" \
  "$POD_USER@$POD_HOST:$POD_REPO/figures/${AOI}/" \
  "$DEST/figures/" || echo "(none — Stage 7 may not have run)"

echo
echo ">>> scenario_diffs/"
mkdir -p "$DEST/scenario_diffs"
rsync -avz -e "$RSH" \
  "$POD_USER@$POD_HOST:$POD_REPO/outputs/${AOI}_scenario_diffs/" \
  "$DEST/scenario_diffs/" || echo "(none)"

echo
echo ">>> baseline/output_folder/"
mkdir -p "$DEST/baseline/output_folder"
rsync -avz -e "$RSH" \
  "$POD_USER@$POD_HOST:$POD_REPO/inputs/processed/${AOI}_baseline/output_folder/" \
  "$DEST/baseline/output_folder/" || echo "(none)"

echo
echo ">>> scenario_year10/"
mkdir -p "$DEST/scenario_year10"
rsync -avz -e "$RSH" \
  --exclude 'processed_inputs/' \
  "$POD_USER@$POD_HOST:$POD_REPO/inputs/processed/${AOI}_scenario_year10/" \
  "$DEST/scenario_year10/" || echo "(none)"

echo
echo ">>> scenario_mature/"
mkdir -p "$DEST/scenario_mature"
rsync -avz -e "$RSH" \
  --exclude 'processed_inputs/' \
  "$POD_USER@$POD_HOST:$POD_REPO/inputs/processed/${AOI}_scenario_mature/" \
  "$DEST/scenario_mature/" || echo "(none)"

echo
echo "================================================================"
echo "Done. Pod outputs preserved at:"
echo "  $(pwd)/$DEST"
echo
echo "Headline:"
test -f "$DEST/figures/headline.txt" && cat "$DEST/figures/headline.txt" || echo "  (no headline.txt)"
echo "================================================================"
