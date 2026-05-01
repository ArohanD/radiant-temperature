import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _intro(mo):
    mo.md(r"""
    # Notebook 3. Analysis and figures

    This notebook reads the SOLWEIG outputs produced by
    [`notebooks/1_run_scenarios.py`](1_run_scenarios.py) and reproduces
    the headline statistics and figures used in the conference deck.

    The analysis is reported at the **peak hour**, defined as the hour
    of the simulation day with the highest tile-mean Tmrt over
    non-roof cells in the baseline run. For Hayti on 2025-06-23 this
    is 15:00 local time.

    Two summary statistics anchor the discussion:

    - **ΔTmrt (median, planted pixels).** The median change in mean
      radiant temperature at the cells modified by the planting. This
      quantifies the local radiative effect of the new canopy.
    - **ΔUTCI (median, planted pixels).** The median change in the
      Universal Thermal Climate Index at the same cells. UTCI bundles
      air temperature, humidity, wind, and the radiation field into a
      single pedestrian-relevant temperature.
    """)
    return


@app.cell
def _setup():
    import sys
    from pathlib import Path
    REPO = Path(__file__).resolve().parent.parent
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import marimo as mo

    return REPO, mo


@app.cell(hide_code=True)
def _section_prefix(mo):
    mo.md(r"""
    ## 1. Run prefix

    Pick the run prefix to analyse. The dropdown lists every prefix
    that has a baseline folder under `inputs/processed/`.
    """)
    return


@app.cell
def _prefix_input(REPO, mo):
    _bases = sorted([p.name.replace("_baseline", "")
                      for p in (REPO / "inputs/processed").glob("*_baseline")])
    if not _bases:
        prefix = mo.ui.text(value="durham_hayti", label="Output prefix:")
    else:
        prefix = mo.ui.dropdown(options=_bases, value=_bases[0],
                                  label="Run prefix:")
    prefix
    return (prefix,)


@app.cell
def _aoi_config(REPO, mo, prefix):
    import os
    os.environ["OUTPUT_PREFIX"] = prefix.value
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, SIM_DATE, baseline_dir, output_root)
    base = baseline_dir(prefix.value)
    out_root = output_root(prefix.value)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "figures").mkdir(exist_ok=True)
    config_md = mo.md(
        f"- baseline: `{base.relative_to(REPO)}`\n"
        f"- output: `{out_root.relative_to(REPO)}`\n"
        f"- AOI: `{AOI_NAME}`, simulation date: `{SIM_DATE}`"
    )
    config_md
    return AOI_NAME, SIM_DATE


@app.cell(hide_code=True)
def _section_headline(mo):
    mo.md(r"""
    ## 2. Headline statistics

    For each scenario, the cell below computes the peak-hour median
    ΔTmrt and ΔUTCI at the planted pixels, the rate at which planted
    pixels cross from extreme heat stress (UTCI > 38 °C) to a lower
    category, and the worst-cooled pixel.

    The expected magnitudes for Hayti are roughly −4.7 °C ΔUTCI for
    the year 10 scenario and −5.8 °C ΔUTCI for the mature scenario.
    """)
    return


@app.cell
def _headline(mo, prefix):
    from src.evaluate import scenario_headline, write_diff_geotiffs
    diff_info = write_diff_geotiffs(prefix.value)
    headline_rows = [scenario_headline(prefix.value, _scen)
                       for _scen in ("year10", "mature")]
    _cards = []
    for _r in headline_rows:
        _cards.append(
            f"### {_r['scenario']}\n\n"
            f"- Peak hour: **{_r['peak_hour']:02d}:00**\n"
            f"- ΔTmrt at planted pixels (median): "
            f"**{_r.get('planted_dtmrt_median', float('nan')):+.2f} °C**\n"
            f"- ΔUTCI at planted pixels (median): "
            f"**{_r.get('planted_dutci_median', float('nan')):+.2f} °C**\n"
            f"- Planted pixels: {_r.get('planted_pixels', 0):,}\n"
            f"- WHO category drop rate: "
            f"{_r.get('who_category_drop_pct', 0):.1f}%"
        )
    headline_md = mo.md("\n\n".join(_cards))
    headline_md
    return (headline_rows,)


@app.cell
def _headline_text(AOI_NAME, REPO, SIM_DATE, headline_rows, mo, prefix):
    from src.aoi import AOI_SIZE_KM
    _out = REPO / f"outputs/{prefix.value}/headline.txt"
    _lines = [
        f"Durham planted-tree intervention, peak hour, {SIM_DATE}",
        "",
        f"AOI: {AOI_NAME}, {AOI_SIZE_KM:g} km x {AOI_SIZE_KM:g} km tile.",
        "",
    ]
    for _r in headline_rows:
        _lines.append(
            f"  {_r['scenario']:<7s}  dTmrt {_r.get('planted_dtmrt_median', float('nan')):+.2f} C  "
            f"dUTCI {_r.get('planted_dutci_median', float('nan')):+.2f} C  "
            f"(min dTmrt {_r.get('planted_dtmrt_min', float('nan')):+.2f} C)"
        )
    _out.write_text("\n".join(_lines) + "\n")
    headline_text_md = mo.md(f"Wrote `{_out.relative_to(REPO)}`.")
    headline_text_md
    return


@app.cell(hide_code=True)
def _section_figures(mo):
    mo.md(r"""
    ## 3. Figures

    The remaining cells regenerate every figure used in the conference
    deck other than the SOLWEIG explainer diagram, which is a
    hand-drawn schematic and does not depend on the analysis output.
    Each figure function reads the merged baseline and scenario
    rasters and writes a PNG under
    `figures/durham_hayti/slides/`.
    """)
    return


@app.cell(hide_code=True)
def _section_fig1(mo):
    mo.md(r"""
    ### Figure 1. Three-panel ΔUTCI

    Baseline UTCI at peak hour, mature-scenario UTCI at peak hour, and
    the difference between the two. The cooling is concentrated at the
    planting sites with limited spillover to neighbouring cells.
    """)
    return


@app.cell
def _fig1(REPO, mo):
    from src import figures as _figures
    _figures.fig1_utci_three_panel_mature()
    _path = REPO / "figures/durham_hayti/slides/fig1_utci_three_panel_mature.png"
    if _path.exists():
        fig1_img = mo.image(src=str(_path), width=900)
    else:
        fig1_img = mo.md("Figure 1 unavailable. SOLWEIG outputs missing.")
    fig1_img
    return


@app.cell(hide_code=True)
def _section_fig2(mo):
    mo.md(r"""
    ### Figure 2. ΔUTCI histogram

    Distribution of ΔUTCI values at the planted pixels. The mode sits
    near zero because most pixels in the disk are partly shaded by
    existing canopy or buildings, and the long left tail captures the
    sites where the new canopy intercepts direct beam radiation.
    """)
    return


@app.cell
def _fig2(REPO, mo):
    from src import figures as _figures
    _figures.fig2_utci_histogram()
    _path = REPO / "figures/durham_hayti/slides/fig2_utci_histogram.png"
    if _path.exists():
        fig2_img = mo.image(src=str(_path), width=900)
    else:
        fig2_img = mo.md("Figure 2 unavailable.")
    fig2_img
    return


@app.cell(hide_code=True)
def _section_fig3(mo):
    mo.md(r"""
    ### Figure 3. Diurnal Tmrt and UTCI

    Hourly tile-mean Tmrt and UTCI for the baseline and the two
    scenarios. The scenario curves diverge from the baseline only
    during daylight hours.
    """)
    return


@app.cell
def _fig3(REPO, mo):
    from src import figures as _figures
    _figures.fig3_diurnal_dual()
    _path = REPO / "figures/durham_hayti/slides/fig3_diurnal_dual.png"
    if _path.exists():
        fig3_img = mo.image(src=str(_path), width=900)
    else:
        fig3_img = mo.md("Figure 3 unavailable.")
    fig3_img
    return


@app.cell(hide_code=True)
def _section_fig_study(mo):
    mo.md(r"""
    ### Study site

    Two-panel map showing the Durham city context and a zoom into the
    densest cluster of planting sites within the AOI.
    """)
    return


@app.cell
def _fig_study(REPO, mo):
    from src import figures as _figures
    _figures.fig_study_site()
    _path = REPO / "figures/durham_hayti/slides/study_site.png"
    if _path.exists():
        study_img = mo.image(src=str(_path), width=900)
    else:
        study_img = mo.md("Study-site figure unavailable.")
    study_img
    return


@app.cell(hide_code=True)
def _section_fig_panels(mo):
    mo.md(r"""
    ### Five raster panels

    DSM, DEM, canopy CDSM, land cover, and the planting-site point
    layer. This is the canonical input set that SOLWEIG consumes.
    """)
    return


@app.cell
def _fig_panels(REPO, mo):
    from src import figures as _figures
    _figures.fig_data_panels()
    _path = REPO / "figures/durham_hayti/slides/data_panels.png"
    if _path.exists():
        panels_img = mo.image(src=str(_path), width=900)
    else:
        panels_img = mo.md("Data-panels figure unavailable.")
    panels_img
    return


@app.cell(hide_code=True)
def _section_fig_dsm(mo):
    mo.md(r"""
    ### Building DSM correction

    Side-by-side comparison of the raw LiDAR first-return DSM and the
    Overture-gated patched DSM. The third panel shows the difference,
    with red where the patch raised the surface and blue where it
    lowered the surface.
    """)
    return


@app.cell
def _fig_dsm(REPO, mo):
    from src import figures as _figures
    _figures.fig_dsm_correction()
    _path = REPO / "figures/durham_hayti/slides/dsm_correction.png"
    if _path.exists():
        dsm_img = mo.image(src=str(_path), width=900)
    else:
        dsm_img = mo.md("DSM-correction figure unavailable.")
    dsm_img
    return


@app.cell(hide_code=True)
def _section_fig_scen(mo):
    mo.md(r"""
    ### Scenario design

    Schematic of the two canopy scenarios with the disk size and
    height annotated.
    """)
    return


@app.cell
def _fig_scen(REPO, mo):
    from src import figures as _figures
    _figures.fig_scenario_design()
    _path = REPO / "figures/durham_hayti/slides/scenario_design.png"
    if _path.exists():
        scen_img = mo.image(src=str(_path), width=900)
    else:
        scen_img = mo.md("Scenario-design figure unavailable.")
    scen_img
    return


@app.cell(hide_code=True)
def _section_fig_validation(mo):
    mo.md(r"""
    ### Validation

    HRRR forcing compared against KRDU observations and Open-Meteo
    reanalysis. Modelled UTCI on grass cells compared against the
    Open-Meteo apparent-temperature product. The HRRR forcing tracks
    the airport observations within roughly 2 °C and modelled UTCI
    sits a few degrees above the apparent-temperature product because
    UTCI accounts for radiation loading.
    """)
    return


@app.cell
def _fig_validation(REPO, mo):
    from src import figures as _figures
    _figures.fig_validation()
    _path = REPO / "figures/durham_hayti/slides/validation.png"
    if _path.exists():
        val_img = mo.image(src=str(_path), width=900)
    else:
        val_img = mo.md("Validation figure unavailable.")
    val_img
    return


@app.cell(hide_code=True)
def _section_fig_lc(mo):
    mo.md(r"""
    ### Tmrt by land cover class

    Distribution of peak-hour Tmrt grouped by UMEP land cover class.
    Paved cells reach the highest values, water cells the lowest, and
    vegetated cells fall between the two.
    """)
    return


@app.cell
def _fig_lc(REPO, mo):
    from src import figures as _figures
    _figures.fig_landcover_tmrt()
    _path = REPO / "figures/durham_hayti/slides/landcover_tmrt.png"
    if _path.exists():
        lc_img = mo.image(src=str(_path), width=900)
    else:
        lc_img = mo.md("Land-cover Tmrt figure unavailable.")
    lc_img
    return


@app.cell(hide_code=True)
def _section_webapp(mo):
    mo.md(r"""
    ### Webapp screenshots

    The cell below renders three slide-ready PNG screenshots of the
    MapLibre inspector via headless Chrome. The cell is skipped when
    `google-chrome` is not on the PATH.
    """)
    return


@app.cell
def _webapp_screenshots(REPO, mo, prefix):
    import shutil as _sh
    if _sh.which("google-chrome") is None:
        webapp_md = mo.md("`google-chrome` not on PATH. Web screenshots skipped.")
    else:
        from src import inspector as _inspector
        _inspector.build_bundle(prefix=prefix.value)
        _written = _inspector.capture_screenshots(prefix=prefix.value)
        _rows = "\n".join(f"- `{p.relative_to(REPO)}`" for p in _written.values())
        webapp_md = mo.md(_rows)
    webapp_md
    return


if __name__ == "__main__":
    app.run()
