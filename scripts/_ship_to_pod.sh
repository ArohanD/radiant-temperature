#!/bin/bash
# Ship Hayti SOLWEIG inputs + scripts to a RunPod pod via direct-TCP SSH.
# The ssh.runpod.io proxy requires a PTY and breaks rsync; the direct TCP
# endpoint (shown in RunPod Connect → "SSH over exposed TCP") is a clean
# shell that supports rsync/scp/sftp.
#
# Usage (from repo root on the laptop):
#   bash scripts/_ship_to_pod.sh

set -euo pipefail
cd "$(dirname "$0")/.."

POD_HOST="69.30.85.195"
POD_PORT="22101"
POD_USER="root"
SSH_KEY="$HOME/.ssh/runpod_hayti"
DEST="/workspace/radiant-temperature/"

echo "Shipping to: $POD_USER@$POD_HOST:$POD_PORT  →  $DEST"
echo "Using key:   $SSH_KEY"
echo

ssh -i "$SSH_KEY" -p "$POD_PORT" "$POD_USER@$POD_HOST" "mkdir -p $DEST"

rsync -avz --progress -e "ssh -i $SSH_KEY -p $POD_PORT" \
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
  scripts \
  environment.yml \
  CLAUDE.md \
  notes \
  inputs/processed/durham_hayti_baseline \
  inputs/raw/durham/trees_planting \
  inputs/raw/durham/overture/buildings_durham_hayti.geojson \
  "$POD_USER@$POD_HOST:$DEST"

echo
echo "Transfer complete."
