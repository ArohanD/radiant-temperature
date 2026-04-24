"""Build the 5 co-registered input rasters for SOLWEIG.

Target: EPSG:32617, 1m resolution, identical extent (~1400x1400 px after 200m buffer).

1. DEM: NC Phase 3 bare-earth, reproject + clip. Native: US Survey Feet → convert to meters.
2. DSM: PDAL pipeline on classified LAZ first returns → 1m grid. Units: US Survey Feet → meters.
3. CDSM: DSM - DEM, masked to tree pixels from land cover.
4. Land cover: EnviroAtlas MULC reclassified to UMEP codes (1=paved, 2=buildings, 5=grass, 6=bare soil, 7=water).
5. Met CSV: ERA5 hourly for chosen day, formatted for SOLWEIG with correct UTC offset (-4 for EDT).

CRITICAL: NC Phase 3 LiDAR is US Survey Feet. Verify unit conversion before downstream steps.
"""

# TODO: Day 2-3 — implement after data downloaded.
