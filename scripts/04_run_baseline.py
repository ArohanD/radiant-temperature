"""Run baseline SOLWEIG on the Hayti tile (no planted intervention).

Expected runtime: ~50 min on CPU (no GPU on this machine) for a 1.4x1.4 km 1m tile.
Outputs are written by solweig_gpu to `<base_path>/output_folder/` — NOT to outputs/baseline/.
Move or symlink afterwards if you want them under outputs/baseline/.

Skeleton:

    from solweig_gpu import thermal_comfort

    thermal_comfort(
        base_path='inputs/processed/durham_baseline',
        selected_date_str='2024-07-23',
        building_dsm_filename='Building_DSM.tif',
        dem_filename='DEM.tif',
        trees_filename='Trees.tif',
        landcover_filename='Landcover.tif',
        tile_size=1400,
        overlap=100,
        use_own_met=True,
        own_met_file='inputs/processed/durham_baseline/ownmet_2024-07-23.txt',
        save_tmrt=True,
    )

Sanity check the output: shade should be cool, parking lots hot, streets intermediate.
Red flags: uniform values, 80°C everywhere, negative Tmrt — usually UTC offset,
met parse, CDSM sign flip, or feet↔meters.
"""

# TODO: Day 3 — implement after rasters pass QA.
