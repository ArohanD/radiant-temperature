"""Slim MapLibre inspector bundle builder.

Writes a self-contained directory under
`inputs/processed/{aoi}_baseline/web/` containing:

- `index.html` — a static MapLibre app rendered from the template at
  `src/inspector_index.html`.
- `tmrt_peak.png` — baseline mean radiant temperature at peak hour
  (band 16 of the 24-band hourly raster, ie. 15:00 local).
- `dutci_mature.png` — ΔUTCI for the mature scenario at peak hour.
- `aoi.geojson`, `planted_sites.geojson` — vector context.

To view the bundle locally:

    python -m http.server 8765 --directory inputs/processed/<aoi>_baseline/web

Then open http://localhost:8765/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from matplotlib import colormaps
from matplotlib.colors import Normalize
from pyproj import Transformer

from src.aoi import get_aoi

REPO = Path(__file__).resolve().parent.parent
INDEX_TEMPLATE = REPO / "src" / "inspector_index.html"
_TO_LL = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)

_active_profile = os.environ.get("AOI_PROFILE", "hayti_demo")


def set_aoi(profile: str) -> None:
    """Switch the bundle target to a specific AOI profile."""
    global _active_profile
    _active_profile = profile
    os.environ["AOI_PROFILE"] = profile


def _bounds_to_coords(bounds) -> list[list[float]]:
    """Raster bounds in UTM 17N → corner coords in lon/lat for MapLibre."""
    return [
        list(_TO_LL.transform(bounds.left, bounds.top)),
        list(_TO_LL.transform(bounds.right, bounds.top)),
        list(_TO_LL.transform(bounds.right, bounds.bottom)),
        list(_TO_LL.transform(bounds.left, bounds.bottom)),
    ]


def _read_band(path: Path, band: int = 1):
    with rasterio.open(path) as ds:
        arr = ds.read(band).astype("float32")
        if ds.nodata is not None:
            arr = np.where(arr == ds.nodata, np.nan, arr)
        return arr, ds.bounds


def _write_continuous_overlay(arr, out: Path, vmin: float, vmax: float,
                                cmap_name: str) -> None:
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    cmap = colormaps[cmap_name]
    valid = np.isfinite(arr)
    rgba = (cmap(norm(np.where(valid, arr, vmin))) * 255).astype("uint8")
    rgba[..., 3] = np.where(valid, 220, 0)
    Image.fromarray(rgba, "RGBA").save(out, optimize=True)


def _write_diff_overlay(arr, out: Path, vlim: float) -> None:
    norm = Normalize(vmin=-vlim, vmax=vlim, clip=True)
    cmap = colormaps["RdBu_r"]
    valid = np.isfinite(arr) & (np.abs(arr) > 0.01)
    rgba = (cmap(norm(np.where(valid, arr, 0))) * 255).astype("uint8")
    rgba[..., 3] = np.where(valid, 220, 0)
    Image.fromarray(rgba, "RGBA").save(out, optimize=True)


def _aoi_box_geojson(cfg) -> dict:
    x0, y0, x1, y1 = cfg.tile_bbox
    ring = [
        list(_TO_LL.transform(x0, y0)),
        list(_TO_LL.transform(x1, y0)),
        list(_TO_LL.transform(x1, y1)),
        list(_TO_LL.transform(x0, y1)),
        list(_TO_LL.transform(x0, y0)),
    ]
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"kind": "aoi"},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }],
    }


def _planted_sites(cfg, out_path: Path) -> bool:
    src = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    if not src.exists():
        return False
    import geopandas as gpd
    gdf = gpd.read_file(src)
    planting = gdf[gdf["present"] == "Planting Site"]
    x0, y0, x1, y1 = cfg.tile_bbox
    lon0, lat0 = _TO_LL.transform(x0, y0)
    lon1, lat1 = _TO_LL.transform(x1, y1)
    in_aoi = planting.cx[lon0:lon1, lat0:lat1]
    in_aoi[["geometry"]].to_file(out_path, driver="GeoJSON")
    return True


def build_bundle(aoi: str | None = None) -> Path:
    """Render a static MapLibre bundle for the active (or supplied) AOI.

    Returns the path of the bundle directory. Idempotent — overwrites any
    previous bundle for the same AOI.
    """
    if aoi is not None:
        set_aoi(aoi)
    cfg = get_aoi(_active_profile)
    out_dir = cfg.baseline_dir / "web"
    out_dir.mkdir(parents=True, exist_ok=True)
    layers: list[dict] = []

    tmrt_src = cfg.baseline_dir / "output_folder" / "TMRT_merged.tif"
    if tmrt_src.exists():
        arr, bounds = _read_band(tmrt_src, band=16)
        _write_continuous_overlay(arr, out_dir / "tmrt_peak.png",
                                    vmin=20, vmax=80, cmap_name="inferno")
        layers.append({
            "id": "tmrt_peak",
            "label": "Baseline Tmrt at peak hour (°C)",
            "url": "tmrt_peak.png",
            "coords": _bounds_to_coords(bounds),
            "visible": True,
        })

    diff_src = REPO / f"outputs/{cfg.name}/diffs/dutci_peak_mature.tif"
    if diff_src.exists():
        arr, bounds = _read_band(diff_src, band=1)
        _write_diff_overlay(arr, out_dir / "dutci_mature.png", vlim=6.0)
        layers.append({
            "id": "dutci_mature",
            "label": "ΔUTCI mature scenario (°C; blue = cooler)",
            "url": "dutci_mature.png",
            "coords": _bounds_to_coords(bounds),
            "visible": False,
        })

    (out_dir / "aoi.geojson").write_text(json.dumps(_aoi_box_geojson(cfg)))
    has_planted = _planted_sites(cfg, out_dir / "planted_sites.geojson")

    template = INDEX_TEMPLATE.read_text()
    html = (template
            .replace("__LAYERS_JSON__", json.dumps(layers))
            .replace("__CENTER_LON__", f"{cfg.center_lon:.6f}")
            .replace("__CENTER_LAT__", f"{cfg.center_lat:.6f}")
            .replace("__AOI_NAME__", cfg.name)
            .replace("__HAS_PLANTED__", "true" if has_planted else "false"))
    (out_dir / "index.html").write_text(html)
    return out_dir
