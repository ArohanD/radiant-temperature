import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _intro(mo):
    mo.md(r"""
    # Notebook 2. SOLWEIG-ready rasters

    This notebook converts the raw inputs gathered in
    [`notebooks/0_fetch_data.py`](0_fetch_data.py) into the four
    co-registered rasters that SOLWEIG requires:

    | raster | content |
    |---|---|
    | `Building_DSM.tif` | Surface elevation of ground plus buildings (no canopy). |
    | `DEM.tif` | Bare-earth terrain elevation. |
    | `Trees.tif` | Canopy heights (CDSM). |
    | `Landcover.tif` | UMEP-coded surface classes. |

    The building DSM follows the canonical recipe of
    [Lindberg and Grimmond (2011)](https://link.springer.com/article/10.1007/s00704-010-0382-8):
    ground returns from LiDAR, with elevations inside building footprints
    replaced by the higher of the LiDAR roof elevation and the Overture
    roof height. This recipe filters out canopy, billboards, and laser
    noise that the raw LiDAR DSM contains.

    Each cell is idempotent. The PDAL retrieval is the slowest step on
    a fresh AOI and is approximately ten minutes for a 2 km × 2 km tile.
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
def _section_config(mo):
    mo.md(r"""
    ## 1. Configuration

    Outputs land in the prefixed baseline folder defined by `OUTPUT_PREFIX`.
    Editing `src/aoi.py` is the recommended way to change the AOI.
    """)
    return


@app.cell
def _aoi_config(REPO, mo):
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, OUTPUT_PREFIX, PROCESSING_BBOX, baseline_dir)
    base = baseline_dir(OUTPUT_PREFIX)
    base.mkdir(parents=True, exist_ok=True)
    config_md = mo.md(f"Output folder: `{base.relative_to(REPO)}`")
    config_md
    return AOI_NAME, PROCESSING_BBOX, base


@app.cell(hide_code=True)
def _section_lidar(mo):
    mo.md(r"""
    ## 2. LiDAR first-return DSM

    The cell below issues a PDAL pipeline against the NC Phase 3 LiDAR
    Entwine Point Tile store and writes a 1 m first-return raster
    clipped to the processing bounding box. The output captures every
    return surface, so it includes ground, buildings, canopy, and
    artefacts. The Overture-gated patch in section 6 reduces this to
    ground plus buildings.
    """)
    return


@app.cell
def _lidar_dsm(PROCESSING_BBOX, REPO, base, mo):
    from src.buildings import pull_lidar_dsm
    lidar_dsm_path = base / "Building_DSM.preMS.tif"
    if not lidar_dsm_path.exists():
        pull_lidar_dsm(PROCESSING_BBOX, lidar_dsm_path)
    lidar_dsm_md = mo.md(
        f"`{lidar_dsm_path.relative_to(REPO)}` "
        f"({lidar_dsm_path.stat().st_size // 1024 // 1024:,} MB)"
    )
    lidar_dsm_md
    return (lidar_dsm_path,)


@app.cell(hide_code=True)
def _section_dem(mo):
    mo.md(r"""
    ## 3. Bare-earth DEM

    The DEM is built from points classified as ground (`Classification == 2`)
    in the same LiDAR archive, then gap-filled with `gdal_fillnodata`. Holes
    under canopy and buildings are common in the raw ground returns and
    would otherwise bias the canopy height calculation in section 5.
    """)
    return


@app.cell
def _dem(PROCESSING_BBOX, REPO, base, mo):
    from src.buildings import build_dem
    dem_path = base / "DEM.tif"
    if not dem_path.exists():
        build_dem(PROCESSING_BBOX, dem_path)
    dem_md = mo.md(f"`{dem_path.relative_to(REPO)}`")
    dem_md
    return (dem_path,)


@app.cell(hide_code=True)
def _section_lc(mo):
    mo.md(r"""
    ## 4. Land cover

    EnviroAtlas ships MULC at 1 m in EPSG:26917. The cell below
    reprojects it onto the AOI grid in EPSG:32617, snapped to the
    processing bounding box. The reclassification to UMEP codes occurs
    in the next section, after the canopy heights have been derived
    from the DSM and DEM.
    """)
    return


@app.cell
def _landcover_raw(PROCESSING_BBOX, REPO, base, mo):
    from src.buildings import build_landcover_raw
    _src = REPO / "inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif"
    landcover_raw_path = base / "MULC_aligned.tif"
    if not landcover_raw_path.exists():
        build_landcover_raw(_src, PROCESSING_BBOX, landcover_raw_path)
    lc_raw_md = mo.md(f"`{landcover_raw_path.relative_to(REPO)}`")
    lc_raw_md
    return (landcover_raw_path,)


@app.cell(hide_code=True)
def _section_trees(mo):
    mo.md(r"""
    ## 5. Canopy CDSM

    Canopy heights are computed as `DSM minus DEM` on cells classified as
    trees by MULC. The result is written to `Trees.tif`. A pre-Overture
    UMEP land cover (`Landcover.preMS.tif`) is also written. The
    building class (UMEP code 2) is assigned in section 7 from the
    Overture footprints rather than from a height threshold, because a
    height threshold misclassifies canopy and billboards as buildings.
    """)
    return


@app.cell
def _trees_and_lc(
    REPO,
    base,
    dem_path,
    landcover_raw_path,
    lidar_dsm_path,
    mo,
):
    from src.buildings import build_trees_and_landcover
    trees_path = base / "Trees.tif"
    lc_pre_path = base / "Landcover.preMS.tif"
    if not (trees_path.exists() and lc_pre_path.exists()):
        build_trees_and_landcover(lidar_dsm_path, dem_path, landcover_raw_path,
                                    trees_path, lc_pre_path)
    trees_md = mo.md(
        f"`{trees_path.relative_to(REPO)}`\n\n"
        f"`{lc_pre_path.relative_to(REPO)}`"
    )
    trees_md
    return


@app.cell(hide_code=True)
def _section_overture(mo):
    mo.md(r"""
    ## 6. Overture footprints

    The Overture Foundation publishes open-licence building polygons
    with height attributes. Inside the AOI, roughly two-thirds of the
    polygons carry a measured height, which is more than sufficient for
    the recipe in section 7. Polygons without a height are still used
    as a footprint mask.
    """)
    return


@app.cell
def _overture_geojson(AOI_NAME, PROCESSING_BBOX, REPO, mo):
    from src.buildings import fetch_overture
    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    if not overture_path.exists():
        fetch_overture(AOI_NAME, PROCESSING_BBOX, overture_path)
    overture_md = mo.md(f"`{overture_path.relative_to(REPO)}`")
    overture_md
    return (overture_path,)


@app.cell(hide_code=True)
def _section_inspect_pre(mo):
    mo.md(r"""
    ## 7. Pre-patch inspection

    Open the inspector below and toggle on **Building DSM (raw LiDAR
    first-returns)** and the **3D buildings (Overture)** layers. The raw
    LiDAR surface is noisy and includes canopy and laser glints, which
    the Overture footprints (drawn as 3D extrusions) do not match. The
    next cell applies the patch that reconciles the two.
    """)
    return


@app.cell
def _inspect_pre(mo):
    from src import inspector as _inspector
    pre_bundle = _inspector.build_bundle()
    pre_url = _inspector.serve(pre_bundle)
    pre_md = mo.md(f"[Open inspector in a new tab]({pre_url})")
    pre_md
    pre_iframe = mo.iframe(pre_url, width="100%", height=600)
    pre_iframe
    return


@app.cell(hide_code=True)
def _section_patch(mo):
    mo.md(r"""
    ## 8. Apply the Overture-gated DSM patch

    For each cell in the AOI, the patched DSM is set as follows:

    - If the cell sits inside an Overture footprint, take the higher of
      the LiDAR roof elevation and the Overture roof elevation
      (`DEM + Overture height`). This recovers post-2015 buildings that
      the 2015 LiDAR missed and caps spurious laser noise above
      existing roofs.
    - Otherwise, set the cell to the DEM elevation. This removes
      canopy, billboards, and other tall non-building features from the
      building DSM.

    Land cover is updated in the same step: every cell inside an
    Overture footprint is reclassified as UMEP class 2 (building).
    """)
    return


@app.cell
def _patch(PROCESSING_BBOX, base, mo, overture_path):
    from src.buildings import patch_with_overture
    patch_stats = patch_with_overture(base, overture_path, PROCESSING_BBOX)
    _rows = "\n".join(f"| {k} | {v} |" for k, v in patch_stats.items())
    patch_md = mo.md("| metric | value |\n|---|---|\n" + _rows)
    patch_md
    return


@app.cell(hide_code=True)
def _section_inspect_post(mo):
    mo.md(r"""
    ## 9. Post-patch inspection

    The same inspector now contains the patched layers. The most
    informative overlay is **DSM diff (current minus raw LiDAR)**,
    which shows in red where the patch raised the DSM (typically a
    post-2015 building whose roof was missing from the 2015 LiDAR) and
    in blue where it lowered the DSM (canopy and noise that were not
    actually buildings).
    """)
    return


@app.cell
def _inspect_post(mo):
    from src import inspector as _inspector
    post_bundle = _inspector.build_bundle()
    post_url = _inspector.serve(post_bundle)
    post_md = mo.md(f"[Open inspector in a new tab]({post_url})")
    post_md
    post_iframe = mo.iframe(post_url, width="100%", height=600)
    post_iframe
    return


@app.cell(hide_code=True)
def _next_steps(mo):
    mo.md(r"""
    ## Next step

    With the four canonical rasters in place, run
    [`notebooks/1_run_scenarios.py`](1_run_scenarios.py) to fire the
    SOLWEIG baseline run and the two planting scenarios.
    """)
    return


if __name__ == "__main__":
    app.run()
