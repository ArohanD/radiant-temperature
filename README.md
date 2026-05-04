# radiant-temperature

A reproducible analysis of the pedestrian heat impact of Durham's
2025–2028 street tree planting program in the Hayti neighborhood.
The whole pipeline — data acquisition, raster construction, three
[SOLWEIG](https://link.springer.com/article/10.1007/s00484-008-0162-7)
runs at 1 m resolution, plausibility checks, headline statistics, and
figures — lives in a single [marimo](https://marimo.io) notebook at
`notebooks/analysis.py`. A static rendered preview is hosted at
<https://arohand.github.io/radiant-temperature/>.

## Getting started locally

The pipeline depends on a few system-level binaries (PDAL, GDAL), so
a conda env is the path of least resistance.

### 1. Install miniforge once

```bash
curl -L -o /tmp/miniforge.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash /tmp/miniforge.sh
exec $SHELL
```

macOS users: substitute the macOS arm64 installer URL.

### 2. Clone and create the project-local env

```bash
git clone https://github.com/ArohanD/radiant-temperature.git
cd radiant-temperature
conda env create -f environment.yml -p ./env
conda activate ./env
```

The env installs to `./env` (~3 GB, gitignored). Activate from the
repo root every session: `conda activate ./env`.

### 3. Open the notebook

```bash
marimo edit notebooks/analysis.py
```

Marimo opens at `http://localhost:2718`. Pick an AOI profile from the
dropdown at the top of the notebook (`hayti_demo` for a ~45-minute
end-to-end smoke test, `durham_hayti` for the full production tile)
and run the cells top to bottom. Long-running cells (PDAL pull,
SOLWEIG runs) are idempotent and skip when their outputs are already
on disk.

### 4. View the interactive map inspector

Section 10 of the notebook builds a self-contained MapLibre bundle at
`inputs/processed/{aoi}_baseline/web/`. Once it has run, serve the
bundle from the repo root:

```bash
python -m http.server 8765 --directory inputs/processed/hayti_demo_baseline/web
```

Open <http://localhost:8765/> in any browser. Swap
`hayti_demo_baseline` for `durham_hayti_baseline` when running on the
production AOI.
