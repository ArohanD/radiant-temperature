# commands.md

Quick reference for running every part of this repo. All commands assume you are at the repo root (`/home/arohan/Documents/code/radiant-temperature`). For deeper context see `README.md`, `CLAUDE.md`, and `notes/runbook.md`.

---

## 1. Environment

The conda env lives at `./env/` (project-local, gitignored).

```bash
# First-time setup (~3 GB, ~10 min)
conda env create -f environment.yml -p ./env

# Every session
conda activate ./env

# Sanity check
python scripts/01_env_validate.py
```

If you'd rather not activate, every shell wrapper accepts `PYTHON=./env/bin/python` so you can drive the pipeline with a one-off interpreter.

---

## 2. Web inspector (3D MapLibre viewer)

The inspector is a self-contained MapLibre app generated per AOI. `_inspect_web.py` writes the bundle; `_serve_inspector.sh` discovers every bundle on disk and serves them behind a single landing page.

```bash
# Generate / refresh the bundle for the current AOI (reads scripts/_aoi.py)
./env/bin/python scripts/_inspect_web.py

# To inspect a pulled pod-run instead of the laptop pipeline output
INSPECT_RUN_ROOT=outputs/pod_runs/durham_hayti_<timestamp> \
  ./env/bin/python scripts/_inspect_web.py

# Serve everything on http://localhost:8765/
bash scripts/_serve_inspector.sh
# Then open: http://localhost:8765/outputs/inspector_index.html

# Override port
PORT=8767 bash scripts/_serve_inspector.sh
```

To serve a single bundle directly without the landing page:

```bash
cd inputs/processed/durham_hayti_baseline/web && python -m http.server 8765
```

Capture slide-ready screenshots of the inspector via headless Chrome:

```bash
./env/bin/python scripts/_capture_webapp.py
# Outputs: figures/durham_hayti/slides/webapp_*.png
```

---

## 3. Presentation

Source: `slides/presentation.md` (Marp). Outputs: `slides/presentation.pdf` and `slides/presentation_full.html`.

Marp is invoked through `npx`, no global install needed:

```bash
# PDF
npx @marp-team/marp-cli slides/presentation.md -o slides/presentation.pdf --allow-local-files

# Self-contained HTML (with presenter mode)
npx @marp-team/marp-cli slides/presentation.md -o slides/presentation_full.html --html --allow-local-files

# Live preview server (auto-reloads on save)
npx @marp-team/marp-cli slides/presentation.md --server
```

Slide visuals are built by `scripts/08_make_slide_visuals.py` (figures land in `figures/durham_hayti/slides/`) and `scripts/_capture_webapp.py` (web inspector screenshots).

---

## 4. Pipeline scripts (numbered = canonical, underscored = scratch/helper)

The AOI, simulation date, and tile geometry are defined in `scripts/_aoi.py` — edit there to relocate a run.

### Numbered pipeline (run in order)

| # | Script | What it does |
|---|---|---|
| 01 | `01_env_validate.py` | Smoke-test deps; prints versions, confirms `thermal_comfort` import, reports CUDA. |
| 02 | `02_download_data.py` | Fetch ERA5/HRRR met, NC LiDAR, EnviroAtlas MULC, Durham planting sites, KRDU obs. Picks `SIM_DATE`. |
| 03 | `03_build_rasters.py` | Reproject + align all rasters to 1 m EPSG:32617; emit canonical `Building_DSM.tif`, `DEM.tif`, `Trees.tif`, `Landcover.tif`, plus the UMEP own-met file. |
| 04 | `04_run_baseline.py` | Baseline SOLWEIG run for the Hayti tile. |
| 05 | `05_build_scenario.py` | Rasterize Durham's planned plantings into the canopy DSM (year-10 + mature variants). |
| 06 | `06_run_scenario.py` | Re-run SOLWEIG for each scenario. |
| 07 | `07_make_figures.py` | Three headline figures + `headline.txt` ΔTmrt stat. |
| 08 | `08_make_slide_visuals.py` | Slide-ready figures under `figures/{AOI}/slides/`. |

Run any individually:

```bash
./env/bin/python scripts/04_run_baseline.py
```

### Helper / scratch scripts (underscore prefix)

| Script | Purpose |
|---|---|
| `_aoi.py` | AOI primitives. Imported by every numbered stage — single source of truth. Not executable. |
| `_lib.py` | Shared geo / env helpers. Not executable. |
| `_sample_run.py` | Day-1 SOLWEIG trust test on the Zenodo Austin sample. |
| `_sample_run_hrrr.py` | Same sample tile, but met forcing built from HRRR — sanity-checks the HRRR pipeline before Durham. |
| `_patch_buildings.py` | Stage 3.5 — patch LiDAR DSM with Overture footprints to recover post-2015 buildings. Run between Stage 3 and 4. |
| `_evaluate_baseline.py` | Physical-plausibility checks on Stage 4 outputs (shadow direction, Tmrt by landcover class, etc.). |
| `_evaluate_scenarios.py` | Headline ΔTmrt / ΔUTCI numbers per scenario. |
| `_compare_to_observations.py` | HRRR vs KRDU ASOS, UTCI vs `apparent_temp` — input + output validation. |
| `_inspect_qgis.py` | Build a PyQGIS loader script + diff rasters for visual inspection. |
| `_inspect_web.py` | Build the MapLibre 3D inspector bundle (see §2). |
| `_capture_webapp.py` | Headless-Chrome screenshots of the inspector for slides. |
| `_serve_inspector.sh` | Local landing page serving every inspector bundle on disk. |

Typical invocation:

```bash
./env/bin/python scripts/_patch_buildings.py
./env/bin/python scripts/_evaluate_baseline.py
./env/bin/python scripts/_evaluate_scenarios.py
./env/bin/python scripts/_compare_to_observations.py
```

### Pipeline orchestration

`run_full_pipeline.sh` chains Stages 3 → 7 (plus the Overture patch and a fresh inspector regen). `run_solweig_only.sh` resumes from Stage 4 — use this when Stage 3's rasters are already built (e.g., on a pod that received them via rsync).

```bash
# Full chain — laptop
PYTHON=./env/bin/python bash scripts/run_full_pipeline.sh

# Resume from Stage 4 — laptop
PYTHON=./env/bin/python bash scripts/run_solweig_only.sh

# Background (long runs)
nohup bash scripts/run_full_pipeline.sh &
tail -f outputs/durham_hayti_pipeline.log
```

Both wrappers pick the interpreter from `${PYTHON:-python}` so the same scripts work on a RunPod pod with system Python.

### RunPod handoff

```bash
bash scripts/_ship_to_pod.sh        # rsync inputs + scripts to pod
# (then on the pod:) bash scripts/_pod_setup.sh && bash scripts/run_solweig_only.sh
bash scripts/_pull_from_pod.sh      # pull outputs into outputs/pod_runs/<AOI>_<timestamp>/
```

Edit `POD_HOST` / `POD_PORT` at the top of each script — RunPod reassigns them on every Stop/Start. See `notes/runpod_handoff.md` and `notes/runbook.md` for the end-to-end checklist.
