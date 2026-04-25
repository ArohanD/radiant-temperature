"""Area of interest. Edit center_lat/lon/size_km to relocate the run.
Code below derives all bbox/coords from the three primitives — generic by design.
SIM_DATE starts as None and is filled in by 02_download_data.py after the
Iowa Mesonet KRDU date pick.
"""
from pyproj import Transformer

AOI_NAME = "durham_downtown"
AOI_CENTER_LAT = 35.9966          # Durham City Hall / Civic Plaza area
AOI_CENTER_LON = -78.8986
AOI_SIZE_KM = 1.0                 # core analysis tile, square (1×1 km)
SHADOW_BUFFER_M = 200             # extra ring for SOLWEIG shadow transfer

SIM_DATE = "2025-06-23"
UTC_OFFSET = -4                   # EDT for any summer date in NC; switch to -5 for EST

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
