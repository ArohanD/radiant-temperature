import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _intro(mo):
    mo.md(r"""
    # Pedestrian heat impact of Durham's 2025–2028 tree planting

    Durham's 2025–2028 urban-canopy initiative places 8,500 trees across
    the city, with 85 percent of plantings concentrated in eight
    neighborhoods that the United States Environmental Protection
    Agency identifies as priority areas. Hayti, redlined in 1937 and
    physically bisected by the Durham Freeway in the 1960s, is one of
    those neighborhoods. This analysis quantifies the pedestrian
    heat-stress reduction the planting program delivers on the
    hottest clear day of summer, at one-meter resolution.

    The pipeline runs in five stages, all in this notebook:

    1. **Acquire** five public datasets (Durham planting sites,
       EnviroAtlas land cover, KRDU airport observations, NOAA HRRR
       meteorological forcing, Overture buildings) plus a NC Phase 3
       LiDAR check.
    2. **Build** four co-registered SOLWEIG-ready rasters from the
       LiDAR DSM, DEM, MULC land cover, and Overture footprints, using
       the [Lindberg and Grimmond (2011)](https://link.springer.com/article/10.1007/s00704-010-0382-8)
       Overture-gated patch recipe.
    3. **Run** [SOLWEIG](https://link.springer.com/article/10.1007/s00484-008-0162-7)
       three times: a baseline plus two planting scenarios (year 10 and
       mature canopy), using the GPU implementation of
       [Kamath et al. (2026)](https://joss.theoj.org/papers/10.21105/joss.09535).
    4. **Validate** the baseline output with three physical
       plausibility checks (hot-pavement, pre-dawn uniformity, solar
       geometry).
    5. **Analyze** the output: headline statistics, figures, and
       limitations.

    A few practical notes:

    - The notebook ships with two AOI profiles. **`hayti_demo`** is a
      600 m × 600 m smoke-test box that runs end-to-end in roughly
      45 minutes on CPU; **`durham_hayti`** is the 2 km × 2 km
      production AOI used for the headline numbers. Pick from the
      dropdown below; everything downstream re-resolves automatically.
    - Section 10 produces a self-contained MapLibre web app for the
      full-fidelity 3D view. It runs outside the notebook (instructions
      in that section).
    - Long-running cells (PDAL pull, SOLWEIG runs) are idempotent: the
      output is detected on disk and the cell is skipped. The first
      run on a fresh AOI takes the full ~45 minutes; subsequent runs
      return in seconds.
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


@app.cell
def _viz_helpers():
    import numpy as _np
    import matplotlib.pyplot as _plt
    import rasterio as _rio
    from matplotlib.colors import ListedColormap as _ListedColormap
    from matplotlib.colors import BoundaryNorm as _BoundaryNorm
    from matplotlib.patches import Patch as _Patch

    _UMEP_PALETTE = {1: "#888888", 2: "#d94731", 5: "#7ec27e",
                      6: "#c8a778", 7: "#4a90d9"}
    _UMEP_LABELS = {1: "Paved", 2: "Building", 5: "Grass / under-tree",
                     6: "Bare soil", 7: "Water"}

    _MULC_PALETTE = {10: "#4a90d9", 20: "#888888", 30: "#c8a778",
                      40: "#2d8a3e", 52: "#7ec27e", 70: "#c2e09b",
                      80: "#f0e68c", 91: "#5fa6c8", 92: "#9ec9e0"}
    _MULC_LABELS = {10: "Water", 20: "Impervious", 30: "Soil / barren",
                     40: "Trees / forest", 52: "Shrub",
                     70: "Grass / herbaceous", 80: "Agriculture",
                     91: "Woody wetland", 92: "Emergent wetland"}

    def _discrete(arr, ax, fig, swatches, labels, missing_msg):
        codes = sorted(c for c in swatches if _np.any(arr == c))
        if not codes:
            ax.text(0.5, 0.5, missing_msg, ha="center", va="center",
                     transform=ax.transAxes)
            return
        cmap_obj = _ListedColormap([swatches[c] for c in codes])
        bounds = [c - 0.5 for c in codes] + [codes[-1] + 0.5]
        norm = _BoundaryNorm(bounds, cmap_obj.N)
        ax.imshow(arr, cmap=cmap_obj, norm=norm, interpolation="nearest")
        handles = [_Patch(facecolor=swatches[c],
                            label=f"{c}  {labels.get(c, '?')}")
                    for c in codes]
        ax.legend(handles=handles, loc="center left",
                   bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=9,
                   handlelength=1.4, handleheight=1.0, borderpad=0.4)

    def show_raster(path, title=None, cmap="viridis", vmin=None, vmax=None,
                     palette=False, cbar_label=None, figsize=(6.5, 5.5)):
        """Render a 1 m raster as a matplotlib Figure.

        `palette` accepts:
          - False (default): continuous colormap with colorbar.
          - "umep": discrete legend for the 5 UMEP land-cover classes.
          - "mulc": discrete legend for the 9 EnviroAtlas MULC raw classes.

        `cbar_label` is the units string drawn next to the continuous colorbar
        (ignored when `palette` is set).
        """
        with _rio.open(path) as ds:
            arr = ds.read(1).astype("float32")
            nd = ds.nodata
        if nd is not None:
            arr = _np.where(arr == nd, _np.nan, arr)
        fig, ax = _plt.subplots(figsize=figsize)
        if palette == "umep" or palette is True:
            _discrete(arr, ax, fig, _UMEP_PALETTE, _UMEP_LABELS,
                       "no UMEP-coded cells")
        elif palette == "mulc":
            _discrete(arr, ax, fig, _MULC_PALETTE, _MULC_LABELS,
                       "no MULC-coded cells")
        else:
            im = ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax)
            cbar = fig.colorbar(im, ax=ax, shrink=0.8)
            if cbar_label:
                cbar.set_label(cbar_label, fontsize=9)
        ax.set_title(title or path.name, fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.tight_layout()
        return fig

    return (show_raster,)


@app.cell(hide_code=True)
def _section_aoi(mo):
    mo.md(r"""
    ## 1. Area of interest

    Two AOI profiles ship with the project:

    - **`hayti_demo`** is a 600 m × 600 m test area centered on the
      densest cluster of planted sites in Hayti (163 of the 245 sites
      fall inside it). Use this for a fast end-to-end pass.
    - **`durham_hayti`** is the 2 km × 2 km production AOI used for the
      conference-deck figures and the headline numbers.

    Outputs are namespaced by AOI under `inputs/processed/{aoi}_*/`,
    `outputs/{aoi}/`, and `figures/{aoi}/slides/`, so the two profiles
    do not overwrite each other.
    """)
    return


@app.cell
def _aoi_selector(mo):
    aoi = mo.ui.dropdown(
        options=["hayti_demo", "durham_hayti"],
        value="hayti_demo",
        label="AOI profile",
    )
    aoi
    return (aoi,)


@app.cell
def _aoi_config(REPO, aoi, mo):
    import os
    os.environ["AOI_PROFILE"] = aoi.value
    os.environ["OUTPUT_PREFIX"] = aoi.value
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import get_aoi
    from src import figures as _figures
    from src import inspector as _inspector
    _figures.set_aoi(aoi.value)
    _inspector.set_aoi(aoi.value)
    cfg = get_aoi(aoi.value)
    cfg.baseline_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    cfg.slides_dir.mkdir(parents=True, exist_ok=True)
    aoi_summary = mo.md(
        f"| parameter | value |\n|---|---|\n"
        f"| name | `{cfg.name}` |\n"
        f"| description | {cfg.description} |\n"
        f"| center (lat, lon) | {cfg.center_lat:.4f}, {cfg.center_lon:.4f} |\n"
        f"| size | {cfg.size_km} km × {cfg.size_km} km |\n"
        f"| simulation date | {cfg.sim_date} |\n"
        f"| UTC offset | {cfg.utc_offset:+d} hours |\n"
        f"| tile size | {cfg.tile_size} px (overlap {cfg.tile_overlap} px) |\n"
        f"| baseline folder | `{cfg.baseline_dir.relative_to(REPO)}` |\n"
        f"| outputs folder | `{cfg.output_root.relative_to(REPO)}` |"
    )
    aoi_summary
    return (cfg,)


@app.cell(hide_code=True)
def _section_cache(mo):
    mo.md(r"""
    ## 2. Local cache inventory

    Datasets that have already been downloaded show up below with their
    on-disk size. Anything missing is fetched in the next section.
    Removing a file forces a fresh download on the next run. The four
    public datasets are AOI-agnostic in content; only the Overture
    footprints are clipped per AOI.
    """)
    return


@app.cell
def _disk_status(REPO, cfg, mo):
    _raw = REPO / "inputs/raw/durham"
    _items = {
        "Durham planting sites": _raw / "trees_planting/durham_trees.geojson",
        "EnviroAtlas MULC raster": _raw / "enviroatlas_mulc/DNC_MULC.tif",
        "KRDU summer 2025 obs": _raw / "krdu_asos/krdu_2025_summer.csv",
        f"Overture buildings ({cfg.name})":
            _raw / f"overture/buildings_{cfg.name}.geojson",
    }
    _rows = []
    for _name, _p in _items.items():
        _present = _p.exists()
        _size = f"{_p.stat().st_size // 1024:,} KB" if _present else "missing"
        _rows.append(f"| {_name} | {'yes' if _present else 'no'} | {_size} |")
    cache_status = mo.md(
        "| dataset | present | size |\n|---|---|---|\n" + "\n".join(_rows)
    )
    cache_status
    return


@app.cell(hide_code=True)
def _section_fetches(mo):
    mo.md(r"""
    ## 3. Public datasets

    Four sources are pulled in this section. Each cell is independent
    and idempotent.

    - **Durham planting sites.** Locations of trees the City plans to
      plant between 2025 and 2028. The full layer carries 6,011 future
      and 22,418 existing trees. Filter to `present == "Planting Site"`
      and clip to the AOI; for the production Hayti tile, 245 sites
      fall inside.
    - **EnviroAtlas MULC raster.** A one-meter land-cover product
      published by the United States Environmental Protection Agency.
      Reported accuracy is roughly 83 percent against NAIP imagery.
      The 2010 vintage is the weakest dataset in the chain but
      adequate for a baselined comparison: urban land cover changes
      slowly over a decade.
    - **KRDU ASOS observations.** Hourly air temperature and sky-cover
      observations from the Raleigh-Durham airport for summer 2025.
      Used to identify the hottest clear-sky day of the summer (the
      simulation date) and to cross-check the meteorological forcing
      in the validation step.
    - **Overture buildings.** Open-license building polygons with
      height attributes. Roughly two-thirds of the polygons in the
      AOI carry a measured height; the rest contribute footprint
      geometry only.
    """)
    return


@app.cell
def _fetch_planting_sites(REPO, cfg, mo):
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur
    _dst = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    if _dst.exists():
        _msg = f"[cached] {_dst.relative_to(REPO)}"
    else:
        _dst.parent.mkdir(parents=True, exist_ok=True)
        _layer = ("https://webgis2.durhamnc.gov/server/rest/services/PublicServices/"
                  "Environmental/FeatureServer/11")
        _feats, _last_oid = [], -1
        while True:
            _params = {
                "where": f"OBJECTID > {_last_oid}",
                "outFields": "OBJECTID,present,program,commonname,plantingdate,contractplantingyr",
                "returnGeometry": "true", "outSR": "4326",
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": "2000", "f": "geojson",
            }
            _url = f"{_layer}/query?{_up.urlencode(_params)}"
            _req = _ur.Request(_url, headers={"User-Agent": "radiant-temperature/0.1"})
            _obj = _json.loads(_ur.urlopen(_req, timeout=120).read())
            _page = _obj.get("features", [])
            if not _page:
                break
            _feats.extend(_page)
            _last_oid = max(f["properties"]["OBJECTID"] for f in _page)
            if len(_page) < 2000:
                break
        _dst.write_text(_json.dumps({"type": "FeatureCollection", "features": _feats}))
        _msg = f"wrote {len(_feats):,} features → {_dst.relative_to(REPO)}"

    import geopandas as _gpd
    import matplotlib.pyplot as _plt
    import pyproj as _pp
    from shapely.geometry import box as _shp_box
    _gdf = _gpd.read_file(_dst)
    _planting = _gdf[_gdf["present"] == "Planting Site"]
    _trans = _pp.Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
    _x0, _y0, _x1, _y1 = cfg.tile_bbox
    _lon0, _lat0 = _trans.transform(_x0, _y0)
    _lon1, _lat1 = _trans.transform(_x1, _y1)
    _aoi_box = _gpd.GeoSeries([_shp_box(_lon0, _lat0, _lon1, _lat1)], crs="EPSG:4326")
    _fig, _ax = _plt.subplots(figsize=(7, 6))
    _planting.plot(ax=_ax, color="#2ca02c", markersize=1, alpha=0.4)
    _aoi_box.boundary.plot(ax=_ax, color="red", linewidth=2)
    _ax.set_title(f"Durham planting sites ({len(_planting):,} citywide; "
                  f"red box = {cfg.name} AOI)", fontsize=10)
    _ax.set_xlabel("longitude"); _ax.set_ylabel("latitude")
    _fig.tight_layout()

    plantings_caption = mo.md(f"**Durham trees and planting sites.** `{_msg}`")
    mo.vstack([plantings_caption, _fig])
    return


@app.cell
def _fetch_mulc(REPO, cfg, mo):
    import urllib.request as _ur
    import zipfile as _zip
    _dst = REPO / "inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif"
    if _dst.exists():
        _msg = f"[cached] {_dst.relative_to(REPO)}"
    else:
        _dst.parent.mkdir(parents=True, exist_ok=True)
        _zip_path = _dst.parent / "DNC_MULC_tif.zip"
        if not _zip_path.exists():
            _req = _ur.Request("https://enviroatlas.epa.gov/download/DNC_MULC_tif.zip",
                                headers={"User-Agent": "radiant-temperature/0.1"})
            _zip_path.write_bytes(_ur.urlopen(_req, timeout=600).read())
        with _zip.ZipFile(_zip_path) as _zf:
            for _m in _zf.namelist():
                if _m.endswith("/"):
                    continue
                _target = _dst.parent / _m.split("/")[-1]
                _target.write_bytes(_zf.read(_m))
        if not _dst.exists():
            _cands = sorted(_dst.parent.glob("*.tif"))
            if _cands:
                _cands[0].rename(_dst)
        _msg = f"wrote {_dst.relative_to(REPO)}"

    import rasterio as _rio
    import matplotlib.pyplot as _plt
    import pyproj as _pp
    import numpy as _np
    from matplotlib.colors import ListedColormap as _LC
    from matplotlib.colors import BoundaryNorm as _BN
    from matplotlib.patches import Patch as _MP
    with _rio.open(_dst) as _ds:
        _scale = max(_ds.width // 800, _ds.height // 800, 1)
        _arr = _ds.read(1, out_shape=(_ds.height // _scale, _ds.width // _scale))
        _bounds = _ds.bounds
        _crs_src = _ds.crs.to_string()
    _trans = _pp.Transformer.from_crs("EPSG:32617", _crs_src, always_xy=True)
    _x0, _y0, _x1, _y1 = cfg.tile_bbox
    _bx0, _by0 = _trans.transform(_x0, _y0)
    _bx1, _by1 = _trans.transform(_x1, _y1)
    _MULC_PALETTE = {10: "#4a90d9", 20: "#888888", 30: "#c8a778",
                      40: "#2d8a3e", 52: "#7ec27e", 70: "#c2e09b",
                      80: "#f0e68c", 91: "#5fa6c8", 92: "#9ec9e0"}
    _MULC_LABELS = {10: "Water", 20: "Impervious", 30: "Soil / barren",
                     40: "Trees / forest", 52: "Shrub",
                     70: "Grass / herbaceous", 80: "Agriculture",
                     91: "Woody wetland", 92: "Emergent wetland"}
    _present = sorted(c for c in _MULC_PALETTE if (_arr == c).any())
    _cmap = _LC([_MULC_PALETTE[c] for c in _present])
    _norm = _BN([c - 0.5 for c in _present] + [_present[-1] + 0.5], _cmap.N)
    _fig, _ax = _plt.subplots(figsize=(8, 6))
    _ax.imshow(_arr, cmap=_cmap, norm=_norm, interpolation="nearest",
                extent=[_bounds.left, _bounds.right, _bounds.bottom, _bounds.top])
    _ax.add_patch(_plt.Rectangle((_bx0, _by0), _bx1 - _bx0, _by1 - _by0,
                                    fill=False, edgecolor="red", linewidth=2))
    _handles = [_MP(facecolor=_MULC_PALETTE[c],
                      label=f"{c}  {_MULC_LABELS[c]}") for c in _present]
    _ax.legend(handles=_handles, loc="center left",
                bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=9,
                handlelength=1.4, handleheight=1.0, borderpad=0.4)
    _ax.set_title(f"DNC_MULC.tif (city-wide, {_scale}× downsampled; "
                  f"red box = {cfg.name} AOI)", fontsize=10)
    _ax.set_xlabel(_crs_src + " easting"); _ax.set_ylabel("northing")
    _fig.tight_layout()

    mulc_caption = mo.md(f"**EnviroAtlas MULC raster.** `{_msg}`")
    mo.vstack([mulc_caption, _fig])
    return


@app.cell
def _fetch_krdu(REPO, cfg, mo):
    import urllib.parse as _up
    import urllib.request as _ur
    _dst = REPO / "inputs/raw/durham/krdu_asos/krdu_2025_summer.csv"
    if _dst.exists():
        _msg = f"[cached] {_dst.relative_to(REPO)}"
    else:
        _dst.parent.mkdir(parents=True, exist_ok=True)
        _params = [
            ("station", "RDU"), ("data", "tmpf"), ("data", "skyc1"),
            ("year1", "2025"), ("month1", "6"), ("day1", "1"),
            ("year2", "2025"), ("month2", "9"), ("day2", "15"),
            ("tz", "America/New_York"), ("format", "onlycomma"),
            ("latlon", "no"), ("missing", "M"), ("trace", "T"), ("direct", "no"),
            ("report_type", "3"), ("report_type", "4"),
        ]
        _url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
                + _up.urlencode(_params))
        _req = _ur.Request(_url, headers={"User-Agent": "radiant-temperature/0.1"})
        _dst.write_bytes(_ur.urlopen(_req, timeout=120).read())
        _msg = f"wrote {_dst.relative_to(REPO)}"

    import pandas as _pd
    import matplotlib.pyplot as _plt
    _df = _pd.read_csv(_dst)
    _df = _df[_df["tmpf"] != "M"].copy()
    _df["valid"] = _pd.to_datetime(_df["valid"])
    _df["tmpc"] = (_df["tmpf"].astype(float) - 32) * 5 / 9
    _fig, _ax = _plt.subplots(figsize=(8, 3.5))
    _ax.plot(_df["valid"], _df["tmpc"], lw=0.5, color="tab:red")
    _ax.axvline(_pd.Timestamp(cfg.sim_date), color="black", linestyle="--",
                  label=f"sim date {cfg.sim_date}")
    _ax.set_xlabel("date")
    _ax.set_ylabel("air temperature (°C)")
    _ax.set_title("KRDU summer 2025 hourly observations", fontsize=10)
    _ax.legend(loc="lower left", fontsize=9)
    _ax.grid(alpha=0.3)
    _fig.autofmt_xdate()
    _fig.tight_layout()

    krdu_caption = mo.md(f"**KRDU ASOS observations.** `{_msg}`")
    mo.vstack([krdu_caption, _fig])
    return


@app.cell
def _fetch_overture(REPO, cfg, mo):
    from src.buildings import fetch_overture as _fetch
    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{cfg.name}.geojson"
    if not overture_path.exists():
        _fetch(cfg.name, cfg.processing_bbox, overture_path)

    import geopandas as _gpd
    import matplotlib.pyplot as _plt
    _gdf = _gpd.read_file(overture_path)
    _has_h = _gdf["height"].notna().sum() if "height" in _gdf.columns else 0
    _fig, _ax = _plt.subplots(figsize=(7, 6))
    _gdf.plot(ax=_ax, column="height" if "height" in _gdf.columns else None,
                cmap="viridis", edgecolor="black", linewidth=0.2,
                missing_kwds={"color": "lightgray", "edgecolor": "black", "linewidth": 0.2},
                legend=True, legend_kwds={"label": "height (m)", "shrink": 0.7})
    _ax.set_title(f"Overture footprints in {cfg.name} AOI "
                  f"({len(_gdf)} polygons, {_has_h} with measured height)",
                  fontsize=10)
    _ax.set_aspect("equal")
    _ax.set_xticks([]); _ax.set_yticks([])
    _fig.tight_layout()

    overture_caption = mo.md(
        f"**Overture buildings.** `{overture_path.relative_to(REPO)} "
        f"({overture_path.stat().st_size // 1024:,} KB)`"
    )
    mo.vstack([overture_caption, _fig])
    return (overture_path,)


@app.cell(hide_code=True)
def _section_met(mo):
    mo.md(r"""
    ## 4. Meteorological forcing

    SOLWEIG is driven by hourly air temperature, relative humidity,
    wind, surface pressure, downwelling shortwave radiation,
    downwelling longwave radiation, and precipitation. The cell below
    pulls a single grid point from the NOAA HRRR analysis archive and
    writes a UMEP own-met file inside the AOI's baseline folder. The
    dataset is hosted on anonymous S3 via the `dynamical-catalog`
    package, so no API key is required. The HRRR archive is in UTC;
    the writer converts to Durham local time using the offset stored
    in the AOI configuration.
    """)
    return


@app.cell
def _fetch_met(REPO, cfg, mo):
    from src.met import write_umep_met_for_aoi
    _path = write_umep_met_for_aoi(cfg.name, cfg.center_lat, cfg.center_lon,
                                    cfg.sim_date, cfg.utc_offset)
    met_status = mo.md(f"**HRRR own-met file.** `{_path.relative_to(REPO)}`")
    met_status
    return


@app.cell(hide_code=True)
def _section_lidar_check(mo):
    mo.md(r"""
    ## 5. LiDAR endpoint check

    The DSM and DEM are derived from the NC Phase 3 LiDAR product
    (NOAA dataset 6209), accessed as an Entwine Point Tile store. The
    actual PDAL retrieval happens later in the pipeline (sections
    6 and 7 below), because the operation is slow and depends on the
    processing bounding box. The cell below confirms only that the
    endpoint is reachable.

    Note that the NC product is published in US Survey Feet. The PDAL
    pipeline must convert to meters explicitly. Forgetting this
    conversion is the most common failure mode with North Carolina
    LiDAR.
    """)
    return


@app.cell
def _lidar_url_check(mo):
    import urllib.request as _ur
    _url = ("https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/"
            "geoid18/6209/ept.json")
    try:
        _req = _ur.Request(_url, headers={"User-Agent": "radiant-temperature/0.1"})
        _head = _ur.urlopen(_req, timeout=10)
        _status = f"reachable ({_head.status})"
    except Exception as _e:
        _status = f"unreachable: {_e}"
    lidar_status = mo.md(
        f"**NC LiDAR EPT (NOAA dataset 6209).** `{_url}`\n\n"
        f"Status: `{_status}`."
    )
    lidar_status
    return


@app.cell(hide_code=True)
def _section_buildings_overview(mo):
    mo.md(r"""
    ## 6. SOLWEIG-ready rasters

    Pedestrian-level radiation modeling depends on accurate
    three-dimensional geometry of buildings and canopy. The challenge
    is that LiDAR cannot distinguish trees from buildings: both
    surfaces return the laser pulse. The canonical solution,
    formalised by [Lindberg and Grimmond (2011)](https://link.springer.com/article/10.1007/s00704-010-0382-8),
    is to gate LiDAR returns against an authoritative source of
    building footprints. The next sections implement that recipe with
    2015 NC Phase 3 LiDAR and 2026 Overture Foundation building
    polygons, then derive canopy heights by subtracting the bare-earth
    DEM from the LiDAR DSM.

    The output is the four co-registered rasters that SOLWEIG
    consumes:

    | raster | content |
    |---|---|
    | `Building_DSM.tif` | Surface elevation of ground plus buildings (no canopy). |
    | `DEM.tif` | Bare-earth terrain elevation. |
    | `Trees.tif` | Canopy heights (CDSM). |
    | `Landcover.tif` | UMEP-coded surface classes. |

    Each cell is idempotent. The PDAL retrieval is the slowest step
    on a fresh AOI: roughly 30 seconds for the 600 m demo box and
    roughly ten minutes for the 2 km Hayti tile.
    """)
    return


@app.cell(hide_code=True)
def _section_lidar_dsm(mo):
    mo.md(r"""
    ### 6a. LiDAR first-return DSM

    The cell below issues a PDAL pipeline against the NC Phase 3
    LiDAR Entwine Point Tile store and writes a one-meter first-return
    raster clipped to the processing bounding box. The output captures
    every return surface, so it includes ground, buildings, canopy,
    and laser artifacts. The Overture-gated patch in section 7 reduces
    this to ground plus buildings.
    """)
    return


@app.cell
def _lidar_dsm(REPO, cfg, mo, show_raster):
    from src.buildings import pull_lidar_dsm
    lidar_dsm_path = cfg.baseline_dir / "Building_DSM.preMS.tif"
    if not lidar_dsm_path.exists():
        pull_lidar_dsm(cfg.processing_bbox, lidar_dsm_path)
    lidar_dsm_caption = mo.md(
        f"`{lidar_dsm_path.relative_to(REPO)}` "
        f"({lidar_dsm_path.stat().st_size // 1024 // 1024:,} MB)"
    )
    lidar_dsm_fig = show_raster(
        lidar_dsm_path,
        title="Building_DSM.preMS.tif — raw LiDAR first-returns",
        cmap="terrain",
        cbar_label="elevation (m, geoid18)",
    )
    mo.vstack([lidar_dsm_caption, lidar_dsm_fig])
    return (lidar_dsm_path,)


@app.cell(hide_code=True)
def _section_dem(mo):
    mo.md(r"""
    ### 6b. Bare-earth DEM

    The DEM is built from points the LiDAR vendor classified as
    ground (`Classification == 2`), then gap-filled with
    `gdal_fillnodata` (search radius 100 cells). Holes under canopy
    and buildings are common in raw ground returns. Smooth
    interpolation is acceptable here because pedestrians never see
    those cells; leaving them as nodata would otherwise corrupt the
    canopy-height calculation in the next sub-step.
    """)
    return


@app.cell
def _dem(REPO, cfg, mo, show_raster):
    from src.buildings import build_dem
    dem_path = cfg.baseline_dir / "DEM.tif"
    if not dem_path.exists():
        build_dem(cfg.processing_bbox, dem_path)
    dem_caption = mo.md(f"`{dem_path.relative_to(REPO)}`")
    dem_fig = show_raster(dem_path, title="DEM.tif — bare-earth terrain",
                            cmap="terrain",
                            cbar_label="elevation (m, geoid18)")
    mo.vstack([dem_caption, dem_fig])
    return (dem_path,)


@app.cell(hide_code=True)
def _section_lc(mo):
    mo.md(r"""
    ### 6c. Land cover

    EnviroAtlas ships MULC at one meter in EPSG:26917. The cell below
    reprojects it to EPSG:32617 and snaps it to the AOI grid. The
    MULC nine-class palette is reclassified to UMEP codes in the next
    sub-step.
    """)
    return


@app.cell
def _landcover_raw(REPO, cfg, mo, show_raster):
    from src.buildings import build_landcover_raw
    _src = REPO / "inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif"
    landcover_raw_path = cfg.baseline_dir / "MULC_aligned.tif"
    if not landcover_raw_path.exists():
        build_landcover_raw(_src, cfg.processing_bbox, landcover_raw_path)
    lc_raw_caption = mo.md(f"`{landcover_raw_path.relative_to(REPO)}`")
    lc_raw_fig = show_raster(landcover_raw_path,
                                title="MULC_aligned.tif — EnviroAtlas land cover (raw classes)",
                                palette="mulc")
    mo.vstack([lc_raw_caption, lc_raw_fig])
    return (landcover_raw_path,)


@app.cell(hide_code=True)
def _section_trees(mo):
    mo.md(r"""
    ### 6d. Canopy CDSM and pre-patch land cover

    Canopy heights are computed as `DSM minus DEM` on cells the MULC
    raster classifies as trees. The result is written to `Trees.tif`.
    A pre-Overture UMEP land cover (`Landcover.preMS.tif`) is also
    written. The building class (UMEP code 2) is not assigned here:
    it comes later from the Overture footprints. A height-threshold
    rule (for example, treating any pixel above 2.5 m above ground
    as a building) misclassifies awnings, billboards, and isolated
    canopy as buildings, which is why the patched recipe is
    preferable.
    """)
    return


@app.cell
def _trees_and_lc(
    REPO,
    cfg,
    dem_path,
    landcover_raw_path,
    lidar_dsm_path,
    mo,
    show_raster,
):
    from src.buildings import build_trees_and_landcover
    trees_path = cfg.baseline_dir / "Trees.tif"
    lc_pre_path = cfg.baseline_dir / "Landcover.preMS.tif"
    if not (trees_path.exists() and lc_pre_path.exists()):
        build_trees_and_landcover(lidar_dsm_path, dem_path, landcover_raw_path,
                                    trees_path, lc_pre_path)
    trees_caption = mo.md(
        f"`{trees_path.relative_to(REPO)}` — canopy heights\n\n"
        f"`{lc_pre_path.relative_to(REPO)}` — UMEP-coded land cover (no buildings)"
    )
    trees_fig = show_raster(trees_path,
                              title="Trees.tif — canopy heights (m)",
                              cmap="YlGn", vmin=0, vmax=25,
                              cbar_label="canopy height above ground (m)")
    lc_pre_fig = show_raster(lc_pre_path,
                               title="Landcover.preMS.tif — UMEP classes (pre-Overture)",
                               palette="umep")
    mo.vstack([trees_caption, mo.hstack([trees_fig, lc_pre_fig])])
    return


@app.cell(hide_code=True)
def _section_patch(mo):
    mo.md(r"""
    ## 7. Apply the Overture-gated DSM patch

    For each cell in the AOI, the patched DSM is set as follows:

    - If the cell sits inside an Overture footprint, take the higher
      of the LiDAR roof elevation (capped at DEM plus 150 m to filter
      birds and laser glints) and the Overture roof elevation
      (`DEM + Overture height`). This recovers post-2015 buildings
      that the 2015 LiDAR missed and rejects spurious laser noise
      above existing roofs.
    - Otherwise, set the cell to the DEM elevation. This removes
      canopy, billboards, and other tall non-building features from
      the Building DSM.

    Land cover is updated in the same step: every cell inside an
    Overture footprint is reclassified as UMEP class 2 (building).
    """)
    return


@app.cell
def _patch(cfg, mo, overture_path, show_raster):
    from src.buildings import patch_with_overture
    patch_stats = patch_with_overture(cfg.baseline_dir, overture_path,
                                        cfg.processing_bbox)
    _rows = "\n".join(f"| {k} | {v} |" for k, v in patch_stats.items())
    patch_table = mo.md("| metric | value |\n|---|---|\n" + _rows)
    patched_dsm_fig = show_raster(
        cfg.baseline_dir / "Building_DSM.tif",
        title="Building_DSM.tif — patched (ground + buildings)",
        cmap="terrain",
        cbar_label="elevation (m, geoid18)",
    )
    patched_lc_fig = show_raster(
        cfg.baseline_dir / "Landcover.tif",
        title="Landcover.tif — patched (Overture buildings = class 2)",
        palette="umep",
    )
    mo.vstack([patch_table, mo.hstack([patched_dsm_fig, patched_lc_fig])])
    return


@app.cell(hide_code=True)
def _section_solweig_intro(mo):
    mo.md(r"""
    ## 8. SOLWEIG runs

    [SOLWEIG](https://link.springer.com/article/10.1007/s00484-008-0162-7)
    (Solar and LongWave Environmental Irradiance Geometry; Lindberg,
    Holmer, and Thorsson 2008) takes a building DSM, a DEM, a canopy
    CDSM, a UMEP land cover, and an hourly meteorological forcing,
    and resolves the six radiation fluxes that govern the radiative
    load on a vertical pedestrian. Output is hourly mean radiant
    temperature (Tmrt) and Universal Thermal Climate Index (UTCI;
    [Bröde et al. 2012](https://link.springer.com/article/10.1007/s00484-011-0454-1))
    rasters at one meter. The GPU implementation is
    [Kamath et al. (2026)](https://joss.theoj.org/papers/10.21105/joss.09535).

    Three runs are fired in sequence:

    1. **Baseline.** Current canopy.
    2. **Year 10 scenario.** Each planted site receives a 5 m × 5 m
       canopy disk at 5 m height, representing a five to ten year
       old tree.
    3. **Mature scenario.** Each planted site receives a 7 m × 7 m
       canopy disk at 12 m height, representing a roughly twenty-five
       year old tree.

    The two scenarios bracket realistic outcomes for the Willow Oak
    and Red Maple species mix that Durham Urban Forestry typically
    plants. Each long-running cell skips when the expected outputs
    are already on disk.

    Wall-clock for the SOLWEIG runs on CPU is roughly 10 minutes per
    scenario for the 600 m demo AOI and 30 to 40 minutes per scenario
    for the 2 km production AOI. An NVIDIA GPU is auto-detected and
    brings the production-AOI per-scenario time down to roughly two
    minutes.
    """)
    return


@app.cell(hide_code=True)
def _section_preflight(mo):
    mo.md(r"""
    ### 8a. Pre-flight check

    SOLWEIG needs the four canonical rasters and the own-met file.
    Section 4 produces the own-met file; sections 6-7 produce the
    rasters. The cell below confirms they are in place.
    """)
    return


@app.cell
def _preflight(cfg, mo):
    _needed = ["Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif",
                f"ownmet_{cfg.sim_date}.txt"]
    missing_inputs = [n for n in _needed if not (cfg.baseline_dir / n).exists()]
    if missing_inputs:
        preflight_md = mo.md(
            f"**Missing inputs:** {missing_inputs}. "
            f"Re-run sections 3-7 above."
        ).callout(kind="danger")
    else:
        preflight_md = mo.md("All baseline inputs present.").callout(kind="success")
    preflight_md
    return (missing_inputs,)


@app.cell(hide_code=True)
def _section_baseline(mo):
    mo.md(r"""
    ### 8b. Baseline SOLWEIG run

    The baseline represents the AOI as it exists today. The wrapper
    in `src/solweig_runner.py` detects an NVIDIA GPU automatically
    and falls back to CPU when none is present. The cell skips
    entirely when the expected per-tile TMRT and UTCI files are
    already on disk.
    """)
    return


@app.cell
def _baseline_run(cfg, missing_inputs, mo):
    if missing_inputs:
        baseline_result = {"skipped": True, "reason": "missing inputs"}
    else:
        from src.solweig_runner import run as _run_solweig
        baseline_result = _run_solweig(cfg.baseline_dir, cfg.sim_date,
                                        tile_size=cfg.tile_size,
                                        tile_overlap=cfg.tile_overlap)
    base_md = mo.md(f"```\n{baseline_result}\n```")
    base_md
    return (baseline_result,)


@app.cell(hide_code=True)
def _section_scenarios(mo):
    mo.md(r"""
    ### 8c. Scenario inputs

    Each planted site is rasterized as a square canopy disk centered
    on the planting point. The cells of `Trees.tif` inside the disk
    are set to the canopy height for the scenario, and the
    corresponding `Landcover.tif` cells are reclassified to UMEP
    code 5 (vegetation). Building cells are skipped on the assumption
    that a planting sited inside a building footprint is a data
    error.

    The `walls/` and `aspect/` preprocessing tiles are symlinked from
    the baseline folder. These products depend only on the building
    DSM, which is identical across scenarios; reusing them avoids
    roughly 20 minutes of CPU work per scenario on the production
    AOI.
    """)
    return


@app.cell
def _scenarios(REPO, cfg, mo):
    from src.scenarios import load_planting_sites, burn_canopy
    _trees_geojson = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    if not _trees_geojson.exists():
        scenarios_md = mo.md("**Missing planting-sites GeoJSON.** Re-run section 3.").callout("danger")
    else:
        scenario_sites = load_planting_sites(_trees_geojson, cfg.tile_bbox)
        burn_results = {}
        for _scen in ("year10", "mature"):
            burn_results[_scen] = burn_canopy(
                cfg.baseline_dir, cfg.scenario_dir(_scen), _scen,
                scenario_sites, cfg.sim_date,
            )
        _summary = "\n".join(f"- **{k}**: `{v}`" for k, v in burn_results.items())
        scenarios_md = mo.md(
            f"Planting sites in tile: `{len(scenario_sites)}`\n\n{_summary}"
        )
    scenarios_md
    return


@app.cell(hide_code=True)
def _section_scenario_runs(mo):
    mo.md(r"""
    ### 8d. Scenario SOLWEIG runs

    With the cached `walls/` and `aspect/` tiles in place, each
    scenario runs in roughly the same time as the baseline. Both
    scenarios run sequentially below; outputs land in
    `inputs/processed/{aoi}_scenario_{name}/output_folder/`.
    """)
    return


@app.cell
def _scenario_runs(cfg, mo):
    from src.solweig_runner import run as _run_solweig
    scenario_results = {}
    for _scen in ("year10", "mature"):
        _d = cfg.scenario_dir(_scen)
        if not (_d / "Trees.tif").exists():
            scenario_results[_scen] = {"skipped": True, "reason": "scenario not built"}
            continue
        scenario_results[_scen] = _run_solweig(_d, cfg.sim_date,
                                                tile_size=cfg.tile_size,
                                                tile_overlap=cfg.tile_overlap)
    _rows = "\n".join(f"- **{k}**: `{v}`" for k, v in scenario_results.items())
    sruns_md = mo.md(_rows)
    sruns_md
    return (scenario_results,)


@app.cell(hide_code=True)
def _section_sanity(mo):
    mo.md(r"""
    ## 9. Baseline plausibility report

    Three physical checks confirm that the baseline output is
    plausible:

    1. **Hot-pavement check.** Paved cells should be at least 2 °C
       hotter than vegetated cells at peak hour.
    2. **Pre-dawn uniformity.** With no solar input, Tmrt should be
       almost spatially uniform at 03:00.
    3. **Solar geometry.** The discovered peak hour and the implied
       shadow direction should match a NOAA solar-position estimate
       for the AOI. For 2025-06-23 in Durham, the peak hour is
       15:00 local time and the solar azimuth is 248°, so shadows
       fall to the east-northeast.
    """)
    return


@app.cell
def _sanity(aoi, baseline_result, mo):
    if baseline_result.get("skipped") and baseline_result.get("reason") == "missing inputs":
        sanity_md = mo.md("Plausibility check unavailable until baseline run completes.")
    else:
        from src.evaluate import baseline_checks
        _report = baseline_checks(aoi.value)
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
def _section_final_inspector(mo):
    mo.md(r"""
    ## 10. Interactive map inspector

    A small static MapLibre bundle is written to
    `inputs/processed/{aoi}_baseline/web/`. It places two raster
    overlays on top of an OpenStreetMap basemap — baseline mean
    radiant temperature at peak hour and ΔUTCI for the mature
    scenario — together with the AOI footprint and the planted-site
    points as toggleable vector layers. The bundle is fully static
    (one `index.html`, two PNG overlays, two GeoJSONs) and does not
    require Python at view time.

    The cell below regenerates the diff GeoTIFFs and rebuilds the
    bundle (idempotent — overwrites in place). To view it, start a
    static HTTP server **from the repo root**:

    ```bash
    python -m http.server 8765 --directory inputs/processed/hayti_demo_baseline/web
    ```

    Then open <http://localhost:8765/> in any browser. Swap
    `hayti_demo_baseline` for `durham_hayti_baseline` when running on
    the production AOI.
    """)
    return


@app.cell
def _build_final_bundle(REPO, aoi, mo, scenario_results):
    if any(r.get("skipped") and r.get("reason") for r in scenario_results.values()):
        bundle_md = mo.md("Inspector bundle requires both scenarios to complete.")
    else:
        from src.evaluate import write_diff_geotiffs as _write_diff_geotiffs
        from src import inspector as _inspector
        _inspector.set_aoi(aoi.value)
        _diff_info = _write_diff_geotiffs(aoi.value)
        _bundle = _inspector.build_bundle()
        bundle_md = mo.md(
            f"Peak hour: **{_diff_info['peak_hour']:02d}:00**. "
            f"Inspector bundle written to `{_bundle.relative_to(REPO)}/`."
        )
    bundle_md
    return


@app.cell(hide_code=True)
def _section_headline(mo):
    mo.md(r"""
    ## 11. Headline statistics

    Translating SOLWEIG's pixel-level output into decision-relevant
    statistics requires careful framing. Cooling is large at the
    planted spots (around −5 to −6 °C ΔUTCI in both AOIs) but
    imperceptible when averaged over the entire neighborhood
    (−0.01 °C tile-wide on the production run). The
    local-versus-neighborhood distinction is essential to
    communicate honestly: the planting program reduces heat stress
    at the sites themselves, not across the entire neighborhood.

    For each scenario the cell below reports:

    - **Peak hour.** The hour of the simulation day with the highest
      tile-mean Tmrt over non-roof cells in the baseline run.
      Approximately 15:00 local time for 2025-06-23 in Durham.
    - **Median ΔTmrt at planted pixels.** Median change in mean
      radiant temperature at the cells modified by the planting.
      This is the radiation-only quantity.
    - **Median ΔUTCI at planted pixels.** Median change in the
      Universal Thermal Climate Index. UTCI bundles air temperature,
      humidity, wind, and the radiation field into a single
      pedestrian-relevant temperature.
    - **Worst ΔTmrt.** The single coldest pixel modified by the
      planting, typically a cell where multiple disks overlap.
    - **WHO category drop rate.** The fraction of planted pixels that
      shift down at least one Bröde et al. 2012 UTCI heat-stress
      category at peak hour (extreme → very strong, very strong →
      strong, etc.).

    The headline figures from the `durham_hayti` production run are
    −4.66 °C and −5.80 °C ΔUTCI for the year 10 and mature scenarios
    respectively, with about 58 percent of planted pixels crossing
    at least one heat-stress category.
    """)
    return


@app.cell
def _headline(aoi, mo):
    from src.evaluate import scenario_headline as _scenario_headline
    from src.evaluate import write_diff_geotiffs as _write_diff_geotiffs
    _write_diff_geotiffs(aoi.value)
    headline_rows = [_scenario_headline(aoi.value, _scen)
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
            f"- Worst ΔTmrt: "
            f"{_r.get('planted_dtmrt_min', float('nan')):+.2f} °C\n"
            f"- WHO category drop rate: "
            f"{_r.get('who_category_drop_pct', 0):.1f}%"
        )
    headline_md = mo.md("\n\n".join(_cards))
    headline_md
    return (headline_rows,)


@app.cell
def _headline_text(REPO, cfg, headline_rows, mo):
    _out = cfg.output_root / "headline.txt"
    _lines = [
        f"Durham planted-tree intervention, peak hour, {cfg.sim_date}",
        "",
        f"AOI: {cfg.name}, {cfg.size_km:g} km x {cfg.size_km:g} km tile.",
        "",
    ]
    for _r in headline_rows:
        _lines.append(
            f"  {_r['scenario']:<7s}  dTmrt {_r.get('planted_dtmrt_median', float('nan')):+.2f} C  "
            f"dUTCI {_r.get('planted_dutci_median', float('nan')):+.2f} C  "
            f"(min dTmrt {_r.get('planted_dtmrt_min', float('nan')):+.2f} C)"
        )
    _out.write_text("\n".join(_lines) + "\n")
    headline_text_md = mo.md(f"Headline written to `{_out.relative_to(REPO)}`.")
    headline_text_md
    return


@app.cell(hide_code=True)
def _section_figures(mo):
    mo.md(r"""
    ## 12. Figures

    The remaining cells regenerate every figure used in the
    conference deck. Each figure function reads the merged baseline
    and scenario rasters and writes a PNG under
    `figures/{aoi}/slides/`.
    """)
    return


@app.cell(hide_code=True)
def _section_fig1(mo):
    mo.md(r"""
    ### Figure 1. Three-panel ΔUTCI

    Baseline UTCI at peak hour, mature-scenario UTCI at peak hour,
    and the difference between the two. The cooling is concentrated
    at the planting sites with limited spillover to neighboring
    cells.
    """)
    return


@app.cell
def _fig1(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_utci_three_panel()
    _path = cfg.slides_dir / "fig1_utci_three_panel_mature.png"
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

    Distribution of ΔUTCI values at the planted pixels on a log
    scale. Two stories: a spike at zero captures cells in the gaps
    between trees where nothing changes, and the long left tail
    captures the cells directly under new canopy disks. The mature
    scenario reaches further left than year 10 because the larger
    disk and taller canopy intercept more direct beam radiation.
    """)
    return


@app.cell
def _fig2(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_utci_histogram()
    _path = cfg.slides_dir / "fig2_utci_histogram.png"
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
    during daylight hours; cooling is solar-driven. A small
    overnight warming under canopy is a documented physical effect:
    the new canopy reduces sky-view factor and suppresses longwave
    radiative loss to the cold sky. The night-time absolute Tmrt
    remains in the comfortable range, so the implication for human
    health is small, but the mechanism is worth disclosing.
    """)
    return


@app.cell
def _fig3(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_diurnal_dual()
    _path = cfg.slides_dir / "fig3_diurnal_dual.png"
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

    Two-panel map showing the Durham city context and a zoom into
    the densest cluster of planting sites within the AOI.
    """)
    return


@app.cell
def _fig_study(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_study_site()
    _path = cfg.slides_dir / "study_site.png"
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
def _fig_panels(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_data_panels()
    _path = cfg.slides_dir / "data_panels.png"
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

    Side-by-side comparison of the raw LiDAR first-return DSM and
    the Overture-gated patched DSM. The third panel shows the
    difference, with red where the patch raised the surface
    (post-2015 buildings) and blue where it lowered the surface
    (canopy and laser noise filtered out).
    """)
    return


@app.cell
def _fig_dsm(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_dsm_correction()
    _path = cfg.slides_dir / "dsm_correction.png"
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
def _fig_scen(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_scenario_design()
    _path = cfg.slides_dir / "scenario_design.png"
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

    HRRR forcing compared against KRDU airport observations and
    Open-Meteo reanalysis. Modelled UTCI on grass cells compared
    against the Open-Meteo apparent-temperature product. The HRRR
    forcing tracks the airport observations within roughly 2 °C and
    modeled UTCI sits a few degrees above the apparent-temperature
    product because UTCI accounts for radiation loading.
    """)
    return


@app.cell
def _fig_validation(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_validation()
    _path = cfg.slides_dir / "validation.png"
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

    Mean peak-hour Tmrt grouped by UMEP land cover class. Paved
    cells reach the highest values, water cells the lowest, and
    vegetated cells fall between. The gap between paved and
    vegetated cells (around 19 °C on the production AOI) is the
    physical ceiling for the intervention's per-cell cooling effect.
    """)
    return


@app.cell
def _fig_lc(aoi, cfg, mo):
    from src import figures as _figures
    _figures.set_aoi(aoi.value)
    _figures.fig_landcover_tmrt()
    _path = cfg.slides_dir / "landcover_tmrt.png"
    if _path.exists():
        lc_img = mo.image(src=str(_path), width=900)
    else:
        lc_img = mo.md("Land-cover Tmrt figure unavailable.")
    lc_img
    return


@app.cell(hide_code=True)
def _section_limitations(mo):
    mo.md(r"""
    ## 13. Limitations

    Several caveats should be reported alongside the headline
    numbers.

    - **Single hot day, not summer mean.** The simulation date is
      the hottest clear-sky day of summer 2025 (June 23), when the
      intervention matters most. Multi-day heatwaves may amplify
      cooling through reduced overnight pavement heat storage under
      shade, but this effect is not modeled here.
    - **One hundred percent planting and survival assumed.** Urban
      street-tree mortality in the first five years is typically 20
      to 40 percent. Realised cooling will be lower than the model
      predicts.
    - **Two scenarios bracket outcomes; they are not a confidence
      interval.** The year 10 and mature cases do not account for
      species variability, leaf-area uncertainty, or MULC
      classification error.
    - **Spatially uniform meteorological forcing.** HRRR is resolved
      at 3 km and applied uniformly across the one-meter tile. Real
      urban canyons have lower wind, real trees transpire, and real
      shaded zones have slightly lower air temperature. All three
      effects would amplify cooling. The model output should be read
      as a radiation-only lower bound.
    - **Tmrt is masked on roofs.** Pixel statistics exclude rooftop
      cells because Tmrt is not physically valid on roofs.
    - **No exposure weighting.** Per-pixel cooling is reported.
      Translating to a public-health benefit requires foot-traffic
      data, which is not available.
    """)
    return


if __name__ == "__main__":
    app.run()
