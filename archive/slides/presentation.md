---
marp: true
theme: default
paginate: true
size: 16:9
math: katex
style: |
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  section {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background: #fdfcfa;
    color: #1a1f2c;
    font-size: 24px;
    padding: 56px 72px 44px;
    letter-spacing: -0.005em;
  }

  /* title slide */
  section.title {
    background: radial-gradient(ellipse at top right, #2c6e58 0%, #14352b 60%, #0a1f18 100%);
    color: #fdfcfa;
    padding: 100px 88px 80px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  section.title h1 {
    font-size: 44px; font-weight: 700; line-height: 1.18;
    color: #fdfcfa; border: none; padding: 0; margin: 0 0 18px;
    max-width: 90%; letter-spacing: -0.018em;
    position: relative;
  }
  section.title h1::before {
    content: ""; display: block;
    width: 56px; height: 3px; background: #e76f51;
    margin-bottom: 22px;
  }
  section.title h2 {
    font-size: 22px; font-weight: 400; color: #c8d8d2;
    margin: 0 0 38px; letter-spacing: 0;
  }
  section.title p { color: #fdfcfa; }
  section.title small { color: #a0b8b0; line-height: 1.6; font-size: 16px; }
  section.title strong { color: #f4a261; font-weight: 600; }

  h1 {
    color: #14352b; font-weight: 700; font-size: 32px;
    margin: 0 0 16px; padding: 0 0 10px;
    border-bottom: 1px solid #d8d2c5;
    letter-spacing: -0.012em;
  }
  h2 {
    color: #1d4f3f; font-size: 22px; font-weight: 600;
    margin: 14px 0 8px; letter-spacing: -0.005em;
  }
  h3 { color: #444; font-size: 18px; margin: 6px 0 3px; }

  strong { color: #c0533e; font-weight: 600; }
  small, .caption { color: #6b7280; font-size: 0.78em; line-height: 1.5; }
  .citation { color: #9ca3af; font-size: 0.72em; font-style: italic; margin-top: 14px; }

  table {
    font-size: 20px; border-collapse: collapse; width: 100%;
    border: 1px solid #e5e1d8; border-radius: 4px; overflow: hidden;
    margin: 12px auto;
  }

  /* Centered-content slide: vertically + horizontally centered table or list */
  section.centered {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 56px 80px;
  }
  section.centered h1 {
    font-size: 30px;
    text-align: center;
    margin: 0 0 28px;
    align-self: center;
    border-bottom: none;
    padding-bottom: 0;
  }
  section.centered table {
    width: auto;
    max-width: 960px;
    margin: 0 auto;
  }
  section.centered td, section.centered th { padding: 12px 18px; }
  th {
    background: #1d4f3f; color: #fdfcfa; padding: 10px 14px;
    font-weight: 600; text-align: left; letter-spacing: 0.01em;
  }
  td { padding: 10px 14px; border-bottom: 1px solid #ece8de; background: #fdfcfa; }
  tr:last-child td { border-bottom: none; }
  tr:nth-child(even) td { background: #f8f6f1; }

  ul { margin: 4px 0; padding-left: 22px; }
  ul li { line-height: 1.5; margin-bottom: 14px; color: #1a1f2c; font-size: 24px; }
  ul li::marker { color: #1d4f3f; }

  blockquote {
    border-left: 4px solid #e76f51;
    padding: 18px 28px;
    margin: 8px 0;
    background: #fdf6f1;
    color: #14352b;
    font-style: normal;
    font-size: 26px;
    line-height: 1.45;
    border-radius: 0 6px 6px 0;
  }

  code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.86em;
    background: #f4f1ec;
    color: #14352b;
    padding: 1px 5px;
    border-radius: 3px;
  }

  img { display: block; max-width: 100%; height: auto; border-radius: 3px; }
  footer { color: #9ca3af; font-size: 13px; }
  section::after { font-size: 13px; color: #c8c2b3; font-weight: 500; }

  /* ====== HEADLINE-style slide: big centered title only ====== */
  section.headline {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 80px 100px;
  }
  section.headline h1 {
    font-size: 56px; line-height: 1.12;
    border: none; padding: 0; margin: 0 0 18px;
    max-width: 92%; letter-spacing: -0.022em;
    color: #14352b;
  }
  section.headline h2 {
    font-size: 28px; font-weight: 400;
    color: #4a5568; margin: 0; letter-spacing: -0.005em;
    line-height: 1.35; max-width: 88%;
  }
  section.headline p {
    font-size: 22px; color: #6b7280;
    margin-top: 24px; line-height: 1.45; max-width: 80%;
  }
  section.headline small { font-size: 16px; margin-top: 32px; }

  /* ====== STAT-style slide: huge centered number ====== */
  section.stat {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 60px;
  }
  section.stat .big {
    font-size: 168px;
    font-weight: 700;
    color: #c0533e;
    line-height: 0.95;
    letter-spacing: -0.04em;
    margin: 0;
  }
  section.stat .big.medium { font-size: 124px; }
  section.stat .big.small  { font-size: 96px;  }
  section.stat .label {
    font-size: 30px;
    color: #14352b;
    margin-top: 28px;
    font-weight: 600;
    max-width: 880px;
    line-height: 1.3;
  }
  section.stat .sub {
    font-size: 20px;
    color: #6b7280;
    margin-top: 16px;
    max-width: 740px;
    line-height: 1.5;
  }

  /* ====== IMAGE-FOCUS: small title, big image ====== */
  section.imgfocus {
    padding: 28px 48px 32px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
  section.imgfocus h1 {
    font-size: 26px;
    margin: 0 0 14px;
    text-align: center;
    border: none;
    padding: 0;
    flex: 0 0 auto;
  }
  section.imgfocus img {
    max-height: 580px;
    width: auto;
    object-fit: contain;
  }
  section.imgfocus p.caption {
    text-align: center;
    margin-top: 8px;
    font-size: 17px;
    color: #6b7280;
    max-width: 90%;
  }

  /* ====== QUOTE-style slide: big centered blockquote ====== */
  section.quote {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 80px 120px;
  }
  section.quote blockquote {
    border-left: 5px solid #e76f51;
    font-size: 34px;
    line-height: 1.4;
    padding: 32px 48px;
    background: #fdf6f1;
    color: #14352b;
    border-radius: 0 8px 8px 0;
  }
  section.quote .label {
    color: #6b7280;
    font-size: 18px;
    margin: 0 0 18px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500;
  }

  /* ====== SECTION DIVIDER ====== */
  section.divider {
    background: linear-gradient(135deg, #1d4f3f 0%, #14352b 100%);
    color: #fdfcfa;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 80px 100px;
  }
  section.divider h1 {
    color: #fdfcfa; border: none; padding: 0;
    font-size: 60px; letter-spacing: -0.022em;
    margin: 0;
  }
  section.divider h1::before {
    content: ""; display: block;
    width: 60px; height: 3px; background: #f4a261;
    margin-bottom: 28px;
  }
  section.divider h2 { color: #c8d8d2; font-weight: 400; margin-top: 18px; font-size: 26px; }

  section.ref {
    background: linear-gradient(135deg, #14352b 0%, #0a1f18 100%);
    color: #ecefe9; padding: 56px 80px;
  }
  section.ref h1 {
    color: #fdfcfa; border: none;
    border-bottom: 1px solid #2c6e58; padding-bottom: 12px;
  }
  section.ref h2 { color: #f4a261; font-size: 20px; margin-top: 18px; }
  section.ref strong { color: #f4a261; }
  section.ref em { color: #c8d8d2; }
  section.ref a { color: #f4a261; }
  section.ref code { background: #1d4f3f; color: #ecefe9; }
  section.ref ul li { color: #ecefe9; line-height: 1.55; font-size: 17px; margin-bottom: 6px; }
  section.ref ul li::marker { color: #f4a261; }
  section.ref small { color: #c8d8d2; }

  .pill {
    display: inline-block; padding: 2px 10px; margin: 2px 0;
    background: #fdf6f1; border: 1px solid #f4cdc1;
    border-radius: 12px; color: #c0533e; font-weight: 600; font-size: 0.94em;
  }
# footer: 'GIS 582 · A. Dutt · 2026-04-27'
---

<!-- _class: title -->
<!-- _paginate: false -->

# Quantifying the cooling impact of Durham's planned tree plantings in Hayti

## A 1m SOLWEIG analysis of pedestrian heat stress on a heatwave day

**Arohan Dutt** &nbsp;·&nbsp; GIS 582 &nbsp;·&nbsp; 2026

<br>

<!-- <small>
Modeled with SOLWEIG-GPU (Kamath et al. JOSS 2026)<br>
NC Phase 3 LiDAR (2015) · EnviroAtlas MULC (2010) · Overture Maps · NOAA HRRR · Durham Open Data
</small> -->

<!--
SPEAKER NOTES:
Hi everyone. Today I'm walking you through a project that asks one specific question: when Durham plants 245 new street trees in the Hayti neighborhood — which they're doing right now between 2025 and 2028 — how much cooler would it actually feel for someone walking right next to one of those trees on a heatwave day?

The structure of the analysis is a before-and-after comparison. I run a 1-meter physics simulation of the entire 4-square-kilometer neighborhood for ONE specific hot day — June 23, 2025, the hottest clear day of last summer — first as Hayti is today, then with mature canopy added at every planned site. The difference between the two is the cooling.

Because we don't know exactly how big these trees will be when they grow in, I run TWO scenarios — a small canopy and a large canopy — to bracket the answer.

Short answer, conditional on full planting and survival: at the planted spots themselves it would feel about 4.7 to 5.8 degrees Celsius cooler at peak heat. Enough to drop most of those spots one category on the WHO heat-stress scale, typically from "extreme" to "very strong."

This is an unvalidated model — no on-site measurements yet. I'll walk through what it captures, what it doesn't, and where the limitations are. Everything is reproducible from open data; code is on GitHub.
-->

---

<!-- _class: headline -->

# Heat is the deadliest weather hazard in the US.

## Radiation, not air temperature, drives the danger.

<!--
SPEAKER NOTES:
Heat kills more Americans than hurricanes, tornadoes, and floods combined. And it kills unequally — neighborhoods with less tree canopy run several degrees hotter than wealthier ones in the same city.

There are two ways to measure heat. The first is air temperature — the number on the weather app. The second, which matters way more for what you actually feel outside, is "mean radiant temperature," or Tmrt. Tmrt is the temperature your skin sees when you add up sunlight hitting you, plus heat radiating from hot pavement, plus heat radiating from buildings and the sky.

Asphalt on a clear summer day reaches about 70°C — hot enough to burn skin in seconds — even when the air is only 35°C. That asphalt then re-radiates heat into your body if you're standing on it. So air temperature alone is a misleading picture of heat risk; the real driver of dangerous exposure is what your body absorbs from radiation.

The fix for radiation is shade. Trees intercept direct sunlight before it reaches the sidewalk. The cooling effect is local but powerful — converting a sun-baked surface to a shaded one. Street trees aren't aesthetic; they're functional infrastructure for managing pedestrian heat exposure.
-->

---

<!-- _class: quote -->

<p class="label">Research question</p>

> On a heatwave day, what pedestrian-level cooling does Durham's planned 2025–2028 tree-planting program deliver in Hayti, and where does that cooling show up?

<!--
SPEAKER NOTES:
This is the question. Three things to flag in the framing:

First — "on a heatwave day." We're not asking about summer averages. We're asking about the worst-case hot, clear afternoon when the canopy intervention would matter most. That's a deliberate scoping choice; the rest of the year matters less for heat-related health risk.

Second — "what cooling does the program deliver." This is a before-and-after comparison: simulate Hayti as it is today, simulate Hayti with the planned trees in place, take the difference. Same day, same weather, same everything else.

Third — "where does the cooling show up." A program could technically reduce average temperatures by a tiny amount across a wide area, OR deliver large cooling at very specific spots. Those are very different programs from a public-health standpoint.
-->

---

<!-- _class: imgfocus -->

# Hayti: historically redlined, EPA priority for canopy

![w:1080](../figures/durham_hayti/slides/study_site.png)

<!--
SPEAKER NOTES:
Hayti is the perfect place to study this question because of its history. In the 1930s the federal government drew a red line around the neighborhood and called it "hazardous" for lending — that's literally where the term "redlining" comes from. Banks stopped giving mortgages there. Then in the 1960s, when they built the Durham Freeway, they ran it right through the middle of Hayti and demolished about half the houses. The result today is a neighborhood with a noticeable canopy gap compared to wealthier parts of Durham — and that gap shows up in summer temperatures.

The EPA officially designated Hayti as one of 8 priority neighborhoods in Durham. Eighty-five percent of Durham's 8,500-tree commitment between 2025 and 2028 — funded by a $5.3 million USDA grant — goes to those 8 neighborhoods.

Two maps. The LEFT shows every tree record in Durham's database — gray dots are existing trees, dark green are the 6,011 sites planned for new plantings. You can see plantings concentrate in specific neighborhoods, not random — that's intentional.

The RIGHT is my study area: a 2 km × 2 km square in the heart of Hayti. Inside that box are 245 planned planting sites — about ten times the density of downtown. We model a 200-meter shadow buffer around the analysis box because tall buildings outside it can still cast shadows into it.
-->

---

<!-- _class: imgfocus -->

# Five co-registered rasters @ 1 meter resolution

![h:560](../figures/durham_hayti/slides/data_panels.png)

<!--
SPEAKER NOTES:
The model needs to know the neighborhood in three dimensions. We give it five rasters at 1-meter resolution — our 2 km × 2 km area is 2000 × 2000 pixels, 4 million pixels per layer.

Top-left: the DEM, the bare ground — what the terrain would look like if every building and tree were removed. From a 2015 NC airborne LiDAR scan. About 30% of the ground was hidden under buildings or trees, those gaps are filled using interpolation.

Top-right: building DSM — heights of buildings above ground. Bright = tall (apartments, towers), dark = short.

Bottom-left: tree canopy heights. Greener = taller. Existing canopy clusters along property lines and parks.

Bottom-right: land cover, color-coded into 5 classes. Red is buildings, gray is paved, green is grass or under-tree, brown is bare soil, blue is water.

| Layer | Source · Vintage |
|---|---|
| DEM | NC Phase 3 LiDAR · 2015 |
| Building DSM | LiDAR + Overture footprints · 2015 + 2026 |
| Trees CDSM | (DSM − DEM) × MULC tree mask |
| Landcover | EnviroAtlas Durham 1 m MULC · 2010 |
| Met forcing | NOAA HRRR analysis |

LiDAR is from a 2015 statewide NC mapping campaign — 11 years old, but the most recent high-resolution scan available. Land cover is from 2010 EnviroAtlas — the oldest input, weakest data link. Weather is NOAA's HRRR analysis. Building footprints are Overture Maps Foundation, 2026 — the newest data, central to the data-cleaning step we'll see next.
-->

---

<!-- _class: imgfocus -->

# Building DSM: Overture-gated correction

![w:1100](../figures/durham_hayti/slides/dsm_correction.png)

<!--
SPEAKER NOTES:
Most of this project was getting the data right. Let me show you the biggest mistake and the fix.

When LiDAR fires a laser pulse from a plane, the first thing the pulse hits — a roof, a tree, a powerline, a bird — sends back the first echo. Naively, you'd take every "first echo" and call the result a "building height map."

LEFT: that result. The lower half is full of bright dots that aren't buildings — they're TREES. The LiDAR can't tell the difference between a roof and a tree canopy from above; both reflect the laser. This is a problem because the simulation treats them differently. Buildings are SOLID — sunlight stops at the wall. Trees are POROUS — sunlight scatters and partially passes through. Mislabel a tree as a building and you compute the wrong shadows, the wrong reflections.

MIDDLE: the fix, from a 2011 paper by Lindberg and Grimmond. The recipe says: only count a LiDAR return as a "building" if it falls inside a real building footprint polygon. Until recently this required negotiating with each city for proprietary GIS data. We use OVERTURE MAPS FOUNDATION instead — open global data combining OpenStreetMap with Microsoft's machine-learning footprints. 

RIGHT: the difference. Blue is removed phantom buildings (mostly trees). Red is real buildings LiDAR missed but Overture knew about — usually post-2015 construction. I also capped any building height at 150 meters to remove a few hundred pixels of noise and artifacts.
-->

---

<!-- _class: imgfocus -->

# SOLWEIG: 2.5D pedestrian radiation model

![w:760](../figures/durham_hayti/slides/methods_solweig.png)

<!--
SPEAKER NOTES:
SOLWEIG is the model that does the physics. Developed at the University of Gothenburg, It stands for "Solar and Long-Wave Environmental Irradiance Geometry."

What it does, once per pixel per hour:

Step 1 — sun position. Calculate where the sun is in the sky from date, time, lat/lon. We're at 36°N on June 23rd; at 3 PM the sun is 65 degrees up in the western sky.

Step 2 — shadow ray-tracing. For every pixel, ray-trace toward the sun. If a building or tree blocks the line of sight, the pixel is in shadow. This is the expensive step — it has to be done for every pixel for every timestep.

Step 3 — six-direction radiation budget. Add up radiation from six directions: direct shortwave from the sky, longwave from the ground below, plus reflections from each cardinal wall direction and from any nearby tree canopy.

Step 4 — Tmrt. Sum all that radiation and you get mean radiant temperature — the number that captures everything your skin sees.

Step 5 — UTCI. Plug Tmrt into the UTCI formula — the Universal Thermal Climate Index, used by national weather services for heat warnings. UTCI combines air temperature, humidity, wind, and Tmrt into a single "feels-like" number with six WHO heat-stress categories.

Implementation: I used solweig-gpu, a PyTorch-based GPU implementation by Kamath et al. (JOSS 2026). I quickly hit my laptop's CPU limits — a single full-day run in a smaller 1km AOI took about two hours, the 2km tiles would have taken about 8. I moved to a RunPod cloud instance with an RTX A5000 GPU; full simulation completed in about 1.5 hours. I had to split the 2 km × 2 km tile into 9 tiles of ~1000 pixels each that ran in parallel.
-->

---

<!-- _class: imgfocus -->

# Special case: heatwave day + before/after × 2 canopy scenarios

![h:560](../figures/durham_hayti/slides/scenario_design.png)

<!--
SPEAKER NOTES:
Three deliberate framing choices that scope the entire analysis.

ONE — the day. I picked the hottest clear day of summer 2025 algorithmically. Pulled all of Raleigh-Durham airport's hourly observations for the year, scored each day on max temperature plus cloud cover, took the top one. That came out to JUNE 23rd, 2025: 99°F at the airport, completely clear skies. Worst-case heat scenario — the conditions where canopy intervention matters most. We are NOT claiming summer-mean cooling. We are answering: what happens when it's really hot.

TWO — before vs after. I run the SAME simulation TWICE on this day. First, Hayti as it is today (the "baseline"). Second, Hayti with planned trees burned into the canopy raster at all 245 planning-site coordinates. Same weather, same buildings, same terrain — only the canopy layer differs between runs. Cooling is the per-pixel difference: scenario minus baseline.

THREE — two canopy scenarios. Durham's plan tells us WHERE to plant but not how big each tree will be. A newly planted tree is a 1 m stick; a mature one might be 18 m. Rather than pick one number, I run two:

LEFT image: SMALL canopy — 5 m tall, 25 m² disk per site. Roughly 5 to 10 years post-planting under typical Willow Oak / Red Maple growth rates.

RIGHT image: LARGE canopy — 12 m tall, 49 m² disk per site. Honest upper bound, capped below the 18 m forest-grown maximum because urban street trees rarely reach forest dimensions.

These two are sensitivity points that bracket the answer. They are NOT a confidence interval — they don't propagate species mix or account for mortality. We also assume 100% planting and survival. 
-->

---

<!-- _class: imgfocus -->

# Result: 245 trees at peak, densest cluster (700 m view)

![w:1280](../figures/durham_hayti/slides/fig1_utci_three_panel_mature.png)

<!--
SPEAKER NOTES:
The headline result. To make per-tree cooling actually visible, I'm zoomed to a slice of the AOI — the densest cluster, containing 164 of the 245 trees. This zoom is NOT representative of the wider AOI; the rest has fewer plantings.

LEFT: baseline UTCI at 3 PM. Discrete colorbar bands aligned to WHO heat-stress thresholds. Dark red is over 46°C, "extreme." Lighter orange is 38–46°C, "very strong." Most streets and parking lots are in the top two bands.

MIDDLE: same view with mature canopy at every planting site. At a glance similar — we're only adding 245 trees to thousands of pixels — but along the streets, new spots have dropped from extreme to very strong. Those are the planted disks.

RIGHT: scenario MINUS baseline. White = no change. BLUE = cooler. Each blue spot is one planted tree's cooling footprint. Almost every site has a clear cooling patch.

The blue is LOCAL — it stops a few meters from each tree as it's representing the cooling at the planting site. Median planted-pixel cooling is about 5.8°C. The most-cooled single pixel drops by 10°C. When combined with the middle chart we can see the effect of the totality of plantings where the radiation of the cooling expands to a larger area. 
-->

---

<!-- _class: stat -->

<div>
<div class="big medium">−4.7 to −5.8 °C</div>
<div class="label">median ΔUTCI at the 245 planted pixels</div>
<div class="sub">small canopy → −4.7 °C · large canopy → −5.8 °C · worst pixel: −10 °C<br>~58 % of planted pixels cross one WHO category (typically extreme → very strong)<br>Tile-wide pedestrian-mean ΔUTCI: −0.01 °C</div>
</div>

<!--
SPEAKER NOTES:
Quantitative headline. Median cooling at the 245 planning sites is 4.7 to 5.8°C of feels-like temperature reduction at peak heat — small canopy gives 4.7, large canopy gives 5.8. The corresponding ΔTmrt — radiation only, no humidity or air temp factored in — is much larger, 19 to 24°C. The worst-cooled single pixel, where multiple disks overlap, drops by 10°C.

About 58% of planted pixels cross ONE WHO heat-stress category — typically from "extreme" (>46°C) to "very strong" (38–46°C). Most others stay in the same category and cool within it. Two-category drops happen at fewer than 1% of pixels.

So cooling is real and meaningful, but it doesn't take pedestrians from extreme heat to comfortable shade — it lowers the danger one notch.

CONTEXT — tile-wide. If you average across the WHOLE 4 km² neighborhood, cooling is just 0.01°C. That's arithmetic: 245 sites × ~50 m² ≈ 0.15% of the tile. A critic who says "this only cools the neighborhood by 0.01°C, that's nothing" is doing the math right but answering the wrong question. The intervention is per-planted-spot, not citywide.

COMPARISON WITH LITERATURE. The original Lindberg/Holmer/Thorsson SOLWEIG papers and subsequent UMEP studies report shade ΔTmrt on the order of 15–25°C at single tree footprints in summer midday. Our Tmrt cooling sits in that range. The headline UTCI cooling — 5-6°C — is smaller because UTCI tempers the radiation effect via wind and humidity. So we're confirming previously observed phenomena at neighborhood scale, not reporting a surprising effect size.
-->

---

<!-- _class: imgfocus -->

# ΔUTCI distribution, ≤30 m of any planted site

![w:760](../figures/durham_hayti/slides/fig2_utci_histogram.png)

<!--
SPEAKER NOTES:
Here's how to read this chart. I drew a 30-meter circle around each of the 245 planned trees, merged those circles into one "near a tree" region, and dropped any rooftop cells. That leaves about 271,000 ground-level squares, one meter on a side. For every square I asked "how much cooler does this spot feel at 3 PM after the trees vs. before?"

The bottom axis is that cooling, in degrees C — negative means cooler. The side axis is how many squares ended up at each cooling value, and it's logarithmic — each gridline is ten times the one below. I had to use a log scale because the spike at zero is so tall it would flatten everything else on a normal axis.

Two stories on this chart.

First, the huge spike at zero. That's most of the buffer area — the gaps BETWEEN trees, near a tree but not directly under one. Those squares didn't change.

Second, the long tail running left to about minus 6 or 7. Those are the squares directly under the new canopy. They flipped from full sun to shade. That's where the headline 5-to-6-degree cooling lives.

The dark blue (12 m canopy) reaches further left and runs higher than light blue (5 m canopy) — bigger trees cast bigger shadows, more cells end up deep in the cooling tail.

The takeaway: this is a binary "covered vs not covered" intervention, not a gradient. Cells under the canopy cool a lot. Everything else stays the same. You don't get partial credit for partial coverage — which has implications for how a planting program should think about spacing.
-->

---

<!-- _class: imgfocus -->

# Sanity checks vs validation

![w:1080](../figures/durham_hayti/slides/validation.png)

<!--
SPEAKER NOTES:
Framing first: SOLWEIG is a published model, validated on-site in many cities. The physics is settled. These two panels check that I'm applying it correctly for Hayti.

LEFT — verifying the weather input. Red is HRRR (the model input), blue is ERA5 (independent European reanalysis), gray is the actual thermometer at RDU airport. HRRR and ERA5 agree to 0.56 °C MAE — clean cross-check that my forcing has the right magnitudes, hours, and location. The airport line runs ~2 °C cooler at night, consistent with a Hayti urban heat island.

RIGHT — sanity-checking the model output. Green is my modeled UTCI averaged across grass cells; blue is Open-Meteo's "apparent temperature." UTCI includes solar radiation; apparent temperature doesn't. They're EXPECTED to diverge at midday, and they do — exactly the radiation effect the model is meant to resolve. The 2.62 °C MAE in the title just describes the gap between two intentionally-different formulas; don't read good or bad into it.

What this establishes: inputs match an independent reanalysis, outputs show the right diurnal shape and the expected radiation divergence, and the physics engine itself is externally validated. What's still open is a Hayti-specific on-site comparison — globe thermometers at planted sites — which is next-level confirmation, not a foundational gap.
-->

---

# Limitations

- **Met forcing is spatially uniform.** No urban-canyon wind reduction, no transpiration cooling. ΔUTCI is mostly derived from the radiation channel.

- **100 % plant + survival assumed.** Urban first-5-year street-tree mortality is often 20–40 %. Realized cooling will be smaller.

- **Two scenarios bracket; they are not a confidence interval.** No Monte Carlo over species, leaf area or mortality.

- **One hot clear day,** not a multi-day heatwave with pavement-heat-storage buildup.

- **No exposure weighting.** Per-pixel cooling, not per-pedestrian-hour. Translating to health benefit needs foot-traffic data we don't have.

<!--
SPEAKER NOTES:
Five limitations to walk through quickly.

ONE — uniform met forcing. HRRR is 3 km cells; I apply one row per hour to every pixel in my 2 km tile. Practically, only the radiation field varies cell-to-cell. Real urban canyons have lower wind, real trees transpire, real shaded zones have lower air temperature than sunlit ones. None of those amplifying effects are in my model. They would all STRENGTHEN the cooling estimate. So −5.8°C should be read as a radiation-only lower bound.

TWO — 100% plant and survival. Urban first-5-year street-tree mortality is typically 20-40%. Realized cooling at any specific site is somewhat less than I report.

THREE — two scenarios are sensitivity points, not a confidence interval. They don't propagate species, leaf area, mortality, or MULC misclassification. EnviroAtlas's own accuracy assessment puts MULC error at about 17%. A real Monte Carlo over those would produce a true CI; I haven't done that.

FOUR — single day. Multi-day heat waves behave differently — pavement stores heat overnight, the next day starts hotter. Canopy cooling may amplify during heatwaves due to reduced overnight storage in shaded surfaces.

FIVE — no exposure weighting. "−5.8°C at planted pixels" is per-pixel. Translating to public-health benefit depends on whether actual pedestrians spend time at those pixels. Bus stops, sidewalks people walk? Or driven by sidewalk-engineering constraints unrelated to foot traffic? Without pedestrian-density data, I can't translate cooling to people-hours of heat-stress reduction.
-->

---

# Conclusion

- **Finding.** On a heatwave day, Durham's planned plantings deliver **−4.7 to −5.8 °C UTCI** at planted pixels (typically one WHO category drop). Tile-wide cooling: 0.01 °C. Intervention is **local, not citywide**.

- **Method.** A pipeline that fuses 2015 NC Phase 3 LiDAR, 2026 Overture building footprints, EnviroAtlas land cover, and HRRR weather into co-registered 1 m rasters that any SOLWEIG run can ingest without city-specific data access.

- **Future work.** Priority one is on-site Tmrt validation at planted sites with globe-thermometer loggers. Replacing the two-scenario bracket with a Monte Carlo over species, mortality, and MULC error would yield a true confidence interval. Extending to multi-day heatwaves across all 8 EPA-priority neighborhoods would let us estimate cumulative citywide impact.

<small class="citation">Code &amp; data: <code>github.com/arohan/radiant-temperature</code></small>

<!--
SPEAKER NOTES:
Three takeaways.

FINDING. On a heatwave day — and I emphasize "on a heatwave day" because that's the scoping — Durham's planned plantings drop feels-like temperature by 4.7 to 5.8°C at the planting sites themselves, conditional on full planting and survival. That's typically one WHO category — usually extreme to very strong. Tile-wide cooling is just 0.01°C because the intervention only modifies 0.15% of pixels. The right framing is per-planted-spot, not citywide.

METHODOLOGICAL CONTRIBUTION. Overture-gated Building DSM. Lindberg and Grimmond's 2011 recipe required proprietary city footprints, which limited reproducibility. By using Overture Maps Foundation as the footprint source, the entire pipeline runs on open data. Anyone running SOLWEIG anywhere in the world can use this exact pipeline. I think this is the most generalizable piece of the work.

FUTURE WORK. The single most important next step is on-site validation — $200 globe-thermometer loggers at planted sites, model vs measurement over a season. Beyond that: Monte Carlo over species, mortality, and MULC error to produce a real confidence interval; extension to multi-day heatwaves and all 8 EPA-priority neighborhoods to quantify cumulative impact; and per-pedestrian exposure weighting using foot-traffic data.

Everything is on GitHub. Thank you. Happy to take questions.
-->

---

<!-- _class: ref -->

# References & acknowledgements

<div style="font-size: 17px;">

- **Lindberg, F., Holmer, B., Thorsson, S.** (2008). SOLWEIG 1.0 — Modelling spatial variations of 3D radiant fluxes and mean radiant temperature in complex urban settings. *Int. J. Biometeorology* 52, 697–713.
- **Lindberg, F., Grimmond, C.S.B.** (2011). The influence of vegetation and building morphology on shadow patterns and mean radiant temperatures. *Theor. Appl. Climatol.* 105, 311–323.
- **Bröde, P. et al.** (2012). Deriving the operational procedure for the Universal Thermal Climate Index (UTCI). *Int. J. Biometeorology* 56, 481–494.
- **Kamath, H. G., Sudharsan, N., Singh, M., Wallenberg, N., Lindberg, F., Niyogi, D.** (2026). SOLWEIG-GPU: GPU-Accelerated Thermal Comfort Modeling Framework for Urban Digital Twins. *Journal of Open Source Software* 11(118), 9535.
- **Lindberg, F. et al.** (2018). Urban Multi-scale Environmental Predictor (UMEP): An integrated tool for city-based climate services. *Environmental Modelling & Software* 99, 70–87.

**Data sources** &nbsp; NC Spatial Data Downloads (LiDAR Phase 3) · NOAA Digital Coast LAZ bucket 6209 · Overture Maps Foundation · EPA EnviroAtlas Durham MULC · NOAA HRRR via dynamical.org · Iowa Mesonet ASOS · Durham Open Data Portal · Open-Meteo ERA5

</div>


