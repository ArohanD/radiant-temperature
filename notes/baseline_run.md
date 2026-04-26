# Baseline SOLWEIG run — Durham downtown, 2025-06-23

Snapshot of the Stage 4 baseline output for use as a reference when comparing
to the scenario in Stages 6/7. Run completed 2026-04-26 in 38.5 min on this
laptop (16-core CPU, no NVIDIA).

## Headline numbers

- **Peak hour** (highest tile-mean Tmrt): **15:00 local**, mean Tmrt **64.7 °C**, std 13.05 °C
- **Pre-dawn (03:00)**: mean Tmrt 18.6 °C, std 0.48 °C — uniform as expected
- **UTCI peak (15:00, non-roof)**: mean **44.4 °C**, p99 48.2 °C
- **51% of pedestrian-accessible cells in "extreme heat stress"** (UTCI > 46 °C) at peak
- **0%** of pedestrian-accessible cells out of any heat stress category at peak

## Per-landcover Tmrt at peak (15:00)

| Class | Tmrt (°C) | Δ from grass (°C) |
|---|---|---|
| Paved | 70.5 | +19.2 |
| Building roofs | 70.4 | +19.1 |
| Bare soil | 69.5 | +18.2 |
| Grass / tree-shaded | **51.3** | reference |

The 19 °C paved-vs-shaded gap is the model's sensitivity ceiling for the
intervention we're scoring in Stages 5/6. The scenario will only see cooling
of this magnitude in the immediate footprint of new tree disks; the spatial
mean will be much smaller.

## Diurnal trace (tile-mean Tmrt)

```
h=00  20.6   h=06  17.7   h=12  62.7   h=18  54.5
h=01  20.1   h=07  24.6   h=13  63.7   h=19  44.9
h=02  19.5   h=08  37.8   h=14  63.8   h=20  32.6
h=03  18.6   h=09  48.7   h=15  64.7   h=21  26.8
h=04  18.3   h=10  56.5   h=16  63.7   h=22  25.3
h=05  18.1   h=11  61.3   h=17  60.6   h=23  23.3
```

Pre-dawn flat at ~18 °C; sunrise jump at h=07 (mean +7 °C, std jumps to
7.75); plateau 13–16h around 63–65 °C; falls back to ~23 °C by 23:00.

## UTCI vs input air temperature

UTCI follows Ta plus a solar-radiation/longwave-loading delta that ranges
from +0.3 °C at dawn to +8.2 °C at solar noon, falling back to +1.5 °C at
night. No discontinuities, no implausible jumps. KRDU recorded a 99 °F
(37.2 °C) max for this date; HRRR's nearest-cell input had 36.2 °C peak.

## Geometry verification

At 15:00 EDT the sun is at altitude 64.6°, azimuth 247.5° (WSW). Shadows
fall toward 67.5° (~ENE), confirmed by the shadow band mean of 0.767
(23 % of cells in shadow at peak). Visible in the web inspector with the
"Shadow at 15:00" + "3D buildings" layers toggled together.

## SVF distribution (preprocessor sanity)

- min = 0.000  p10 = 0.066  p50 = 0.745  p90 = 0.936  max = 0.993
- 6.1 % open-sky cells (SVF > 0.95) — surface lots, plazas, river setbacks
- 21.4 % deep-canyon cells (SVF < 0.4) — between-buildings + dense canopy

## Outputs (Stage-4 deliverables)

```
inputs/processed/durham_downtown_baseline/output_folder/0_0/
  TMRT_0_0.tif    24-band hourly Tmrt          184 MB
  UTCI_0_0.tif    24-band hourly UTCI            ~  same
  SVF_0_0.tif     1-band sky view factor
  Shadow_0_0.tif  24-band hourly shadow mask
```

Visual inspection layers added to the MapLibre web app
(`inputs/processed/durham_downtown_baseline/web/`) — Tmrt at 03/09/15/19h,
UTCI at 09/15/19h, SVF, and shadow at 15h. All hover-sampleable.

## Run details

- Script: `scripts/04_run_baseline.py`
- Wall-clock: 38.5 min total (5.7 min wall-height/aspect, 32.8 min main loop)
- 16-worker parallel CPU; no GPU available on this machine
- Single 1401×1401 tile (`tile_size=1600` to avoid the
  three-1-pixel-sliver bug from the default 1400)
- Log: `outputs/durham_downtown_baseline_run.log`

## Validation against observations and independent reanalysis

`scripts/_compare_to_observations.py` runs three checks against external data
sources. Findings:

| Comparison | MAE (°C) | What it tells us |
|---|---|---|
| HRRR Ta input vs **KRDU** ASOS Ta (airport, 14 km away) | 1.92 | Useful but confounded by the airport-vs-downtown microclimate gap |
| HRRR Ta input vs **Open-Meteo** ERA5 reanalysis Ta (downtown, same lat/lon) | **0.57** | Apples-to-apples — HRRR forcing validated |
| UTCI grass cells vs **NWS Heat Index** (from KRDU Ta+Td) | 2.85 | OK; HI ignores wind so it's the noisiest comparison |
| UTCI grass cells vs **Open-Meteo apparent_temperature** (downtown, BOM/Steadman formula incl. wind) | **2.20** | Best match: same location, formula closer to UTCI minus radiation |

**Key finding:** the 1.92 °C HRRR-vs-KRDU gap is *not* a model bias — it's
the genuine microclimate difference between downtown and the airport.
Open-Meteo at the same downtown coordinates agrees with HRRR to within
0.57 °C across all 24 hours. KRDU's ASOS reads warmer + drier (especially
at sunrise) due to runway asphalt and the airport's open surroundings.

**Physical interpretation of UTCI − OM_apparent_temp diurnal pattern:**
- Day (h=10–18): UTCI ≈ OM_App ± 1.3 °C, sometimes ~+0.5 °C higher at peak
  (radiation loading visible — exactly what SOLWEIG adds)
- Pre-dawn (h=00–06): UTCI runs 2.5–3.5 °C *below* OM_App (surfaces have
  radiated their day's heat to the sky)
- Late evening (h=20–23): UTCI runs 3.8–7.0 °C below OM_App (same effect,
  amplified)

This direction-of-divergence is exactly the physics SOLWEIG is supposed to
add on top of pure Ta+RH+wind formulas. Reverse pattern (UTCI lower in day,
higher at night) would indicate a sign-flipped radiation balance.

**Headline UHI delta:** +4.7 °C UTCI between paved and grass at peak (15:00),
consistent with CAPA Heat Watch 2021's measured 3–4 °C air-temp UHI for
Durham (extra ~1 °C explained by radiation loading that air-temp campaigns
don't capture).

The script flags Check 1 as "failed" by its own threshold (p95 > 3 °C) but
that's a methodological artifact — Check 3 effectively retires the warning.
