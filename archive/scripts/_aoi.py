"""Area of interest + run config. Edit primitives below to relocate / re-tag a run.
Code below derives all bbox/coords from the three primitives — generic by design.
SIM_DATE starts as None and is filled in by 02_download_data.py after the
Iowa Mesonet KRDU date pick.
"""
import os
from pyproj import Transformer

AOI_NAME = "durham_hayti"
AOI_CENTER_LAT = 35.985            # Hayti — historically Black, EPA-priority
AOI_CENTER_LON = -78.900           # neighborhood ~100m N of Hayti Heritage Ctr
AOI_SIZE_KM = 2.0                  # captures Hayti core + freeway interface
                                    # + south to Lakewood Ave
SHADOW_BUFFER_M = 200             # extra ring for SOLWEIG shadow transfer

SIM_DATE = "2025-06-23"
UTC_OFFSET = -4                   # EDT for any summer date in NC; switch to -5 for EST

# Optional run tag, appended to AOI_NAME in OUTPUT paths only (so iterating on
# scenario assumptions doesn't clobber a prior run, but raw inputs stay shared).
# Leave as "" to mean "current run for this AOI". Set via env var or edit here:
#     RUN_TAG=v2_lowcanopy bash scripts/run_solweig_only.sh
RUN_TAG = os.environ.get("RUN_TAG", "")
RUN_NAME = f"{AOI_NAME}_{RUN_TAG}" if RUN_TAG else AOI_NAME

# Wall-height preprocessing is single-threaded per tile, so total raster_dim^2
# work is split across (raster_dim/TILE_SIZE)^2 tiles, each on its own CPU
# core. Pick TILE_SIZE so tile-count >= host vCPU count:
#   laptop (8-16 cores), 2km AOI (2401 px): TILE_SIZE=1000 → 9 tiles
#   pod RTX A5000 (~8 vCPU), 2km AOI:        TILE_SIZE=1000 → 9 tiles  (matches)
# baseline (Stage 4) and scenarios (Stage 6) MUST share TILE_SIZE — otherwise
# Stage 5's wall-height symlink cache misses and Stage 6 re-runs ~20 min of
# CPU prep per scenario. Verify host vCPU with `nproc` on laptop;
# `cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us` / 100000 on a container.
TILE_SIZE = int(os.environ.get("TILE_SIZE", "1000"))
TILE_OVERLAP = 100

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)
CENTER_X, CENTER_Y = _to_utm.transform(AOI_CENTER_LON, AOI_CENTER_LAT)

_HALF = AOI_SIZE_KM * 500.0
TILE_BBOX = (
    CENTER_X - _HALF, CENTER_Y - _HALF,
    CENTER_X + _HALF, CENTER_Y + _HALF,
)
PROCESSING_BBOX = (
    CENTER_X - _HALF - SHADOW_BUFFER_M, CENTER_Y - _HALF - SHADOW_BUFFER_M,
    CENTER_X + _HALF + SHADOW_BUFFER_M, CENTER_Y + _HALF + SHADOW_BUFFER_M,
)

if __name__ == "__main__":
    print(f"AOI:               {AOI_NAME}")
    print(f"Center (lat,lon):  ({AOI_CENTER_LAT}, {AOI_CENTER_LON})")
    print(f"Center (UTM 17N):  ({CENTER_X:.1f}, {CENTER_Y:.1f})")
    print(f"Size:              {AOI_SIZE_KM} km × {AOI_SIZE_KM} km, {SHADOW_BUFFER_M}m shadow buffer")
    print(f"TILE_BBOX:         {TILE_BBOX}")
    print(f"PROCESSING_BBOX:   {PROCESSING_BBOX}")
    print(f"SIM_DATE:          {SIM_DATE}")
    print(f"UTC_OFFSET:        {UTC_OFFSET}")
