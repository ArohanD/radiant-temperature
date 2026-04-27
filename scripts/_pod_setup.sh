#!/bin/bash
# One-shot setup for a fresh RunPod pod (PyTorch image, system Python 3.11).
# Codifies every install-time fix we hit on 2026-04-26 so the next pod boots
# clean.
#
# Usage on the pod, after rsync'ing the repo via _ship_to_pod.sh:
#   cd /workspace/radiant-temperature
#   bash scripts/_pod_setup.sh
#
# Run is idempotent — safe to re-execute. Takes ~3 min on first run, ~10 sec
# on subsequent runs.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "================================================================"
echo "Pod setup for radiant-temperature"
echo "================================================================"

# 1. System packages: GDAL CLI + libgdal-dev (so pip-built GDAL bindings link
# against the right libgdal), proj-data (provides /usr/share/proj/proj.db so
# rasterio can reproject), python3.11-dev (headers for building the GDAL
# extension), rsync (often missing on minimal containers), locales (for btop).
echo
echo ">>> apt: gdal-bin libgdal-dev proj-data python3.11-dev rsync locales"
apt-get update -qq
apt-get install -y -qq \
  gdal-bin libgdal-dev proj-data \
  python3.11-dev \
  rsync \
  locales

locale-gen en_US.UTF-8 >/dev/null 2>&1 || true

# 2. Python packages. Pin numpy<2 because solweig-gpu's preprocessor still
# uses numpy.bool8 etc. solweig-gpu, rasterio, geopandas pull large transitive
# trees; -q quiets the noise.
echo
echo ">>> pip: solweig-gpu + numpy<2 + geo stack"
pip install -q "numpy<2" solweig-gpu rasterio geopandas pyproj shapely matplotlib overturemaps

# 3. GDAL Python bindings: apt installs python3-gdal, but it's compiled for
# the system Python (3.10/3.12), not the runpod pytorch image's 3.11. Force
# pip to rebuild against the system libgdal we just installed.
echo
echo ">>> rebuild osgeo bindings for the active Python"
GDAL_VER=$(gdal-config --version)
pip install -q --no-build-isolation --force-reinstall --no-cache-dir --no-deps "GDAL==${GDAL_VER}"

# 4. Verify everything imports + GPU is visible
echo
echo ">>> verifying"
python -c "
import torch
from osgeo import gdal
from solweig_gpu import thermal_comfort
import rasterio, geopandas
print(f'  torch CUDA:      {torch.cuda.is_available()}')
print(f'  GPU:             {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')
print(f'  GDAL:            {gdal.__version__}')
print(f'  rasterio:        {rasterio.__version__}')
print(f'  solweig-gpu:     OK')
"

echo
echo "================================================================"
echo "Pod setup complete. Next:"
echo "  bash scripts/run_solweig_only.sh"
echo "================================================================"
