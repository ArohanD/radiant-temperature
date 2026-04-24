"""Inject Durham's planned plantings into the Trees + Landcover rasters to produce scenario inputs.

1. Load Trees & Planting Sites GeoJSON; filter to future/planned status.
2. Reproject to EPSG:32617; clip to tile bounds.
3. For each point: burn ~3x3 pixel disk at ~8-10m canopy height into the Trees raster.
4. Update land cover at those pixels to grass class (code 5).

Writes a COMPLETE scenario input directory mirroring the baseline:
  inputs/processed/durham_scenario/
    ├── Building_DSM.tif   (copy/symlink of baseline)
    ├── DEM.tif            (copy/symlink of baseline)
    ├── Trees.tif          (modified — baseline + burned planting disks)
    ├── Landcover.tif      (modified — planting pixels -> grass)
    └── ownmet_<date>.txt  (copy/symlink of baseline)

This lets scripts/06_run_scenario.py pass base_path='inputs/processed/durham_scenario/' with
zero other changes — outputs cleanly separate under each base_path's output_folder/.
"""

# TODO: Day 4 — implement after baseline run is trustworthy.
