import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _intro(mo):
    mo.md(
        r"""
        # Notebook 0. Data acquisition

        This notebook collects every input that does not require local heavy
        computation. The retrieval of NC LiDAR is deferred to notebook 2 because
        the PDAL pipeline depends on the AOI bounding box and is the slowest
        step in the analysis.

        Each fetch cell is keyed by destination filename and skipped when the
        file is already present on disk. Re-running the notebook is therefore
        cheap once the cache is warm.

        ## Suggested order of execution

        1. Confirm the AOI configuration in the next section.
        2. Read the local cache table to see which datasets are already present.
        3. Step through the fetch cells. Each prints a short status line.
        4. Open the final web inspector to confirm that the inputs cover the
           expected footprint.
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
def _section_config(mo):
    mo.md(
        r"""
        ## 1. Configuration

        Every value below is read from `src/aoi.py`. To relocate the analysis
        to a different neighbourhood, edit that module and re-run the
        notebook.
        """
    )
    return


@app.cell
def _aoi_config(mo):
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, AOI_CENTER_LAT, AOI_CENTER_LON, AOI_SIZE_KM,
                          SIM_DATE, UTC_OFFSET, PROCESSING_BBOX)
    aoi_summary = mo.md(
        f"""
        | parameter | value |
        |---|---|
        | name | `{AOI_NAME}` |
        | centre (lat, lon) | {AOI_CENTER_LAT}, {AOI_CENTER_LON} |
        | size | {AOI_SIZE_KM} km × {AOI_SIZE_KM} km |
        | simulation date | {SIM_DATE} |
        | UTC offset | {UTC_OFFSET:+d} hours |
        """
    )
    aoi_summary
    return AOI_CENTER_LAT, AOI_CENTER_LON, AOI_NAME, PROCESSING_BBOX, SIM_DATE, UTC_OFFSET


@app.cell(hide_code=True)
def _section_cache(mo):
    mo.md(
        r"""
        ## 2. Local cache inventory

        Datasets that have already been downloaded show up below with their
        on-disk size. Anything missing is fetched in the next section. Removing
        a file forces a fresh download on the next run.
        """
    )
    return


@app.cell
def _disk_status(REPO, mo):
    _raw = REPO / "inputs/raw/durham"
    _items = {
        "Durham planting sites": _raw / "trees_planting/durham_trees.geojson",
        "EnviroAtlas MULC raster": _raw / "enviroatlas_mulc/DNC_MULC.tif",
        "KRDU summer 2025 obs": _raw / "krdu_asos/krdu_2025_summer.csv",
        "Overture buildings": _raw / "overture/buildings_durham_hayti.geojson",
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
    mo.md(
        r"""
        ## 3. Public datasets

        Four sources are pulled in this section. Each cell is independent and
        idempotent.

        - **Durham planting sites.** Locations of trees Durham plans to plant
          between 2025 and 2028. The full layer is paginated; the cell pulls
          all pages once and caches the resulting GeoJSON.
        - **EnviroAtlas MULC raster.** A 1 m land-cover product covering
          Durham County. The download is a zipped GeoTIFF.
        - **KRDU ASOS observations.** Hourly air temperature and sky-cover
          observations from the Raleigh-Durham airport for summer 2025. Used
          to identify the hottest clear-sky day for the simulation and to
          cross-check the meteorological forcing later.
        - **Overture buildings.** Open-licence building footprints with
          height attributes for the area of interest.
        """
    )
    return


@app.cell
def _fetch_planting_sites(REPO, mo):
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
    trees_status = mo.md(f"**Durham trees and planting sites.** `{_msg}`")
    trees_status
    return


@app.cell
def _fetch_mulc(REPO, mo):
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
    mulc_status = mo.md(f"**EnviroAtlas MULC raster.** `{_msg}`")
    mulc_status
    return


@app.cell
def _fetch_krdu(REPO, mo):
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
    krdu_status = mo.md(f"**KRDU ASOS observations.** `{_msg}`")
    krdu_status
    return


@app.cell
def _fetch_overture(AOI_NAME, PROCESSING_BBOX, REPO, mo):
    from src.buildings import fetch_overture as _fetch
    _dst = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    if not _dst.exists():
        _fetch(AOI_NAME, PROCESSING_BBOX, _dst)
    overture_status = mo.md(
        f"**Overture buildings.** `{_dst.relative_to(REPO)} "
        f"({_dst.stat().st_size // 1024:,} KB)`"
    )
    overture_status
    return


@app.cell(hide_code=True)
def _section_met(mo):
    mo.md(
        r"""
        ## 4. Meteorological forcing

        SOLWEIG is driven by hourly air temperature, humidity, wind, surface
        pressure, downwelling shortwave radiation, downwelling longwave
        radiation, and precipitation. The cell below pulls a single grid
        point from the NOAA HRRR analysis archive and writes a UMEP-compliant
        own-met file inside the baseline run folder. The dataset is hosted on
        anonymous S3 via the `dynamical-catalog` package, so no API key is
        required.
        """
    )
    return


@app.cell
def _fetch_met(AOI_CENTER_LAT, AOI_CENTER_LON, REPO, SIM_DATE, UTC_OFFSET, mo):
    from src.met import write_umep_met_for_aoi
    from src.aoi import OUTPUT_PREFIX
    _path = write_umep_met_for_aoi(OUTPUT_PREFIX, AOI_CENTER_LAT, AOI_CENTER_LON,
                                    SIM_DATE, UTC_OFFSET)
    met_status = mo.md(f"**HRRR own-met file.** `{_path.relative_to(REPO)}`")
    met_status
    return


@app.cell(hide_code=True)
def _section_lidar(mo):
    mo.md(
        r"""
        ## 5. LiDAR endpoint check

        The DSM and DEM are derived from the NC Phase 3 LiDAR product
        (NOAA dataset 6209), accessed as an Entwine Point Tile store. The
        actual PDAL retrieval is deferred to notebook 2 because the
        operation is slow and depends on the processing bounding box. The
        cell below confirms only that the endpoint is reachable.
        """
    )
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
        f"Status: `{_status}`. PDAL retrieval runs in notebook 2."
    )
    lidar_status
    return


@app.cell(hide_code=True)
def _section_inspector(mo):
    mo.md(
        r"""
        ## 6. Visual confirmation

        The view below renders the AOI footprint, the planted-site point
        markers, the Overture building polygons, and the EnviroAtlas land
        cover on top of an OpenStreetMap basemap. Toggle layers from the panel
        on the left.

        Use this view to confirm that the AOI box covers the part of Hayti
        the analysis is meant to study and that the planted-site points are
        clustered as expected.
        """
    )
    return


@app.cell
def _inspector_view(REPO, mo):
    from src import inspector as _inspector
    _bundle = _inspector.build_bundle()
    _url = _inspector.serve(_bundle)
    inspector_md = mo.md(
        f"Inspector bundle: `{_bundle.relative_to(REPO)}`. "
        f"[Open in a new tab]({_url})."
    )
    inspector_md
    inspector_iframe = mo.iframe(_url, width="100%", height=600)
    inspector_iframe
    return


@app.cell(hide_code=True)
def _next_steps(mo):
    mo.md(
        r"""
        ## Next step

        With the public datasets in place, run
        [`notebooks/2_prepare_buildings.py`](2_prepare_buildings.py) to
        derive the four co-registered SOLWEIG-ready rasters. That step is
        the slowest in the pipeline because it includes the PDAL pull from
        the NC Phase 3 LiDAR archive.
        """
    )
    return


if __name__ == "__main__":
    app.run()
