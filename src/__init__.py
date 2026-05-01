"""Reusable building blocks for the four marimo notebooks.

Modules:
  aoi             — AOI primitives (name, center, date, tile geometry).
  geo             — geo env setup (PROJ_DATA, GDAL_DATA) + multiprocessing.
  met             — HRRR fetch + UMEP own-met file writer.
  buildings       — LiDAR DSM, DEM, MULC reproject, Overture-gated patch.
  scenarios       — burn planted-canopy disks into Trees.tif + Landcover.tif.
  solweig_runner  — wrapper around solweig_gpu.thermal_comfort with idempotency
                    + wall-cache reuse across scenarios.
  evaluate        — physical sanity checks on baseline + scenario outputs.
  compare_obs     — KRDU + Open-Meteo cross-checks of HRRR forcing & UTCI.
  figures         — every PNG used in the deck (study site, panels, money shot,
                    histograms, validation, etc.).
  inspector       — self-contained MapLibre web bundle + screenshot capture.
"""
