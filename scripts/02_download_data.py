"""Download all raw inputs for the Durham Hayti tile.

Fires in priority order (slowest / queued requests first):
1. ERA5 hourly via Copernicus CDS API (expect queueing).
2. NC Phase 3 bare-earth DEM from sdd.nc.gov.
3. NC Phase 3 classified LAZ from USGS 3DEP on AWS.
4. EnviroAtlas Durham 1m MULC from EPA.
5. Durham Trees & Planting Sites GeoJSON from live-durhamnc.opendata.arcgis.com.
6. KRDU ASOS hourly observations (Iowa Mesonet) — paper-only, not needed for presentation.

Outputs land in inputs/raw/. See CLAUDE.md for source URLs and notes.
"""

# TODO: Day 2 — implement after environment validation passes.
