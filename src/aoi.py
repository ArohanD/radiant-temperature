"""Area of interest + run config. Edit primitives below to relocate / re-tag a run.
Code below derives all bbox/coords from the three primitives — generic by design.
"""
import os
from pyproj import Transformer

AOI_NAME = "durham_hayti"
AOI_CENTER_LAT = 35.985            # Hayti, historically Black, EPA-priority
AOI_CENTER_LON = -78.900           # neighborhood ~100 m N of Hayti Heritage Ctr
AOI_SIZE_KM = 2.0                  # Hayti core + freeway interface + Lakewood Ave
SHADOW_BUFFER_M = 200              # extra ring for SOLWEIG shadow transfer

SIM_DATE = "2025-06-23"
UTC_OFFSET = -4                    # EDT in summer; -5 for EST winter

# Output prefix the notebooks read by default. Override with env var when
# running multiple parameter sweeps from the same AOI.
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", AOI_NAME)

# Wall-height preprocessing is single-threaded per tile, so total raster_dim^2
# work is split across (raster_dim/TILE_SIZE)^2 tiles, each on its own CPU
# core. Pick TILE_SIZE so tile-count >= host vCPU count.
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


def baseline_dir(prefix: str = OUTPUT_PREFIX):
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / f"inputs/processed/{prefix}_baseline"


def scenario_dir(scenario: str, prefix: str = OUTPUT_PREFIX):
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / f"inputs/processed/{prefix}_scenario_{scenario}"


def output_root(prefix: str = OUTPUT_PREFIX):
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / f"outputs/{prefix}"


if __name__ == "__main__":
    print(f"AOI:               {AOI_NAME}")
    print(f"Center (lat,lon):  ({AOI_CENTER_LAT}, {AOI_CENTER_LON})")
    print(f"Center (UTM 17N):  ({CENTER_X:.1f}, {CENTER_Y:.1f})")
    print(f"Size:              {AOI_SIZE_KM} km × {AOI_SIZE_KM} km, {SHADOW_BUFFER_M}m shadow buffer")
    print(f"TILE_BBOX:         {TILE_BBOX}")
    print(f"PROCESSING_BBOX:   {PROCESSING_BBOX}")
    print(f"SIM_DATE:          {SIM_DATE}  UTC_OFFSET:        {UTC_OFFSET}")
    print(f"OUTPUT_PREFIX:     {OUTPUT_PREFIX}")
