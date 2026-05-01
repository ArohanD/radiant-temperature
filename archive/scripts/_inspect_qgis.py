"""Generate inspection rasters + a PyQGIS loader script for visually checking
the patched Durham rasters.

Produces an `inspect/` subdir with:
  - dsm_diff.tif         (Building_DSM.tif − Building_DSM.preMS.tif; positive = Overture added)
  - lc_change.tif        (1 = became building, 2 = stopped being building, 0 = no change)
  - load_in_qgis.py      (paste into QGIS Python console — loads everything with full styling)

Why a console script and not a .qgs file: hand-templated .qgs XML keeps tripping
QGIS's CRS resolution (basemaps land at lat/lon 0 = Africa). Letting QGIS itself
build the project from PyQGIS calls dodges the whole issue.

Run: `./env/bin/python scripts/_inspect_qgis.py`
Then in QGIS: Plugins → Python Console → open `load_in_qgis.py` and click ▶
(or paste its contents into the input pane and Enter).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import numpy as np
import rasterio

from _aoi import AOI_NAME, PROCESSING_BBOX

OUT = REPO / f"inputs/processed/{AOI_NAME}_baseline"
INSPECT = OUT / "inspect"
INSPECT.mkdir(exist_ok=True)
OVERTURE_GEOJSON = REPO / "inputs/raw/durham/overture/buildings.geojson"


def write_diff_rasters() -> None:
    print("== building diff rasters ==")
    with rasterio.open(OUT / "Building_DSM.tif") as ds:
        new_dsm = ds.read(1); profile = ds.profile.copy()
    with rasterio.open(OUT / "Building_DSM.preMS.tif") as ds:
        old_dsm = ds.read(1)
    valid = (new_dsm != -9999) & (old_dsm != -9999)
    diff = np.where(valid, new_dsm - old_dsm, 0).astype("float32")
    profile.update(dtype="float32", nodata=0)
    with rasterio.open(INSPECT / "dsm_diff.tif", "w", **profile) as out:
        out.write(diff, 1)
    n_added = int((diff > 0.5).sum())
    print(f"  dsm_diff.tif: {n_added:,} cells lifted (> 0.5m); max bump {diff.max():.1f}m")

    with rasterio.open(OUT / "Landcover.tif") as ds:
        new_lc = ds.read(1); lc_profile = ds.profile.copy()
    with rasterio.open(OUT / "Landcover.preMS.tif") as ds:
        old_lc = ds.read(1)
    change = np.zeros_like(new_lc)
    change[(new_lc == 2) & (old_lc != 2)] = 1
    change[(new_lc != 2) & (old_lc == 2)] = 2
    lc_profile.update(dtype="uint8", nodata=0)
    with rasterio.open(INSPECT / "lc_change.tif", "w", **lc_profile) as out:
        out.write(change, 1)
    print(f"  lc_change.tif: +building={(change==1).sum():,}  -building={(change==2).sum():,}")


# Files to copy/symlink into the inspect dir so the loader script can use absolute paths
RASTERS_TO_LINK = [
    "Building_DSM.tif", "Building_DSM.preMS.tif",
    "Landcover.tif", "Landcover.preMS.tif",
    "DEM.tif", "Trees.tif",
]


def stage_inputs() -> None:
    for name in RASTERS_TO_LINK:
        local = INSPECT / name
        if not local.exists():
            local.symlink_to((OUT / name).resolve())
    if OVERTURE_GEOJSON.exists():
        local = INSPECT / "overture_buildings.geojson"
        if not local.exists():
            local.write_bytes(OVERTURE_GEOJSON.read_bytes())


# -------------------------------------------------------------- loader script

LOADER_TEMPLATE = '''"""Paste into QGIS Python console (Plugins → Python Console → ▶)
or open this file via the console's open-script button.

Loads all Durham inspection layers with proper styling, sets project CRS to
EPSG:32617, and zooms to the AOI. Replaces any existing layers.
"""
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsRasterShader, QgsColorRampShader, QgsSingleBandPseudoColorRenderer,
    QgsPalettedRasterRenderer, QgsRectangle, QgsSymbol, QgsSimpleFillSymbolLayer,
    QgsSingleSymbolRenderer,
)
from qgis.PyQt.QtGui import QColor
from pathlib import Path

INSPECT = Path(r"{INSPECT_DIR}")
AOI_BBOX = ({xmin}, {ymin}, {xmax}, {ymax})  # PROCESSING_BBOX in EPSG:32617

proj = QgsProject.instance()
proj.clear()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:32617"))


def pseudo(layer, stops, vmin, vmax):
    """stops = [(value, '#hex'), ...]"""
    fnc = QgsColorRampShader()
    fnc.setColorRampType(QgsColorRampShader.Interpolated)
    items = [QgsColorRampShader.ColorRampItem(v, QColor(c), str(v)) for v, c in stops]
    fnc.setColorRampItemList(items)
    shader = QgsRasterShader(); shader.setRasterShaderFunction(fnc)
    r = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    r.setClassificationMin(vmin); r.setClassificationMax(vmax)
    layer.setRenderer(r); layer.triggerRepaint()


def paletted(layer, items):
    """items = [(int_value, '#hex', 'label'), ...]"""
    classes = []
    for v, c, lbl in items:
        classes.append(QgsPalettedRasterRenderer.Class(v, QColor(c), lbl))
    r = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
    layer.setRenderer(r); layer.triggerRepaint()


def add_raster(name, path, style_fn=None, checked=True):
    lyr = QgsRasterLayer(str(path), name)
    if not lyr.isValid():
        print(f"  FAILED to load {{name}}: {{path}}"); return None
    if style_fn:
        style_fn(lyr)
    proj.addMapLayer(lyr)
    node = proj.layerTreeRoot().findLayer(lyr.id())
    if node is not None:
        node.setItemVisibilityChecked(checked)
    return lyr


# Add bottom→top so layer tree top is the last added
add_raster("DEM (terrain, m)", INSPECT / "DEM.tif",
           lambda l: pseudo(l, [(95,"#2166ac"),(110,"#d1e5f0"),(120,"#fddbc7"),(135,"#b2182b")], 95, 135),
           checked=False)
add_raster("Trees (CDSM, m)", INSPECT / "Trees.tif",
           lambda l: pseudo(l, [(0,"#ffffff"),(3,"#c7e9c0"),(10,"#74c476"),(20,"#238b45"),(35,"#00441b")], 0, 35),
           checked=False)
add_raster("Landcover (LiDAR only)", INSPECT / "Landcover.preMS.tif",
           lambda l: paletted(l, [(1,"#7f7f7f","paved"),(2,"#cc0000","building"),(5,"#33aa33","grass"),(6,"#a0522d","soil"),(7,"#3399ff","water")]),
           checked=False)
add_raster("Landcover (patched)", INSPECT / "Landcover.tif",
           lambda l: paletted(l, [(1,"#7f7f7f","paved"),(2,"#cc0000","building"),(5,"#33aa33","grass"),(6,"#a0522d","soil"),(7,"#3399ff","water")]),
           checked=False)
add_raster("Building_DSM (LiDAR only)", INSPECT / "Building_DSM.preMS.tif",
           lambda l: pseudo(l, [(100,"#0d0d0d"),(122,"#5a5a5a"),(135,"#9c5b00"),(160,"#ff6600"),(190,"#ffe000"),(220,"#ffffff")], 100, 220),
           checked=False)
add_raster("Building_DSM (patched)", INSPECT / "Building_DSM.tif",
           lambda l: pseudo(l, [(100,"#0d0d0d"),(122,"#5a5a5a"),(135,"#9c5b00"),(160,"#ff6600"),(190,"#ffe000"),(220,"#ffffff")], 100, 220),
           checked=False)
add_raster("LC change (added=red, removed=blue)", INSPECT / "lc_change.tif",
           lambda l: paletted(l, [(1,"#cc0000","added"),(2,"#3366ff","removed")]),
           checked=True)
add_raster("DSM diff (Overture − LiDAR, m)", INSPECT / "dsm_diff.tif",
           lambda l: pseudo(l, [(-30,"#2166ac"),(-1,"#d1e5f0"),(0,"#f7f7f7"),(1,"#fddbc7"),(10,"#f4a582"),(30,"#b2182b"),(60,"#67001f")], -30, 60),
           checked=True)

# Overture footprints — outline only, magenta
geojson = INSPECT / "overture_buildings.geojson"
if geojson.exists():
    vlyr = QgsVectorLayer(str(geojson), "Overture footprints (outline)", "ogr")
    if vlyr.isValid():
        sym = QgsSymbol.defaultSymbol(vlyr.geometryType())
        sym.deleteSymbolLayer(0)
        fill = QgsSimpleFillSymbolLayer()
        fill.setColor(QColor(0,0,0,0))
        fill.setStrokeColor(QColor(255,0,255))
        fill.setStrokeWidth(0.4)
        sym.appendSymbolLayer(fill)
        vlyr.setRenderer(QgsSingleSymbolRenderer(sym))
        proj.addMapLayer(vlyr)
        proj.layerTreeRoot().findLayer(vlyr.id()).setItemVisibilityChecked(True)

iface.mapCanvas().setExtent(QgsRectangle(*AOI_BBOX))
iface.mapCanvas().refresh()
print("Loaded Durham inspection layers. CRS = EPSG:32617. Add a basemap via Web → QuickMapServices.")
'''


def write_loader_script() -> None:
    print("== writing PyQGIS loader script ==")
    xmin, ymin, xmax, ymax = PROCESSING_BBOX
    txt = LOADER_TEMPLATE.format(
        INSPECT_DIR=str(INSPECT),
        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
    )
    dst = INSPECT / "load_in_qgis.py"
    dst.write_text(txt)
    print(f"  wrote {dst}")


def main() -> None:
    write_diff_rasters()
    stage_inputs()
    write_loader_script()
    print(f"\nIn QGIS: Plugins → Python Console → open + run:\n  {INSPECT}/load_in_qgis.py")


if __name__ == "__main__":
    main()
