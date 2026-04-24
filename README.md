# radiant-temperature

Durham Hayti tree-planting pedestrian-heat study. SOLWEIG Tmrt modeling, 5-day sprint.

Full project context (scientific approach, data sources, gotchas, timeline): see [`CLAUDE.md`](./CLAUDE.md).

## Environment

Project-local conda env at `./env/`, managed by [miniforge](https://github.com/conda-forge/miniforge).

```bash
# First time:
conda env create -f environment.yml -p ./env

# Every session:
conda activate ./env
```

## Pipeline

Scripts in `scripts/` run in numeric order:

1. `01_env_validate.py` — Day-1 gate. Verify dependencies.
2. `02_download_data.py` — Day 2. Raw inputs into `inputs/raw/`.
3. `03_build_rasters.py` — Day 2–3. Aligned DEM/DSM/CDSM/land cover + met CSV.
4. `04_run_baseline.py` — Day 3. Baseline Tmrt.
5. `05_build_scenario.py` — Day 4. Inject planted trees.
6. `06_run_scenario.py` — Day 4. Scenario Tmrt.
7. `07_make_figures.py` — Day 5. Figures + headline stat.
