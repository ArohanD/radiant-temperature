"""Run baseline SOLWEIG on the Hayti tile (no planted intervention).

Expected: ~50 min on CPU (no GPU on this machine) for a 1.4x1.4 km 1m tile.
Output: hourly Tmrt GeoTIFFs 6am-9pm in outputs/baseline/ for the chosen hot day.

Sanity check the output: shade should be cool, parking lots hot, streets intermediate.
Red flags: uniform values, 80°C everywhere, negative Tmrt — usually UTC offset, met parse, or unit error.
"""

# TODO: Day 3 — implement after rasters pass QA.
