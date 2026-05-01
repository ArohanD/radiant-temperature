import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _intro(mo):
    mo.md(
        r"""
        # Notebook 1. SOLWEIG runs

        SOLWEIG is the Solar and LongWave Environmental Irradiance Geometry
        model of [Lindberg, Holmer, and Thorsson (2008)](https://link.springer.com/article/10.1007/s00484-008-0162-7).
        Given a building DSM, a DEM, a canopy CDSM, a UMEP land cover, and an
        hourly meteorological forcing, the model resolves the six radiation
        fluxes that govern the radiative load on a vertical pedestrian and
        produces hourly mean radiant temperature (Tmrt) and Universal Thermal
        Climate Index (UTCI) rasters.

        This notebook fires three SOLWEIG runs:

        1. **Baseline.** Current canopy.
        2. **Year 10 scenario.** Each planted site receives a 5 m × 5 m
           canopy disk at 5 m height, representing a five to ten year old
           tree.
        3. **Mature scenario.** Each planted site receives a 7 m × 7 m
           canopy disk at 12 m height, representing a roughly 25 year old
           tree.

        The two scenarios bracket the realistic range of canopy outcomes for
        the species mix that Durham Urban Forestry typically plants. Each
        long-running cell skips when the expected outputs are already on disk.
        """
    )
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
    mo.md(
        r"""
        ## 1. Run prefix

        The prefix below keys both the input folders
        (`inputs/processed/{prefix}_*`) and the output folders
        (`outputs/{prefix}/`). Use a different prefix to keep parameter
        sweeps from clobbering each other.
        """
    )
    return


@app.cell
def _prefix_input(mo):
    prefix = mo.ui.text(value="durham_hayti", label="Output prefix:")
    prefix
    return (prefix,)


@app.cell
def _aoi_config(REPO, mo, prefix):
    import os
    os.environ["OUTPUT_PREFIX"] = prefix.value
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, SIM_DATE, TILE_OVERLAP, TILE_SIZE,
                          baseline_dir, scenario_dir, output_root)
    base = baseline_dir(prefix.value)
    out_root = output_root(prefix.value)
    out_root.mkdir(parents=True, exist_ok=True)
    config_md = mo.md(
        f"| key | value |\n|---|---|\n"
        f"| AOI | `{AOI_NAME}` |\n"
        f"| simulation date | `{SIM_DATE}` |\n"
        f"| tile size | {TILE_SIZE} px |\n"
        f"| tile overlap | {TILE_OVERLAP} px |\n"
        f"| baseline folder | `{base.relative_to(REPO)}` |\n"
        f"| outputs folder | `{out_root.relative_to(REPO)}` |"
    )
    config_md
    return SIM_DATE, TILE_OVERLAP, TILE_SIZE, base, scenario_dir


@app.cell(hide_code=True)
def _section_preflight(mo):
    mo.md(
        r"""
        ## 2. Pre-flight check

        SOLWEIG needs all four canonical rasters and the own-met file.
        Notebook 2 produces them. The cell below confirms they are in place.
        If anything is missing, run notebook 2 before continuing.
        """
    )
    return


@app.cell
def _preflight(SIM_DATE, base, mo):
    _needed = ["Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif",
                f"ownmet_{SIM_DATE}.txt"]
    missing_inputs = [n for n in _needed if not (base / n).exists()]
    if missing_inputs:
        preflight_md = mo.md(
            f"**Missing inputs:** {missing_inputs}. "
            f"Run `marimo edit notebooks/2_prepare_buildings.py` first."
        ).callout(kind="danger")
    else:
        preflight_md = mo.md("All baseline inputs present.").callout(kind="success")
    preflight_md
    return (missing_inputs,)


@app.cell(hide_code=True)
def _section_baseline(mo):
    mo.md(
        r"""
        ## 3. Baseline SOLWEIG run

        Wall-time on a 2 km × 2 km tile is roughly 30 minutes on CPU and
        roughly 2 minutes on an A6000. The wrapper detects the GPU
        automatically. The cell skips entirely when the expected per-tile
        TMRT and UTCI files are already on disk.
        """
    )
    return


@app.cell
def _baseline_run(SIM_DATE, TILE_OVERLAP, TILE_SIZE, base, missing_inputs, mo):
    if missing_inputs:
        baseline_result = {"skipped": True, "reason": "missing inputs"}
    else:
        from src.solweig_runner import run as _run_solweig
        baseline_result = _run_solweig(base, SIM_DATE,
                                        tile_size=TILE_SIZE,
                                        tile_overlap=TILE_OVERLAP)
    base_md = mo.md(f"```\n{baseline_result}\n```")
    base_md
    return (baseline_result,)


@app.cell(hide_code=True)
def _section_scenarios(mo):
    mo.md(
        r"""
        ## 4. Scenario inputs

        Each planted site is rasterised as a square canopy disk centred on
        the planting point. The cells of `Trees.tif` inside the disk are set
        to the canopy height for the scenario, and the corresponding
        `Landcover.tif` cells are reclassified to UMEP code 5 (vegetation).
        Building cells are left untouched on the assumption that a planting
        sited inside a building footprint is a data error.

        The `walls/` and `aspect/` preprocessing tiles are symlinked from
        the baseline folder. These products depend only on the building DSM
        (which is identical across scenarios), so reusing them avoids
        roughly 20 minutes of CPU work per scenario run.
        """
    )
    return


@app.cell
def _scenarios(REPO, SIM_DATE, base, mo, prefix, scenario_dir):
    from src.scenarios import load_planting_sites, burn_canopy
    from src.aoi import TILE_BBOX as _TILE_BBOX
    _trees_geojson = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    if not _trees_geojson.exists():
        scenarios_md = mo.md("**Missing planting-sites GeoJSON.** Run notebook 0.").callout("danger")
    else:
        scenario_sites = load_planting_sites(_trees_geojson, _TILE_BBOX)
        burn_results = {}
        for _scen in ("year10", "mature"):
            burn_results[_scen] = burn_canopy(
                base, scenario_dir(_scen, prefix.value), _scen, scenario_sites,
                SIM_DATE,
            )
        _summary = "\n".join(f"- **{k}**: `{v}`" for k, v in burn_results.items())
        scenarios_md = mo.md(
            f"Planting sites in tile: `{len(scenario_sites)}`\n\n{_summary}"
        )
    scenarios_md
    return


@app.cell(hide_code=True)
def _section_scenario_runs(mo):
    mo.md(
        r"""
        ## 5. Scenario SOLWEIG runs

        With the cached `walls/` and `aspect/` tiles in place, each scenario
        runs in roughly the same time as the baseline. Both scenarios run
        sequentially below; outputs land in
        `inputs/processed/{prefix}_scenario_{name}/output_folder/`.
        """
    )
    return


@app.cell
def _scenario_runs(SIM_DATE, TILE_OVERLAP, TILE_SIZE, mo, prefix, scenario_dir):
    from src.solweig_runner import run as _run_solweig
    scenario_results = {}
    for _scen in ("year10", "mature"):
        _d = scenario_dir(_scen, prefix.value)
        if not (_d / "Trees.tif").exists():
            scenario_results[_scen] = {"skipped": True, "reason": "scenario not built"}
            continue
        scenario_results[_scen] = _run_solweig(_d, SIM_DATE,
                                                tile_size=TILE_SIZE,
                                                tile_overlap=TILE_OVERLAP)
    _rows = "\n".join(f"- **{k}**: `{v}`" for k, v in scenario_results.items())
    sruns_md = mo.md(_rows)
    sruns_md
    return (scenario_results,)


@app.cell(hide_code=True)
def _section_sanity(mo):
    mo.md(
        r"""
        ## 6. Baseline sanity report

        Three physical checks confirm that the baseline output is plausible:

        1. **Hot-pavement check.** Paved cells should be at least 2 °C
           hotter than vegetated cells at peak hour.
        2. **Pre-dawn uniformity.** With no solar input, Tmrt should be
           almost spatially uniform at 03:00.
        3. **Solar geometry.** The discovered peak hour and the implied
           shadow direction should match a NOAA solar-position estimate
           for the AOI.
        """
    )
    return


@app.cell
def _sanity(baseline_result, mo, prefix):
    if baseline_result.get("skipped") and baseline_result.get("reason") == "missing inputs":
        sanity_md = mo.md("Sanity check unavailable until baseline run completes.")
    else:
        from src.evaluate import baseline_checks
        _report = baseline_checks(prefix.value)
        _fails = _report["failed_gates"]
        _rows = []
        _rows.append(f"| peak hour | {_report['peak_hour']:02d}:00 |")
        _rows.append(f"| solar altitude at peak | {_report['solar_altitude_at_peak']:.1f}° |")
        _rows.append(f"| pre-dawn Tmrt std | {_report['pre_dawn_std']:.2f} °C |")
        for _cls, _val in _report["tmrt_per_class_at_peak"].items():
            _rows.append(f"| Tmrt at peak ({_cls}) | {_val:.1f} °C |")
        for _k, _v in _report["utci_at_peak"].items():
            _rows.append(f"| UTCI at peak ({_k}) | {_v:.2f} |")
        _table = "| metric | value |\n|---|---|\n" + "\n".join(_rows)
        _note = "All gates passed." if not _fails else f"Failed gates: {_fails}"
        sanity_md = mo.md(f"{_table}\n\n{_note}")
    sanity_md
    return


@app.cell(hide_code=True)
def _section_inspector(mo):
    mo.md(
        r"""
        ## 7. Final inspector

        The inspector below carries every layer in the analysis: raw and
        patched DSM, the two scenario canopy disks as 3D extrusions, the
        baseline TMRT and UTCI fields at peak hour, and the peak-hour
        cooling rasters (ΔTmrt and ΔUTCI) for both scenarios. Toggle layers
        from the panel on the left.
        """
    )
    return


@app.cell
def _diffs_and_inspector(mo, prefix, scenario_results):
    if any(r.get("skipped") and r.get("reason") for r in scenario_results.values()):
        final_md = mo.md("Inspector view requires both scenarios to complete.")
        final_iframe = None
    else:
        from src.evaluate import write_diff_geotiffs
        from src import inspector as _inspector
        _diff_info = write_diff_geotiffs(prefix.value)
        _bundle = _inspector.build_bundle(prefix=prefix.value)
        _url = _inspector.serve(_bundle)
        final_md = mo.md(
            f"Peak hour: **{_diff_info['peak_hour']:02d}:00**.\n\n"
            f"[Open inspector in a new tab]({_url})"
        )
        final_iframe = mo.iframe(_url, width="100%", height=650)
    final_md
    final_iframe
    return


@app.cell(hide_code=True)
def _next_steps(mo):
    mo.md(
        r"""
        ## Next step

        Run [`notebooks/3_analyze_results.py`](3_analyze_results.py) to
        compute the headline statistics and reproduce the figures used in
        the conference deck.
        """
    )
    return


if __name__ == "__main__":
    app.run()
