# CLAUDE.md — Durham SOLWEIG Project

You are Claude Code working in this repo (`radiant-temperature`). This file is the authoritative brief for the project — it was adapted from the original context document the user brought in, and it fully supersedes any Day-1 memory of how this repo was bootstrapped.

**To enter the project environment:** from the repo root, run `conda activate ./env`. First-time setup: `conda env create -f environment.yml -p ./env`. See `README.md` for the one-liner.

**Operational runbook:** `notes/runbook.md` — end-to-end checklist for running on the laptop, on a RunPod GPU pod, or both. Captures every machine-portability gotcha hit during the 2026-04-26 Hayti run (PROJ data dirs, GDAL Python bindings on pod's Python 3.11, RunPod SSH proxy vs exposed-TCP, tile_size sizing for vCPU count, the wall-cache symlink trick, etc.). **Read it before kicking off a fresh run.**

**Pipeline portability:** All bash wrappers use `${PYTHON:-python}` (laptop overrides with `PYTHON=./env/bin/python`; pod uses system python). `scripts/_lib.setup_geo_env()` only sets `PROJ_DATA`/`GDAL_DATA` when the local conda env actually has those dirs. `scripts/_patch_buildings.py` finds `overturemaps` via PATH. `scripts/_aoi.py` is the single source of truth for `AOI_NAME`, `SIM_DATE`, `TILE_SIZE`, `TILE_OVERLAP` (Stage 4 + Stage 6 import the same values so the wall-cache symlinks align).

---

## What this project is

Quantify the pedestrian-heat cooling impact of Durham, NC's actual 2025–2028 street tree planting program for a 1 km × 1 km tile in Hayti (a historically redlined, EPA-identified priority neighborhood). Output is a conference presentation in 5 days and a paper after.

**Scientific method:** Run SOLWEIG (Solar and LongWave Environmental Irradiance Geometry model, Lindberg et al., Univ. of Gothenburg) at 1m resolution on a 1.4×1.4 km tile (buffered by 200m for shadow edge effects; crop to center 1×1 km). Produce baseline Tmrt map. Rasterize Durham's planned tree plantings from the Durham Open Data Portal into the canopy DSM. Re-run SOLWEIG. Compute ΔTmrt. Headline: average peak-hour Tmrt reduction from the city's real planting plan.

**Deliverables by end of week:**
1. Baseline Tmrt GeoTIFFs (hourly, 6am–9pm, for a chosen hot day)
2. Scenario Tmrt GeoTIFFs (same, with Durham's planned plantings added)
3. Three figures: baseline/scenario/diff 3-panel; ΔTmrt histogram near planted sites; diurnal time series
4. One headline statistic
5. ~10-slide presentation

## Key technical facts

**SOLWEIG basics:** 2.5D model. For each pixel each timestep: sun position → shadow casting → surface temps from land cover → 6-direction (up/down/N/S/E/W) shortwave + longwave radiation → Tmrt. One-time preprocessing: sky view factor (SVF, ray-casting, expensive), wall height/aspect. Per-timestep: everything else. Tmrt is NOT valid on rooftops — mask them out downstream.

**Implementation choice:** Use **solweig-gpu** (Kamath et al., JOSS 2026, `pip install solweig-gpu`). PyTorch-based, auto-uses CUDA if present, falls back to CPU. Built-in tiling with overlap for shadow transfer. This is the best choice for a laptop workflow. Alternatives: original UMEP SOLWEIG (NumPy, requires QGIS for easy use), umep-dev/solweig (Rust+PyO3, experimental).

**Benchmarks (i7-10700, published in the JOSS paper):**
- 1000×1000 px tile: ~20 min CPU, ~47 sec GPU (A6000)
- 1500×1500 px tile: ~55 min CPU, ~105 sec GPU
- 2000×2000 px tile: ~108 min CPU, ~158 sec GPU

Our 1.4×1.4 km tile at 1m → ~1.96M pixels → expect ~50 min CPU, ~90 sec GPU per full SOLWEIG run. Memory <1 GB, 8 GB RAM sufficient.

**Compute target:** This laptop has **no NVIDIA GPU** (verified at bootstrap) — CPU only. Plan for ~50 min per run. Each full SOLWEIG call is expensive; debug on small samples first, and only fire a full tile run when you're confident the inputs are right.

## Required inputs (five co-registered rasters + met forcing)

All must be at **EPSG:32617 (UTM Zone 17N), 1m resolution, identical extent** — about 1400×1400 px.

| Input | Source | Notes |
|---|---|---|
| DEM (bare earth, m a.s.l.) | NC Spatial Data Downloads (sdd.nc.gov) — pre-built 2015 Phase 3 bare-earth | Use as-is, don't reprocess |
| DSM (ground + buildings, m a.s.l.) | NC Phase 3 LiDAR classified LAZ from USGS 3DEP on AWS or NOAA Digital Coast. Build via PDAL first-return rasterize | Native units are **US Survey Feet** — convert carefully |
| CDSM (canopy heights above ground, m) | `DSM − DEM`, masked to tree pixels | Zero elsewhere |
| Land cover (UMEP codes) | EnviroAtlas Durham 1m MULC (EPA). Reclassify to UMEP codes: 1=paved, 2=buildings, 5=grass, 6=bare soil, 7=water | 2010 NAIP-based, accuracy ~83%. Weakest link, acknowledge. |
| Met forcing | ERA5 hourly from Copernicus CDS API for chosen day (2m T, 2m dewpoint, surface pressure, downwelling shortwave, 10m wind). Fallback: Raleigh-Durham TMY EPW from PVGIS | ERA5 is UTC; Durham is EST/EDT. Get the offset right. |

**Scenario input (the key reframing):** Download "Trees & Planting Sites" layer from Durham Open Data Portal (live-durhamnc.opendata.arcgis.com). It contains existing street trees and future planned plantings. Filter to future/planned only. These points are the intervention.

**Optional:** Microsoft Global ML Building Footprints (has heights from 2020–2024 imagery) if you see obvious post-2015 construction in your tile. Hayti is mostly stable, probably skip.

**Visual QA layer:** NC Orthoimagery 2021 (6-inch, 4-band RGB-IR), WMS/WCS from NC OneMap. Used to eyeball classifications.

**Validation anchor:** KRDU (Raleigh-Durham airport) ASOS hourly observations for the simulated day, from Iowa Mesonet. Save for paper; not needed for presentation.

## Data recency situation (important context)

- NC LiDAR: **2015** (NC Phase 3, QL2). 11 years old. Next refresh: NC Orthoimagery 2025 contract includes Durham but not released yet.
- EnviroAtlas MULC: **2010**. No LiDAR used. Will be obsoleted by Durham's 2026 canopy assessment (in progress, not released).
- Microsoft building footprints: 2020–2024 imagery. Newest urban geometry available.
- Durham Trees & Planting Sites: live-updated, current.

This is why we frame the project as **marginal effect of planned plantings against a fixed 2015 baseline**, not "current state of Durham." The 2015 data limitation doesn't undermine the finding under this framing.

## Pipeline spec

### 1. Environment setup — already done at bootstrap

The env lives at `./env/`, created from `environment.yml` (python 3.10, gdal, pytorch CPU, pdal, python-pdal, rasterio, geopandas, cdsapi, matplotlib, timezonefinder, sip, jupyter, + `solweig-gpu` via pip). Activate: `conda activate ./env`.

Accounts needed: Copernicus CDS (API key to `~/.cdsapirc`); NC Spatial Data Downloads (email verify); QGIS already installed on this machine for inspection.

### 2. Validate pipeline on sample data BEFORE touching Durham data

Download SOLWEIG-GPU sample data from Zenodo, run `thermal_comfort()` end-to-end, open output Tmrt in QGIS. This catches environment issues on day 1 rather than on the scenario run. Do this after `scripts/01_env_validate.py` passes.

### 3. Acquire Durham data (`scripts/02_download_data.py`)

Fire the ERA5 request first — CDS queues can be slow. Then NC DEM, NC LAZ, EnviroAtlas MULC, Durham planting sites GeoJSON, NC 2021 orthoimagery (as WMS, don't download), KRDU obs.

### 4. Decision gate before processing

Open the Trees & Planting Sites layer over 2021 orthoimagery in QGIS. Confirm the Hayti candidate tile contains **≥30 planned planting sites**. Shift tile within Hayti corridor until it does. If no trees → no scenario → no story. Lock tile boundaries only after this check.

### 5. Raster prep (`scripts/03_build_rasters.py`)

```bash
# Build DSM from LAZ first returns
pdal pipeline dsm_pipeline.json

# Reproject all rasters to same grid
gdalwarp -t_srs EPSG:32617 -tr 1 1 -te XMIN YMIN XMAX YMAX \
  -r bilinear -t_srs '+proj=utm +zone=17 +datum=WGS84 +units=m' \
  input.tif output.tif

# Build CDSM
gdal_calc.py -A dsm.tif -B dem.tif --calc="A-B" --outfile=cdsm_raw.tif
# Mask to tree pixels from land cover, zero elsewhere
```

**CRITICAL: NC Phase 3 LiDAR is in US Survey Feet.** If the reprojection doesn't convert units, building heights come out 3× too tall and Tmrt will be garbage. Check PDAL pipeline and gdalwarp handle this explicitly.

Reclassify EnviroAtlas MULC to UMEP codes:
- 1 = paved (roads, parking, sidewalks)
- 2 = buildings
- 5 = grass
- 6 = bare soil
- 7 = water

### 6. Baseline SOLWEIG run (`scripts/04_run_baseline.py`)

**Real `thermal_comfort()` API** — takes a directory + filename convention, not individual paths:

```python
from solweig_gpu import thermal_comfort

# base_path must contain Building_DSM.tif, DEM.tif, Trees.tif, Landcover.tif
# and is ALSO where outputs land (under base_path/output_folder/).
thermal_comfort(
    base_path='inputs/processed/durham_baseline',
    selected_date_str='2024-07-23',          # simulation date (YYYY-MM-DD)
    building_dsm_filename='Building_DSM.tif',
    dem_filename='DEM.tif',
    trees_filename='Trees.tif',               # this is the CDSM — canopy heights above ground
    landcover_filename='Landcover.tif',       # UMEP codes; see below
    tile_size=1400,
    overlap=100,
    use_own_met=True,
    own_met_file='inputs/processed/durham_baseline/ownmet_2024-07-23.txt',
    save_tmrt=True,
)
```

Key API facts to remember:
- **No `output_dir` parameter.** Outputs are written to `base_path/output_folder/`; preprocessed intermediates to `base_path/processed_inputs/`. To keep baseline and scenario runs apart, give them **separate `base_path` directories**.
- **No `utc_offset` parameter.** When using ERA5/WRF mode (`use_own_met=False`), `start_time`/`end_time` are in **UTC** and conversion to local is internal. In own-met mode, the met file's time columns define the clock.
- **`Trees.tif`** is the package's name for the CDSM (canopy heights above ground, m, zero where no tree). Our Day-2 raster build pipeline should emit a file with this exact name.
- **`Building_DSM.tif`** is buildings+terrain (i.e., the DSM — NOT terrain-only).
- **Landcover is optional** (`landcover_filename=None` is allowed) but we want it set — SOLWEIG uses it for surface temperature and albedo. Bundled class definitions: `env/lib/python3.10/site-packages/solweig_gpu/landcoverclasses_2016a.txt`.

**Own-met file format (UMEP 23-column, space-delimited, header row required):**

```
iy  id  it imin   Q*      QH      QE      Qs      Qf    Wind    RH     Td     press   rain    Kdn    snow    ldown   fcld    wuh     xsmd    lai_hr  Kdiff   Kdir    Wd
```

Columns: `iy`=year, `id`=day-of-year, `it`=hour, `imin`=minute. Use `-999.00` for unknown values. Minimum fields we need to populate from ERA5: `Wind` (10m, m/s), `RH` (%), `Td` (°C, 2m dewpoint-derived), `press` (kPa), `rain` (mm/h), `Kdn` (downwelling shortwave, W/m²), `ldown` (downwelling longwave, W/m²). The rest can stay `-999.00`.

**Alternative ERA5 mode** (skips the conversion step):

```python
thermal_comfort(
    base_path='inputs/processed/durham_baseline',
    selected_date_str='2024-07-23',
    use_own_met=False,
    data_source_type='ERA5',
    data_folder='inputs/raw/era5/',
    start_time='2024-07-23 06:00:00',   # UTC
    end_time='2024-07-23 23:00:00',     # UTC
    # ... rasters as above
    save_tmrt=True,
)
```

Either works. Own-met gives more control and is easier to debug; ERA5 mode skips writing the UMEP-format text file.

Inspect: shade should be cool, parking lots should be hot, streets intermediate. Crop results to center 1×1 km after the run.

**Red flags:** 80°C everywhere, uniform patterns, negative Tmrt. Usual culprits: UTC offset wrong, met file misparsed, CDSM sign-flipped, feet↔meters.

### 7. Scenario run: rasterize Durham's planned plantings (`scripts/05_build_scenario.py` + `06_run_scenario.py`)

```python
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

planting_sites = gpd.read_file('inputs/raw/trees_planting_sites.geojson')
planting_sites = planting_sites[planting_sites['status'] == 'planting site']  # adjust field name
planting_sites = planting_sites.to_crs('EPSG:32617')
planting_sites = planting_sites.clip(tile_bounds)

# For each point, burn a 3x3 pixel disk at ~8-10m canopy height into CDSM
# (mature shade tree approximation)
```

Update land cover at those pixels to grass class (SOLWEIG combines CDSM + land cover for shade handling). Write the modified rasters into a **separate `base_path` directory** (e.g., `inputs/processed/durham_scenario/`) using the same canonical filenames (`Building_DSM.tif`, `DEM.tif`, `Trees.tif`, `Landcover.tif`). Re-run `thermal_comfort(base_path='inputs/processed/durham_scenario', ...)` with all other arguments identical to the baseline call — this keeps baseline and scenario outputs cleanly separated under each base_path's `output_folder/`.

### 8. Analysis and figures (`scripts/07_make_figures.py`)

Compute ΔTmrt = scenario − baseline per timestep and for daily peak-hour mean.

**Fig 1 (the money shot):** 3-panel map — baseline at peak, scenario at peak, ΔTmrt diff. Overlay planting site dots on diff panel.

**Fig 2:** Histogram of ΔTmrt for pixels within 30m of a planned tree.

**Fig 3:** Diurnal time series, mean Tmrt across tile, baseline vs scenario.

**Headline stat:** "Durham's planned 2025–2028 plantings within this Hayti tile deliver an average peak-hour pedestrian Tmrt reduction of X°C, with cooling exceeding Y°C in the immediate vicinity of planted sites."

## Time budget constraints

17 productive hours across 5 days: 3 weekdays × 2.5 hrs + 2 weekend days × 5 hrs. Day 5 is for slides.

**Hard cuts (do not attempt this week):**
- Interactive brush UI
- Multiple planting scenarios
- Multiple tiles
- Multiple days / full summer
- UTCI or PET (Tmrt alone is the story)
- Validation against KRDU (save for paper)
- Reclassifying land cover from 2021 orthoimagery
- Neural surrogate

**Fallbacks if behind:**
- Skip Microsoft footprint patch (Hayti is mostly stable anyway)
- Skip Fig 3 time series
- If scenario is not ready by Day 4 hour 3, fall back to uniform +10% random placement — story weakens from "Durham's actual plan" to "Durham at +10% canopy" but still usable
- Switch to Google Colab GPU runtime if laptop can't handle it (solweig-gpu supports it out of the box)

## Minimum viable deliverable

If everything collapses:
- One baseline Tmrt map of Hayti at peak hour
- One ΔTmrt diff map from planned plantings
- One number: mean peak-hour Tmrt reduction
- One slide defining Tmrt and why it matters
- One slide on Durham's equity-targeted planting program

## Known gotchas

1. **NC LiDAR is in US Survey Feet.** Reprojection must convert. This is the #1 failure mode with NC data.
2. **ERA5 is UTC; Durham is EST/EDT.** Get the offset right or shadows point the wrong way.
3. **Shadow edge effects.** Buildings outside your tile cast shadows into it. Use 200m buffer around the analysis area; crop at the end.
4. **Tmrt not valid on roofs.** Mask out building pixels before computing any pixel statistics.
5. **CRS/grid alignment.** All 5 rasters must share projection, extent, pixel size exactly. Use `gdalwarp -te -tr -t_srs` explicitly. Don't hand-align in QGIS.
6. **Trunk zone DSM (TDSM) optional but matters.** UMEP's TreeGenerator synthesizes one from CDSM if you omit it. For Hayti's dense canopies, pedestrian-level Tmrt is noticeably affected.

## References

- SOLWEIG-GPU: Kamath et al., JOSS 2026. PyPI: `solweig-gpu`. Readthedocs available.
- Original SOLWEIG: Lindberg, Holmer, Thorsson 2008; Lindberg & Grimmond 2011 (shadow algorithm).
- UMEP QGIS plugin: https://umep-docs.readthedocs.io
- Durham Open Data: live-durhamnc.opendata.arcgis.com
- Durham Urban Forestry: durhamnc.gov/799/Urban-Forestry (2018 EPA priority neighborhood study, 8,500 trees by 2028, 85% to EPA-identified priority areas)
- NC Spatial Data Downloads: sdd.nc.gov
- NC OneMap: nconemap.gov
- EnviroAtlas Durham MULC: via epa.gov/enviroatlas
- USGS 3DEP on AWS: registry.opendata.aws/usgs-lidar
- Iowa Mesonet KRDU ASOS: mesonet.agron.iastate.edu

## Repo layout

```
radiant-temperature/
├── CLAUDE.md               # this file
├── README.md
├── environment.yml         # conda env spec (source of truth for ./env)
├── env/                    # gitignored — project-local conda env
├── scripts/
│   ├── 01_env_validate.py
│   ├── 02_download_data.py
│   ├── 03_build_rasters.py
│   ├── 04_run_baseline.py
│   ├── 05_build_scenario.py
│   ├── 06_run_scenario.py
│   └── 07_make_figures.py
├── inputs/
│   ├── raw/                # downloads as-acquired (gitignored)
│   └── processed/          # 5 aligned rasters + met CSV (gitignored)
├── outputs/
│   ├── baseline/           # gitignored
│   └── scenario/           # gitignored
├── figures/                # PNGs gitignored; figure-generating code tracked
└── notes/                  # free-form notes, tracked
```
