"""Notebook 0: data acquisition for the configured AOI.

Pulls everything a SOLWEIG run needs that does not depend on heavy local
processing. The PDAL retrieval lives in notebook 2. Each fetch is keyed by
destination filename and skipped when the file already exists. The final
cell renders the raw inputs in the MapLibre inspector for visual confirmation.
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
def _aoi_config(mo):
    from src.geo import setup_geo_env
    setup_geo_env()
    from src.aoi import (AOI_NAME, AOI_CENTER_LAT, AOI_CENTER_LON, AOI_SIZE_KM,
                          SIM_DATE, UTC_OFFSET, TILE_BBOX, PROCESSING_BBOX)
    aoi_summary = mo.md(
        f"""
        ## Area of interest

        | parameter | value |
        |---|---|
        | name | `{AOI_NAME}` |
        | centre (lat, lon) | {AOI_CENTER_LAT}, {AOI_CENTER_LON} |
        | size | {AOI_SIZE_KM} km × {AOI_SIZE_KM} km |
        | simulation date | {SIM_DATE} |
        | UTC offset | {UTC_OFFSET:+d} hours |

        Configuration is read from `src/aoi.py`. Edit that module and re-run to
        relocate the analysis.
        """
    )
    aoi_summary
    return (
        AOI_CENTER_LAT,
        AOI_CENTER_LON,
        AOI_NAME,
        PROCESSING_BBOX,
        SIM_DATE,
        UTC_OFFSET,
    )


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
        "## Local cache\n\n"
        "| dataset | present | size |\n|---|---|---|\n" + "\n".join(_rows)
    )
    cache_status
    return


@app.cell
def _fetch_planting_sites(REPO, mo):
    """Durham Open Data, Trees and Planting Sites layer (paginated GeoJSON)."""
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
    trees_status = mo.md(f"### Durham trees and planting sites\n\n`{_msg}`")
    trees_status
    return


@app.cell
def _fetch_mulc(REPO, mo):
    """EnviroAtlas Durham 1m MULC GeoTIFF (zip extract)."""
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
    mulc_status = mo.md(f"### EnviroAtlas MULC raster\n\n`{_msg}`")
    mulc_status
    return


@app.cell
def _fetch_krdu(REPO, mo):
    """Iowa Mesonet hourly observations for KRDU, summer 2025."""
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
    krdu_status = mo.md(f"### KRDU ASOS observations\n\n`{_msg}`")
    krdu_status
    return


@app.cell
def _fetch_overture(AOI_NAME, PROCESSING_BBOX, REPO, mo):
    """Overture Foundation building footprints for the AOI."""
    from src.buildings import fetch_overture as _fetch
    _dst = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    if not _dst.exists():
        _fetch(AOI_NAME, PROCESSING_BBOX, _dst)
    overture_status = mo.md(
        f"### Overture buildings\n\n"
        f"`{_dst.relative_to(REPO)} ({_dst.stat().st_size // 1024:,} KB)`"
    )
    overture_status
    return


@app.cell
def _fetch_met(AOI_CENTER_LAT, AOI_CENTER_LON, REPO, SIM_DATE, UTC_OFFSET, mo):
    """HRRR analysis hourly met forcing for SIM_DATE."""
    from src.met import write_umep_met_for_aoi
    from src.aoi import OUTPUT_PREFIX
    _path = write_umep_met_for_aoi(OUTPUT_PREFIX, AOI_CENTER_LAT, AOI_CENTER_LON,
                                    SIM_DATE, UTC_OFFSET)
    met_status = mo.md(f"### HRRR met forcing\n\n`{_path.relative_to(REPO)}`")
    met_status
    return


@app.cell
def _lidar_url_check(mo):
    """Verify the NC Phase 3 EPT endpoint resolves. Actual LiDAR retrieval is
    deferred to notebook 2 because the PDAL operation is expensive."""
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
        f"### NC LiDAR EPT (NOAA dataset 6209)\n\n"
        f"`{_url}`\n\n"
        f"Status: `{_status}`. PDAL retrieval runs in notebook 2."
    )
    lidar_status
    return


@app.cell
def _inspector_view(REPO, mo):
    """Self-contained MapLibre view of the raw inputs gathered above."""
    from src import inspector as _inspector
    _bundle = _inspector.build_bundle()
    _url = _inspector.serve(_bundle)
    inspector_md = mo.md(
        f"## Web inspector\n\n"
        f"Layered view of the AOI footprint, planted sites, Overture building "
        f"polygons, and the MULC class palette.\n\n"
        f"Bundle written to `{_bundle.relative_to(REPO)}`. "
        f"Serving at [{_url}]({_url})."
    )
    inspector_md
    inspector_iframe = mo.iframe(_url, width="100%", height=600)
    inspector_iframe
    return


if __name__ == "__main__":
    app.run()
