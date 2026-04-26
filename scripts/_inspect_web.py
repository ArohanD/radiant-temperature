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

Run:
  ./env/bin/python scripts/_inspect_web.py
  cd inputs/processed/{AOI_NAME}_baseline/web && python -m http.server 8765
  open http://localhost:8765
"""
from __future__ import annotations

import json
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

OUT = REPO / f"inputs/processed/{AOI_NAME}_baseline"
SOLWEIG_OUT = OUT / "output_folder" / "0_0"
WEB = OUT / "web"
WEB.mkdir(exist_ok=True)
OVERTURE_GEOJSON = REPO / "inputs/raw/durham/overture/buildings.geojson"

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
<title>Durham downtown — patched-raster inspection</title>
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

  // ----- AOI boxes
  map.addSource('aoi', {{ type:'geojson', data: MANIFEST.aoi }});
  map.addLayer({{ id:'aoi-line', type:'line', source:'aoi',
    paint: {{ 'line-color': ['match', ['get','kind'],
              'tile', '#33ddff', 'processing', '#ffaa00', '#ffffff'],
             'line-width': 2, 'line-dasharray': [2,2] }} }});

  // Build the layer toggle UI
  const ui = document.getElementById('layers');
  const allLayers = [
    ...MANIFEST.rasters.map(r => ({{ id:r.id, label:r.label, visible:r.visible }})),
    {{ id:'overture-3d', label:'3D buildings (Overture)', visible:true }},
    {{ id:'aoi-line', label:'AOI bbox', visible:true }},
  ];
  for (const l of allLayers) {{
    const lbl = document.createElement('label');
    lbl.innerHTML = `<input type="checkbox" data-layer="${{l.id}}" ${{l.visible?'checked':''}}> ${{l.label}}`;
    ui.appendChild(lbl);
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
            visible: bool = False, display: dict | None = None, **kw):
        src = OUT / src_name
        if not src.exists():
            print(f"  skip {src_name} (missing)")
            return
        png = WEB / png_name
        coords, w, h, data = render_png(src, png, kind, **kw)
        size_kb = png.stat().st_size // 1024
        print(f"  {png_name:30s} {w}×{h}  png {size_kb} KB  bin {(WEB/(png.stem+'.bin')).stat().st_size//1024} KB")
        rasters_meta.append({
            "id": layer_id, "label": label,
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

    add("landcover", "Landcover (SOLWEIG-ready: MULC + Overture buildings)",
        "Landcover.tif", "landcover.png",
        "palette", palette=LC_PALETTE, visible=False, display=lc_disp)
    add("landcover_pre", "Landcover (MULC-only, no buildings)",
        "Landcover.preMS.tif", "landcover_pre.png",
        "palette", palette=LC_PALETTE, visible=False, display=lc_disp)
    add("dsm", "Building DSM (SOLWEIG-ready: ground + buildings only)",
        "Building_DSM.tif", "dsm.png",
        "continuous", vmin=100, vmax=220, cmap="inferno", visible=False, display=elev_disp)
    add("dsm_lidar_raw", "Building DSM (raw LiDAR first-returns — has trees + noise)",
        "Building_DSM.preMS.tif", "dsm_lidar_raw.png",
        "continuous", vmin=100, vmax=220, cmap="inferno", visible=False, display=elev_disp)
    add("trees", "Trees CDSM (canopy heights)", "Trees.tif",
        "trees.png", "continuous", vmin=0, vmax=35, cmap="Greens", visible=False,
        display=canopy_disp)
    add("dem", "DEM (terrain, m)", "DEM.tif",
        "dem.png", "continuous", vmin=95, vmax=135, cmap="terrain", visible=False,
        display=terrain_disp)

    # ---------------- SOLWEIG outputs (Stage 4) -----------------------------
    if SOLWEIG_OUT.exists():
        print("\n  -- SOLWEIG output layers --")

        def add_band(layer_id: str, label: str, src: Path, band: int, png_name: str,
                      kind: str, visible: bool = False, display: dict | None = None, **kw):
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
                "id": layer_id, "label": label, "url": png_name,
                "coords": [list(tl),list(tr),list(br),list(bl)], "visible": visible,
                "data": data,
                "display": display or {"kind":"continuous","unit":"","fmt":".2f"},
            })
            print(f"  {png_name:30s} band {band:>2d}  png {png.stat().st_size//1024} KB  "
                  f"bin {png.with_suffix('.bin').stat().st_size//1024} KB")

        tmrt_path = SOLWEIG_OUT / "TMRT_0_0.tif"
        utci_path = SOLWEIG_OUT / "UTCI_0_0.tif"
        svf_path = SOLWEIG_OUT / "SVF_0_0.tif"
        shadow_path = SOLWEIG_OUT / "Shadow_0_0.tif"

        tmrt_disp = {"kind":"continuous", "unit":"°C", "fmt":".1f"}
        utci_disp = {"kind":"continuous", "unit":"°C UTCI", "fmt":".1f"}
        svf_disp  = {"kind":"continuous", "unit":"(0=closed, 1=open)", "fmt":".3f"}
        shadow_disp = {"kind":"continuous", "unit":"(0=shadow, 1=sun)", "fmt":".2f"}

        # Tmrt at three representative hours: morning shadows, plateau, evening
        if tmrt_path.exists():
            for hour, vis in [(9, False), (15, True), (19, False), (3, False)]:
                tag = "peak" if hour == 15 else "night" if hour == 3 else f"{hour:02d}h"
                add_band(f"tmrt_h{hour:02d}", f"Tmrt at {hour:02d}:00 local ({tag})",
                         tmrt_path, hour + 1, f"tmrt_h{hour:02d}.png",
                         "continuous", visible=vis, display=tmrt_disp,
                         vmin=15, vmax=70, cmap="inferno")
        if utci_path.exists():
            for hour, vis in [(15, False), (9, False), (19, False)]:
                tag = "peak" if hour == 15 else f"{hour:02d}h"
                add_band(f"utci_h{hour:02d}", f"UTCI 'feels-like' at {hour:02d}:00 ({tag})",
                         utci_path, hour + 1, f"utci_h{hour:02d}.png",
                         "continuous", visible=vis, display=utci_disp,
                         vmin=20, vmax=50, cmap="magma")
        if svf_path.exists():
            add_band("svf", "Sky View Factor (preprocessor output)",
                     svf_path, 1, "svf.png",
                     "continuous", visible=False, display=svf_disp,
                     vmin=0, vmax=1, cmap="viridis")
        if shadow_path.exists():
            add_band("shadow_h15", "Shadow at 15:00 (1=sun, 0=shadow)",
                     shadow_path, 16, "shadow_h15.png",
                     "continuous", visible=False, display=shadow_disp,
                     vmin=0, vmax=1, cmap="gray")

    overture_path = stage_overture()

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
