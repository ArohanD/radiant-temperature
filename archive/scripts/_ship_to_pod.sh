#!/bin/bash
# Ship the SOLWEIG inputs + scripts for the current AOI to a RunPod pod via
# direct-TCP SSH. Preserves the source directory hierarchy (--relative) so
# files land at e.g. /workspace/radiant-temperature/inputs/processed/<AOI>_baseline/.
#
# RunPod's ssh.runpod.io proxy requires a PTY and breaks rsync; the direct TCP
# endpoint (shown in RunPod Connect → "SSH over exposed TCP") is a clean shell
# that supports rsync/scp/sftp. Edit POD_HOST/POD_PORT below — RunPod
# reassigns them on every Stop/Start.
#
# Usage (from repo root on the laptop):
#   bash scripts/_ship_to_pod.sh

set -euo pipefail
cd "$(dirname "$0")/.."

POD_HOST="${POD_HOST:-69.30.85.195}"
POD_PORT="${POD_PORT:-22101}"
POD_USER="${POD_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/runpod_hayti}"
POD_REPO="${POD_REPO:-/workspace/radiant-temperature}"

# Resolve AOI from _aoi.py — same source of truth as every other script.
AOI=$(${PYTHON:-./env/bin/python} -c "import sys; sys.path.insert(0,'scripts'); from _aoi import AOI_NAME; print(AOI_NAME)")

echo "Shipping AOI=$AOI to: $POD_USER@$POD_HOST:$POD_PORT  →  $POD_REPO/"
echo "Using key:   $SSH_KEY"
echo

# Make the destination root if missing
ssh -i "$SSH_KEY" -p "$POD_PORT" "$POD_USER@$POD_HOST" "mkdir -p $POD_REPO"

# --relative + leading ./ on each source preserves the path under POD_REPO.
# So ./inputs/processed/<AOI>_baseline/ lands at
# $POD_REPO/inputs/processed/<AOI>_baseline/ on the pod (not flattened).
rsync -avz --progress --relative -e "ssh -i $SSH_KEY -p $POD_PORT" \
  --exclude 'env/' \
  --exclude '__pycache__/' \
  --exclude '.git/' \
  --exclude 'outputs/' \
  --exclude 'figures/' \
  --exclude 'processed_inputs/' \
  --exclude 'output_folder/' \
  --exclude 'durham_downtown_*' \
  --exclude 'nc_dem/' \
  --exclude 'nc_laz/' \
  --exclude 'enviroatlas_mulc/' \
  ./scripts \
  ./environment.yml \
  ./CLAUDE.md \
  ./notes \
  ./inputs/processed/${AOI}_baseline \
  ./inputs/raw/durham/trees_planting \
  ./inputs/raw/durham/overture/buildings_${AOI}.geojson \
  "$POD_USER@$POD_HOST:$POD_REPO/"

echo
echo "Transfer complete. SSH in and run:"
echo "  cd $POD_REPO && bash scripts/_pod_setup.sh && bash scripts/run_solweig_only.sh"
