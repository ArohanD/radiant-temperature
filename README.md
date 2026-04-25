# radiant-temperature

Durham Hayti tree-planting pedestrian-heat study. SOLWEIG Tmrt modeling, 5-day sprint.

Full project context (scientific approach, data sources, gotchas, timeline): see [`CLAUDE.md`](./CLAUDE.md).

---

## Reproducing the current state from a fresh clone

Everything below assumes a Linux x86_64 machine with `bash`, `git`, `curl`, and `unzip`. Tested on Ubuntu with kernel 6.8. Should also work on macOS arm64 with the equivalent miniforge installer.

### 1. Install miniforge (skip if already installed)

```bash
curl -L -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash /tmp/miniforge.sh   # accept defaults; answer "yes" to conda init
exec $SHELL              # reload so `conda` resolves on PATH
```

### 2. Clone and create the project-local env

```bash
git clone <this-repo> radiant-temperature
cd radiant-temperature
conda env create -f environment.yml -p ./env
conda activate ./env
```

The env lives at `./env/` (~3 GB, gitignored). Deleting the repo deletes the env. Activate from the repo root every session — `conda activate ./env`.

### 3. Set up the Copernicus CDS API key

The CDS key is **project-local** (gitignored), not in `~/.cdsapirc`. This keeps credentials out of the home directory and prevents leaking into other projects.

a. Get a key: register at <https://cds.climate.copernicus.eu/>, accept the ERA5 license, copy your personal API token from the user profile page.

b. Create `./.cdsapirc` in the repo root:

```
url: https://cds.climate.copernicus.eu/api
key: <your-token-here>
```

c. Lock down permissions and tell `cdsapi` where to find the file (env-scoped, so it only applies when this env is active):

```bash
chmod 600 .cdsapirc
conda env config vars set CDSAPI_RC="$(pwd)/.cdsapirc"
conda deactivate && conda activate ./env   # reload env vars
```

Verify: `python -c "import cdsapi; cdsapi.Client()"` should not raise.

### 4. Validate the environment (Day-1 gate, part 1)

```bash
python scripts/01_env_validate.py
```

Expected output: version lines for numpy, rasterio, geopandas, pdal, gdal, torch, cdsapi, solweig_gpu, then `thermal_comfort imported: <function>` and `CUDA available: False` (this machine is CPU-only).

### 5. Download the SOLWEIG-GPU sample dataset

Zenodo DOI: [10.5281/zenodo.18561860](https://doi.org/10.5281/zenodo.18561860) (Austin TX, 2020-08-13, ~3367×3913 @ 2 m, EPSG:32614).

```bash
mkdir -p inputs/raw/sample
cd inputs/raw/sample
curl -L -o Input_rasters.zip https://zenodo.org/records/18561860/files/Input_rasters.zip
unzip Input_rasters.zip
curl -L -O https://zenodo.org/records/18561860/files/ownmet_Forcing_data.txt
curl -L -O https://zenodo.org/records/18561860/files/README.txt
cd ../../..
```

After this you should have:
```
inputs/raw/sample/
├── Input_rasters/
│   ├── Building_DSM.tif
│   ├── DEM.tif
│   ├── Trees.tif
│   └── Landcover.tif
├── ownmet_Forcing_data.txt
└── README.txt
```

### 6. Run the sample (Day-1 gate, part 2)

```bash
python scripts/_sample_run.py
```

Crops the sample to a 500×500 central window and runs `thermal_comfort()` on CPU. Takes **~3.5 min** on a modern laptop.

Outputs land at:
```
inputs/processed/sample_crop/
├── Building_DSM.tif, DEM.tif, Trees.tif, Landcover.tif   (cropped inputs)
├── ownmet_Forcing_data.txt                               (copied)
├── processed_inputs/                                     (SVF, walls, aspect — solweig-gpu intermediates)
└── output_folder/0_0/
    ├── TMRT_0_0.tif   (24-band, hourly Tmrt, °C; band N = hour N−1 local)
    └── UTCI_0_0.tif   (24-band, hourly UTCI, °C)
```

### 7. Verify the sample output

Quick numerical sanity check:

```bash
python - <<'PY'
import numpy as np, rasterio
with rasterio.open("inputs/processed/sample_crop/output_folder/0_0/TMRT_0_0.tif") as ds:
    for b, hr in [(8, "07:00"), (14, "13:00"), (20, "19:00")]:
        a = ds.read(b); a = a[np.isfinite(a)]
        print(f"  band {b:2d} ({hr}): min={a.min():.1f} mean={a.mean():.1f} max={a.max():.1f} std={a.std():.2f}")
PY
```

Expected (within rounding):
```
band  8 (07:00): min=19.8 mean=20.7 max=21.9 std=0.41
band 14 (13:00): min=34.4 mean=63.3 max=78.4 std=10.48
band 20 (19:00): min=32.3 mean=39.2 max=45.5 std=3.49
```

The key signal is **std ≈ 10°C at 13:00** — proves shadows are differentiating sunlit from shaded pixels.

Visual check: open `TMRT_0_0.tif` in QGIS, render band 14 with a heat ramp. You should see hot streets and roofs (red/orange), cool tree canopy and building shadows (blue). Tile is in north Austin (≈30.332°N, −97.721°W) — sanity-check against satellite imagery.

For more on what the numbers mean (Tmrt vs UTCI vs air temperature), see `notes/sample_validation.md`.

---

## Repo layout

```
radiant-temperature/
├── CLAUDE.md               # full project brief — scientific spec
├── README.md               # this file
├── environment.yml         # conda env source of truth
├── .cdsapirc               # CDS API key (gitignored, you create this)
├── env/                    # project-local conda env (gitignored)
├── scripts/
│   ├── 01_env_validate.py  # Day-1 gate: dependency smoke test
│   ├── _sample_run.py      # Day-1 gate: SOLWEIG sample run (underscore = scratch, not pipeline)
│   ├── 02_download_data.py … 07_make_figures.py   # pipeline stubs (Days 2–5)
├── inputs/
│   ├── raw/                # downloads as-acquired (gitignored)
│   └── processed/          # aligned rasters + outputs (gitignored)
├── outputs/                # gitignored
├── figures/                # PNGs gitignored; figure code tracked
└── notes/                  # tracked notes
```

## Pipeline (forward-looking, not yet implemented)

Scripts in `scripts/` run in numeric order:

1. `01_env_validate.py` — **done** (Day 1).
2. `02_download_data.py` — Day 2. ERA5, NC LiDAR, Durham Trees GeoJSON, EnviroAtlas MULC.
3. `03_build_rasters.py` — Day 2–3. Aligned DEM/DSM/CDSM/landcover at 1 m EPSG:32617 + UMEP met file.
4. `04_run_baseline.py` — Day 3. Baseline Tmrt for the Hayti tile.
5. `05_build_scenario.py` — Day 4. Inject Durham's planned plantings.
6. `06_run_scenario.py` — Day 4. Scenario Tmrt.
7. `07_make_figures.py` — Day 5. Three figures + headline ΔTmrt stat.
