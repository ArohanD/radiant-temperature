# Scenario results — Durham planted-tree intervention, 2025-06-23

Outputs of Stages 5–7 against the baseline run captured in `baseline_run.md`.
Run completed 2026-04-26 (mature 38.6 min + year10 37.6 min = 76.1 min wall).

Two scenarios share everything with the baseline except `Trees.tif` and
`Landcover.tif` inside the planted disks (see `scenario_design.md`):

| Scenario | Canopy h | Disk | Per-site footprint | Burned cells (active sites) |
|---|---|---|---|---|
| `year10` | 5 m | 5×5 px | 25 m² | 462 (22/22) |
| `mature` | 12 m | 7×7 px | 49 m² | 987 (22/22) |

## Headline numbers at peak (15:00 local)

**Median across the 462 / 987 planted pixels** (the cells we directly
modified):

| | year10 | mature |
|---|---|---|
| ΔTmrt | **−18.6 °C** | **−21.1 °C** |
| ΔUTCI ("feels-like") | **−4.5 °C** | **−5.2 °C** |
| Worst (coldest) pixel ΔTmrt | −26.6 °C | −26.2 °C |

**Tile-wide pedestrian-accessible mean** (all non-roof cells, mostly cells
that *didn't* change):

| | year10 | mature |
|---|---|---|
| Tile-mean ΔTmrt | −0.014 °C | −0.035 °C |
| Tile-mean ΔUTCI | −0.004 °C | −0.009 °C |

**Within 30 m of any planted point** (~52,000 cells, of which 462–987 are the
planted ones themselves):

| | year10 | mature |
|---|---|---|
| Median ΔTmrt | −0.08 °C | −0.21 °C |
| Median ΔUTCI | −0.02 °C | −0.05 °C |

The huge planted-pixel cooling vs the small tile-wide mean is the central
reframing: **22 sites × 25–49 m² = 0.03 % of the tile**. The intervention is
local. Where it's local, it's dramatic — converting a sun-baked paved cell
into a tree-shaded grass cell, exactly the 19 °C paved-vs-grass gap measured
in the baseline.

## Diurnal trace (tile-mean Tmrt, non-roof)

```
h    base  year10  mature        h    base  year10  mature
00   20.6   20.6   20.6          12   60.7   60.7   60.7
03   18.6   18.6   18.6          15   62.8   62.8   62.7  ← peak
06   17.8   17.8   17.8          18   52.8   52.8   52.7
09   46.7   46.7   46.7          21   26.5   26.5   26.5
```

Cooling effect is concentrated in daylight hours (h=07 onward) and tracks
the magnitude of available solar load. Peak cooling per-cell at peak hour.

## Real but small night-time warming under canopy

A physical effect worth disclosing in the slide: at planted pixels overnight
(h=00–06), Tmrt is **slightly higher** than baseline — `+0.1` to `+0.5 °C`
in year10, `+0.04` to `+0.26 °C` in mature.

Mechanism: canopy reduces sky-view factor, suppressing longwave radiation
loss to the cold sky. Surfaces stay warmer overnight under canopy. Real and
well-documented in urban-climate literature; the model captures it. **The
canopy cools the day but slightly warms the night under canopy.** The
pedestrian implication is small (the night-time absolute Tmrt is still
~18 °C — comfortable).

## Why mature is only slightly cooler than year10 per pixel

- year10 cooling at planted pixels: −18.6 °C
- mature cooling at planted pixels: −21.1 °C
- Difference: only −2.5 °C extra for going from 5 m to 12 m canopy

**Diminishing returns.** A 5 m canopy already blocks most direct beam
shortwave at noon (the dominant Tmrt driver). Going taller adds modest
extra interception of off-axis radiation and a bit more sky-view factor
reduction. The mature scenario's bigger contribution is the **larger
spatial footprint** (49 m² vs 25 m² per site), which is why the mature
within-30 m median is 2.5× the year10's, not 1.15×.

## What the figures show

- `figures/fig1_three_panel_year10.png`, `_mature.png` — baseline | scenario | Δ at peak hour. Roofs masked transparent (Tmrt invalid). Planted points overlaid in green on the Δ panel.
- `figures/fig2_near_tree_histogram.png` — distribution of ΔTmrt for cells within 30 m of any planted point. Long left tail of strongly-cooled cells (the planted disks themselves), bulk near zero (cells in the buffer that weren't planted).
- `figures/fig3_diurnal.png` — three lines (baseline, year10, mature). Differences visible only during daylight; closely overlap at night.
- `figures/headline.txt` — slide-ready one-line claim.

## Stage-7 gates (per the plan)

- ΔTmrt < 0 at planted pixels at peak: ✓ (both scenarios)
- |Δ| within plausible range tile-wide: ✓ (mean cooling 0.014–0.035 °C — small because intervention is small, not because model is broken)
- At-tree cooling ≥ 1 °C: ✓ (both at >18 °C)

All gates pass.

## Outputs

```
inputs/processed/durham_downtown_scenario_year10/output_folder/0_0/
inputs/processed/durham_downtown_scenario_mature/output_folder/0_0/
  TMRT_0_0.tif   24-band hourly Tmrt
  UTCI_0_0.tif   24-band hourly UTCI
  SVF_0_0.tif    sky view factor (preprocessor)
  Shadow_0_0.tif 24-band hourly shadow

outputs/scenario_diffs/
  dtmrt_peak_{year10,mature}.tif   Δ at peak hour, NaN at building cells
  (web inspector reads these as overlay layers)

figures/
  fig1_three_panel_{year10,mature}.png
  fig2_near_tree_histogram.png
  fig3_diurnal.png
  headline.txt
```
