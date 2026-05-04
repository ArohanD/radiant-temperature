"""Area-of-interest profiles for the Durham SOLWEIG analysis.

Two profiles ship with the project:

  hayti_demo    600 m x 600 m smoke-test AOI centred on the densest cluster
                of planted sites within the Hayti production AOI (163 of 245
                sites). Designed to run end-to-end on CPU in roughly five
                minutes total. The default.

  durham_hayti  Full 2 km x 2 km production AOI used for the headline
                figures and the conference deck.

Selection precedence:
  1. Explicit argument to `get_aoi(profile)`.
  2. Environment variable `AOI_PROFILE`.
  3. Default `hayti_demo`.

Module-level constants (`AOI_NAME`, `SIM_DATE`, etc.) reflect the active
profile. They exist to keep the legacy `src/figures.py` and
`src/inspector.py` modules working without a refactor.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer

REPO = Path(__file__).resolve().parent.parent

# Centre of the densest 600 m x 600 m cluster of planting sites within the
# Hayti AOI (163 of 245 sites). Computed once via a 50 m sliding grid over
# Durham's "Trees and Planting Sites" GeoJSON, then transformed from UTM 17N
# to WGS84. To regenerate after a refresh of the planting-sites layer:
#   sites = gpd.read_file(<trees.geojson>).to_crs("EPSG:32617")
#   sites = sites[sites["present"] == "Planting Site"]
#   ... sliding-window densest 600 m search ...
_HAYTI_DENSE_CLUSTER_LAT = 35.988017
_HAYTI_DENSE_CLUSTER_LON = -78.892156

AOI_PROFILES: dict[str, dict] = {
    "hayti_demo": {
        "name": "hayti_demo",
        "center_lat": _HAYTI_DENSE_CLUSTER_LAT,
        "center_lon": _HAYTI_DENSE_CLUSTER_LON,
        "size_km": 0.6,
        "shadow_buffer_m": 100,
        "sim_date": "2025-06-23",
        "utc_offset": -4,
        "tile_size": 600,
        "tile_overlap": 50,
        "description": (
            "Smoke-test AOI. 600 m square around the densest cluster of "
            "planted sites in Hayti (163 of 245 sites)."
        ),
    },
    "durham_hayti": {
        "name": "durham_hayti",
        "center_lat": 35.985,
        "center_lon": -78.900,
        "size_km": 2.0,
        "shadow_buffer_m": 200,
        "sim_date": "2025-06-23",
        "utc_offset": -4,
        "tile_size": 1000,
        "tile_overlap": 100,
        "description": (
            "Production AOI. 2 km square covering historic Hayti, the "
            "Durham Freeway interface, and the corridor south to Lakewood "
            "Avenue."
        ),
    },
}

DEFAULT_PROFILE = "hayti_demo"


@dataclass(frozen=True)
class AOIConfig:
    name: str
    center_lat: float
    center_lon: float
    size_km: float
    shadow_buffer_m: int
    sim_date: str
    utc_offset: int
    tile_size: int
    tile_overlap: int
    description: str
    center_x: float
    center_y: float
    tile_bbox: tuple[float, float, float, float]
    processing_bbox: tuple[float, float, float, float]

    @property
    def baseline_dir(self) -> Path:
        return REPO / f"inputs/processed/{self.name}_baseline"

    def scenario_dir(self, scenario: str) -> Path:
        return REPO / f"inputs/processed/{self.name}_scenario_{scenario}"

    @property
    def output_root(self) -> Path:
        return REPO / f"outputs/{self.name}"

    @property
    def figures_dir(self) -> Path:
        return REPO / f"figures/{self.name}"

    @property
    def slides_dir(self) -> Path:
        return self.figures_dir / "slides"

    @property
    def met_path(self) -> Path:
        return self.baseline_dir / f"ownmet_{self.sim_date}.txt"


def _build_config(profile: dict) -> AOIConfig:
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)
    cx, cy = to_utm.transform(profile["center_lon"], profile["center_lat"])
    half = profile["size_km"] * 500.0
    buf = profile["shadow_buffer_m"]
    tile_bbox = (cx - half, cy - half, cx + half, cy + half)
    processing_bbox = (cx - half - buf, cy - half - buf,
                        cx + half + buf, cy + half + buf)
    return AOIConfig(
        name=profile["name"],
        center_lat=profile["center_lat"],
        center_lon=profile["center_lon"],
        size_km=profile["size_km"],
        shadow_buffer_m=profile["shadow_buffer_m"],
        sim_date=profile["sim_date"],
        utc_offset=profile["utc_offset"],
        tile_size=profile["tile_size"],
        tile_overlap=profile["tile_overlap"],
        description=profile["description"],
        center_x=cx,
        center_y=cy,
        tile_bbox=tile_bbox,
        processing_bbox=processing_bbox,
    )


def get_aoi(profile: str | None = None) -> AOIConfig:
    """Return the configuration for the requested AOI profile.

    Selection precedence: explicit argument, then `AOI_PROFILE` env var,
    then `hayti_demo`. Raises `KeyError` for an unknown profile name.
    """
    name = profile or os.environ.get("AOI_PROFILE", DEFAULT_PROFILE)
    if name not in AOI_PROFILES:
        raise KeyError(
            f"Unknown AOI profile {name!r}. "
            f"Available: {sorted(AOI_PROFILES)}"
        )
    return _build_config(AOI_PROFILES[name])


def list_profiles() -> list[str]:
    return list(AOI_PROFILES.keys())


# ============================================================================
# Backward-compatible module-level constants.
# These mirror the active profile and exist so legacy modules (figures.py,
# inspector.py) do not need to be refactored to take an AOIConfig argument.
# ============================================================================
_active = get_aoi()

AOI_NAME = _active.name
AOI_CENTER_LAT = _active.center_lat
AOI_CENTER_LON = _active.center_lon
AOI_SIZE_KM = _active.size_km
SHADOW_BUFFER_M = _active.shadow_buffer_m
SIM_DATE = _active.sim_date
UTC_OFFSET = _active.utc_offset
TILE_SIZE = _active.tile_size
TILE_OVERLAP = _active.tile_overlap
CENTER_X = _active.center_x
CENTER_Y = _active.center_y
TILE_BBOX = _active.tile_bbox
PROCESSING_BBOX = _active.processing_bbox
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", AOI_NAME)


def baseline_dir(prefix: str | None = None) -> Path:
    return REPO / f"inputs/processed/{prefix or OUTPUT_PREFIX}_baseline"


def scenario_dir(scenario: str, prefix: str | None = None) -> Path:
    return REPO / f"inputs/processed/{prefix or OUTPUT_PREFIX}_scenario_{scenario}"


def output_root(prefix: str | None = None) -> Path:
    return REPO / f"outputs/{prefix or OUTPUT_PREFIX}"


if __name__ == "__main__":
    for name in list_profiles():
        cfg = get_aoi(name)
        print(f"{name}:")
        print(f"  centre (lat, lon): ({cfg.center_lat}, {cfg.center_lon})")
        print(f"  size:              {cfg.size_km} km × {cfg.size_km} km")
        print(f"  tile bbox (UTM):   {cfg.tile_bbox}")
        print(f"  description:       {cfg.description}")
