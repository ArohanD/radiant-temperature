"""Produce the three figures + headline statistic for the conference slides.

Fig 1: 3-panel map (baseline peak / scenario peak / ΔTmrt diff) with planting sites overlaid on diff.
Fig 2: Histogram of ΔTmrt for pixels within 30m of a planned tree.
Fig 3: Diurnal time series, mean Tmrt across tile, baseline vs scenario.

Headline stat: mean peak-hour Tmrt reduction across the tile, plus max near-tree cooling.

Mask out building-roof pixels before any pixel statistic — Tmrt is not valid on roofs.
"""

# TODO: Day 5 — implement after both SOLWEIG runs complete.
