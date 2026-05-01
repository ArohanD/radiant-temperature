"""Notebook 1: end-to-end SOLWEIG runs for the baseline and two planting scenarios.

The notebook assumes that notebook 2 has produced a complete set of input
rasters under `inputs/processed/{prefix}_baseline/`. Each long-running cell
skips when the expected outputs already exist.
"""
import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell
def _setup():
    import sys
    from pathlib import Path
    REPO = Path(__file__).resolve().parent.parent
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import marimo as mo
    return REPO, mo


@app.cell
def _prefix_input(mo):
    """Output prefix selector. Folders under inputs/processed/ and outputs/
    are keyed by this string."""
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
        f"## Run configuration\n\n"
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


@app.cell
def _preflight(SIM_DATE, base, mo):
    """Confirm that notebook 2 has produced a complete input set."""
    _needed = ["Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif",
                f"ownmet_{SIM_DATE}.txt"]
    missing_inputs = [n for n in _needed if not (base / n).exists()]
    if missing_inputs:
        preflight_md = mo.md(
            f"**Missing inputs:** {missing_inputs}. Run "
            f"`marimo edit notebooks/2_prepare_buildings.py` first."
        ).callout(kind="danger")
    else:
        preflight_md = mo.md(
            "All baseline inputs present."
        ).callout(kind="success")
    preflight_md
    return (missing_inputs,)


@app.cell
def _baseline_run(SIM_DATE, TILE_OVERLAP, TILE_SIZE, base, missing_inputs, mo):
    """Fire SOLWEIG on the baseline rasters. Skips when outputs are complete."""
    if missing_inputs:
        baseline_result = {"skipped": True, "reason": "missing inputs"}
    else:
        from src.solweig_runner import run as _run_solweig
        baseline_result = _run_solweig(base, SIM_DATE,
                                        tile_size=TILE_SIZE,
                                        tile_overlap=TILE_OVERLAP)
    base_md = mo.md(f"### Baseline SOLWEIG\n\n```\n{baseline_result}\n```")
    base_md
    return (baseline_result,)


@app.cell
def _scenarios(REPO, SIM_DATE, base, mo, prefix, scenario_dir):
    """Burn year10 and mature canopy disks into scenario folders."""
    from src.scenarios import load_planting_sites, burn_canopy
    from src.aoi import TILE_BBOX as _TILE_BBOX
    _trees_geojson = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    if not _trees_geojson.exists():
        scenarios_md = mo.md("**Missing planting-sites GeoJSON.** Run notebook 0.").callout("danger")
        scenario_sites = None
        burn_results = {}
    else:
        scenario_sites = load_planting_sites(_trees_geojson, _TILE_BBOX)
        burn_results = {}
        for _scen in ("year10", "mature"):
            burn_results[_scen] = burn_canopy(
                base, scenario_dir(_scen, prefix.value), _scen, scenario_sites,
                SIM_DATE,
            )
        _summary = "\n".join(f"- **{k}** — `{v}`" for k, v in burn_results.items())
        scenarios_md = mo.md(
            f"### Scenario inputs\n\n"
            f"Planting sites in tile: `{len(scenario_sites)}`\n\n{_summary}"
        )
    scenarios_md
    return (burn_results,)


@app.cell
def _scenario_runs(SIM_DATE, TILE_OVERLAP, TILE_SIZE, burn_results, mo, prefix,
                    scenario_dir):
    """Run SOLWEIG for each scenario folder."""
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
    _rows = "\n".join(f"- **{k}** — `{v}`" for k, v in scenario_results.items())
    sruns_md = mo.md(f"### Scenario SOLWEIG runs\n\n{_rows}")
    sruns_md
    return (scenario_results,)


@app.cell
def _sanity(baseline_result, mo, prefix):
    """Physical-plausibility checks on the baseline output."""
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
        sanity_md = mo.md(f"### Baseline sanity report\n\n{_table}\n\n{_note}")
    sanity_md
    return


@app.cell
def _diffs_and_inspector(mo, prefix, scenario_results):
    """Write peak-hour diff GeoTIFFs and rebuild the inspector to include
    every output layer."""
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
            f"### Final inspector\n\n"
            f"Peak hour: **{_diff_info['peak_hour']:02d}:00**.\n\n"
            f"[Open inspector in new tab]({_url})"
        )
        final_iframe = mo.iframe(_url, width="100%", height=650)
    final_md
    final_iframe
    return


if __name__ == "__main__":
    app.run()
