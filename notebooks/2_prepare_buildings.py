"""Notebook 2: derive the four SOLWEIG-ready rasters from the raw inputs.

The pipeline pulls a 1 m DSM and DEM from NC Phase 3 LiDAR via PDAL, reprojects
the EnviroAtlas MULC raster onto the same grid, derives the canopy CDSM
(Trees.tif), and applies the Overture footprint patch that produces the final
ground-plus-buildings DSM. Each step is idempotent. Two interactive views
(pre- and post-patch) reproduce the visualisation used in the conference
deck for the Overture correction.
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
def _aoi_config(REPO, mo):
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, OUTPUT_PREFIX, PROCESSING_BBOX, baseline_dir)
    base = baseline_dir(OUTPUT_PREFIX)
    base.mkdir(parents=True, exist_ok=True)
    config_md = mo.md(
        f"## Output folder\n\n`{base.relative_to(REPO)}`\n\n"
        f"All rasters from this notebook are written into that path."
    )
    config_md
    return AOI_NAME, PROCESSING_BBOX, base


@app.cell
def _lidar_dsm(PROCESSING_BBOX, REPO, base, mo):
    """First-return DSM via PDAL on NC Phase 3 LiDAR (EPT)."""
    from src.buildings import pull_lidar_dsm
    lidar_dsm_path = base / "Building_DSM.preMS.tif"
    if not lidar_dsm_path.exists():
        pull_lidar_dsm(PROCESSING_BBOX, lidar_dsm_path)
    lidar_dsm_md = mo.md(
        f"### LiDAR first-return DSM\n\n"
        f"`{lidar_dsm_path.relative_to(REPO)}` "
        f"({lidar_dsm_path.stat().st_size // 1024 // 1024:,} MB)"
    )
    lidar_dsm_md
    return (lidar_dsm_path,)


@app.cell
def _dem(PROCESSING_BBOX, REPO, base, mo):
    """Bare-earth DEM from Class=2 ground returns plus gdal_fillnodata."""
    from src.buildings import build_dem
    dem_path = base / "DEM.tif"
    if not dem_path.exists():
        build_dem(PROCESSING_BBOX, dem_path)
    dem_md = mo.md(f"### DEM (bare earth)\n\n`{dem_path.relative_to(REPO)}`")
    dem_md
    return (dem_path,)


@app.cell
def _landcover_raw(PROCESSING_BBOX, REPO, base, mo):
    """Reproject EnviroAtlas MULC onto the AOI grid (pre-Overture)."""
    from src.buildings import build_landcover_raw
    _src = REPO / "inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif"
    landcover_raw_path = base / "MULC_aligned.tif"
    if not landcover_raw_path.exists():
        build_landcover_raw(_src, PROCESSING_BBOX, landcover_raw_path)
    lc_raw_md = mo.md(f"### MULC reprojected\n\n`{landcover_raw_path.relative_to(REPO)}`")
    lc_raw_md
    return (landcover_raw_path,)


@app.cell
def _trees_and_lc(REPO, base, dem_path, lidar_dsm_path, landcover_raw_path, mo):
    """Derive Trees CDSM and the MULC-only Landcover. The Overture patch in
    the next cell stamps the building class onto Landcover."""
    from src.buildings import build_trees_and_landcover
    trees_path = base / "Trees.tif"
    lc_pre_path = base / "Landcover.preMS.tif"
    if not (trees_path.exists() and lc_pre_path.exists()):
        build_trees_and_landcover(lidar_dsm_path, dem_path, landcover_raw_path,
                                    trees_path, lc_pre_path)
    trees_md = mo.md(
        f"### Trees CDSM and raw Landcover\n\n"
        f"`{trees_path.relative_to(REPO)}`\n\n"
        f"`{lc_pre_path.relative_to(REPO)}`"
    )
    trees_md
    return


@app.cell
def _overture_geojson(AOI_NAME, PROCESSING_BBOX, REPO, mo):
    """Ensure the Overture building footprint GeoJSON is present."""
    from src.buildings import fetch_overture
    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    if not overture_path.exists():
        fetch_overture(AOI_NAME, PROCESSING_BBOX, overture_path)
    overture_md = mo.md(f"### Overture buildings\n\n`{overture_path.relative_to(REPO)}`")
    overture_md
    return (overture_path,)


@app.cell
def _inspect_pre(REPO, base, mo, overture_path):
    """Pre-patch view: raw LiDAR DSM with Overture footprints overlaid."""
    from src import inspector as _inspector
    pre_bundle = _inspector.build_bundle()
    pre_url = _inspector.serve(pre_bundle)
    pre_md = mo.md(
        "### Pre-patch inspection\n\n"
        "Raw LiDAR first-returns include canopy, billboards, and laser noise. "
        "The Overture overlay shows the footprints that the next cell uses to "
        "gate which cells are treated as buildings.\n\n"
        f"[Open in new tab]({pre_url})"
    )
    pre_md
    pre_iframe = mo.iframe(pre_url, width="100%", height=600)
    pre_iframe
    return


@app.cell
def _patch(PROCESSING_BBOX, base, mo, overture_path):
    """Apply the Overture-gated patch."""
    from src.buildings import patch_with_overture
    patch_stats = patch_with_overture(base, overture_path, PROCESSING_BBOX)
    _rows = "\n".join(f"| {k} | {v} |" for k, v in patch_stats.items())
    patch_md = mo.md(
        "### Overture-gated DSM patch\n\n"
        "| metric | value |\n|---|---|\n" + _rows
    )
    patch_md
    return (patch_stats,)


@app.cell
def _inspect_post(mo, patch_stats):
    """Post-patch view. Building heights now reflect the canonical recipe:
    `max(LiDAR, DEM + Overture_height)` inside footprints, ground elsewhere.
    """
    from src import inspector as _inspector
    post_bundle = _inspector.build_bundle()
    post_url = _inspector.serve(post_bundle)
    post_md = mo.md(
        "### Post-patch inspection\n\n"
        "The DSM now contains buildings only. Compare the DSM-diff layer to "
        "see what was removed (canopy, noise) and what was added (post-2015 "
        "structures whose roofs the LiDAR missed).\n\n"
        f"[Open in new tab]({post_url})"
    )
    post_md
    post_iframe = mo.iframe(post_url, width="100%", height=600)
    post_iframe
    return


if __name__ == "__main__":
    app.run()
