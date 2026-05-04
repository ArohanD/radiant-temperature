# radiant-temperature

A reproducible analysis of the pedestrian heat impact of Durham's
2025–2028 street tree planting program in the Hayti neighborhood. The
analysis runs the [SOLWEIG](https://link.springer.com/article/10.1007/s00484-008-0162-7)
urban-radiation model at one-meter resolution against a 2025-06-23
heatwave forcing and compares two canopy-growth scenarios against a
baseline. The headline result from the production AOI: roughly
**−4.7 to −5.8 °C ΔUTCI** at the planted pixels at peak hour, varying
with canopy maturity. Tile-wide mean ΔUTCI is −0.01 °C — the
intervention is local rather than neighborhood-scale, and that
distinction matters when communicating the result.

The whole pipeline — data acquisition, raster construction, three
SOLWEIG runs, plausibility checks, headline statistics, figures —
lives in a single [marimo](https://marimo.io) notebook at
`notebooks/analysis.py`.

![SOLWEIG inputs and outputs](notebooks/assets/methods_solweig.png)

## What you get

- **A static rendered preview** at `docs/index.html` — also hosted via
  GitHub Pages — for viewers who only want to read the analysis.
- **An interactive marimo notebook** for editing or re-running locally.
  The reactive graph re-runs only what changed; long cells (PDAL pull,
  SOLWEIG runs) detect cached output and skip.
- **A static MapLibre inspector** that overlays peak-hour Tmrt and
  ΔUTCI on an OpenStreetMap basemap. The notebook builds it into a
  self-contained `web/` directory next to the SOLWEIG outputs;
  serving it locally is one `python -m http.server` away.

## Repository layout

```
radiant-temperature/
├── README.md                       — this file
├── environment.yml                 — conda env (pdal, gdal, pytorch, marimo, …)
├── notebooks/
│   ├── analysis.py                 — the analysis (single marimo notebook)
│   ├── __marimo__/session/         — committed snapshot for static preview
│   └── assets/                     — diagrams referenced from the notebook
├── src/                            — reusable code the notebook imports
│   ├── aoi.py                      — AOI profile registry + dataclass
│   ├── geo.py                      — PROJ / GDAL env setup
│   ├── met.py                      — HRRR fetch + UMEP own-met writer
│   ├── buildings.py                — LiDAR DSM, DEM, MULC, Overture patch
│   ├── scenarios.py                — canopy-disk burn for the two scenarios
│   ├── solweig_runner.py           — solweig-gpu wrapper, idempotent
│   ├── evaluate.py                 — plausibility checks + headline stats
│   ├── figures.py                  — every figure referenced from the notebook
│   ├── compare_obs.py              — HRRR vs KRDU vs Open-Meteo cross-check
│   ├── inspector.py                — slim MapLibre bundle builder
│   └── inspector_index.html        — static template for the inspector
├── docs/index.html                 — static notebook export, served by GitHub Pages
├── figures/durham_hayti/slides/    — production figures (committed)
└── inputs/, outputs/               — raw + derived data (gitignored)
```

`archive/` holds historical material from the 5-day sprint that led to
this notebook (old script-based pipeline, slide deck, conference-prep
notes). It is gitignored.

## Setup

The environment bundles a few system-level binaries (PDAL, GDAL) so a
conda env is the path of least resistance.

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
git clone <this-repo> radiant-temperature
cd radiant-temperature
conda env create -f environment.yml -p ./env
conda activate ./env
```

The env installs to `./env` (~3 GB, gitignored). Activate from the
repo root every session: `conda activate ./env`.

Verify:

```bash
python -c "import marimo, solweig_gpu, rasterio, geopandas, pdal; print('ok')"
```

## Running the notebook

```bash
marimo edit notebooks/analysis.py
```

Marimo opens at `http://localhost:2718`. Pick an AOI profile from the
dropdown at the top:

| profile | size | wall time on CPU |
|---|---|---|
| `hayti_demo` | 600 m × 600 m | ~45 minutes end-to-end on a fresh AOI |
| `durham_hayti` | 2 km × 2 km | a few hours on CPU; ~5 minutes on an A6000 |

Subsequent re-runs are near-instant — every long-running cell (PDAL
pull, SOLWEIG runs) is idempotent and skips when its output exists.

The notebook proceeds top to bottom in 13 numbered sections:
acquire (1–5) → build SOLWEIG-ready rasters (6) → patch (7) →
SOLWEIG (8) → plausibility checks (9) → inspector (10) → headline
statistics (11) → figures (12) → limitations (13). Each `.tif` raster
gets a matplotlib preview inline; section 10 builds the static
MapLibre inspector.

To swap AOIs, change the dropdown and re-execute downstream cells.
Outputs are namespaced by AOI under `inputs/processed/{aoi}_*`,
`outputs/{aoi}/`, and `figures/{aoi}/slides/`, so the two profiles
never overwrite each other.

To register a new AOI, append an entry to `AOI_PROFILES` in
`src/aoi.py` and add its name to the dropdown options in the
notebook's `_aoi_selector` cell.

## Viewing the inspector

After section 10 of the notebook has run for an AOI, a static
MapLibre bundle exists at
`inputs/processed/{aoi}_baseline/web/`. Serve it from the repo root:

```bash
python -m http.server 8765 --directory inputs/processed/hayti_demo_baseline/web
```

Open <http://localhost:8765/> in any browser. Substitute
`durham_hayti_baseline` for the production AOI.

The bundle contains a single static `index.html` plus a few PNG and
GeoJSON assets. Nothing depends on Python at view time, so the
directory can also be uploaded as-is to any static host (Netlify, S3,
GitHub Pages) to share the inspector.

## Publishing

### Static HTML preview

```bash
marimo export html notebooks/analysis.py -o docs/index.html
```

Push to GitHub, then enable GitHub Pages on the repo with source set
to `<branch>/docs`. The HTML bakes every figure in as base64 — fully
self-contained, ~10 MB.

### molab GitHub preview

Replace `github.com` with `molab.marimo.io/github` in the URL of
`notebooks/analysis.py` to share a viewer-friendly notebook view that
anyone can fork. The committed session snapshot under
`notebooks/__marimo__/session/` supplies the rendered outputs.

To refresh either after editing the notebook:

```bash
marimo export html notebooks/analysis.py -o docs/index.html
marimo export session notebooks/analysis.py
git commit -am "edit: <describe change>"
git push
```

## Data sources

| source | role | notes |
|---|---|---|
| NC Phase 3 LiDAR (2015) via NOAA dataset 6209 | First-return DSM, ground DEM | Native US Survey Feet — converted to meters in the PDAL pipeline. |
| Overture Foundation buildings | Footprint and height for the DSM patch | About two-thirds of polygons carry a measured height. |
| EnviroAtlas Durham 1 m MULC (2010) | Land cover | EPSG:26917 → EPSG:32617, reclassified to UMEP codes. |
| Durham Open Data — Trees & Planting Sites | Locations of planned plantings | Filtered to `present == "Planting Site"`. |
| NOAA HRRR analysis via `dynamical-catalog` | Hourly meteorological forcing | Anonymous S3, no API key. |
| Iowa Mesonet KRDU ASOS | Validation observations | Used to pick the simulation date and to cross-check forcing. |

## Citations

- Bröde, P., Fiala, D., Błażejczyk, K., Holmér, I., Jendritzky, G.,
  Kampmann, B., Tinz, B., Havenith, G. (2012). Deriving the
  operational procedure for the Universal Thermal Climate Index
  (UTCI). *International Journal of Biometeorology* 56, 481–494.
- Kamath, H. G., Sudharsan, N., Singh, M., Wallenberg, N., Lindberg,
  F., Niyogi, D. (2026). SOLWEIG-GPU: GPU-Accelerated Thermal Comfort
  Modeling Framework for Urban Digital Twins. *Journal of Open Source
  Software* 11(118), 9535.
- Lindberg, F., Holmer, B., Thorsson, S. (2008). SOLWEIG 1.0 —
  Modelling spatial variations of 3D radiant fluxes and mean radiant
  temperature in complex urban settings. *International Journal of
  Biometeorology* 52, 697–713.
- Lindberg, F., Grimmond, C. S. B. (2011). The influence of vegetation
  and building morphology on shadow patterns and mean radiant
  temperatures in urban areas. *Theoretical and Applied Climatology*
  105, 311–323.

## Acknowledgements

Data products from Durham Urban Forestry, the United States
Environmental Protection Agency (EnviroAtlas), NC OneMap, the
National Oceanic and Atmospheric Administration, and the Overture
Foundation made this analysis possible.
