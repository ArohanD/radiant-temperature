# Result — Durham downtown planted-tree intervention

Single-paragraph project summary, the seed of the slide.

---

On a hot, clear summer day (2025-06-23, 99 °F at KRDU), in a 1 km × 1 km
slice of downtown Durham, the city's planned 22 street-tree plantings deliver
**4.5–5.2 °C of pedestrian heat-stress (UTCI) cooling at the planted spots
themselves at peak hour (15:00 EDT)**, with mean radiant temperature dropping
**18.6–21.1 °C** at the same locations. The range spans a 5–10-year
post-planting canopy (5 m, lower bound) to mature canopy (12 m, upper
bound). Tile-wide, the intervention is local — 22 sites cover ~0.03 % of
the area — so spatial-mean cooling is small (0.01–0.04 °C); the right
framing is **what these planted spots feel**, not what the citywide air
temperature does. Modeled with SOLWEIG (Lindberg et al., GPU implementation
by Kamath et al. 2026) at 1 m resolution, using NC Phase-3 LiDAR (2015) and
Overture-derived building footprints for ground geometry, EnviroAtlas MULC
(2010) for landcover, and NOAA HRRR analysis (dynamical.org) for the day's
meteorological forcing — validated against KRDU ASOS observations and an
independent ERA5 reanalysis (Open-Meteo) at the AOI center, with the
forcing matching the independent reanalysis to within 0.6 °C across all 24
hours.

---

## Slide one-liner

> **Durham's planned 2025–28 downtown plantings cool the spots they
> occupy by 4.5–5.2 °C "feels-like" temperature at peak heat — the
> pedestrian-relevant impact of converting a sun-baked paved cell into a
> shaded one.**

## Slide caveat list (small print)

- Single hot clear day in June 2025; not summer-mean.
- 22 sites in this downtown tile; the city's 2025–28 program is 8,500 trees
  citywide, 85 % of them in EPA-priority neighborhoods (not modeled here).
- Canopy assumption: 5–12 m height range, 25–49 m² footprint per site —
  half-baked into the cooling-range we report.
- Building roofs are excluded from all pedestrian statistics (Tmrt is not
  physically valid on roofs).
- Tile-wide cooling is small because the intervention is small (22 sites ×
  ~30 m²); per-site cooling is large.
- Canopy slightly *warms* nighttime Tmrt at planted cells (+0.1 to +0.5 °C),
  via reduced sky-view factor — real urban-climate effect, captured by the
  model.

## Files

- `figures/fig1_three_panel_{year10,mature}.png` — the money shot
- `figures/fig2_near_tree_histogram.png` — distribution of Δ near planted points
- `figures/fig3_diurnal.png` — diurnal cycle, baseline vs both scenarios
- `figures/headline.txt` — one-line claim, regenerated from data
- `notes/scenario_results.md` — full numbers + diagnostics
- `notes/baseline_run.md` — baseline + observation-validation context
- `notes/scenario_design.md` — why we chose two canopy assumptions
- `notes/decision_log.md` — every meaningful decision in the project, why
- web app at `inputs/processed/durham_downtown_baseline/web/` — interactive
  ΔTmrt overlays + planted-point markers + 3D buildings; `python -m
  http.server 8765` to serve
