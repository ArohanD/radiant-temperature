# AOI decision record

## Current AOI: Hayti (2026-04-26 pivot)

**AOI name**: `durham_hayti`
**Center (lat, lon)**: `35.985°N, -78.900°W` (~100 m N of Hayti Heritage Center, 804 Old Fayetteville St)
**Center (UTM 17N, EPSG:32617)**: `(689317.1, 3984323.8)`
**Size**: 2.0 km × 2.0 km core, 200 m shadow buffer
**TILE_BBOX (EPSG:32617)**: `(688317.1, 3983323.8, 690317.1, 3985323.8)`
**PROCESSING_BBOX (EPSG:32617)**: `(688117.1, 3983123.8, 690517.1, 3985523.8)`

**Coverage at this center**:
- North: just past the Durham Freeway (NC-147) — historic boundary that bisected and isolated Hayti
- South: through Lakewood Avenue
- East: across S Roxboro / N to E Pettigrew
- West: ~Duke Street
- Captures Hayti core + Hayti Heritage Center + Lincoln Hospital site + the freeway interface that's central to the neighborhood's redlining/displacement story

**Simulation date**: `2025-06-23` (unchanged — KRDU max 99°F, midday cloud score 1.00; year's hottest clear day in summer 2025).

## Why Hayti

- One of Durham's **8 EPA-identified priority neighborhoods** that get 85 % of the city's 8,500-tree planting commitment (2025–2028, $5.3M USDA grant, see `scenario_design.md`).
- Historically Black neighborhood, redlined in the 1930s, ~50 % displaced in 1960s urban renewal for the Durham Freeway. Persistent canopy gap and heat-island.
- Aligns with **CLAUDE.md's original equity framing**, which we'd previously deferred when piloting downtown for visual impact.
- Higher density of `Planting Site` features expected vs downtown (downtown: 22 sites in 1 km; Hayti likely several dozen in 2 km — confirmed at runtime).

## Pivot history

1. **Original spec (CLAUDE.md)**: Hayti, 1 km × 1 km. EPA-priority equity framing.
2. **First run (2026-04-25)**: pivoted to **downtown** (35.997°N, -78.899°W, 1 km × 1 km) for visual impact. 22 planting sites. Pipeline validated end-to-end. Outputs preserved at `inputs/processed/durham_downtown_*` + `figures/durham_downtown/` + `outputs/durham_downtown_scenario_diffs/`.
3. **Now (2026-04-26)**: pivot back to **Hayti**, scaled up to 2 km × 2 km. Same pipeline, same date, same canopy-scenario design.

## To relocate

Edit `scripts/_aoi.py` — `AOI_NAME`, `AOI_CENTER_LAT/LON`, `AOI_SIZE_KM`. Re-run `02_download_data.py` (citywide data, mostly cached) for the planting-point sanity count, then Stage 3 onward. The data sources are city-wide so no re-downloads needed for any Durham relocation. For non-Durham AOIs, swap MULC source (EnviroAtlas covers ~30 US cities); LiDAR (NC Phase 3 covers all NC; USGS 3DEP for elsewhere); HRRR + Overture are global.
