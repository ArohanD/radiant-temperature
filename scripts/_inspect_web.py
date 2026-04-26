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
WEB = OUT / "web"
WEB.mkdir(exist_ok=True)
OVERTURE_GEOJSON = REPO / "inputs/raw/durham/overture/buildings.geojson"

T_TO_LL = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)


# ---------------------------------------------------- raster → PNG with colormap

def _to_rgba_continuous(arr: np.ndarray, vmin: float, vmax: float, cmap_name: str,
                         nodata: float | None) -> np.ndarray:
    """Map a continuous raster to RGBA, with nodata → fully transparent."""
    a = arr.astype("float32")
    if nodata is not None:
        mask = a == nodata
    else:
        mask = np.zeros_like(a, dtype=bool)
    norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    rgba = (matplotlib.colormaps[cmap_name](norm(a)) * 255).astype("uint8")
    rgba[..., 3] = np.where(mask, 0, 220)  # 86% opacity for visible cells
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


def render_png(src: Path, dst: Path, kind: str, **kw) -> tuple[list[list[float]], int, int]:
    """Render a single raster to PNG and return its [[lon,lat],..] corners (TR-BR-BL-TL)
    suitable for a MapLibre `image` source's `coordinates` field."""
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

    # MapLibre expects coordinates in this order: TL, TR, BR, BL  (lon, lat)
    tl = T_TO_LL.transform(b.left, b.top)
    tr = T_TO_LL.transform(b.right, b.top)
    br = T_TO_LL.transform(b.right, b.bottom)
    bl = T_TO_LL.transform(b.left, b.bottom)
    coords = [list(tl), list(tr), list(br), list(bl)]
    return coords, rgba.shape[1], rgba.shape[0]


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
      paint: {{ 'raster-opacity': r.visible ? 0.8 : 0, 'raster-fade-duration': 0 }}
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
}});
</script>
</body>
</html>
'''


def main() -> None:
    print("== rendering raster overlays as PNG ==")
    rasters_meta = []

    def add(layer_id: str, label: str, src_name: str, png_name: str, kind: str,
            visible: bool = False, **kw):
        src = OUT / src_name
        if not src.exists():
            print(f"  skip {src_name} (missing)")
            return
        png = WEB / png_name
        coords, w, h = render_png(src, png, kind, **kw)
        size_kb = png.stat().st_size // 1024
        print(f"  {png_name:30s} {w}×{h}  {size_kb} KB")
        rasters_meta.append({
            "id": layer_id, "label": label,
            "url": png_name, "coords": coords, "visible": visible,
        })

    # Render dsm_diff from the two inputs (computed in-memory; not a single source raster)
    with rasterio.open(OUT / "Building_DSM.tif") as ds:
        new_dsm = ds.read(1); b = ds.bounds; nd = ds.nodata
    with rasterio.open(OUT / "Building_DSM.preMS.tif") as ds:
        old_dsm = ds.read(1)
    valid = (new_dsm != nd) & (old_dsm != nd)
    diff = np.where(valid, new_dsm - old_dsm, 0).astype("float32")
    rgba = _to_rgba_diff(diff, vlim=30.0)
    Image.fromarray(rgba, "RGBA").save(WEB / "dsm_diff.png", optimize=True)
    tl = T_TO_LL.transform(b.left, b.top)
    tr = T_TO_LL.transform(b.right, b.top)
    br = T_TO_LL.transform(b.right, b.bottom)
    bl = T_TO_LL.transform(b.left, b.bottom)
    rasters_meta.append({"id":"dsm_diff", "label":"DSM diff (red = Overture lifted, blue = lowered)",
                         "url":"dsm_diff.png", "coords":[list(tl),list(tr),list(br),list(bl)],
                         "visible":True})
    print(f"  dsm_diff.png                   {rgba.shape[1]}×{rgba.shape[0]}  "
          f"{(WEB/'dsm_diff.png').stat().st_size//1024} KB")

    add("landcover_patched", "Landcover (patched, UMEP codes)", "Landcover.tif", "landcover.png",
        "palette", palette=LC_PALETTE, visible=False)
    add("landcover_pre", "Landcover (LiDAR only)", "Landcover.preMS.tif", "landcover_pre.png",
        "palette", palette=LC_PALETTE, visible=False)
    add("dsm_patched", "Building DSM (patched, m above sea level)", "Building_DSM.tif",
        "dsm_patched.png", "continuous", vmin=100, vmax=220, cmap="inferno", visible=False)
    add("dsm_pre", "Building DSM (LiDAR only)", "Building_DSM.preMS.tif",
        "dsm_pre.png", "continuous", vmin=100, vmax=220, cmap="inferno", visible=False)
    add("trees", "Trees CDSM (canopy height, m)", "Trees.tif",
        "trees.png", "continuous", vmin=0, vmax=35, cmap="Greens", visible=False)
    add("dem", "DEM (terrain, m)", "DEM.tif",
        "dem.png", "continuous", vmin=95, vmax=135, cmap="terrain", visible=False)

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
