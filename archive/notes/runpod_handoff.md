# RunPod handoff — Hayti SOLWEIG run

Brief for a fresh Claude Code session running on a RunPod RTX A5000 pod.
Paste the **"Handoff prompt"** section at the bottom into Claude on the pod
after `claude` and `cd /workspace/radiant-temperature`.

---

## Situation

- AOI is `durham_hayti` — 2 km × 2 km, see `notes/aoi.md`. Hot day = 2025-06-23.
- A laptop run is also in progress at home (started 2026-04-26 16:45 EDT,
  ~5 hr ETA). The pod run takes priority — it should finish in ~30 min vs
  laptop's ~5 hr — but the laptop run is a free safety net so let it keep
  going unless it OOMs again.
- Stage 3 (raster build) and Stage 3.5 (Overture building patch) are
  **already done**. The Stage-4 inputs are ready in
  `inputs/processed/durham_hayti_baseline/` on the laptop. The pod just
  needs to receive those + run Stages 4–7.

## Inputs to ship from laptop → pod

Five files in `inputs/processed/durham_hayti_baseline/` (≈55 MB total):

| File                       | Size       | What            |
| -------------------------- | ---------- | --------------- |
| `Building_DSM.tif`         | 22.5 MB    | Buildings + DEM |
| `DEM.tif`                  | 22.5 MB    | Bare earth      |
| `Trees.tif`                |  9.2 MB    | CDSM            |
| `Landcover.tif`            | 0.4 MB     | UMEP codes      |
| `ownmet_2025-06-23.txt`    | 4 KB       | HRRR met        |

Also need the planting-points GeoJSON for Stage 5:

- `inputs/raw/durham/trees_planting/durham_trees.geojson` (~5 MB)

## Pod setup (one-time, ~5 min)

```bash
# in pod's /workspace
git clone git@github.com:ArohanD/radiant-temperature.git
cd radiant-temperature
git checkout main   # commit c61302e or newer

# install solweig-gpu and geo deps into the pod's existing PyTorch env
pip install "numpy<2" rasterio geopandas pyproj shapely solweig-gpu \
            dynamical_catalog matplotlib

# verify GPU is visible
python -c "import torch; print('CUDA:', torch.cuda.is_available(),
    'device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
# expect: CUDA: True  device: NVIDIA RTX A5000
```

If `solweig-gpu` install fails because of the numpy<2 pin clashing with the
runpod image's numpy 2.x, do `pip install --upgrade --force-reinstall "numpy<2"`
**after** `pip install solweig-gpu` and re-test the import.

## Ship inputs from laptop (run on **laptop**, not pod)

Get the pod's SSH details from the RunPod console (Connect → SSH).

```bash
# from laptop, in repo root
POD=root@<pod-ip>
PORT=<pod-ssh-port>

scp -P $PORT -r \
    inputs/processed/durham_hayti_baseline \
    inputs/raw/durham/trees_planting \
    inputs/raw/durham/overture/buildings_durham_hayti.geojson \
    $POD:/workspace/radiant-temperature/inputs/staged/
```

Then on the pod, move them into the right places:

```bash
mkdir -p inputs/processed inputs/raw/durham/trees_planting inputs/raw/durham/overture
mv inputs/staged/durham_hayti_baseline inputs/processed/
mv inputs/staged/trees_planting/* inputs/raw/durham/trees_planting/
mv inputs/staged/buildings_durham_hayti.geojson inputs/raw/durham/overture/
```

## GPU-mode tile size

The laptop pipeline uses `tile_size=1000` for OOM safety on CPU. The A5000
has 24 GB VRAM and can comfortably do a single 2401×2401 tile. To take
advantage, edit `scripts/04_run_baseline.py` and `scripts/06_run_scenario.py`:

```python
tile_size=2600,   # single-tile mode on GPU; fits in 24 GB VRAM
```

If a single tile OOMs the GPU, fall back to `tile_size=1500` (2×2 grid).

## Run Stages 4–7

```bash
# from /workspace/radiant-temperature
bash scripts/run_solweig_only.sh
# baseline: ~3-5 min on A5000
# 2 scenarios: ~6-10 min total
# figures: ~1 min
# total: under 20 min wall clock
```

Watch progress in another shell:

```bash
tail -f outputs/durham_hayti_baseline_run.log
tail -f outputs/durham_hayti_scenario_run.log
```

## Ship outputs back to laptop (run on **laptop**)

After the pod pipeline completes:

```bash
# from laptop, in repo root
scp -P $PORT -r \
    $POD:/workspace/radiant-temperature/inputs/processed/durham_hayti_baseline/output_folder \
    inputs/processed/durham_hayti_baseline/output_folder

scp -P $PORT -r \
    $POD:/workspace/radiant-temperature/inputs/processed/durham_hayti_scenario_year10 \
    $POD:/workspace/radiant-temperature/inputs/processed/durham_hayti_scenario_mature \
    inputs/processed/

scp -P $PORT -r \
    $POD:/workspace/radiant-temperature/figures/durham_hayti \
    figures/

scp -P $PORT -r \
    $POD:/workspace/radiant-temperature/outputs/durham_hayti_scenario_diffs \
    outputs/

# regenerate web inspector locally so paths line up
./env/bin/python scripts/_inspect_web.py
```

Then **stop the pod** in the RunPod console to stop the meter.

## Gotchas (from laptop debugging — may not all apply on pod)

1. `mp.set_start_method('fork', force=True)` is set in scripts already —
   harmless on Linux, prevents an icechunk/dynamical interaction.
2. `PROJ_DATA` is set defensively in `_lib.setup_geo_env()` — points at the
   conda env on laptop, harmless on pod (no conda).
3. **Don't include** `arohandutt@live.com` in any HTTP User-Agent / contact
   string — already cleaned out, just a reminder if any new code is added.
4. Outputs land under `<base_path>/output_folder/<tile_key>/` — solweig-gpu
   has no `output_dir` arg.
5. NC LiDAR vertical units are US Survey Feet — already converted in Stage
   3 outputs, no action needed.

## Sanity gates after baseline (mirror what `04_run_baseline.py` checks)

- `output_folder/0_0/TMRT_0_0.tif` (or whichever single tile) opens, 24 bands
- Peak-hour band: tile-mean Tmrt > 60 °C, std > 5 °C
- Pre-dawn band: std < 2 °C
- UTCI peak: tile-mean in 30–60 °C range

If a gate fails, **don't** fire scenarios — debug first.

---

## Handoff prompt — paste into fresh Claude session on pod

```
Pick up the Hayti SOLWEIG runs on this RunPod A5000 pod. Full brief at
notes/runpod_handoff.md in this repo. Project context is in CLAUDE.md.

Status: Stages 1-3 done on a separate laptop. The pod just needs to (1)
receive 5 input rasters + 1 GeoJSON via scp from the laptop, (2) install
solweig-gpu + geo deps on top of the runpod PyTorch image, (3) run Stages
4-7 (baseline SOLWEIG, scenario build, scenario SOLWEIG, figures).

Bump tile_size to 2600 in scripts/04_run_baseline.py and 06_run_scenario.py
to take advantage of the 24 GB VRAM (single-tile mode). Fall back to 1500
if OOM. Expected wall time: under 20 min total.

Goal: produce figures/durham_hayti/*.png and outputs/durham_hayti_scenario_diffs/
so the laptop can fetch them and finish the slide. Do NOT run scripts/_inspect_web.py
on the pod — paths are wrong; that's a laptop-side step.

The user (arohan) is at the keyboard — confirm before destructive actions.
```
