"""Inject Durham's planned plantings into the CDSM + land cover to produce scenario inputs.

1. Load Trees & Planting Sites GeoJSON; filter to future/planned status.
2. Reproject to EPSG:32617; clip to tile bounds.
3. For each point: burn ~3x3 pixel disk at ~8-10m canopy height into CDSM.
4. Update land cover at those pixels to grass class.

Writes inputs/processed/cdsm_scenario.tif and inputs/processed/landcover_scenario.tif.
"""

# TODO: Day 4 — implement after baseline run is trustworthy.
