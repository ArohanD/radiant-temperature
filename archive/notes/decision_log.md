# Decision log

## 2026-04-25 — DEM nodata fill

**Problem:** PDAL's IDW raster from NC Phase 3 ground returns (`Class=2`) left ~614k nodata cells (~31% of the 1.4 km tile) — concentrated under buildings and dense canopy where the laser couldn't reach the ground. First sanity check appeared to fail catastrophically: `(DSM − DEM) p99 = 10,145 m`, initially mistaken for the canonical NC US-Survey-Feet vertical-units bug. Root cause was the −9999 nodata sentinel propagating into height arithmetic; the actual heights were fine wherever both rasters had data.

**Options weighed:**
- **Leave nodata as-is** — breaks every downstream raster arithmetic step (Trees CDSM, Landcover height-disambig, etc.) unless every consumer remembers to mask. Fragile.
- **Constant fill** (e.g., tile mean elevation) — introduces visibly flat slabs under buildings, distorts shadows around foundations.
- **IDW interpolation in PDAL** — would mean re-running the slow EPT pull.
- **Substitute a different DEM source** (USGS 3DEP, NC pre-built bare-earth) — adds a dependency and a CRS reconciliation step for what's a cheap fix.

**Decision:** `gdal_fillnodata.py -md 100 -si 0` (IDW with 100-cell search radius, no smoothing). Standard tool, works in-pipeline, smooth interpolation is acceptable since these cells are *under* buildings/canopy and the apparent ground surface won't be visible to pedestrians anyway. Documented in `03_build_rasters.py` and the data-considerations table.

---

## 2026-04-25 — Building footprint source for DSM modernization

**Problem:** NC LiDAR is 2015. Many post-2015 downtown Durham buildings (DPAC east wing, recent residential towers) are missing.

**Options weighed:**
- **Microsoft Global ML Building Footprints** — heights from 2020–2024 imagery.
- **OpenStreetMap** — community-edited, variable height coverage.
- **Overture Maps** — aggregates OSM + Microsoft ML + others, single canonical layer.
- **Durham CountyFootprints2016** — official municipal layer; server timed out, and 2016 data anyway.

**Decision:** Overture. Best of both (OSM + Microsoft heights), single fetch, ~73% of footprints in our AOI carry a `height` attribute.

---

## 2026-04-25 — Default height for footprint-only buildings

**Problem:** 27% of Overture footprints in AOI have no `height`. Initial recipe applied a 12m default.

**Counted impact:** Only 15 buildings (1.8% of total) actually fell into the "no Overture height + no LiDAR support" pocket where a default could possibly help — and inspection showed all 15 were short structures (sheds, garages) that LiDAR had measured correctly at ~1m. The 12m default was *inflating* correct measurements.

**Decision:** Drop the default entirely. Apply Overture height only when present; for footprint-only buildings, leave DSM at the LiDAR-measured value. Footprints without heights still get reclassed to building in Landcover (outlines update; heights don't).

---

## 2026-04-25 — LiDAR noise spike cleanup

**Problem:** PDAL first-returns max DSM contained 418 cells more than 100 m above ground (max 1162 m AGL — birds / aircraft / processing artifacts). Would cast spurious km-long shadows in SOLWEIG.

**Options weighed:**
- Hard cap at a fixed elevation.
- Replace each spike with the 3×3 neighborhood median (robust to single-pixel noise).
- Statistical outlier detection (z-score, IQR).

**Decision:** 3×3 median replacement, threshold at `(DSM − DEM) > 100 m`. Simple, robust to clustered noise, preserves real tall-building geometry. Same pattern for Trees.tif at the >40 m threshold (140 cells).

**Subsequently superseded** — see "Building_DSM construction (the canonical-method correction)" below. Once we adopted the canonical SOLWEIG recipe, these spikes vanished naturally because the offending cells default to DEM.

---

## 2026-04-26 — Building_DSM construction (the canonical-method correction)

**Problem:** Initial pipeline took the LiDAR first-returns max as `Building_DSM.tif`. Visual inspection in the web app showed (a) tree canopies baked into the DSM; (b) an obvious tree-cluster blob on West Morgan St being treated as a building; (c) the LiDAR-noise-spike issue we'd been patching around.

**Investigation:** Confirmed via solweig-gpu source (`solweig_gpu.py:52` — `building_dsm_filename` documented as *"Building+terrain DSM"*), the UMEP SOLWEIG manual (*"this DSM consist of both ground and building heights"*), and the original Lindberg & Grimmond (2011) vegetation-handling paper. Trees in the DSM are double-counted: hard building-shadows from the DSM **and** canopy-shadows from the CDSM, with wrong albedo/emissivity and no canopy porosity. UMEP's own LiDAR-processing tutorial gives the canonical recipe: *"ground returns + unclassified returns clipped to building footprint polygons."*

**Options weighed:**
- **Keep current recipe** (LiDAR first-return max + Overture overlay) — wrong by SOLWEIG's data contract; produces visibly wrong DSM.
- **Filter LiDAR by point classification** (`Class=2 ground` + `Class=6 building`) before rasterizing — would require re-pulling EPT; only works if the input LAZ has reliable building classification (varies by NC Phase 3 tile).
- **Use Overture footprints to gate which LiDAR returns count as "building"** (the user's proposal; the textbook UMEP recipe with a different polygon source).

**Decision:** Adopt the Overture-as-source-of-truth recipe:
- `Building_DSM = DEM` everywhere by default.
- At each Overture footprint cell: `max(LiDAR_first_return, DEM + Overture_height)` — LiDAR-measured roof preferred (more precise), Overture as fallback for cells with no LiDAR support.
- `Landcover`: drop the LiDAR-height-based building/paved split; just MULC reclass, then every Overture footprint cell forced to building (UMEP code 2).

**Consequences:**
- `_clean_outliers.py` becomes redundant — outlier cells were tree/bird returns over non-building land; under the new rule they default to DEM.
- The Landcover height-disambiguation step in `03_build_rasters.py` becomes redundant.
- Real-but-Overture-missing buildings would now render as flat ground. Acceptable risk in a US downtown (Overture aggregates OSM + Microsoft ML); worth a visual sanity check post-rebuild.

**References:** Lindberg & Grimmond (2011, TAC); UMEP SOLWEIG manual; solweig-gpu JOSS paper (Kamath et al., 2026); UMEP LiDAR-processing tutorial.

---

## 2026-04-26 — Two scenarios instead of one (canopy-size assumption)

**Problem:** The plan's `05_build_scenario.py` originally specified a single 3×3-pixel disk at 8 m canopy height per planted tree. Web research into Durham's actual program (City Tree Planting Program, 8,500 trees 2025–2028, dominant archetype Willow Oak / Red Maple) shows the assumption is internally inconsistent: 8 m height is a year-5–10 figure for those species, but a 3×3 (~9 m²) footprint is a year-1 sapling figure. NC Extension cites Willow Oak at 18–24 m mature with a 12–15 m crown (~110 m² footprint) and ~30 yr to 80% mature. Whatever single number we pick, a critic can argue we either understated or overstated.

**Options weighed:**
- **Single canopy at "year 5–10"** (5 m, 25 m²) — defensible for the next decade of Durham's plan but understates long-term value.
- **Single canopy at "mature"** (12 m, 50 m²) — the Tmrt-reduction argument is strongest here, but 25 yr is a long horizon for a sprint headline; opens the "you're claiming credit for trees not even planted" critique.
- **Run both** — twice the compute (~75 min vs ~38 min), but lets the headline communicate the canopy assumption explicitly as a range. More defensible at the cost of one extra SOLWEIG run.

**Decision:** Run **both scenarios**. Stage 7 reports a range (`ΔTmrt at peak: X °C year-10 → Y °C mature`). The two scenarios share Building_DSM, DEM, Landcover (sans planting-site reclasses), and met file with the baseline; only Trees CDSM and Landcover diverge inside the planted disks.

**Implementation:**
- `05_build_scenario.py` parameterized over `SCENARIOS = {year10, mature}`; produces two folders `inputs/processed/{AOI_NAME}_scenario_{year10,mature}/`.
- `06_run_scenario.py` discovers all `*_scenario_*` folders and fires SOLWEIG against each in sequence; idempotent (skips folders with an existing `output_folder/`).
- `mature` capped at 12 m / 50 m² (not the literature's 18 m / 110 m²) to half-bake in soil-volume + pruning constraints typical of urban street trees, plus Durham's UFMP species-diversity rule (≤10% any species).

**References:** [Durham City Tree Planting Program](https://www.durhamnc.gov/4330/City-Tree-Planting-Program); [2018 UFMP](https://www.durhamnc.gov/DocumentCenter/View/34156/Urban-Forest-Management-Plan); [Quercus phellos — NC Extension](https://plants.ces.ncsu.edu/plants/quercus-phellos/); see `notes/scenario_design.md` for the full data + reasoning.

---

A few notes on form:
- Each entry: Problem / Options / Tradeoffs / Decision (sometimes Consequences, References when worth it). Don't be religious about the headers — drop ones that aren't load-bearing for a given decision.
- Keep this in notes/ (already tracked in git per the repo layout in CLAUDE.md), not in the gitignored inputs/ or outputs/. It's project history, not data.
- New entries go at the bottom; the file reads chronologically.
- Resist the urge to log every fix. The bar is "would future-me struggle to reconstruct the why from the code or commit history alone?" If yes, log it.
