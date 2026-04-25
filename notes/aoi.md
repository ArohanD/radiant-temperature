# AOI decision record

**AOI name**: `durham_downtown`
**Center (lat, lon)**: `35.9966°N, -78.8986°W`
**Center (UTM 17N, EPSG:32617)**: `(689415.6, 3985613.4)`
**Size**: 1.0 km × 1.0 km core, 200 m shadow buffer
**TILE_BBOX (EPSG:32617)**: `(688915.6, 3985113.4, 689915.6, 3986113.4)`
**PROCESSING_BBOX (EPSG:32617)**: `(688715.6, 3984913.4, 690115.6, 3986313.4)`

**Simulation date**: `2025-06-23` (KRDU max 99°F, midday cloud score 1.00 — clear/FEW). Top hot+clear day of summer 2025, picked automatically by `02_download_data.py` from Iowa Mesonet ASOS.

**Planting sites within AOI**: **22** (filter `present == "Planting Site"` from Durham's Trees & Planting Sites layer; 6,011 total citywide).

## Why this location

- City Hall / Civic Plaza area: dense pavement (Civic Plaza, surface lots near Mangum/Roxboro) plus mature street trees on Main Street. High Tmrt contrast for the 3-panel figure.
- Recognizable to local audiences. Easy to caption on a slide.
- 1×1 km box centered here covers roughly Geer Street (north), East Pettigrew (south), Mangum (east), Duke Street (west).

## Pivot from CLAUDE.md

The original spec called for Hayti specifically because of its EPA equity-priority designation. The user redirected to downtown for visual impact. Methodology unchanged. The equity framing in the headline / slide should adjust accordingly (or be dropped if not honest for downtown).

## To relocate

Edit `scripts/_aoi.py` — `AOI_NAME`, `AOI_CENTER_LAT`, `AOI_CENTER_LON`, `AOI_SIZE_KM`. Re-run `02_download_data.py` to redo the planting-point sanity count for the new bbox. The data sources are city-wide so no re-downloads needed for any Durham relocation.
