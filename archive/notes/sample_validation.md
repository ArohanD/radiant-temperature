# Sample run validation — Day 1

What this note is for: an honest record of how we decided the SOLWEIG environment was trustworthy enough to move on to Durham data. Read this before re-validating on a new machine, or before relying on Day-1 outputs.

## What we ran

Source data: SOLWEIG-GPU sample dataset, [Zenodo DOI 10.5281/zenodo.18561860](https://doi.org/10.5281/zenodo.18561860).
- 4 input rasters at 2 m, EPSG:32614 (UTM 14N), Austin TX area (~30.33°N, −97.72°W).
- One UMEP-format met forcing file for 2020-08-13.

Pipeline: `scripts/_sample_run.py` cropped each raster to a 500×500 central window (~3 min CPU run, vs. ~4 hours for the full ~3367×3913 grid) and called `solweig_gpu.thermal_comfort()` in own-met mode with `save_tmrt=True`.

Outputs: 24-band hourly `TMRT_0_0.tif` and `UTCI_0_0.tif` under `inputs/processed/sample_crop/output_folder/0_0/`.

## Numerical sanity (per-band stats from our run)

| Band | Local hour | Tmrt min | mean | max | std | Reading |
|---|---|---|---|---|---|---|
| 1 | 00:00 | 22.2 | 23.3 | 25.0 | 0.6 | Night, low spread ✓ |
| 8 | 07:00 | 19.8 | 20.7 | 21.9 | 0.4 | Early morning, low sun ✓ |
| 14 | **13:00** | 34.4 | 63.3 | 78.4 | **10.5** | Peak, big spread = shadows working ✓ |
| 20 | 19:00 | 32.3 | 39.2 | 45.5 | 3.5 | Long shadows, surfaces still warm ✓ |
| 24 | 23:00 | 25.5 | 26.3 | 26.7 | 0.3 | Night, flat again ✓ |

The headline signal is **std ≈ 10°C at 13:00**. Without working shadow physics this would collapse toward the std at 07:00 / 23:00. Our 10°C separation is consistent with Lindberg, Onomura & Grimmond (2016), which reports shadowing changes Tmrt by ~30°C and ground cover by ~5°C in summer.

## Visual sanity (QGIS check)

Open `TMRT_0_0.tif`, band 14, with a heat ramp:

- **Diagonal NW→SE arterial through the middle is bright orange** — sunlit pavement, correct.
- **Crisp shadows on the SW/W of every building** — at Austin's latitude on 13 Aug at 13:00 the sun is just past zenith and slightly south, casting shadows just north and a touch east. ✓
- **Big blue patches on the western half** — mature tree canopies casting cool ground shadows.
- **Smooth penumbra gradients around buildings** — radiation accumulation working, not a boolean shadow mask.
- **Building roofs look bright orange** — Tmrt is not physically meaningful on roofs (mask them out downstream); they read hot in raw output, expected.

## Interpreting Tmrt vs UTCI vs air temperature

This caused confusion at first — worth recording.

- **Tmrt (mean radiant temperature)** is the equivalent uniform-surroundings temperature that would deliver the same radiation load to a body. It is **not** "feels like." On sunny pavement on an Austin August afternoon, Tmrt of 70–80°C is correct and matches measured pavement surface temperatures.
- **UTCI (Universal Thermal Climate Index)** is the "feels like" number on a temperature-equivalent scale. Combines Ta, RH, wind, and Tmrt into a single value. Categories:
  - 32–38°C: strong heat stress
  - 38–46°C: very strong heat stress
  - >46°C: extreme heat stress
- **Air temperature (Ta)** is what a thermometer in shade reads — supplied by the met forcing.

Our sample at 13:00 reports UTCI 35–46°C → "strong" to brushing-against "extreme" heat stress, consistent with August in Austin.

For Durham reporting: **Tmrt is the headline quantity** because it isolates the radiative effect of tree shade. UTCI gets reported as a secondary "what does it feel like" number on the slides.

## How UTCI is produced

Important: UTCI is **computed locally** by solweig-gpu, not read from any external dataset. See `env/lib/python3.10/site-packages/solweig_gpu/calculate_utci.py` — it implements the Bröde et al. (2012) 6th-order polynomial UTCI approximation, taking per-pixel Tmrt + spatially uniform Ta/Wind/Pa from the met file.

Implication: spatial variation in UTCI is driven entirely by Tmrt. Single-tile-wide wind underestimates street-canyon channeling, which is a known SOLWEIG-without-URock limitation — another reason to lead with Tmrt for Durham.

## What this validates and what it doesn't

**Trusted after Day 1:**
- Conda env builds, all imports resolve, CPU-only PyTorch path works.
- `thermal_comfort()` API call signature is correct; output format is what we expect.
- Radiation engine produces physically plausible spatial patterns and per-hour stats.

**Not yet validated (future risks):**
- US Survey Feet → meters conversion on NC LiDAR (Zenodo sample was metric).
- ERA5 met parsing into UMEP 23-col format (Zenodo sample shipped its own met file).
- UTC offset handling for Durham's local time (Zenodo sample's met was in local already).
- CDSM construction from `DSM − DEM` masked to tree pixels.

These three are flagged as the most likely Day-2/Day-3 failure modes. See `CLAUDE.md` §"Known gotchas".

## Reference for cross-machine reproduction

Tmrt values should match the table above to within a fraction of a degree on any CPU build of pytorch, since SOLWEIG is deterministic given the inputs. If you see large divergence:
- Different sample data version on Zenodo → check the DOI matches.
- Floating-point nondeterminism from a different BLAS → unlikely to shift means by more than ~0.1°C.
- Met file parsed differently → check the first few rows of `ownmet_Forcing_data.txt` look intact.
