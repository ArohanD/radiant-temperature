# Scenario design — Durham planted-tree intervention

How the "scenario" rasters in Stages 5–6 represent Durham's planned
2025–2028 street-tree planting program.

## Source dataset

**Durham Open Data Portal — "Trees & Planting Sites"** layer
(`https://webgis2.durhamnc.gov/server/rest/services/PublicServices/Environmental/FeatureServer/11`),
maintained by City of Durham Urban Forestry. Downloaded by
`02_download_data.py` to `inputs/raw/durham/trees_planting/durham_trees.geojson`.

| Citywide | Count |
|---|---|
| Total features | 28,574 |
| Existing trees (`present == "Tree"`) | 22,418 |
| Planted-but-future sites (`present == "Planting Site"`) | 6,011 |

We filter to `present == "Planting Site"` and clip to `TILE_BBOX` (the 1×1 km
analysis core, not the 1.4 km PROCESSING_BBOX). **Result: 22 sites** in our
downtown AOI.

## What we know about those 22 sites

| Attribute | Coverage |
|---|---|
| `plantingdate == "2025-2026"` | 13 of 22 (active in current funding window) |
| `plantingdate` blank | 7 of 22 |
| `plantingdate` 2019-2020 / 2022-2023 | 2 of 22 (likely already planted, dataset lag) |
| `commonname` (species) populated | 5 of 22 (Chinese Fringe Tree ×2, Shantung Maple, Chinese Pistache, Red Maple) |
| `program == "PB"` | 1 of 22 (rest blank) |

We include **all 22** in the scenario regardless of date or species. The dataset
is the canonical city record; the data lag for already-planted sites is real
and acts as a conservative lower bound.

## The umbrella program (context, not modeled directly)

- **City of Durham General Services / Urban Forestry Division**, partnered with Keep Durham Beautiful.
- **8,500 trees, fall 2025 – spring 2028**. ([durhamnc.gov/4330](https://www.durhamnc.gov/4330/City-Tree-Planting-Program))
- 2025-26 season alone planted **2,836 trees** (1,333 in priority neighborhoods). ([Earth Day press release](https://www.durhamnc.gov/m/newsflash/home/detail/4120))
- Funded in part by a **$5.3M USDA Urban & Community Forestry grant** (2024–2029, Justice40/IRA), covering ~4,000 of the trees plus a UFMP refresh. ([CivicAlerts](https://www.durhamnc.gov/CivicAlerts.aspx?AID=3502&ARC=5187))
- Equity targeting: **85% of city plantings → 8 EPA-identified Census Block Neighborhood Groups** (designated 2018 via EnviroAtlas). ([EPA Science Matters](https://www.epa.gov/sciencematters/going-back-our-roots-epa-researchers-help-city-durham-north-carolina-site-new-trees))
- **Our downtown AOI is *not* in those 8 priority neighborhoods.** The honest framing for this study is "what cooling does the program's downtown corridor planting buy at peak heat" — not the equity story (which would require pivoting back to Hayti / Walltown / Old East Durham).

## Canopy assumption — why two scenarios

The Durham Open Data layer doesn't carry per-site species for `Planting Site`
records (only for `Tree`). The dominant Durham street-tree archetype per the
[2018 UFMP](https://www.durhamnc.gov/DocumentCenter/View/34156/Urban-Forest-Management-Plan)
and [Street Tree SOP](https://www.durhamnc.gov/DocumentCenter/View/44428/Street-Tree-Planting-SOP)
is medium-large deciduous shade trees: Willow Oak, Red Maple, Eastern Redbud,
Crape Myrtle. NC State Extension cites Willow Oak at **18–24 m mature height,
12–15 m crown diameter, ~30 yr to 80% mature** ([NC Extension](https://plants.ces.ncsu.edu/plants/quercus-phellos/)).

A single canopy assumption would be defensible either way, but neither would
honestly represent the question. We run two:

| Scenario | Canopy height | Disk size | Per-site footprint | Represents |
|---|---|---|---|---|
| `year10` | **5 m** | 5×5 px | ~25 m² | 5–10 yr post-planting (Willow Oak / Red Maple growth rates) |
| `mature` | **12 m** | 7×7 px | ~50 m² | ~25-yr canopy; honest upper bound for "what the plan delivers at maturity" |

Stage 7 reports both as a range: *"ΔTmrt at peak hour: X °C (year-10) to
Y °C (mature)."* The headline communicates uncertainty in the canopy
assumption rather than committing to one number that critics can reasonably
challenge.

The 12 m / 50 m² mature case is itself **conservative** versus the literature's
mature Willow Oak (18 m, 110 m² footprint) — we don't push to the literature
maximum because (a) Durham's diversity rule (≤ 10% any species) means a mix
of smaller species too, and (b) urban street trees rarely reach forest-grown
dimensions due to soil-volume constraints and pruning.

## Burning rules

For each site (in `05_build_scenario.py`):

- **Trees CDSM**: `Trees[disk] = max(Trees[disk], canopy_h_m)` — `max` so we
  never shrink existing canopy if a planting site happens to overlap one.
- **Landcover**: cells in the disk are reclassed to UMEP `5` (grass /
  under-tree ground), **except** cells that are already UMEP `2` (building) —
  those are left alone (you don't reclassify a roof to grass for a tree
  alongside it).
- **Site sanity**: if a site centroid falls inside a building footprint, it's
  reported and **skipped entirely** (likely a data alignment artifact between
  the city's tree layer and Overture's building layer).

## Compute cost

- Stage 5 (build): seconds.
- Stage 6 (run): ~2 × baseline = **≈ 75 min** total for both scenarios on this
  laptop (CPU only, ~38 min each).

## Data gaps acknowledged

- **Per-site species**: not in the public layer for `Planting Site` records.
  Filling this would require contacting Urban Forestry directly (out of sprint
  scope).
- **Soil-volume / urban growth penalty**: not modeled. Real urban street trees
  often cap below the NC Extension forest-grown numbers; our 12 m / 50 m²
  "mature" already half-bakes this in.
- **Time-since-planting per site**: unknown. We treat all sites as "planted
  but immature" in `year10` and "fully grown" in `mature`. A more rigorous
  approach would interpolate by `plantingdate`, but the dataset is too sparse
  for that.
- **Hayti-specific equity framing**: not modeled here — out of AOI. If we
  ever pivot back to Hayti, planting-site density per the same dataset is
  much higher and the same recipe applies.
