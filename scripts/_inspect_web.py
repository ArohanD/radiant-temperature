"""Build a small MapLibre GL JS web app for 3D inspection of the patched Durham
rasters. Drops a self-contained `web/` dir under the AOI's processed folder; you
serve it with `python -m http.server` and open the URL in a browser.

What you get:
  - OSM raster basemap (no API key)
  - Overture building footprints extruded as 3D blocks (heights from Overture
    `height` property; 8m default for footprint-only buildings, drawn translucent
    so it's clear which ones are guesses)
  - Raster overlays: LiDAR DSM, patched DSM, DSM diff, Landcover (patched),
    Trees (CDSM), DEM. Toggle from a layer panel.
  - AOI tile boxes (TILE_BBOX = analysis area, PROCESSING_BBOX = with shadow buffer)
  - Right-click on a building to print its Overture height into the console
  - Pitch/rotate enabled — drag with right mouse button or hold Ctrl + drag

Run (default — laptop pipeline outputs):
  ./env/bin/python scripts/_inspect_web.py
  cd inputs/processed/{AOI_NAME}_baseline/web && python -m http.server 8765

Run (against a pulled pod-run, isolated from laptop pipeline):
  INSPECT_RUN_ROOT=outputs/pod_runs/{AOI_NAME}_<timestamp> ./env/bin/python scripts/_inspect_web.py
  cd outputs/pod_runs/{AOI_NAME}_<timestamp>/web && python -m http.server 8766
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import numpy as np
import rasterio
import matplotlib
from matplotlib import colors
from PIL import Image
from pyproj import Transformer

from _aoi import AOI_NAME, PROCESSING_BBOX, TILE_BBOX, AOI_CENTER_LAT, AOI_CENTER_LON

# Source rasters (Building_DSM, DEM, Trees, Landcover, etc.) always live in
# the laptop's canonical inputs/processed/{AOI}_baseline/ — they're inputs to
# every run, identical bytes regardless of which machine produced the SOLWEIG
# outputs. So OUT is fixed.
OUT = REPO / f"inputs/processed/{AOI_NAME}_baseline"

# INSPECT_RUN_ROOT optionally overrides the OUTPUT locations: SOLWEIG outputs
# (output_folder), scenario rasters, scenario diff rasters, and the web bundle.
# Use this to point at a pulled pod_run dir (e.g., outputs/pod_runs/{AOI}_<ts>/)
# and serve a second inspector instance without touching the laptop's live bundle.
# Layout it expects under the run root:
#     <run_root>/baseline/output_folder/   (SOLWEIG outputs)
#     <run_root>/scenario_year10/          (scenario rasters + outputs)
#     <run_root>/scenario_mature/
#     <run_root>/scenario_diffs/           (dtmrt_peak_*.tif)
# The web bundle lands at <run_root>/web/.
_RUN_ROOT = os.environ.get("INSPECT_RUN_ROOT")
if _RUN_ROOT:
    _ROOT = Path(_RUN_ROOT).resolve()
    SOLWEIG_OUT = _ROOT / "baseline" / "output_folder"
    SCENARIO_DIRS = {scen: _ROOT / f"scenario_{scen}" for scen in ("year10", "mature")}
    SCENARIO_DIFF_DIR = _ROOT / "scenario_diffs"
    WEB = _ROOT / "web"
    print(f"[inspect_web] INSPECT_RUN_ROOT={_ROOT}")
    print(f"[inspect_web] source rasters from {OUT}  (always)")
    print(f"[inspect_web] outputs from {_ROOT}")
else:
    SOLWEIG_OUT = OUT / "output_folder"
    SCENARIO_DIRS = {scen: REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}"
                     for scen in ("year10", "mature")}
    SCENARIO_DIFF_DIR = REPO / f"outputs/{AOI_NAME}_scenario_diffs"
    WEB = OUT / "web"


def _solweig_raster(prefix: str) -> Path:
    """Return the right SOLWEIG output for a given prefix (TMRT, UTCI, SVF, Shadow).
    Multi-tile mode produces output_folder/<key>/<prefix>_<key>.tif files; this
    helper merges them on demand into output_folder/<prefix>_merged.tif (cached).
    Single-tile mode returns output_folder/0_0/<prefix>_0_0.tif directly.
    Returns a Path that may not exist (caller checks .exists())."""
    import rasterio
    tiles = sorted(SOLWEIG_OUT.glob(f"*/{prefix}_*.tif"))
    if not tiles:
        return SOLWEIG_OUT / "0_0" / f"{prefix}_0_0.tif"  # nonexistent placeholder
    if len(tiles) == 1:
        return tiles[0]
    merged = SOLWEIG_OUT / f"{prefix}_merged.tif"
    if merged.exists():
        return merged
    from rasterio.merge import merge as rio_merge
    handles = [rasterio.open(p) for p in tiles]
    nodata_val = handles[0].nodata
    arr, transform = rio_merge(handles, nodata=nodata_val)
    profile = handles[0].profile.copy()
    for h in handles:
        h.close()
    profile.update(height=arr.shape[1], width=arr.shape[2], transform=transform,
                   count=arr.shape[0], compress="lzw", nodata=nodata_val)
    with rasterio.open(merged, "w", **profile) as out:
        out.write(arr)
    print(f"  merged {len(tiles)} {prefix} tiles → {merged.name} (nodata={nodata_val})")
    return merged
TREES_GEOJSON_RAW = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
WEB.mkdir(parents=True, exist_ok=True)
# Overture GeoJSON is AOI-namespaced (each AOI gets its own bbox download in
# _patch_buildings.py). Fall back to a non-namespaced legacy filename.
_overture_default = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
_overture_legacy  = REPO / "inputs/raw/durham/overture/buildings.geojson"
OVERTURE_GEOJSON = _overture_default if _overture_default.exists() else _overture_legacy

T_TO_LL = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)


# ---------------------------------------------------- raster → PNG with colormap

def _to_rgba_continuous(arr: np.ndarray, vmin: float, vmax: float, cmap_name: str,
                         nodata: float | None) -> np.ndarray:
    """Map a continuous raster to RGBA, with nodata + NaN → fully transparent."""
    a = arr.astype("float32")
    mask = ~np.isfinite(a)
    if nodata is not None:
        mask |= (a == nodata)
    safe = np.where(mask, vmin, a)
    norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    rgba = (matplotlib.colormaps[cmap_name](norm(safe)) * 255).astype("uint8")
    rgba[..., 3] = np.where(mask, 0, 220)
    return rgba


def _to_rgba_palette(arr: np.ndarray, palette: dict[int, tuple[int, int, int]]) -> np.ndarray:
    """Map an integer-coded raster to RGBA using a fixed palette. Anything not
    in the palette becomes transparent."""
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype="uint8")
    for v, (r, g, b) in palette.items():
        m = arr == v
        rgba[m, 0] = r; rgba[m, 1] = g; rgba[m, 2] = b; rgba[m, 3] = 220
    return rgba


def _to_rgba_diff(arr: np.ndarray, vlim: float = 30.0) -> np.ndarray:
    """Diverging blue→white→red, transparent at exactly 0."""
    norm = colors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    rgba = (matplotlib.colormaps["RdBu_r"](norm(np.clip(arr, -vlim, vlim))) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.abs(arr) < 0.5, 0, 200)
    return rgba


def write_data_bin(arr: np.ndarray, dst_bin: Path, bounds_utm, nodata) -> dict:
    """Write a raw little-endian binary blob of the array, plus return the metadata
    block the JS hover tool needs to sample it. Float32 stays float32; integer-coded
    rasters (Landcover, lc_change) are kept as uint8."""
    if arr.dtype.kind == "f":
        out = arr.astype("<f4")
        dtype_label = "float32"
    elif arr.dtype.kind in "ui":
        out = arr.astype("<u1")
        dtype_label = "uint8"
    else:
        raise ValueError(f"unsupported dtype {arr.dtype}")
    dst_bin.write_bytes(out.tobytes())
    return {
        "data_url": dst_bin.name,
        "dtype": dtype_label,
        "width": int(arr.shape[1]),
        "height": int(arr.shape[0]),
        "bounds_utm": [float(bounds_utm.left), float(bounds_utm.bottom),
                        float(bounds_utm.right), float(bounds_utm.top)],
        "nodata": (None if nodata is None else float(nodata)),
    }


def render_png(src: Path, dst: Path, kind: str, **kw) -> tuple[list[list[float]], int, int, dict]:
    """Render a raster to PNG, write a sidecar .bin for hover sampling, and return
    (lon/lat corners, width, height, data-block) for the manifest."""
    with rasterio.open(src) as ds:
        a = ds.read(1)
        nodata = ds.nodata
        b = ds.bounds  # left, bottom, right, top  (EPSG:32617)

    if kind == "continuous":
        rgba = _to_rgba_continuous(a, kw["vmin"], kw["vmax"], kw["cmap"], nodata)
    elif kind == "palette":
        rgba = _to_rgba_palette(a, kw["palette"])
    elif kind == "diff":
        rgba = _to_rgba_diff(a, kw.get("vlim", 30.0))
    else:
        raise ValueError(kind)

    Image.fromarray(rgba, "RGBA").save(dst, optimize=True)
    data_block = write_data_bin(a, dst.with_suffix(".bin"), b, nodata)

    tl = T_TO_LL.transform(b.left, b.top)
    tr = T_TO_LL.transform(b.right, b.top)
    br = T_TO_LL.transform(b.right, b.bottom)
    bl = T_TO_LL.transform(b.left, b.bottom)
    coords = [list(tl), list(tr), list(br), list(bl)]
    return coords, rgba.shape[1], rgba.shape[0], data_block


# UMEP landcover palette
LC_PALETTE = {
    1: (130, 130, 130),  # paved
    2: (204,   0,   0),  # building
    5: ( 60, 170,  60),  # grass / trees-on-ground
    6: (160,  80,  40),  # bare soil
    7: ( 50, 150, 230),  # water
}

LC_CHANGE_PALETTE = {
    1: (220,   0,   0),  # added building
    2: ( 50,  80, 220),  # removed building
}


# --------------------------------------------------- Overture → web-friendly geojson

def stage_overture() -> Path | None:
    """Copy the Overture GeoJSON in. Already in EPSG:4326 — no reprojection needed.
    Add `height_m` and `has_height` properties for styling."""
    if not OVERTURE_GEOJSON.exists():
        print("  no Overture GeoJSON — skipping building extrusions")
        return None
    src = json.loads(OVERTURE_GEOJSON.read_text())
    n_with = 0; n_without = 0
    for f in src["features"]:
        h = f["properties"].get("height")
        if h is None:
            f["properties"]["height_m"] = 0.0
            f["properties"]["has_height"] = 0
            n_without += 1
        else:
            f["properties"]["height_m"] = float(h)
            f["properties"]["has_height"] = 1
            n_with += 1
    dst = WEB / "overture_buildings.geojson"
    dst.write_text(json.dumps(src))
    print(f"  staged {len(src['features']):,} overture footprints "
          f"({n_with:,} with height, {n_without:,} without) → {dst}")
    return dst


# -------------------------------------------------------------- HTML template

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SOLWEIG inspector — patched-raster inspection</title>
<meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/proj4@2.11.0/dist/proj4.js"></script>
<style>
  html,body,#map {{ margin:0; padding:0; height:100%; width:100%; }}
  #ui {{
    position:absolute; top:10px; left:10px; z-index:1;
    background:rgba(20,20,28,.92); color:#eee; font:13px/1.4 system-ui, sans-serif;
    padding:10px 12px; border-radius:6px; max-width:280px;
    box-shadow:0 2px 8px rgba(0,0,0,.4);
  }}
  #ui h3 {{ margin:0 0 8px; font-size:13px; color:#9cf; font-weight:600; }}
  #ui label {{ display:block; padding:2px 0; cursor:pointer; }}
  #ui .group-head {{
    margin:8px 0 3px;
    font-size:11px;
    font-weight:600;
    text-transform:uppercase;
    letter-spacing:0.04em;
    color:#9cf;
    border-bottom:1px solid #335;
    padding-bottom:2px;
  }}
  #ui .group-head:first-child {{ margin-top:0; }}
  #ui input[type=checkbox] {{ margin-right:6px; vertical-align:middle; }}
  #ui input[type=range] {{ width:100%; margin-top:2px; }}
  #ui hr {{ border:none; border-top:1px solid #333; margin:8px 0; }}
  #ui small {{ color:#888; }}
  #info {{
    position:absolute; bottom:10px; left:10px; z-index:1;
    background:rgba(20,20,28,.92); color:#eee; font:12px/1.4 monospace;
    padding:6px 10px; border-radius:4px; pointer-events:none;
  }}
  #hover {{
    position:absolute; top:10px; right:10px; z-index:1;
    background:rgba(20,20,28,.92); color:#eee; font:12px/1.45 monospace;
    padding:8px 10px; border-radius:6px; min-width:280px; max-width:380px;
    box-shadow:0 2px 8px rgba(0,0,0,.4); pointer-events:none;
  }}
  #hover .head {{ color:#9cf; font-weight:600; margin-bottom:4px; }}
  #hover .row {{ display:flex; justify-content:space-between; gap:8px; }}
  #hover .row .k {{ color:#bbb; }}
  #hover .row .v {{ color:#fff; }}
  #hover .empty {{ color:#666; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="ui">
  <h3>Durham — Overture patch inspector</h3>
  <small>Hold right-mouse to pitch/rotate. Click a building for its height.</small>
  <hr>
  <div id="layers"></div>
  <hr>
  <label>Building extrusion opacity
    <input type="range" id="bldgOpacity" min="0" max="100" value="85">
  </label>
  <label>Raster overlay opacity
    <input type="range" id="rasterOpacity" min="0" max="100" value="80">
  </label>
</div>
<div id="info">click a building</div>
<div id="hover"><div class="head">Pixel values at cursor</div><div id="hoverBody" class="empty">move your mouse over the map…</div></div>
<script>
const MANIFEST = {MANIFEST_JSON};

const map = new maplibregl.Map({{
  container: 'map',
  style: {{
    version: 8,
    sources: {{
      osm: {{
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap contributors',
        maxzoom: 19
      }}
    }},
    layers: [{{ id:'osm', type:'raster', source:'osm' }}]
  }},
  center: [{CENTER_LON}, {CENTER_LAT}],
  zoom: 16,
  pitch: 55,
  bearing: -25,
  maxPitch: 80
}});

map.addControl(new maplibregl.NavigationControl({{ visualizePitch:true }}), 'top-right');
map.addControl(new maplibregl.ScaleControl({{ unit:'metric' }}), 'bottom-right');

map.on('load', () => {{
  // ----- raster image overlays
  for (const r of MANIFEST.rasters) {{
    map.addSource(r.id, {{ type:'image', url: r.url, coordinates: r.coords }});
    map.addLayer({{
      id: r.id, type:'raster', source: r.id,
      layout: {{ visibility: r.visible ? 'visible' : 'none' }},
      paint: {{ 'raster-opacity': 0.8, 'raster-fade-duration': 0 }}
    }});
  }}

  // ----- Overture buildings as 3D extrusions
  if (MANIFEST.overture) {{
    map.addSource('overture', {{ type:'geojson', data: MANIFEST.overture }});
    map.addLayer({{
      id: 'overture-3d', type:'fill-extrusion', source:'overture',
      paint: {{
        'fill-extrusion-height': [
          'case', ['>', ['get','height_m'], 0], ['get','height_m'], 8.0
        ],
        'fill-extrusion-base': 0,
        'fill-extrusion-color': [
          'case', ['==', ['get','has_height'], 1], '#ff8a3d', '#7d7d7d'
        ],
        'fill-extrusion-opacity': 0.85
      }}
    }});
  }}

  // ----- planted sites (Stage 5/6/7 — the intervention)
  if (MANIFEST.planted) {{
    map.addSource('planted', {{ type:'geojson', data: MANIFEST.planted }});
    map.addLayer({{
      id:'planted-points', type:'circle', source:'planted',
      paint: {{
        'circle-radius': 6, 'circle-color': '#39ff14',
        'circle-stroke-color': '#0d0d0d', 'circle-stroke-width': 1.5,
        'circle-opacity': 0.9
      }}
    }});
  }}

  // ----- 3D extruded planted disks per scenario (the actual canopy footprint
  //       and height we burn into Trees.tif). Sized per scenario_design.md.
  const SCEN_DISK_COLORS = {{ year10: '#7fc97f', mature: '#1b7837' }};  // light → deep green
  if (MANIFEST.planted_disks) {{
    for (const [scen, url] of Object.entries(MANIFEST.planted_disks)) {{
      const sid = `planted-disks-${{scen}}`;
      map.addSource(sid, {{ type:'geojson', data: url }});
      map.addLayer({{
        id: sid, type:'fill-extrusion', source: sid,
        layout: {{ visibility: scen === 'mature' ? 'visible' : 'none' }},
        paint: {{
          'fill-extrusion-height': ['get', 'canopy_h_m'],
          'fill-extrusion-base': 0,
          'fill-extrusion-color': SCEN_DISK_COLORS[scen] || '#33aa33',
          'fill-extrusion-opacity': 0.85
        }}
      }});
    }}
  }}

  // ----- AOI boxes
  map.addSource('aoi', {{ type:'geojson', data: MANIFEST.aoi }});
  map.addLayer({{ id:'aoi-line', type:'line', source:'aoi',
    paint: {{ 'line-color': ['match', ['get','kind'],
              'tile', '#33ddff', 'processing', '#ffaa00', '#ffffff'],
             'line-width': 2, 'line-dasharray': [2,2] }} }});

  // Build the layer toggle UI, grouped by processing stage
  const ui = document.getElementById('layers');
  const allLayers = [
    ...MANIFEST.rasters.map(r => ({{ id:r.id, label:r.label, visible:r.visible, group:r.group||'Other' }})),
    {{ id:'overture-3d',   label:'3D buildings (Overture)',     visible:true,  group:'Inputs (raw, Stage 3)' }},
    ...(MANIFEST.planted ? [{{ id:'planted-points', label:'Planted sites (point markers)', visible:true, group:'Scenario inputs (Stage 5)' }}] : []),
    ...Object.keys(MANIFEST.planted_disks || {{}}).map(scen => ({{
      id: `planted-disks-${{scen}}`,
      label: `3D planted disks — ${{scen}} (${{ scen === 'year10' ? '5 m / 5×5 m sq' : '12 m / 7×7 m sq' }})`,
      visible: scen === 'mature',
      group: 'Scenario inputs (Stage 5)',
    }})),
    {{ id:'aoi-line',      label:'AOI bbox',                    visible:true,  group:'Context' }},
  ];

  // Stable group order
  const GROUP_ORDER = [
    'Inputs (raw, Stage 3)',
    'Intermediate (Stage 3 build)',
    'Scenario inputs (Stage 5)',
    'Baseline results (Stage 4)',
    'Scenario results (Stage 7)',
    'Context',
    'Other',
  ];
  const grouped = new Map();
  for (const g of GROUP_ORDER) grouped.set(g, []);
  for (const l of allLayers) {{
    if (!grouped.has(l.group)) grouped.set(l.group, []);
    grouped.get(l.group).push(l);
  }}

  for (const [g, layers] of grouped) {{
    if (!layers.length) continue;
    const head = document.createElement('div');
    head.className = 'group-head';
    head.textContent = g;
    ui.appendChild(head);
    for (const l of layers) {{
      const lbl = document.createElement('label');
      lbl.innerHTML = `<input type="checkbox" data-layer="${{l.id}}" ${{l.visible?'checked':''}}> ${{l.label}}`;
      ui.appendChild(lbl);
    }}
  }}
  ui.addEventListener('change', e => {{
    const id = e.target.dataset.layer; if (!id) return;
    const vis = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty(id, 'visibility', vis);
  }});

  document.getElementById('bldgOpacity').addEventListener('input', e => {{
    map.setPaintProperty('overture-3d','fill-extrusion-opacity', e.target.value/100);
  }});
  document.getElementById('rasterOpacity').addEventListener('input', e => {{
    for (const r of MANIFEST.rasters) {{
      map.setPaintProperty(r.id, 'raster-opacity', e.target.value/100);
    }}
  }});

  map.on('click', 'overture-3d', e => {{
    const f = e.features[0]; const p = f.properties;
    const h = p.has_height === 1 || p.has_height === '1'
      ? `${{(+p.height_m).toFixed(1)}} m  (Overture)`
      : `no height — drawn at 8 m default`;
    document.getElementById('info').textContent =
      `building: ${{h}}   id=${{p.id ?? '?'}}`;
  }});
  map.on('mouseenter','overture-3d', () => map.getCanvas().style.cursor='pointer');
  map.on('mouseleave','overture-3d', () => map.getCanvas().style.cursor='');

  // ----- hover-value tool: load each raster's binary blob and sample on mousemove
  proj4.defs("EPSG:32617","+proj=utm +zone=17 +datum=WGS84 +units=m +no_defs");
  const dataCache = new Map();      // id -> TypedArray once loaded
  const dataLoading = new Map();    // id -> Promise

  async function loadBin(r) {{
    if (dataCache.has(r.id)) return dataCache.get(r.id);
    if (dataLoading.has(r.id)) return dataLoading.get(r.id);
    const p = fetch(r.data.data_url).then(x => x.arrayBuffer()).then(ab => {{
      const arr = r.data.dtype === 'uint8'
        ? new Uint8Array(ab)
        : new Float32Array(ab);
      dataCache.set(r.id, arr);
      return arr;
    }});
    dataLoading.set(r.id, p);
    return p;
  }}

  // Preload everything in parallel — local server, ~50MB total
  Promise.all(MANIFEST.rasters.map(loadBin)).then(() => {{
    document.getElementById('hoverBody').textContent =
      'move your mouse over the map (rasters loaded)';
  }});

  function sample(r, lon, lat) {{
    const arr = dataCache.get(r.id);
    if (!arr) return undefined;
    const [x, y] = proj4("EPSG:4326","EPSG:32617",[lon,lat]);
    const [xmin, ymin, xmax, ymax] = r.data.bounds_utm;
    if (x < xmin || x > xmax || y < ymin || y > ymax) return undefined;
    const col = Math.floor((x - xmin) / (xmax - xmin) * r.data.width);
    const row = Math.floor((ymax - y) / (ymax - ymin) * r.data.height);
    if (col < 0 || col >= r.data.width || row < 0 || row >= r.data.height) return undefined;
    const v = arr[row * r.data.width + col];
    if (Number.isNaN(v)) return null;
    if (r.data.nodata !== null && v === r.data.nodata) return null;
    return v;
  }}

  function fmtNum(v, fmt) {{
    if (fmt === '+.1f') return (v >= 0 ? '+' : '') + v.toFixed(1);
    const m = /^\\.(\\d+)f$/.exec(fmt) || /^[+]?\\.(\\d+)f$/.exec(fmt);
    return v.toFixed(m ? parseInt(m[1]) : 2);
  }}

  function renderHover(lon, lat) {{
    const rows = [];
    for (const r of MANIFEST.rasters) {{
      if (map.getLayoutProperty(r.id, 'visibility') !== 'visible') continue;
      const v = sample(r, lon, lat);
      let txt;
      if (v === undefined) {{ txt = '<span class="empty">outside raster / loading</span>'; }}
      else if (v === null) {{ txt = '<span class="empty">nodata</span>'; }}
      else if (r.display.kind === 'palette') {{
        const lbl = r.display.labels[String(v)] || '?';
        txt = `${{v}} <span class="empty">(${{lbl}})</span>`;
      }} else {{
        txt = `${{fmtNum(v, r.display.fmt)}} ${{r.display.unit || ''}}`.trim();
      }}
      rows.push(`<div class="row"><span class="k">${{r.label}}</span><span class="v">${{txt}}</span></div>`);
    }}
    const utm = proj4("EPSG:4326","EPSG:32617",[lon,lat]);
    const head = `<div class="row"><span class="k">lon, lat</span><span class="v">${{lon.toFixed(5)}}, ${{lat.toFixed(5)}}</span></div>` +
                 `<div class="row"><span class="k">UTM 17N x, y</span><span class="v">${{utm[0].toFixed(1)}}, ${{utm[1].toFixed(1)}}</span></div>`;
    document.getElementById('hoverBody').innerHTML =
      head + (rows.length ? '<hr style="border:none;border-top:1px solid #333;margin:5px 0">' + rows.join('') : '<div class="empty" style="margin-top:5px">enable a raster layer to see values</div>');
  }}

  map.on('mousemove', e => renderHover(e.lngLat.lng, e.lngLat.lat));
}});
</script>
</body>
</html>
'''


def main() -> None:
    print("== rendering raster overlays as PNG ==")
    rasters_meta = []

    def add(layer_id: str, label: str, src_name: str, png_name: str, kind: str,
            visible: bool = False, display: dict | None = None, group: str = "Other", **kw):
        src = OUT / src_name
        if not src.exists():
            print(f"  skip {src_name} (missing)")
            return
        png = WEB / png_name
        coords, w, h, data = render_png(src, png, kind, **kw)
        size_kb = png.stat().st_size // 1024
        print(f"  {png_name:30s} {w}×{h}  png {size_kb} KB  bin {(WEB/(png.stem+'.bin')).stat().st_size//1024} KB")
        rasters_meta.append({
            "id": layer_id, "label": label, "group": group,
            "url": png_name, "coords": coords, "visible": visible,
            "data": data, "display": display or {"kind": "continuous", "unit": "", "fmt": ".2f"},
        })

    # Diff: SOLWEIG-ready DSM minus raw LiDAR DSM. Negative (blue) where we
    # dropped non-building tall stuff (trees, noise, awnings) by gating with
    # Overture footprints. Positive (red) where Overture added a roof that
    # LiDAR missed (post-2015 buildings, mostly).
    with rasterio.open(OUT / "Building_DSM.tif") as ds:
        new_dsm = ds.read(1); b = ds.bounds; nd = ds.nodata
    with rasterio.open(OUT / "Building_DSM.preMS.tif") as ds:
        raw_dsm = ds.read(1); raw_nd = ds.nodata
    valid = (new_dsm != nd) & (raw_dsm != raw_nd)
    diff = np.where(valid, new_dsm - raw_dsm, 0).astype("float32")
    Image.fromarray(_to_rgba_diff(diff, vlim=30.0), "RGBA").save(WEB / "dsm_diff.png", optimize=True)
    diff_data = write_data_bin(diff, WEB / "dsm_diff.bin", b, nodata=None)
    tl = T_TO_LL.transform(b.left, b.top); tr = T_TO_LL.transform(b.right, b.top)
    br = T_TO_LL.transform(b.right, b.bottom); bl = T_TO_LL.transform(b.left, b.bottom)
    rasters_meta.append({
        "id":"dsm_diff",
        "label":"DSM diff (current − raw LiDAR; red=Overture added, blue=tree/noise removed)",
        "group":"Intermediate (Stage 3 build)",
        "url":"dsm_diff.png", "coords":[list(tl),list(tr),list(br),list(bl)], "visible":True,
        "data": diff_data, "display": {"kind":"continuous", "unit":"m", "fmt":"+.1f"},
    })
    print(f"  dsm_diff.png                   {diff.shape[1]}×{diff.shape[0]}  "
          f"png {(WEB/'dsm_diff.png').stat().st_size//1024} KB  "
          f"bin {(WEB/'dsm_diff.bin').stat().st_size//1024} KB")

    LC_LABELS = {1: "paved", 2: "building", 5: "grass / under-tree",
                 6: "bare soil", 7: "water"}
    lc_disp = {"kind": "palette", "labels": LC_LABELS, "name": "UMEP class"}
    elev_disp = {"kind": "continuous", "unit": "m a.s.l.", "fmt": ".1f"}
    canopy_disp = {"kind": "continuous", "unit": "m above ground", "fmt": ".1f"}
    terrain_disp = {"kind": "continuous", "unit": "m a.s.l.", "fmt": ".1f"}

    G_INPUT = "Inputs (raw, Stage 3)"
    G_INTERMEDIATE = "Intermediate (Stage 3 build)"

    add("dem", "DEM (terrain, m)", "DEM.tif",
        "dem.png", "continuous", vmin=95, vmax=135, cmap="terrain", visible=False,
        display=terrain_disp, group=G_INPUT)
    add("dsm_lidar_raw", "Building DSM (raw LiDAR first-returns — has trees + noise)",
        "Building_DSM.preMS.tif", "dsm_lidar_raw.png",
        "continuous", vmin=100, vmax=220, cmap="inferno", visible=False, display=elev_disp,
        group=G_INPUT)
    add("landcover_pre", "Landcover (MULC-only, no buildings)",
        "Landcover.preMS.tif", "landcover_pre.png",
        "palette", palette=LC_PALETTE, visible=False, display=lc_disp, group=G_INPUT)
    add("trees", "Trees CDSM (canopy heights)", "Trees.tif",
        "trees.png", "continuous", vmin=0, vmax=35, cmap="Greens", visible=False,
        display=canopy_disp, group=G_INPUT)

    add("dsm", "Building DSM (SOLWEIG-ready: ground + buildings only)",
        "Building_DSM.tif", "dsm.png",
        "continuous", vmin=100, vmax=220, cmap="inferno", visible=False, display=elev_disp,
        group=G_INTERMEDIATE)
    add("landcover", "Landcover (SOLWEIG-ready: MULC + Overture buildings)",
        "Landcover.tif", "landcover.png",
        "palette", palette=LC_PALETTE, visible=False, display=lc_disp, group=G_INTERMEDIATE)

    # ---------------- SOLWEIG outputs (Stage 4) -----------------------------
    if SOLWEIG_OUT.exists():
        print("\n  -- SOLWEIG output layers --")

        def add_band(layer_id: str, label: str, src: Path, band: int, png_name: str,
                      kind: str, visible: bool = False, display: dict | None = None,
                      group: str = "Other", **kw):
            with rasterio.open(src) as ds:
                a = ds.read(band)
                bds = ds.bounds
                nodata = ds.nodata
            if kind == "continuous":
                rgba = _to_rgba_continuous(a, kw["vmin"], kw["vmax"], kw["cmap"], nodata)
            elif kind == "palette":
                rgba = _to_rgba_palette(a, kw["palette"])
            else:
                raise ValueError(kind)
            png = WEB / png_name
            Image.fromarray(rgba, "RGBA").save(png, optimize=True)
            data = write_data_bin(a, png.with_suffix(".bin"), bds, nodata)
            tl = T_TO_LL.transform(bds.left, bds.top); tr = T_TO_LL.transform(bds.right, bds.top)
            br = T_TO_LL.transform(bds.right, bds.bottom); bl = T_TO_LL.transform(bds.left, bds.bottom)
            rasters_meta.append({
                "id": layer_id, "label": label, "group": group, "url": png_name,
                "coords": [list(tl),list(tr),list(br),list(bl)], "visible": visible,
                "data": data,
                "display": display or {"kind":"continuous","unit":"","fmt":".2f"},
            })
            print(f"  {png_name:30s} band {band:>2d}  png {png.stat().st_size//1024} KB  "
                  f"bin {png.with_suffix('.bin').stat().st_size//1024} KB")

        tmrt_path = _solweig_raster("TMRT")
        utci_path = _solweig_raster("UTCI")
        svf_path = _solweig_raster("SVF")
        shadow_path = _solweig_raster("Shadow")

        tmrt_disp = {"kind":"continuous", "unit":"°C", "fmt":".1f"}
        utci_disp = {"kind":"continuous", "unit":"°C UTCI", "fmt":".1f"}
        svf_disp  = {"kind":"continuous", "unit":"(0=closed, 1=open)", "fmt":".3f"}
        shadow_disp = {"kind":"continuous", "unit":"(0=shadow, 1=sun)", "fmt":".2f"}

        G_BASELINE = "Baseline results (Stage 4)"

        if tmrt_path.exists():
            for hour, vis in [(9, False), (15, True), (19, False), (3, False)]:
                tag = "peak" if hour == 15 else "night" if hour == 3 else f"{hour:02d}h"
                add_band(f"tmrt_h{hour:02d}", f"Tmrt at {hour:02d}:00 local ({tag})",
                         tmrt_path, hour + 1, f"tmrt_h{hour:02d}.png",
                         "continuous", visible=vis, display=tmrt_disp,
                         vmin=15, vmax=70, cmap="inferno", group=G_BASELINE)
        if utci_path.exists():
            for hour, vis in [(15, False), (9, False), (19, False)]:
                tag = "peak" if hour == 15 else f"{hour:02d}h"
                add_band(f"utci_h{hour:02d}", f"UTCI 'feels-like' at {hour:02d}:00 ({tag})",
                         utci_path, hour + 1, f"utci_h{hour:02d}.png",
                         "continuous", visible=vis, display=utci_disp,
                         vmin=20, vmax=50, cmap="magma", group=G_BASELINE)
        if svf_path.exists():
            add_band("svf", "Sky View Factor (preprocessor output)",
                     svf_path, 1, "svf.png",
                     "continuous", visible=False, display=svf_disp,
                     vmin=0, vmax=1, cmap="viridis", group=G_BASELINE)
        if shadow_path.exists():
            add_band("shadow_h15", "Shadow at 15:00 (1=sun, 0=shadow)",
                     shadow_path, 16, "shadow_h15.png",
                     "continuous", visible=False, display=shadow_disp,
                     vmin=0, vmax=1, cmap="gray", group=G_BASELINE)

    # ---------------- Stage 7 — scenario diff layers ------------------------
    if SCENARIO_DIFF_DIR.exists():
        print("\n  -- scenario diff layers (Stage 7) --")
        diff_disp = {"kind":"continuous", "unit":"°C", "fmt":"+.1f"}
        for scen in ("year10", "mature"):
            src = SCENARIO_DIFF_DIR / f"dtmrt_peak_{scen}.tif"
            if not src.exists():
                continue
            with rasterio.open(src) as ds:
                a = ds.read(1).astype("float32")
                bds = ds.bounds
            # Diverging colormap for cooling/warming. NaN = building (transparent).
            mask = ~np.isfinite(a)
            from matplotlib import colors as mcolors_
            norm = mcolors_.TwoSlopeNorm(vmin=-25, vcenter=0, vmax=5)
            rgba = (matplotlib.colormaps["RdBu_r"](norm(np.where(mask, 0, a))) * 255).astype("uint8")
            rgba[..., 3] = np.where(mask | (np.abs(a) < 0.05), 0, 220)
            png = WEB / f"dtmrt_peak_{scen}.png"
            Image.fromarray(rgba, "RGBA").save(png, optimize=True)
            data = write_data_bin(a, png.with_suffix(".bin"), bds, nodata=None)
            tl = T_TO_LL.transform(bds.left, bds.top); tr = T_TO_LL.transform(bds.right, bds.top)
            br = T_TO_LL.transform(bds.right, bds.bottom); bl = T_TO_LL.transform(bds.left, bds.bottom)
            rasters_meta.append({
                "id": f"dtmrt_{scen}",
                "label": f"ΔTmrt at peak (scenario={scen} − baseline)",
                "group": "Scenario results (Stage 7)",
                "url": png.name, "coords":[list(tl),list(tr),list(br),list(bl)],
                "visible": (scen == "mature"),
                "data": data, "display": diff_disp,
            })
            print(f"  {png.name:30s}  png {png.stat().st_size//1024} KB  "
                  f"bin {png.with_suffix('.bin').stat().st_size//1024} KB")

    overture_path = stage_overture()

    # Stage planted-points layer for the inspector + 3D disks per scenario
    planted_geojson_path = None
    planted_disks = {}  # scenario_name -> path
    if TREES_GEOJSON_RAW.exists():
        import geopandas as gpd
        sites = gpd.read_file(TREES_GEOJSON_RAW)
        sites = sites[sites["present"] == "Planting Site"].to_crs("EPSG:32617")
        sites_utm = sites.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]].copy()
        # Point markers (lat/lon)
        sites_ll = sites_utm.to_crs("EPSG:4326")
        planted_geojson_path = WEB / "planted_sites.geojson"
        sites_ll.to_file(planted_geojson_path, driver="GeoJSON")
        print(f"  staged {len(sites_ll)} planting-site points → {planted_geojson_path}")

        # 3D extruded disks: square buffers in UTM, then to lat/lon for MapLibre.
        # Per scenario_design.md: year10 = 5 m canopy / 5×5 m sq footprint;
        #                         mature = 12 m canopy / 7×7 m sq footprint.
        SCENARIO_DISKS = {"year10": (5.0, 2.5), "mature": (12.0, 3.5)}
        for scen, (canopy_h_m, half_side_m) in SCENARIO_DISKS.items():
            buf = sites_utm.copy()
            buf["geometry"] = buf.geometry.buffer(half_side_m, cap_style=3)  # square
            buf["canopy_h_m"] = canopy_h_m
            buf["scenario"] = scen
            buf_ll = buf[["geometry", "canopy_h_m", "scenario"]].to_crs("EPSG:4326")
            dst = WEB / f"planted_disks_{scen}.geojson"
            buf_ll.to_file(dst, driver="GeoJSON")
            planted_disks[scen] = dst.name
            print(f"  staged {len(buf_ll)} planting disks ({scen}, h={canopy_h_m} m) → {dst}")

    # ---------------- Trees CDSM diff (scenario − baseline) -----------------
    print("\n  -- Trees CDSM diff layers (scenario − baseline) --")
    canopy_disp_diff = {"kind":"continuous", "unit":"m canopy added", "fmt":"+.1f"}
    with rasterio.open(OUT / "Trees.tif") as ds:
        base_t = ds.read(1).astype("float32")
        t_bds = ds.bounds
    for scen, vmax_canopy in (("year10", 5.0), ("mature", 12.0)):
        scen_t_path = SCENARIO_DIRS[scen] / "Trees.tif"
        if not scen_t_path.exists():
            continue
        with rasterio.open(scen_t_path) as ds:
            scen_t = ds.read(1).astype("float32")
        diff = scen_t - base_t
        # Color: solid green ramp from 0 (transparent) to vmax_canopy
        mask = np.abs(diff) < 0.01
        norm = colors.Normalize(vmin=0, vmax=max(5, vmax_canopy + 2))
        rgba = (matplotlib.colormaps["Greens"](norm(np.where(mask, 0, diff))) * 255).astype("uint8")
        rgba[..., 3] = np.where(mask, 0, 230)
        png = WEB / f"trees_diff_{scen}.png"
        Image.fromarray(rgba, "RGBA").save(png, optimize=True)
        data = write_data_bin(diff, png.with_suffix(".bin"), t_bds, nodata=None)
        tl = T_TO_LL.transform(t_bds.left, t_bds.top); tr = T_TO_LL.transform(t_bds.right, t_bds.top)
        br = T_TO_LL.transform(t_bds.right, t_bds.bottom); bl = T_TO_LL.transform(t_bds.left, t_bds.bottom)
        rasters_meta.append({
            "id": f"trees_diff_{scen}",
            "label": f"Δ Trees CDSM ({scen} − baseline) — green = canopy added",
            "group": "Scenario inputs (Stage 5)",
            "url": png.name, "coords":[list(tl),list(tr),list(br),list(bl)],
            "visible": False,
            "data": data, "display": canopy_disp_diff,
        })
        print(f"  {png.name:30s}  png {png.stat().st_size//1024} KB  bin {png.with_suffix('.bin').stat().st_size//1024} KB")

    # AOI boxes as a single FeatureCollection
    def box_to_feature(bbox, kind):
        x0, y0, x1, y1 = bbox
        ring_utm = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        ring_ll = [list(T_TO_LL.transform(x, y)) for x, y in ring_utm]
        return {"type":"Feature", "properties":{"kind":kind},
                "geometry":{"type":"Polygon", "coordinates":[ring_ll]}}
    aoi_fc = {"type":"FeatureCollection", "features":[
        box_to_feature(TILE_BBOX, "tile"),
        box_to_feature(PROCESSING_BBOX, "processing"),
    ]}

    manifest = {
        "rasters": rasters_meta,
        "overture": "overture_buildings.geojson" if overture_path else None,
        "planted": "planted_sites.geojson" if planted_geojson_path else None,
        "planted_disks": planted_disks,
        "aoi": aoi_fc,
    }

    html = INDEX_HTML.format(
        MANIFEST_JSON=json.dumps(manifest),
        CENTER_LON=AOI_CENTER_LON,
        CENTER_LAT=AOI_CENTER_LAT,
    )
    (WEB / "index.html").write_text(html)
    print(f"\n  wrote {WEB/'index.html'}")
    print(f"\nServe:\n  cd {WEB} && python -m http.server 8765\n  open http://localhost:8765/")


if __name__ == "__main__":
    main()
