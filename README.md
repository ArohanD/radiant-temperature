# radiant-temperature

A reproducible analysis of the pedestrian heat impact of Durham's 2025–2028
street tree planting program in the Hayti neighborhood. The study quantifies
the change in mean radiant temperature (Tmrt) and the Universal Thermal
Climate Index (UTCI) at 1 m resolution on a heatwave day, comparing a
baseline run against two canopy growth scenarios.

The analysis uses the SOLWEIG model (Lindberg et al., 2008) accelerated on
GPU via `solweig-gpu` (Kamath et al., 2026). Inputs are derived from public
data: NC Phase 3 LiDAR for terrain and structures, Overture Foundation
buildings for footprint correction, EnviroAtlas land cover, NOAA HRRR
analysis for meteorological forcing, and the Durham Open Data Portal for the
locations of planned plantings.

## Headline finding

For the 245 planned planting sites within a 2 km × 2 km tile centered on
Hayti, peak-hour ΔUTCI at the planted pixels falls between −4.7 °C (year 10
canopy, 5 m height) and −5.8 °C (mature canopy, 12 m height) on June 23, 2025
(99 °F at KRDU, clear skies). About 58 percent of planted pixels cross at
least one WHO heat-stress category, typically from extreme to very strong
heat stress. The worst-cooled single pixel falls by 10 °C. Tile-wide mean
ΔUTCI is −0.01 °C, indicating that the intervention is local rather than
neighborhood scale.

![SOLWEIG inputs and outputs](notebooks/assets/methods_solweig.png)

## Repository tour

The analysis lives in a single marimo notebook, `notebooks/analysis.py`. It
is a regular Python file; cells are idempotent so an expensive step that
has already produced its output is skipped on re-run. End-to-end on the
demo AOI takes roughly 45 minutes on CPU; subsequent re-runs return in
seconds.

The notebook covers the full pipeline in 17 numbered sections: data
acquisition (sections 1–6), SOLWEIG-ready raster construction with the
Overture-gated DSM patch (sections 7–10), the three SOLWEIG runs and the
sanity report (sections 11–13), the headline statistics (section 14), the
conference-deck figures (section 15), and the limitations and citations
(sections 16–17). A static preview is published via molab — see "View
on molab" below. Inspector iframes are interactive only in the live
notebook; in the static preview they appear empty because they point at a
localhost server that exists only while the notebook is being executed.

Reusable code lives in `src/`:

| module | summary |
|---|---|
| `src/aoi.py` | AOI primitives (centre, size, simulation date, tile bounding boxes). Single source of truth for relocation. |
| `src/geo.py` | PROJ and GDAL environment setup. |
| `src/met.py` | HRRR analysis fetch and UMEP own-met file writer. |
| `src/buildings.py` | LiDAR DSM and DEM via PDAL, MULC reproject, Overture patch. |
| `src/scenarios.py` | Canopy disk burn-in for the two scenarios. |
| `src/solweig_runner.py` | Wrapper around `solweig_gpu.thermal_comfort` with idempotency and wall-cache reuse. |
| `src/evaluate.py` | Physical sanity checks and headline statistics. |
| `src/figures.py` | Every figure used in the conference deck. |
| `src/inspector.py` | Self-contained MapLibre inspector bundle, daemon HTTP server, and headless screenshot capture. |
| `src/compare_obs.py` | Cross-checks of HRRR forcing against KRDU observations and Open-Meteo reanalysis. |

The folder `archive/` holds prior project artefacts (the 5-day sprint scripts,
slide deck, presentation notes, decision logs, and historical pod runs) and
is gitignored.

## Getting started

### 1. Prerequisites

- Linux or macOS (Windows requires WSL2).
- A `conda` or `mamba` installation. Miniforge is recommended.
- Roughly 10 GB of free disk for the conda environment and cached inputs.
- `git` on PATH. The conda environment provides `gdal-bin` and `pdal`.
- Optional: an NVIDIA GPU with CUDA. Without one, SOLWEIG falls back to CPU.
- Optional: `google-chrome` on PATH if the headless inspector-screenshot
  cell is to be exercised.

### 2. Create the environment

```bash
git clone <this-repo> radiant-temperature
cd radiant-temperature
conda env create -f environment.yml -p ./env
conda activate ./env
```

The environment installs `marimo` along with `solweig-gpu`, `rasterio`,
`geopandas`, `pdal`, `pytorch`, `dynamical-catalog`, and `overturemaps`.

Verify the install:

```bash
python -c "import marimo, solweig_gpu, rasterio, geopandas, pdal; print('ok')"
```

### 3. Open the notebook

```bash
# Edit interactively; opens a reactive UI in the browser.
marimo edit notebooks/analysis.py

# Run headless and inspect outputs on disk.
marimo run notebooks/analysis.py
```

Both modes print a local URL (default `http://localhost:2718`). The
notebook defaults to the `hayti_demo` AOI; pick `durham_hayti` from the
dropdown at the top to switch to the production tile.

### 4. Quick smoke test

```bash
python -c "from src.aoi import get_aoi; c = get_aoi('hayti_demo'); print(c.name, c.size_km, c.sim_date)"
# hayti_demo 0.6 2025-06-23
```

### 5. AOI profiles

Two AOI profiles ship with the project, registered in `src/aoi.py`:

| profile | size | purpose |
|---|---|---|
| `hayti_demo` | 600 m × 600 m | Smoke-test box centred on the densest cluster of planted sites in Hayti (163 of the 245 sites). The full pipeline runs end-to-end on this AOI in roughly 45 minutes on CPU and is the default selected at the top of the notebook. |
| `durham_hayti` | 2 km × 2 km | Production AOI used for the headline figures and the conference deck. Full SOLWEIG runs take roughly 30–40 minutes per scenario on CPU. |

The **AOI profile** dropdown sits immediately below the intro section.
Pick `hayti_demo` to verify the pipeline end-to-end without burning an
hour on PDAL and SOLWEIG; flip to `durham_hayti` for the production run.
Outputs are namespaced by AOI under `inputs/processed/{aoi}_*`,
`outputs/{aoi}/`, and `figures/{aoi}/slides/`, so the two profiles never
overwrite each other and you can switch back and forth at any time.

To register a new AOI, append an entry to `AOI_PROFILES` in `src/aoi.py`
following the same field layout, then add its name to the dropdown options
in the notebook's `_aoi_selector` cell.

### 6. View on molab

The notebook has been snapshotted into `notebooks/__marimo__/session/`
so its outputs render in molab's static GitHub preview. Once the repo is
pushed to GitHub, replace `github.com` in the URL with
`molab.marimo.io/github` to share a viewer-friendly link to the rendered
analysis.

## Data sources

| source | role | notes |
|---|---|---|
| NC Phase 3 LiDAR (2015) via NOAA dataset 6209 | First-return DSM, ground DEM | Native EPSG:6346, metres. Pulled by PDAL via Entwine point tile. |
| Overture Foundation buildings | Footprint and height for the DSM patch | GeoJSON at 4326. |
| EnviroAtlas Durham 1 m MULC (2010) | Land cover, reclassified to UMEP codes | EPSG:26917, reprojected to 32617. |
| Durham Open Data — Trees & Planting Sites | Locations of planned plantings | Filtered to `present == "Planting Site"`. |
| NOAA HRRR analysis via `dynamical-catalog` | Hourly meteorological forcing | Anonymous S3, no API key required. |
| Iowa Mesonet KRDU ASOS | Validation observations | Used to confirm the simulation date selection and to cross-check forcing. |

## Folder layout after a complete run

```
radiant-temperature/
├── README.md
├── environment.yml
├── notebooks/
│   ├── analysis.py
│   ├── __marimo__/session/analysis.py.json   (committed; molab preview)
│   └── assets/
├── src/
├── inputs/
│   ├── raw/durham/
│   └── processed/
│       ├── {prefix}_baseline/
│       ├── {prefix}_scenario_year10/
│       └── {prefix}_scenario_mature/
├── outputs/
│   └── {prefix}/
│       ├── headline.txt
│       ├── figures/
│       └── diffs/
├── figures/
└── archive/   (gitignored)
```

## Citations

- Lindberg, F., Holmer, B., Thorsson, S. (2008). SOLWEIG 1.0 — Modelling
  spatial variations of 3D radiant fluxes and mean radiant temperature in
  complex urban settings. *International Journal of Biometeorology* 52,
  697–713.
- Lindberg, F., Grimmond, C. S. B. (2011). The influence of vegetation and
  building morphology on shadow patterns and mean radiant temperatures in
  urban areas. *Theoretical and Applied Climatology* 105, 311–323.
- Bröde, P., Fiala, D., Błażejczyk, K., Holmér, I., Jendritzky, G., Kampmann,
  B., Tinz, B., Havenith, G. (2012). Deriving the operational procedure for
  the Universal Thermal Climate Index (UTCI). *International Journal of
  Biometeorology* 56, 481–494.
- Kamath, H. G., Sudharsan, N., Singh, M., Wallenberg, N., Lindberg, F.,
  Niyogi, D. (2026). SOLWEIG-GPU: GPU-Accelerated Thermal Comfort Modeling
  Framework for Urban Digital Twins. *Journal of Open Source Software*
  11(118), 9535.
- Lindberg, F., Grimmond, C. S. B., Gabey, A., Huang, B., Kent, C. W., Sun,
  T., et al. (2018). Urban Multi-scale Environmental Predictor (UMEP): An
  integrated tool for city-based climate services. *Environmental Modelling
  and Software* 99, 70–87.

## Acknowledgements

Data products from Durham Urban Forestry, the United States Environmental
Protection Agency (EnviroAtlas), NC OneMap, the National Oceanic and
Atmospheric Administration, and the Overture Foundation made this analysis
possible.
