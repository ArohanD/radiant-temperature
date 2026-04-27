# Runbook — kicking off a SOLWEIG run

Concise checklist for going from "I want to run the pipeline on AOI X" to
"figures and headline are on disk." Captures every gotcha hit during the
2026-04-26 Hayti run.

The pipeline is split between two machines because of how the costs lie:

- **Laptop**: data acquisition + raster prep (Stages 1-3.5). Has the local
  cache of citywide MULC and Durham planting points; downloads Durham-area
  LiDAR/DEM/Overture once, reuses across AOIs in NC.
- **Pod (RunPod RTX A5000)**: the SOLWEIG GPU runs (Stages 4-7). 25-30 min
  per scenario instead of ~90 min on the laptop. ~$0.30/hr.

Either machine can run any stage — the scripts are machine-agnostic — but
this is the cheap, fast path.

---

## What the pipeline needs as input

The **only thing you edit by hand** is `scripts/_aoi.py`. Everything else is
auto-acquired or derived:

| What | Source | Where it lands | Stage that fetches it |
|---|---|---|---|
| AOI definition (lat, lon, size, sim date) | you | `scripts/_aoi.py` | n/a — manual |
| EnviroAtlas 1m MULC | epa.gov | `inputs/raw/durham/enviroatlas_mulc/durham_mulc.tif` | 02 |
| Durham planting sites | live-durhamnc ArcGIS | `inputs/raw/durham/trees_planting/durham_trees.geojson` | 02 |
| NC LiDAR (.laz, classified) | sdd.nc.gov | `inputs/raw/durham/nc_laz/*.laz` | 03 |
| NC bare-earth DEM (US Survey ft) | sdd.nc.gov | `inputs/raw/durham/nc_dem/*.tif` | 03 |
| HRRR met forcing (one date) | dynamical.org S3 | embedded in `inputs/processed/{AOI}_baseline/ownmet_*.txt` | 03 |
| Overture building footprints | overturemaps API | `inputs/raw/durham/overture/buildings_{AOI}.geojson` | 3.5 |

For AOIs **outside Durham** but in NC: edit just `_aoi.py`. The data sources
above (NC LiDAR + DEM, HRRR, Overture) cover the entire state. EnviroAtlas
MULC and Durham planting points are Durham-specific; outside Durham you need
a different MULC source (EnviroAtlas covers ~30 US cities) and a different
planting-points layer.

---

## Where outputs go

By default, everything namespaces by `AOI_NAME` from `_aoi.py`:

- `inputs/processed/{AOI}_baseline/` — baseline rasters + SOLWEIG outputs
- `inputs/processed/{AOI}_scenario_year10/`, `_scenario_mature/` — scenario
  rasters + outputs
- `figures/{AOI}/` — fig1/fig2/fig3 PNGs + `headline.txt`
- `outputs/{AOI}_scenario_diffs/` — `dtmrt_peak_*.tif`
- `outputs/pod_runs/{AOI}_<timestamp>/` — pulled pod outputs (isolated, never
  overwritten by laptop runs)

To **iterate without clobbering today's outputs**, the simplest move is to
rename `AOI_NAME` between runs (e.g., `durham_hayti` → `durham_hayti_v2`).
A `RUN_TAG` env var hook is also defined in `_aoi.py` but not yet propagated
through the scripts — pending future work if you want to share inputs across
runs but split outputs.

---

## Sizing knob: `TILE_SIZE`

Wall-height + aspect preprocessing inside `solweig-gpu` is **single-threaded
per tile** but parallelizes across tiles. Pick `TILE_SIZE` so the tile count
matches host CPU count:

| Host | vCPUs | Raster dim (2 km AOI) | TILE_SIZE | # tiles |
|---|---|---|---|---|
| laptop (i7) | 16 | 2401 | 1000 | 9 |
| RunPod A5000 | ~8 | 2401 | 1000 | 9 |
| RunPod RTX 4090 / H100 (more vCPU) | 16+ | 2401 | 800 | 9 |

Defined once in `scripts/_aoi.py`. Baseline (Stage 4) and scenarios (Stage 6)
**must share TILE_SIZE** — Stage 5's wall-cache symlinks key on tile names,
and a mismatch sends each scenario back through ~20 min of CPU prep.

Verify host vCPU:
- Laptop: `nproc`
- Container (the host's `nproc` lies — read cgroups): `cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us`, divide by 100000.

---

## End-to-end recipe

### Phase 0 — pick / configure the AOI

Edit `scripts/_aoi.py`:

```python
AOI_NAME = "durham_hayti"            # rename for new runs
AOI_CENTER_LAT = 35.985
AOI_CENTER_LON = -78.900
AOI_SIZE_KM = 2.0
SIM_DATE = "2025-06-23"               # hot day, KRDU >= 35°C, clear sky
UTC_OFFSET = -4                       # EDT in summer
```

Verify: `./env/bin/python scripts/_aoi.py`. Should print bbox + simulated date.

### Phase 1 — laptop: data + rasters

```fish
conda activate ./env
PYTHON=./env/bin/python bash scripts/run_full_pipeline.sh
```

This chains Stages 3 → 7. If you want to **stop after Stage 3.5** (so the
heavy SOLWEIG runs go on the pod), just comment out the Stage 4-7 lines in
`scripts/run_full_pipeline.sh` for this run, or run them individually:

```fish
./env/bin/python scripts/03_build_rasters.py
./env/bin/python scripts/_patch_buildings.py
```

After Stage 3.5, `inputs/processed/{AOI}_baseline/` has all 5 SOLWEIG-ready
inputs (`Building_DSM.tif`, `DEM.tif`, `Trees.tif`, `Landcover.tif`,
`ownmet_{SIM_DATE}.txt`).

### Phase 2 — provision the pod

In RunPod's UI:

1. **Deploy** an RTX A5000 with the **Runpod Pytorch 2.4.0** template
   (Python 3.11 + CUDA 12.4). 1 GPU, 30 GB container disk, 20 GB volume disk,
   on-demand pricing, **SSH terminal access ON**.
2. **Settings → SSH Public Keys**: paste your laptop's public key (or a fresh
   throwaway key just for this pod, if you don't want to reuse a personal
   key — `ssh-keygen -t ed25519 -f ~/.ssh/runpod_<aoi> -N ""` then
   `cat ~/.ssh/runpod_<aoi>.pub`).
3. After deploy, RunPod Connect panel shows **"SSH over exposed TCP"** — note
   the IP and port. (NOT the `ssh.runpod.io` proxy line — that doesn't
   support rsync/scp.)
4. The proxy uses RunPod's account-registered key list, but the exposed-TCP
   sshd reads `/root/.ssh/authorized_keys` directly. SSH in via the proxy
   command and append your public key:
   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo 'ssh-ed25519 AAAA...' >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

### Phase 3 — ship inputs to the pod

Edit `scripts/_ship_to_pod.sh` lines 14-16 if needed (the `POD_HOST` /
`POD_PORT` change every Stop/Start), or pass via env:

```fish
POD_HOST=69.30.85.195 POD_PORT=22101 SSH_KEY=~/.ssh/runpod_<aoi> bash scripts/_ship_to_pod.sh
```

Ships ~70 MB. The script uses `--relative` so paths preserve their hierarchy
under `/workspace/radiant-temperature/`.

### Phase 4 — pod: install deps + run the SOLWEIG stages

SSH in via the exposed-TCP command:
```fish
ssh root@69.30.85.195 -p 22101 -i ~/.ssh/runpod_<aoi>
```

On the pod:
```bash
cd /workspace/radiant-temperature
bash scripts/_pod_setup.sh        # one-shot: gdal, solweig-gpu, GDAL bindings
bash scripts/run_solweig_only.sh  # chains Stages 4 → 7
```

Expected wall time on A5000:
- Stage 4 (baseline): ~25 min (mostly CPU wall-height + ~3 min GPU SOLWEIG)
- Stage 5 (scenario build + cache symlink): ~30 sec
- Stage 6 (2 scenarios, GPU only thanks to wall-cache hit): ~10 min
- Stage 7 (figures + headline): ~1 min

**Total ~35-40 min**.

If you want to nohup it and disconnect:
```bash
nohup bash scripts/run_solweig_only.sh > /workspace/run.log 2>&1 &
disown
```

### Phase 5 — pull outputs back to laptop

On the laptop:
```fish
POD_HOST=69.30.85.195 POD_PORT=22101 SSH_KEY=~/.ssh/runpod_<aoi> bash scripts/_pull_from_pod.sh
```

Lands at `outputs/pod_runs/{AOI}_<timestamp>/` — isolated from anything the
laptop pipeline writes. Headline gets printed at the end.

### Phase 6 — inspect locally

Generate the web bundle from the laptop's existing layout:
```fish
./env/bin/python scripts/_inspect_web.py
cd inputs/processed/{AOI}_baseline/web
python -m http.server 8765
```
Browse to <http://localhost:8765>.

(For a separate inspector pointing at the pod_runs/ directory, see followups
below — not yet implemented.)

### Phase 7 — stop the pod

In RunPod UI: **Stop** (cheap pause, ~$0.006/hr storage) or **Terminate**
(zero cost, wipes `/workspace`). Stop if you might want to iterate; Terminate
if you're done.

---

## Common failure modes & fixes

| Symptom | Cause | Fix |
|---|---|---|
| `./env/bin/python: No such file or directory` on pod | Bash wrappers used to hardcode this | Already fixed: scripts use `${PYTHON:-python}` |
| `RuntimeError: PROJ: ... Cannot find proj.db` on pod | `_lib.setup_geo_env` set `PROJ_DATA` to nonexistent conda path | Already fixed: only sets when `./env/share/proj` exists |
| `ModuleNotFoundError: No module named 'osgeo._gdal'` on pod | apt's `python3-gdal` was built for system Python, not 3.11 | Already fixed in `_pod_setup.sh` (force-reinstall via pip against system libgdal) |
| `protocol version mismatch — is your shell clean?` | RunPod proxy injects a banner that breaks rsync | Use the exposed-TCP host/port, not `ssh.runpod.io` |
| `Permission denied (publickey)` on exposed-TCP | New key not in `/root/.ssh/authorized_keys` (proxy uses a different key list) | Append the public key on the pod via the working proxy connection |
| Stage 4 fails with `peak mean < 60 °C` | Old hard gate, AOI-dependent | Already fixed: demoted to WARN at 50 °C |
| Stage 7 `operands could not be broadcast (1600,1600) (2401,2401)` | Multi-tile SOLWEIG outputs read as if single-tile | Already fixed: `merged_raster()` mosaics on demand |
| Wall-height stage takes 22 min then GPU sits idle | tile_size matches single-tile, only 1 CPU core busy | Set TILE_SIZE so tile-count >= vCPU count (see sizing table) |
| Stage 6 wall-height repeats per scenario | Stage 5 wall-cache symlinks didn't seed | Verify baseline ran with same TILE_SIZE; clear `processed_inputs/` and re-run |

---

## What's intentionally NOT in this runbook

- The original AOI-pivot history and equity framing — see `notes/aoi.md`.
- Scenario design (year10 vs mature canopy) — see `notes/scenario_design.md`.
- Validation against KRDU — paper-stage, see `notes/baseline_validation.md`.
- A second web inspector instance for browsing pod_runs/ — pending; ask
  Claude to wire it up when needed.
