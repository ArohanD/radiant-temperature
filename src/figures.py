"""Stage 8 — build slide-deck-ready figures from the existing run artifacts.

Produces figures under `figures/{AOI_NAME}/slides/` for the 10-min presentation:

  study_site.png       AOI box on Durham + planting-site density
  data_panels.png      DEM hillshade | DSM | Trees CDSM | Landcover (UMEP)
  dsm_correction.png   raw LiDAR DSM | SOLWEIG-ready DSM | difference (the canonical-
                       method correction documented in notes/decision_log.md)
  landcover_tmrt.png   per-landcover-class Tmrt at peak (the 19 °C paved-vs-shade gap)
  methods_solweig.png  cartoon of SOLWEIG's per-pixel radiation balance
  scenario_design.png  year10 vs mature canopy disk size + height
  validation.png       HRRR Ta input vs Open-Meteo + KRDU + UTCI vs apparent_temp

Reads from:
  inputs/processed/{AOI_NAME}_baseline/{DEM,Building_DSM,Trees,Landcover,Building_DSM.preMS}.tif
  inputs/processed/{AOI_NAME}_baseline/output_folder/TMRT_merged.tif
  inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson
  inputs/raw/durham/trees_planting/durham_trees.geojson
  inputs/processed/{AOI_NAME}_baseline/ownmet_{SIM_DATE}.txt

All figures save at 200 dpi PNG. Run from repo root:
    ./env/bin/python scripts/08_make_slide_visuals.py
"""
from __future__ import annotations

import sys
import urllib.parse
import urllib.request
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.geo import setup_geo_env
setup_geo_env()

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap
from matplotlib.patches import Rectangle, Circle, FancyArrowPatch, Patch
import matplotlib.patheffects as pe
import rasterio
from rasterio.plot import show as rio_show
import geopandas as gpd
import pandas as pd

import src.aoi as _aoi_mod
from src.aoi import (
    AOI_NAME, AOI_CENTER_LAT, AOI_CENTER_LON, AOI_SIZE_KM,
    SIM_DATE, TILE_BBOX,
)


def set_aoi(profile: str) -> None:
    """Switch this module's AOI-dependent paths to a different profile.

    Call once from a notebook before invoking the `fig_*` entry points so
    that the module-level constants (BASE, OUT, AOI_NAME, ...) reflect the
    chosen AOI. Without this call, the module uses the AOI active at
    import time (typically `hayti_demo` by default).
    """
    import importlib
    import os as _os
    _os.environ["AOI_PROFILE"] = profile
    importlib.reload(_aoi_mod)
    global AOI_NAME, AOI_CENTER_LAT, AOI_CENTER_LON, AOI_SIZE_KM
    global SIM_DATE, TILE_BBOX, BASE, OUT
    AOI_NAME = _aoi_mod.AOI_NAME
    AOI_CENTER_LAT = _aoi_mod.AOI_CENTER_LAT
    AOI_CENTER_LON = _aoi_mod.AOI_CENTER_LON
    AOI_SIZE_KM = _aoi_mod.AOI_SIZE_KM
    SIM_DATE = _aoi_mod.SIM_DATE
    TILE_BBOX = _aoi_mod.TILE_BBOX
    BASE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
    OUT = REPO / f"figures/{AOI_NAME}/slides"
    OUT.mkdir(parents=True, exist_ok=True)


BASE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
OUT = REPO / f"figures/{AOI_NAME}/slides"
OUT.mkdir(parents=True, exist_ok=True)

DPI = 200
plt.rcParams.update({
    "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 10,
    "axes.spines.top": False, "axes.spines.right": False,
})

UMEP_COLORS = {1: "#888888", 2: "#d94731", 5: "#7ec27e", 6: "#c8a778", 7: "#4a90d9"}
UMEP_LABELS = {1: "Paved", 2: "Building", 5: "Grass / under-tree", 6: "Bare soil", 7: "Water"}


def _read(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as ds:
        return ds.read(1), ds.profile


def _hillshade(dem: np.ndarray, az: float = 315, alt: float = 45) -> np.ndarray:
    az_r, alt_r = np.deg2rad(az), np.deg2rad(alt)
    x, y = np.gradient(dem, edge_order=2)
    slope = np.pi / 2 - np.arctan(np.hypot(x, y))
    aspect = np.arctan2(-x, y)
    shaded = (np.sin(alt_r) * np.sin(slope)
              + np.cos(alt_r) * np.cos(slope) * np.cos(az_r - aspect))
    return np.clip(shaded, 0, 1)


def _add_scalebar(ax, length_m: float = 500, *, location: str = "lower right",
                  pad: float = 0.04, label_above: bool = True,
                  segments: int = 4) -> None:
    """Add a zebra-style scale bar to a matplotlib axes whose data units are
    meters. Works for both pixel-extent (1 px = 1 m) and UTM-extent axes.
    `location` is one of 'lower left', 'lower right', 'upper left',
    'upper right'. Style: thin alternating black/white segments with endpoint
    labels (0 and length_m), no backing panel."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    inv_y = ymin > ymax  # imshow with default origin='upper' has inverted y
    xspan = xmax - xmin
    yspan = abs(ymax - ymin)
    bar_h = yspan * 0.010  # 1.0 % of axes height — thin
    y_dir = -1 if inv_y else 1

    if "right" in location:
        x0 = xmin + xspan * (1 - pad) - length_m
    else:
        x0 = xmin + xspan * pad
    if "lower" in location:
        y0 = (max(ymin, ymax) - yspan * pad) if inv_y else (ymin + yspan * pad)
    else:
        y0 = (min(ymin, ymax) + yspan * pad) if inv_y else (ymax - yspan * pad)

    seg_w = length_m / segments
    for i in range(segments):
        color = "black" if i % 2 == 0 else "white"
        ax.add_patch(Rectangle((x0 + i * seg_w, y0), seg_w, bar_h * y_dir,
                               facecolor=color, edgecolor="black",
                               lw=0.6, zorder=22))

    # endpoint labels
    label_off = bar_h * 1.6 * y_dir
    if label_above:
        label_y = (y0 + label_off) if not inv_y else (y0 + label_off)
        va = "bottom" if not inv_y else "top"
    else:
        label_y = y0 - label_off
        va = "top" if not inv_y else "bottom"
    common = dict(ha="center", va=va, fontsize=7, fontweight="bold", zorder=22)
    # add a thin white halo so labels read cleanly over any background
    halo = [pe.withStroke(linewidth=2, foreground="white")]
    ax.text(x0, label_y, "0", path_effects=halo, **common)
    ax.text(x0 + length_m, label_y, f"{int(length_m)} m",
            path_effects=halo, **common)


def _crop_to_tile(arr: np.ndarray, profile: dict) -> np.ndarray:
    """Crop a PROCESSING_BBOX raster down to TILE_BBOX (the analysis core).
    Assumes 1 m square pixels and that tile is centered with SHADOW_BUFFER_M ring."""
    buf_px = round((profile["transform"].a or 1) * 0)  # always 1
    buf_px = 200  # SHADOW_BUFFER_M / 1m px
    return arr[buf_px:-buf_px, buf_px:-buf_px]


# ============================================================ FIGURE 1: study site

def fig_study_site() -> None:
    """A 2-panel: (left) Durham wider context with AOI box + planting-site density,
    (right) zoomed AOI with Overture buildings + planting points."""
    print("== fig_study_site ==")
    sites_path = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"

    sites = gpd.read_file(sites_path).to_crs("EPSG:32617")
    planting_only = sites[sites["present"] == "Planting Site"].copy()
    bldgs = gpd.read_file(overture_path).to_crs("EPSG:32617")

    # tile bbox in UTM
    xmin, ymin, xmax, ymax = TILE_BBOX
    tile_box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({xmin} {ymin},{xmax} {ymin},{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))"
    ], crs="EPSG:32617")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ----- left: Durham-wide planting-site density + AOI box
    ax = axes[0]
    sites_lonlat = sites.to_crs("EPSG:4326")
    planting_lonlat = planting_only.to_crs("EPSG:4326")
    ax.scatter(sites_lonlat[sites_lonlat["present"] == "Tree"].geometry.x,
               sites_lonlat[sites_lonlat["present"] == "Tree"].geometry.y,
               s=1, c="#bbbbbb", alpha=0.4, label=f"Existing trees (n={(sites['present']=='Tree').sum():,})")
    ax.scatter(planting_lonlat.geometry.x, planting_lonlat.geometry.y,
               s=3, c="#1b7837", alpha=0.85,
               label=f"Planned plantings (n={len(planting_only):,})")
    aoi_box_ll = tile_box.to_crs("EPSG:4326")
    ax.plot(*aoi_box_ll.iloc[0].exterior.xy, color="#d62728", lw=2.5,
             label=f"{AOI_NAME} AOI")
    ax.set_aspect("equal")
    ax.set_xlim(-79.00, -78.80)
    ax.set_ylim(35.92, 36.07)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Durham: Trees & Planning Sites layer\n(Durham Open Data Portal)")
    ax.legend(loc="lower left", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.2)

    # ----- right: zoom onto the densest planting cluster within the AOI.
    # If the AOI is small enough to fit in the zoom window, just show the
    # full AOI (the cluster is the AOI).
    ax = axes[1]
    planting_in = planting_only.clip(tile_box.iloc[0])

    win_m = 800.0
    if min(xmax - xmin, ymax - ymin) <= win_m:
        zx_min, zx_max, zy_min, zy_max = xmin, xmax, ymin, ymax
        cluster_zoomed = False
    else:
        cx, cy = _densest_cluster_center(planting_in, win_m=win_m)
        half = win_m / 2
        zx_min = max(xmin, cx - half)
        zx_max = min(xmax, cx + half)
        zy_min = max(ymin, cy - half)
        zy_max = min(ymax, cy + half)
        cluster_zoomed = True

    zoom_box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({zx_min} {zy_min},{zx_max} {zy_min},{zx_max} {zy_max},"
        f"{zx_min} {zy_max},{zx_min} {zy_min}))"
    ], crs="EPSG:32617")
    bldgs_in = bldgs[bldgs.intersects(zoom_box.iloc[0])]
    bldgs_in.plot(ax=ax, facecolor="#bdbdbd", edgecolor="#666", lw=0.2)
    # count plantings inside the zoom window (for the legend)
    in_zoom_mask = ((planting_in.geometry.x >= zx_min) & (planting_in.geometry.x <= zx_max)
                    & (planting_in.geometry.y >= zy_min) & (planting_in.geometry.y <= zy_max))
    n_in_zoom = int(in_zoom_mask.sum())
    if cluster_zoomed:
        sc_label = f"{n_in_zoom} of {len(planting_in)} plantings in this zoom"
    else:
        sc_label = f"{n_in_zoom} plantings in AOI"
    ax.scatter(planting_in.geometry.x, planting_in.geometry.y,
               s=22, c="#1b7837", edgecolors="black", lw=0.4, zorder=3,
               label=sc_label)
    ax.set_aspect("equal")
    ax.set_xlim(zx_min, zx_max)
    ax.set_ylim(zy_min, zy_max)
    ax.set_xlabel("Easting (m, UTM 17N)")
    ax.set_ylabel("Northing (m, UTM 17N)")
    # Force clean tick formatting: limit count + use offset notation so 6/7-digit
    # UTM coords don't run together at slide size
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(MaxNLocator(nbins=5))
        fmt = ScalarFormatter(useOffset=True, useMathText=False)
        fmt.set_useOffset(True)
        fmt.set_scientific(False)
        axis.set_major_formatter(fmt)
    span_km_x = (zx_max - zx_min) / 1000.0
    span_km_y = (zy_max - zy_min) / 1000.0
    if cluster_zoomed:
        ax.set_title(f"Densest planting cluster within {AOI_NAME} AOI "
                      f"({span_km_x:.1f} × {span_km_y:.1f} km zoom, "
                      f"EPSG:32617)\n"
                      f"Full AOI is {AOI_SIZE_KM:g} km × {AOI_SIZE_KM:g} km. "
                      f"Durham Freeway crosses N edge.")
    else:
        ax.set_title(f"{AOI_NAME} AOI "
                      f"({span_km_x:.1f} × {span_km_y:.1f} km, EPSG:32617)\n"
                      f"Building footprints from Overture Maps.")
    ax.legend(loc="lower left", fontsize=9, framealpha=0.95)
    _add_scalebar(ax, 200, location="lower right")

    plt.tight_layout()
    out = OUT / "study_site.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 2: data panels

def fig_data_panels() -> None:
    """4-panel: DEM hillshade, Building DSM (heights AGL), Trees CDSM, Landcover."""
    print("== fig_data_panels ==")
    dem, dem_p = _read(BASE / "DEM.tif")
    dsm, _ = _read(BASE / "Building_DSM.tif")
    trees, _ = _read(BASE / "Trees.tif")
    lc, _ = _read(BASE / "Landcover.tif")

    # Crop the 200 m shadow buffer ring; show only the analysis core.
    dem = _crop_to_tile(dem, dem_p)
    dsm = _crop_to_tile(dsm, dem_p)
    trees = _crop_to_tile(trees, dem_p)
    lc = _crop_to_tile(lc, dem_p)

    valid = (dem != -9999) & (dsm != -9999)
    bldg_h = np.where(valid, dsm - dem, np.nan)
    bldg_h = np.where(bldg_h > 0.5, bldg_h, np.nan)  # show only positive AGL

    fig, axes = plt.subplots(2, 2, figsize=(12, 12))

    # DEM hillshade
    ax = axes[0, 0]
    hs = _hillshade(np.where(valid, dem, np.nan))
    ax.imshow(hs, cmap="gray", vmin=0.3, vmax=0.95)
    ax.imshow(np.where(valid, dem, np.nan), cmap="terrain", alpha=0.5)
    ax.set_title("DEM (bare-earth terrain)\nNC Phase 3 LiDAR (2015): PDAL ground returns + IDW fill")
    _add_scalebar(ax, 500)
    ax.set_axis_off()

    # Building DSM (height AGL)
    ax = axes[0, 1]
    im = ax.imshow(bldg_h, cmap="magma", vmin=0, vmax=40)
    ax.set_title("Building DSM: heights above ground (m)\n"
                 "max(LiDAR first-return, DEM + Overture height) within footprints")
    _add_scalebar(ax, 500)
    ax.set_axis_off()
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="m AGL")

    # Trees CDSM
    ax = axes[1, 0]
    trees_show = np.where(trees > 0, trees, np.nan)
    im = ax.imshow(trees_show, cmap="YlGn", vmin=0, vmax=25)
    ax.set_title("Trees CDSM: canopy height above ground (m)\n"
                 "(LiDAR DSM − DEM) × MULC tree mask, capped 40 m")
    _add_scalebar(ax, 500)
    ax.set_axis_off()
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="m")

    # Landcover
    ax = axes[1, 1]
    lc_show = lc.copy()
    classes = sorted(UMEP_COLORS.keys())
    cmap = ListedColormap([UMEP_COLORS[c] for c in classes])
    norm = BoundaryNorm([c - 0.5 for c in classes] + [classes[-1] + 0.5], len(classes))
    ax.imshow(lc_show, cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_title("Landcover (UMEP classes)\n"
                 "EnviroAtlas MULC 1m (2010) reclass + Overture footprints → buildings")
    _add_scalebar(ax, 500, location="lower right")
    ax.set_axis_off()
    handles = [Patch(facecolor=UMEP_COLORS[c], label=UMEP_LABELS[c]) for c in classes]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.95)

    plt.suptitle(f"SOLWEIG inputs: {AOI_NAME} "
                  f"({AOI_SIZE_KM:g} km × {AOI_SIZE_KM:g} km @ 1 m, EPSG:32617)",
                  fontsize=14, fontweight="bold", y=1.0)
    plt.tight_layout()
    out = OUT / "data_panels.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 3: DSM correction

def fig_dsm_correction() -> None:
    """The canonical-method correction: 3-panel showing raw LiDAR DSM (with tree
    blobs + noise) → SOLWEIG-ready DSM (Overture-gated) → difference.

    Implements decision_log.md "2026-04-26 Building_DSM construction" — show the
    reviewer exactly why the new recipe matters."""
    print("== fig_dsm_correction ==")
    dem, dem_p = _read(BASE / "DEM.tif")
    dsm_raw, _ = _read(BASE / "Building_DSM.preMS.tif")
    dsm_clean, _ = _read(BASE / "Building_DSM.tif")

    dem = _crop_to_tile(dem, dem_p)
    dsm_raw = _crop_to_tile(dsm_raw, dem_p)
    dsm_clean = _crop_to_tile(dsm_clean, dem_p)

    valid_raw = (dsm_raw != -9999) & (dem != -9999)
    valid_clean = (dsm_clean != -9999) & (dem != -9999)
    h_raw = np.where(valid_raw, dsm_raw - dem, np.nan)
    h_clean = np.where(valid_clean, dsm_clean - dem, np.nan)
    diff = h_clean - np.where(np.isfinite(h_raw), h_raw, 0)

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    # raw LiDAR
    ax = axes[0]
    im = ax.imshow(h_raw, cmap="magma", vmin=0, vmax=40)
    ax.set_title("Raw LiDAR DSM (first-returns max)\n"
                 "trees + birds + glints baked in, wrong by SOLWEIG's data contract",
                 fontsize=11)
    _add_scalebar(ax, 500)
    ax.set_axis_off()
    plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02, label="m AGL")

    # SOLWEIG-ready
    ax = axes[1]
    im = ax.imshow(h_clean, cmap="magma", vmin=0, vmax=40)
    ax.set_title("SOLWEIG-ready DSM\n"
                 "DEM everywhere; max(LiDAR, DEM + Overture height) inside footprints only",
                 fontsize=11)
    _add_scalebar(ax, 500)
    ax.set_axis_off()
    plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02, label="m AGL")

    # diff
    ax = axes[2]
    im = ax.imshow(diff, cmap="RdBu_r", vmin=-25, vmax=25)
    ax.set_title("Difference (clean − raw)\n"
                 "blue = LiDAR tree/noise removed; red = Overture-only buildings added",
                 fontsize=11)
    _add_scalebar(ax, 500)
    ax.set_axis_off()
    plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02, label="m Δ")

    plt.suptitle("Building DSM construction: Lindberg & Grimmond (2011) canonical recipe\n"
                 "Trees in the DSM cause double-counted shadows, wrong albedo/emissivity, no canopy porosity. "
                 "Overture footprints gate which LiDAR returns count as 'building'.",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    out = OUT / "dsm_correction.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# UTCI heat-stress categories per Bröde et al. 2012 (UTCI-Fiala model)
UTCI_THRESHOLDS = [
    (-40, 9,  "no/cold stress",   "#5b9bd5"),
    (9,   26, "no thermal stress","#a8d8a8"),
    (26,  32, "moderate",         "#f4d35e"),
    (32,  38, "strong",           "#f4a261"),
    (38,  46, "very strong",      "#e76f51"),
    (46,  90, "extreme",          "#9d2826"),
]


# ============================================================ FIGURE: landcover UTCI (heat-stress)

def fig_landcover_utci() -> None:
    """Per-landcover UTCI at peak with heat-stress category bands. The "feels-like"
    cousin of fig_landcover_tmrt — turns the abstract Tmrt number into something
    the audience can read against the heat-stress scale they actually care about."""
    print("== fig_landcover_utci ==")
    lc, _ = _read(BASE / "Landcover.tif")
    with rasterio.open(BASE / "output_folder" / "UTCI_merged.tif") as ds:
        utci_peak = ds.read(16)  # band 16 = h=15 local

    finite = np.isfinite(utci_peak)
    rows = []
    for code, label in UMEP_LABELS.items():
        if code == 2:  # building roofs — UTCI not pedestrian-relevant
            continue
        m = (lc == code) & finite
        if m.sum() < 100:
            continue
        rows.append((label, code, utci_peak[m].mean(), utci_peak[m].std(), m.sum()))
    rows.sort(key=lambda r: -r[2])
    labels = [r[0] for r in rows]
    means = [r[2] for r in rows]
    stds = [r[3] for r in rows]
    counts = [r[4] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5.5))

    # heat-stress category bands as horizontal bands behind the bars
    for lo, hi, name, color in UTCI_THRESHOLDS:
        ax.axhspan(lo, hi, facecolor=color, alpha=0.18, zorder=0)
        if 20 <= (lo + hi) / 2 <= 55:
            ax.text(len(labels) - 0.45, (lo + hi) / 2, name,
                    fontsize=9, color="#444", va="center", ha="right",
                    fontweight="500", zorder=1,
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    colors = [UMEP_COLORS[r[1]] for r in rows]
    bars = ax.bar(labels, means, yerr=stds, capsize=4,
                  color=colors, edgecolor="black", lw=0.8, zorder=3)
    for bar, m, c in zip(bars, means, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, m + 0.7,
                f"{m:.1f} °C\n({c/1e6:.2f} M cells)",
                ha="center", fontsize=9, zorder=4)

    grass = next(r[2] for r in rows if r[1] == 5)
    paved = next(r[2] for r in rows if r[1] == 1)
    ax.annotate(f"{paved-grass:.1f} °C 'feels-like'\npaved-vs-shade gap",
                xy=(0, paved), xytext=(2.3, paved - 2),
                fontsize=10, fontweight="bold", color="#c0533e",
                arrowprops=dict(arrowstyle="->", color="#c0533e", lw=1.5))

    ax.set_ylabel("Mean UTCI 'feels-like' temperature (°C)")
    ax.set_title(f"What the day feels like: UTCI by landcover at 15:00 EDT, {SIM_DATE}\n"
                  f"{AOI_NAME} baseline · heat-stress categories shaded behind bars")
    ax.set_ylim(20, 55)
    ax.grid(axis="y", alpha=0.3, zorder=2)
    plt.tight_layout()
    out = OUT / "landcover_utci.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}  | {dict(zip(labels, [round(m,1) for m in means]))}")


# ============================================================ FIGURE: UTCI 3-panel money shot

def _densest_cluster_center(planting: "gpd.GeoDataFrame", win_m: float = 600.0):
    """Find the (cx, cy) center of the densest `win_m × win_m` window of planting
    points using a coarse 50-m sliding grid."""
    xs = planting.geometry.x.values
    ys = planting.geometry.y.values
    step = 50.0
    xmin, ymin, xmax, ymax = (xs.min(), ys.min(), xs.max(), ys.max())
    half = win_m / 2
    best = (0, (xs.mean(), ys.mean()))
    cx = xmin
    while cx <= xmax:
        cy = ymin
        while cy <= ymax:
            n = int(((xs >= cx - half) & (xs <= cx + half)
                     & (ys >= cy - half) & (ys <= cy + half)).sum())
            if n > best[0]:
                best = (n, (cx, cy))
            cy += step
        cx += step
    print(f"  densest {win_m:.0f} m window: center=({best[1][0]:.0f},{best[1][1]:.0f}) "
          f"with {best[0]} plantings")
    return best[1]


def _median_at_planted_pixels(diff_full: np.ndarray,
                                planting: "gpd.GeoDataFrame",
                                bounds) -> float:
    """Median ΔUTCI at the 1-m pixels covered by the planting points.
    `diff_full` is the AOI-sized diff array (with buildings already masked
    to NaN); `bounds` is its rasterio bounds. Returns NaN if no plantings."""
    if len(planting) == 0:
        return float("nan")
    xs = planting.geometry.x.values
    ys = planting.geometry.y.values
    cols = np.floor(xs - bounds.left).astype(int)
    rows = np.floor(bounds.top - ys).astype(int)
    H, W = diff_full.shape
    keep = (cols >= 0) & (cols < W) & (rows >= 0) & (rows < H)
    if not keep.any():
        return float("nan")
    vals = diff_full[rows[keep], cols[keep]]
    vals = vals[np.isfinite(vals)]
    return float(np.median(vals)) if vals.size else float("nan")


def fig_utci_three_panel() -> None:
    """Three-panel zoomed money shot: Baseline UTCI | Mature UTCI | ΔUTCI, all
    cropped to a 700 m × 700 m window around the densest planting cluster so the
    pixel-scale cooling is actually visible at slide size. A small overview inset
    on the ΔUTCI panel shows where the zoom sits in the full 2 km AOI."""
    print("== fig_utci_three_panel ==")
    lc, _ = _read(BASE / "Landcover.tif")
    is_building = (lc == 2)

    base_path = BASE / "output_folder" / "UTCI_merged.tif"
    mature_path = (REPO / f"inputs/processed/{AOI_NAME}_scenario_mature"
                   / "output_folder" / "UTCI_merged.tif")
    with rasterio.open(base_path) as ds:
        base_utci = ds.read(16)
        bounds = ds.bounds
    with rasterio.open(mature_path) as ds:
        mat_utci = ds.read(16)
    diff = mat_utci - base_utci

    base_d = np.where(is_building, np.nan, base_utci)
    mat_d  = np.where(is_building, np.nan, mat_utci)
    diff_d = np.where(is_building, np.nan, diff)

    sites_path = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    sites = gpd.read_file(sites_path).to_crs("EPSG:32617")
    planting = sites[sites["present"] == "Planting Site"]
    xmin, ymin, xmax, ymax = TILE_BBOX
    box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({xmin} {ymin},{xmax} {ymin},{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))"
    ], crs="EPSG:32617").iloc[0]
    planting = planting.clip(box)

    # Pick zoom window. For AOIs larger than ~700 m, zoom into the densest
    # 700 m planting cluster so pixel-scale cooling is visible at slide size.
    # For AOIs at or below that size (e.g. hayti_demo at 600 m), the AOI is
    # already the cluster — show the full tile.
    ZOOM_M = 700.0
    aoi_w = xmax - xmin
    aoi_h = ymax - ymin
    if min(aoi_w, aoi_h) <= ZOOM_M:
        zx0, zy0, zx1, zy1 = xmin, ymin, xmax, ymax
        ZOOM_M = float(min(aoi_w, aoi_h))
        zoomed = False
    else:
        cx, cy = _densest_cluster_center(planting, win_m=ZOOM_M)
        half = ZOOM_M / 2
        zx0, zy0, zx1, zy1 = cx - half, cy - half, cx + half, cy + half
        zoomed = True
    # crop arrays to zoom window (1m grid: pixel = meter from raster bounds)
    px0 = int(zx0 - bounds.left)
    px1 = int(zx1 - bounds.left)
    py0 = int(bounds.top - zy1)  # imshow y is flipped (top-down)
    py1 = int(bounds.top - zy0)
    base_z = base_d[py0:py1, px0:px1]
    mat_z  = mat_d[py0:py1, px0:px1]
    diff_z = diff_d[py0:py1, px0:px1]
    extent_z = (zx0, zx1, zy0, zy1)

    # Buildings as gray outlines (pedestrian context inside the zoom)
    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    bldgs = gpd.read_file(overture_path).to_crs("EPSG:32617")
    zoom_box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({zx0} {zy0},{zx1} {zy0},{zx1} {zy1},{zx0} {zy1},{zx0} {zy0}))"
    ], crs="EPSG:32617").iloc[0]
    bldgs_z = bldgs[bldgs.intersects(zoom_box)]
    planting_z = planting.clip(zoom_box)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6.6), constrained_layout=True)

    # Discrete UTCI heat-stress bands (Bröde et al. 2012 thresholds), but labeled
    # in °C on the colorbar. Categorical bins make a 5 °C cooling pop visually —
    # a pixel dropping from >46 to 38–46 °C is a clear color step. Tick labels
    # are the bin BOUNDARIES so the audience reads actual temperature values,
    # not category names.
    utci_bins = [-40, 9, 26, 32, 38, 46, 90]
    utci_colors = ["#5b9bd5", "#a8d8a8", "#f4d35e", "#f4a261", "#e76f51", "#9d2826"]
    cat_cmap = ListedColormap(utci_colors)
    cat_norm = BoundaryNorm(utci_bins, cat_cmap.N)
    boundary_ticks = [9, 26, 32, 38, 46]

    im0 = axes[0].imshow(base_z, cmap=cat_cmap, norm=cat_norm, extent=extent_z,
                         interpolation="nearest")
    axes[0].set_title("Baseline UTCI 'feels-like' @ 15:00 EDT", fontsize=12, fontweight="bold")
    cb0 = fig.colorbar(im0, ax=axes[0], ticks=boundary_ticks,
                       shrink=0.78, drawedges=True)
    cb0.ax.set_yticklabels([f"{t} °C" for t in boundary_ticks], fontsize=9)
    cb0.set_label("UTCI 'feels-like' (°C)", fontsize=9)

    im1 = axes[1].imshow(mat_z, cmap=cat_cmap, norm=cat_norm, extent=extent_z,
                         interpolation="nearest")
    axes[1].set_title("Scenario (mature canopy) UTCI", fontsize=12, fontweight="bold")
    cb1 = fig.colorbar(im1, ax=axes[1], ticks=boundary_ticks,
                       shrink=0.78, drawedges=True)
    cb1.ax.set_yticklabels([f"{t} °C" for t in boundary_ticks], fontsize=9)
    cb1.set_label("UTCI 'feels-like' (°C)", fontsize=9)

    # Δ panel — diverging blue=cool, red=warm
    finite_z = np.isfinite(diff_z)
    vlim = max(2.0, float(np.nanpercentile(np.abs(diff_z[finite_z]), 99))) if finite_z.any() else 2.0
    import matplotlib.colors as mcolors
    norm = mcolors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    im2 = axes[2].imshow(diff_z, cmap="RdBu_r", norm=norm, extent=extent_z)
    n_zoom = len(planting_z)
    median_planted = _median_at_planted_pixels(diff_d, planting_z, bounds)
    median_str = (f"{median_planted:+.1f} °C"
                   if np.isfinite(median_planted) else "n/a")
    axes[2].set_title(
        f"ΔUTCI (mature − baseline)  ·  median at planted pixels ≈ {median_str}",
        fontsize=12, fontweight="bold")
    fig.colorbar(im2, ax=axes[2], label="ΔUTCI (°C)", shrink=0.78)

    # Building outlines on every panel for street/block context. No planting
    # markers — the blue cooling pixels in the ΔUTCI panel ARE the planting
    # locations, and overlaying circles on top hides the actual data.
    for ax in axes:
        bldgs_z.plot(ax=ax, facecolor="none", edgecolor="#222", lw=0.5, zorder=4)
    axes[2].text(0.02, 0.98, f"{n_zoom} planted disks in this view\n(each blue spot = one tree)",
                 transform=axes[2].transAxes, va="top", ha="left",
                 fontsize=9, color="#1d4f9c", fontweight="600",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                           edgecolor="#bbb", alpha=0.92))

    for ax in axes:
        ax.set_xlim(zx0, zx1); ax.set_ylim(zy0, zy1)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_aspect("equal")

    n_in_aoi = len(planting)
    if zoomed:
        title = (f"What {n_in_aoi} planned trees do at peak heat: "
                  f"densest cluster, {int(ZOOM_M)} m × {int(ZOOM_M)} m view")
    else:
        title = (f"What {n_in_aoi} planned trees do at peak heat: "
                  f"{AOI_NAME} AOI ({int(ZOOM_M)} m × {int(ZOOM_M)} m)")
    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.04)
    out = OUT / "fig1_utci_three_panel_mature.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE: UTCI histogram

def fig_utci_histogram() -> None:
    """ΔUTCI distribution within 30 m of any planted point — the 'feels-like'
    counterpart to fig2_near_tree_histogram. Long left tail = cells that got
    significantly cooler under canopy."""
    print("== fig_utci_histogram ==")
    lc, _ = _read(BASE / "Landcover.tif")
    is_building = (lc == 2)
    sites_path = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    sites = gpd.read_file(sites_path).to_crs("EPSG:32617")
    planting = sites[sites["present"] == "Planting Site"]
    xmin, ymin, xmax, ymax = TILE_BBOX
    box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({xmin} {ymin},{xmax} {ymin},{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))"
    ], crs="EPSG:32617").iloc[0]
    planting = planting.clip(box)

    base_p = BASE / "output_folder" / "UTCI_merged.tif"
    with rasterio.open(base_p) as ds:
        transform = ds.transform; shape = ds.shape
        base_utci = ds.read(16)

    from rasterio.features import geometry_mask
    near = geometry_mask([pt.buffer(30) for pt in planting.geometry],
                          transform=transform, out_shape=shape, invert=True)
    near &= ~is_building

    diffs = {}
    for scen in ("year10", "mature"):
        scen_p = (REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}"
                  / "output_folder" / "UTCI_merged.tif")
        with rasterio.open(scen_p) as ds:
            scen_utci = ds.read(16)
        d = (scen_utci - base_utci)[near & np.isfinite(base_utci) & np.isfinite(scen_utci)]
        diffs[scen] = d

    fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    bins = np.linspace(-7, 2, 90)
    colors = {"year10": "#5c8ed6", "mature": "#1d4f9c"}
    display = {"year10": "5 m canopy (25 m² disk)",
               "mature": "12 m canopy (49 m² disk)"}
    for scen, d in diffs.items():
        med = float(np.median(d))
        ax.hist(d, bins=bins, alpha=0.55,
                label=f"{display[scen]}  (median Δ = {med:+.2f} °C, n={len(d):,})",
                color=colors[scen], edgecolor="none")
    ax.axvline(0, color="k", lw=0.8, ls=":")
    ax.set_xlabel("ΔUTCI 'feels-like' at peak hour 15:00 (°C)")
    ax.set_ylabel("number of pedestrian-accessible cells")
    ax.set_title(f"Cooling of 'feels-like' temperature near planted sites (≤30 m, non-roof)\n"
                 f"{AOI_NAME} · {SIM_DATE}")
    ax.legend(loc="upper left")
    ax.set_yscale("log")
    out = OUT / "fig2_utci_histogram.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 4: landcover Tmrt bar

def fig_landcover_tmrt() -> None:
    """Per-landcover-class Tmrt at peak — visualizes the 19 °C paved-vs-shade gap
    that bounds the intervention's possible cooling per cell."""
    print("== fig_landcover_tmrt ==")
    lc, _ = _read(BASE / "Landcover.tif")
    with rasterio.open(BASE / "output_folder" / "TMRT_merged.tif") as ds:
        tmrt_peak = ds.read(16)  # 1-indexed band 16 = h=15 local

    finite = np.isfinite(tmrt_peak)
    rows = []
    for code, label in UMEP_LABELS.items():
        if code == 2:  # building roofs — Tmrt not physically valid for pedestrians
            continue
        m = (lc == code) & finite
        if m.sum() < 100:
            continue
        rows.append((label, code, tmrt_peak[m].mean(), tmrt_peak[m].std(), m.sum()))

    rows.sort(key=lambda r: -r[2])
    labels = [r[0] for r in rows]
    means = [r[2] for r in rows]
    stds = [r[3] for r in rows]
    counts = [r[4] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5.2))
    colors = [UMEP_COLORS[r[1]] for r in rows]
    bars = ax.bar(labels, means, yerr=stds, capsize=4,
                  color=colors, edgecolor="black", lw=0.8)
    for bar, m, c in zip(bars, means, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, m + 1.5,
                f"{m:.1f} °C\n({c/1e6:.2f} M cells)",
                ha="center", fontsize=9)
    ax.set_ylabel("Mean Tmrt (°C)")
    ax.set_title(f"Mean radiant temperature at peak hour (15:00 EDT, {SIM_DATE})\n"
                  f"by landcover class, {AOI_NAME} baseline run")
    ax.set_ylim(0, max(means) + 12)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out = OUT / "landcover_tmrt.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}  | bar values: {dict(zip(labels, [round(m,1) for m in means]))}")


# ============================================================ FIGURE 5: methods schematic

def fig_methods_solweig() -> None:
    """Cartoon of SOLWEIG's per-pixel radiation balance — for the methods slide."""
    print("== fig_methods_solweig ==")
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")
    ax.set_axis_off()

    # ground
    ax.fill_between([0, 14], 0, 0.6, color="#7d6648")
    ax.text(0.5, 0.25, "ground", color="white", fontsize=9, fontweight="bold")

    # building (left)
    ax.add_patch(Rectangle((1, 0.6), 2, 4, facecolor="#888", edgecolor="black"))
    ax.text(2, 2.5, "Building\n(DSM)", ha="center", color="white", fontsize=10, fontweight="bold")

    # tree (middle)
    ax.add_patch(Circle((6.5, 3.5), 1.4, facecolor="#3a7d3a", edgecolor="black", alpha=0.85))
    ax.plot([6.5, 6.5], [0.6, 2.3], "k-", lw=4)
    ax.text(6.5, 3.5, "Canopy\n(CDSM)", ha="center", color="white", fontsize=9, fontweight="bold")

    # building (right)
    ax.add_patch(Rectangle((10, 0.6), 2.5, 2.5, facecolor="#888", edgecolor="black"))

    # pedestrian (target pixel)
    ax.add_patch(Circle((4.7, 1.0), 0.18, facecolor="#d62728", zorder=5))
    ax.text(4.7, 0.6, "target\npixel", ha="center", color="#d62728", fontsize=9, fontweight="bold")

    # sun + direct beam
    sun_x, sun_y = 11.5, 7.3
    ax.add_patch(Circle((sun_x, sun_y), 0.42, facecolor="#ffcc33", edgecolor="black"))
    ax.text(sun_x, sun_y, "☀", ha="center", va="center", fontsize=18)
    ax.annotate("", xy=(4.7, 1.2), xytext=(sun_x - 0.3, sun_y - 0.3),
                arrowprops=dict(arrowstyle="->", color="#d97706", lw=2))
    ax.text(8.2, 4.4, "Direct beam\nshortwave", color="#d97706",
            fontsize=10, fontweight="bold", rotation=-25)

    # diffuse + reflected (curved)
    for x_origin, label in [(2, "wall ↩"), (12, "wall ↩"), (6.5, "canopy ↩")]:
        ax.annotate("", xy=(4.7, 1.2), xytext=(x_origin, 2.5),
                    arrowprops=dict(arrowstyle="->", color="#3b82f6", lw=1.3,
                                    connectionstyle="arc3,rad=0.2"))

    ax.text(0.6, 5.5, "SOLWEIG per-pixel:\n"
                     "1. Sun position from date/time/lat/lon\n"
                     "2. Shadow cast against DSM + CDSM\n"
                     "3. 6-direction radiation: ↑ sky, ↓ ground,\n"
                     "    N/S/E/W walls + canopy reflections\n"
                     "4. Mean radiant temperature Tmrt (°C)\n"
                     "5. UTCI = f(Ta, RH, wind, Tmrt)",
            fontsize=10, family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff8dc", edgecolor="black"))

    ax.text(7, 0.05, "Lindberg, Holmer & Thorsson (2008); Lindberg & Grimmond (2011)  •  "
                    "GPU implementation: Kamath et al. (JOSS 2026, solweig-gpu)",
            ha="center", fontsize=9, style="italic")

    plt.tight_layout()
    out = OUT / "methods_solweig.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 6: scenario design

def fig_scenario_design() -> None:
    """Side-by-side year10 vs mature canopy disks — visual definition of what
    the two scenarios actually represent."""
    print("== fig_scenario_design ==")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2),
                             gridspec_kw={"width_ratios": [1, 1]})

    # year10
    ax = axes[0]
    ax.set_xlim(-5, 5)
    ax.set_ylim(0, 14)
    ax.set_aspect("equal")
    ax.fill_between([-5, 5], 0, 0.4, color="#7d6648")
    ax.add_patch(Circle((0, 5), 2.5, facecolor="#7fc97f", edgecolor="black", alpha=0.85))
    ax.plot([0, 0], [0.4, 4], "k-", lw=4)
    ax.annotate("", xy=(2.7, 0.5), xytext=(2.7, 4.9),
                arrowprops=dict(arrowstyle="<->", color="black"))
    ax.text(3.2, 2.5, "5 m\nheight", fontsize=10)
    ax.annotate("", xy=(-2.5, 7.8), xytext=(2.5, 7.8),
                arrowprops=dict(arrowstyle="<->", color="black"))
    ax.text(0, 8.4, "5 × 5 px = 25 m²", ha="center", fontsize=10)
    ax.set_title("Small canopy scenario: 5 m height, 25 m² disk\n"
                 "(Willow Oak / Red Maple at 5–10 yr post-planting)", fontsize=11)
    ax.set_axis_off()

    # mature
    ax = axes[1]
    ax.set_xlim(-5, 5)
    ax.set_ylim(0, 14)
    ax.set_aspect("equal")
    ax.fill_between([-5, 5], 0, 0.4, color="#7d6648")
    ax.add_patch(Circle((0, 8), 3.5, facecolor="#1b7837", edgecolor="black", alpha=0.85))
    ax.plot([0, 0], [0.4, 5.5], "k-", lw=5)
    ax.annotate("", xy=(3.7, 0.5), xytext=(3.7, 11.5),
                arrowprops=dict(arrowstyle="<->", color="black"))
    ax.text(4.0, 6, "12 m\nheight", fontsize=10)
    ax.annotate("", xy=(-3.5, 12.2), xytext=(3.5, 12.2),
                arrowprops=dict(arrowstyle="<->", color="black"))
    ax.text(0, 12.7, "7 × 7 px = 49 m²", ha="center", fontsize=10)
    ax.set_title("Large canopy scenario: 12 m height, 49 m² disk\n"
                 "(honest upper bound; below 18 m forest-grown maximum)", fontsize=11)
    ax.set_axis_off()

    fig.text(0.5, 0.02,
             "Both scenarios share Building_DSM, DEM, Landcover (outside disks), and met file with the baseline.\n"
             "Only Trees CDSM and Landcover (UMEP 5 = grass / under-tree) diverge inside the planted disks.",
             ha="center", fontsize=10, style="italic")
    plt.suptitle("Two canopy assumptions per planting site: sensitivity bracket, not a confidence interval",
                 fontsize=13, fontweight="bold")
    plt.tight_layout(rect=(0, 0.05, 1, 0.95))
    out = OUT / "scenario_design.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 7: validation

def fig_validation() -> None:
    """HRRR Ta input vs Open-Meteo + KRDU; UTCI grass-cell vs apparent_temp."""
    print("== fig_validation ==")
    # ----- read HRRR Ta from our met file (Td used to compute Ta? No — we wrote Ta is not stored
    # explicitly; what we have is Wind/RH/Td/press/Kdn/ldown). HRRR Ta isn't in the
    # 23-col met file directly. Recover Ta from RH+Td using the Magnus formula.
    met = pd.read_csv(BASE / f"ownmet_{SIM_DATE}.txt", sep=r"\s+", skiprows=0,
                      header=0, comment="%")
    # The ownmet header row starts with %iy — pandas with header=0 keeps the
    # first column as %iy. Re-read more carefully.
    raw = (BASE / f"ownmet_{SIM_DATE}.txt").read_text().splitlines()
    cols = raw[0].lstrip("%").split()
    rows = [r.split() for r in raw[1:] if r.strip()]
    df = pd.DataFrame(rows, columns=cols).astype(float)

    # The UMEP "Td" column is actually air temperature, not dewpoint —
    # solweig-gpu maps it to T2 internally (see scripts/_lib.py:108).
    df["Ta"] = df["Td"].values
    df["hour"] = df["it"].astype(int)

    # ----- pull Open-Meteo at AOI center
    om_url = ("https://archive-api.open-meteo.com/v1/archive?"
              + urllib.parse.urlencode({
                  "latitude": AOI_CENTER_LAT, "longitude": AOI_CENTER_LON,
                  "start_date": SIM_DATE, "end_date": SIM_DATE,
                  "hourly": "temperature_2m,apparent_temperature",
                  "timezone": "America/New_York",
              }))
    print(f"  fetching Open-Meteo: {om_url}")
    om = json.loads(urllib.request.urlopen(om_url, timeout=30).read())
    om_df = pd.DataFrame({
        "hour": pd.to_datetime(om["hourly"]["time"]).hour,
        "Ta_om": om["hourly"]["temperature_2m"],
        "AT_om": om["hourly"]["apparent_temperature"],
    })

    # ----- pull KRDU
    krdu_url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
                + urllib.parse.urlencode([
                    ("station", "RDU"), ("data", "tmpc"), ("data", "dwpc"),
                    ("year1", SIM_DATE[:4]), ("month1", SIM_DATE[5:7]), ("day1", SIM_DATE[8:10]),
                    ("year2", SIM_DATE[:4]), ("month2", SIM_DATE[5:7]), ("day2", SIM_DATE[8:10]),
                    ("tz", "America%2FNew_York"), ("format", "onlycomma"),
                    ("latlon", "no"), ("missing", "M"), ("trace", "T"),
                    ("direct", "no"), ("report_type", "3"), ("report_type", "4"),
                ]).replace("%252F", "%2F"))
    print(f"  fetching KRDU: {krdu_url[:120]}...")
    try:
        krdu_txt = urllib.request.urlopen(krdu_url, timeout=30).read().decode()
        kdf = pd.read_csv(pd.io.common.StringIO(krdu_txt))
        kdf = kdf[kdf["tmpc"] != "M"].copy()
        kdf["tmpc"] = kdf["tmpc"].astype(float)
        kdf["valid"] = pd.to_datetime(kdf["valid"])
        kdf["hour"] = kdf["valid"].dt.hour
        krdu_hourly = kdf.groupby("hour")["tmpc"].mean().reset_index()
    except Exception as e:
        print(f"  WARN: KRDU pull failed ({e}) — drawing without KRDU")
        krdu_hourly = pd.DataFrame({"hour": [], "tmpc": []})

    # ----- UTCI at grass cells
    print("  computing UTCI grass-cell mean per hour...")
    lc, _ = _read(BASE / "Landcover.tif")
    grass_mask = (lc == 5)
    with rasterio.open(BASE / "output_folder" / "UTCI_merged.tif") as ds:
        utci_hourly = []
        for h in range(24):
            band = ds.read(h + 1)
            v = band[grass_mask & np.isfinite(band)]
            utci_hourly.append(v.mean() if v.size else np.nan)

    # ----- plot
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    ax.plot(df["hour"], df["Ta"], "o-", label="HRRR Ta (model input)", color="#d62728", lw=2)
    ax.plot(om_df["hour"], om_df["Ta_om"], "s--", label="Open-Meteo ERA5 reanalysis (AOI center)",
            color="#1f77b4", lw=1.7)
    if len(krdu_hourly):
        ax.plot(krdu_hourly["hour"], krdu_hourly["tmpc"], "^:",
                label="KRDU ASOS (RDU airport, 14 km)", color="#444", lw=1.5)
    ax.set_xlabel("Hour (EDT)")
    ax.set_ylabel("Air temperature (°C)")
    mae_om = np.abs(df["Ta"].values - om_df["Ta_om"].values).mean()
    ax.set_title(f"Met forcing validation: {SIM_DATE}\n"
                 f"MAE(HRRR vs Open-Meteo) = {mae_om:.2f} °C")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(np.arange(24), utci_hourly, "o-", label="UTCI at grass cells (modeled)",
            color="#1b7837", lw=2)
    ax.plot(om_df["hour"], om_df["AT_om"], "s--",
            label="Open-Meteo apparent_temperature\n(BOM/Steadman, downtown lat/lon)",
            color="#1f77b4", lw=1.7)
    common = ~np.isnan(np.array(utci_hourly))
    if common.sum() == 24:
        mae_at = np.abs(np.array(utci_hourly) - om_df["AT_om"].values).mean()
        ax.set_title(f"UTCI cross-check: grass cells vs apparent_temp\n"
                     f"MAE = {mae_at:.2f} °C (UTCI has radiation; AT does not)")
    else:
        ax.set_title("UTCI cross-check: grass cells vs apparent_temp")
    ax.set_xlabel("Hour (EDT)")
    ax.set_ylabel("°C")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out = OUT / "validation.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 8: dual diurnal trace

def fig_diurnal_dual() -> None:
    """Two-panel diurnal trace: tile-mean Tmrt above, tile-mean UTCI below — both
    with baseline/year10/mature lines and peak-hour highlight. Backup slide insert
    that complements the existing fig3_diurnal.png (Tmrt-only)."""
    print("== fig_diurnal_dual ==")
    lc, _ = _read(BASE / "Landcover.tif")
    is_building = (lc == 2)

    scenarios = {
        "baseline": BASE / "output_folder",
        "year10":   REPO / f"inputs/processed/{AOI_NAME}_scenario_year10/output_folder",
        "mature":   REPO / f"inputs/processed/{AOI_NAME}_scenario_mature/output_folder",
    }
    style = {
        "baseline": dict(color="#222",    lw=2.2, label="baseline"),
        "year10":   dict(color="#5c8ed6", lw=2.0, label="5 m canopy (25 m² disks)"),
        "mature":   dict(color="#1d4f9c", lw=2.0, label="12 m canopy (49 m² disks)"),
    }

    tmrt = {k: [] for k in scenarios}
    utci = {k: [] for k in scenarios}
    for scen, folder in scenarios.items():
        with rasterio.open(folder / "TMRT_merged.tif") as ds:
            for h in range(24):
                b = ds.read(h + 1).astype("float32")
                m = np.isfinite(b) & (b > -100) & ~is_building
                tmrt[scen].append(float(b[m].mean()))
        with rasterio.open(folder / "UTCI_merged.tif") as ds:
            for h in range(24):
                b = ds.read(h + 1).astype("float32")
                m = np.isfinite(b) & (b > -100) & ~is_building
                utci[scen].append(float(b[m].mean()))

    PEAK = int(np.argmax(tmrt["baseline"]))
    print(f"  peak hour discovered: {PEAK:02d}:00")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7.5),
                                   sharex=True, constrained_layout=True)
    hours = list(range(24))

    # Tmrt panel
    for k in scenarios:
        ax1.plot(hours, tmrt[k], **style[k])
    ax1.axvspan(PEAK - 0.4, PEAK + 0.4, color="#fde0a8", alpha=0.55,
                label=f"peak ({PEAK}:00)")
    ax1.set_ylabel("Tile-mean Tmrt (°C)\nnon-roof cells")
    ax1.set_title(f"Diurnal radiant temperature (Tmrt) and feels-like (UTCI): "
                  f"{AOI_NAME} · {SIM_DATE}",
                  fontsize=12, fontweight="bold")
    ax1.grid(alpha=0.3, ls=":")
    ax1.legend(loc="upper left", fontsize=9)
    # annotate peak deltas
    d_y10 = tmrt["year10"][PEAK] - tmrt["baseline"][PEAK]
    d_mat = tmrt["mature"][PEAK] - tmrt["baseline"][PEAK]
    ax1.text(0.98, 0.05,
             f"At peak (tile-mean):  Δ 5 m canopy = {d_y10:+.3f} °C   "
             f"Δ 12 m canopy = {d_mat:+.3f} °C\n"
             "(small because intervention is local)",
             transform=ax1.transAxes, ha="right", va="bottom",
             fontsize=9, style="italic", color="#555",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8dc",
                       edgecolor="#ddd"))

    # UTCI panel
    for k in scenarios:
        ax2.plot(hours, utci[k], **style[k])
    ax2.axvspan(PEAK - 0.4, PEAK + 0.4, color="#fde0a8", alpha=0.55)
    # heat-stress thresholds (UTCI categories)
    for thr, lab in [(26, "moderate"), (32, "strong"), (38, "very strong"), (46, "extreme")]:
        ax2.axhline(thr, color="#bbb", ls="--", lw=0.8, zorder=1)
        ax2.text(23.5, thr + 0.2, lab, fontsize=8, color="#888",
                 ha="right", va="bottom")
    ax2.set_xlabel("Hour (local, EDT)")
    ax2.set_ylabel("Tile-mean UTCI (°C)\n'feels-like' temperature")
    ax2.set_xticks(range(0, 24, 3))
    ax2.grid(alpha=0.3, ls=":")
    du_y10 = utci["year10"][PEAK] - utci["baseline"][PEAK]
    du_mat = utci["mature"][PEAK] - utci["baseline"][PEAK]
    ax2.text(0.98, 0.05,
             f"At peak (tile-mean):  Δ 5 m canopy = {du_y10:+.3f} °C   "
             f"Δ 12 m canopy = {du_mat:+.3f} °C",
             transform=ax2.transAxes, ha="right", va="bottom",
             fontsize=9, style="italic", color="#555",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8dc",
                       edgecolor="#ddd"))

    out = OUT / "fig3_diurnal_dual.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================ FIGURE 9: top-down cartographic

def fig_topdown_map() -> None:
    """A proper top-down cartographic raster of Tmrt at peak hour with the full
    cartographic kit: legend, north arrow, scale bar. Meets project rubric's
    'maps require proper legends, scales, adequate color classes' requirement."""
    print("== fig_topdown_map ==")
    with rasterio.open(BASE / "output_folder" / "TMRT_merged.tif") as ds:
        tmrt_peak = ds.read(16)  # band 16 = h=15 local (peak hour)
        bounds = ds.bounds  # in EPSG:32617

    # Mask invalid + building cells
    lc, _ = _read(BASE / "Landcover.tif")
    is_building = (lc == 2)
    tmrt_show = np.where(is_building | ~np.isfinite(tmrt_peak), np.nan, tmrt_peak)

    # crop the 200 m shadow buffer
    buf = 200
    tmrt_show = tmrt_show[buf:-buf, buf:-buf]
    is_building = is_building[buf:-buf, buf:-buf]
    extent = (bounds.left + buf, bounds.right - buf,
              bounds.bottom + buf, bounds.top - buf)

    overture_path = REPO / f"inputs/raw/durham/overture/buildings_{AOI_NAME}.geojson"
    sites_path = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
    bldgs = gpd.read_file(overture_path).to_crs("EPSG:32617")
    sites = gpd.read_file(sites_path).to_crs("EPSG:32617")
    planting = sites[sites["present"] == "Planting Site"].copy()

    xmin, ymin, xmax, ymax = TILE_BBOX
    tile_box = gpd.GeoSeries.from_wkt([
        f"POLYGON(({xmin} {ymin},{xmax} {ymin},{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))"
    ], crs="EPSG:32617")
    bldgs_in = bldgs[bldgs.intersects(tile_box.iloc[0])]
    planting_in = planting.clip(tile_box.iloc[0])

    fig = plt.figure(figsize=(14, 12))
    ax = fig.add_axes([0.06, 0.08, 0.74, 0.85])

    # Use a discrete colormap with adequate color classes (8 classes covers 0-80°C
    # in 10°C steps — pedestrian Tmrt-thresholds: <30 cool, 30-40 warm, 40-50 hot,
    # 50-60 strong heat-stress, 60+ extreme).
    levels = [10, 20, 30, 40, 50, 60, 70, 80]
    cmap = LinearSegmentedColormap.from_list(
        "tmrt_classes", ["#1a3a8a", "#3a7bbe", "#7fb3d5", "#f0e68c",
                         "#ffae5c", "#ff6f00", "#cc0000", "#660033"], N=len(levels) - 1)
    norm = BoundaryNorm(levels, cmap.N)

    im = ax.imshow(tmrt_show, extent=extent, origin="upper",
                   cmap=cmap, norm=norm, interpolation="nearest", zorder=1)

    # Buildings as outlines (so the raster shows through where Tmrt is masked)
    bldgs_in.plot(ax=ax, facecolor="#3a3a3a", edgecolor="black", lw=0.3,
                  alpha=0.85, zorder=3)

    # Planting dots
    ax.scatter(planting_in.geometry.x, planting_in.geometry.y,
               s=22, c="#39ff14", edgecolors="black", lw=0.6, zorder=5,
               label=f"Planned plantings (n={len(planting_in)})")

    # AOI box
    ax.plot(*tile_box.iloc[0].exterior.xy, color="#d62728", lw=1.8,
            zorder=4, label="2 km × 2 km AOI")

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m, UTM Zone 17N, EPSG:32617)")
    ax.set_ylabel("Northing (m, UTM Zone 17N, EPSG:32617)")
    ax.set_title("Mean radiant temperature (Tmrt) at peak hour\n"
                 f"Hayti, Durham, NC  ·  15:00 EDT  ·  {SIM_DATE}  ·  1 m resolution",
                 fontsize=14, fontweight="bold", pad=12)
    ax.grid(True, alpha=0.25, lw=0.5, ls="--")
    ax.tick_params(axis="both", labelsize=8)

    # ----- Scale bar (lower-left, inside the axes, with white backing panel)
    sb_x = xmin + 80
    sb_y = ymin + 80
    ax.add_patch(Rectangle((sb_x - 40, sb_y - 65), 620, 165,
                           facecolor="white", edgecolor="black", lw=0.8,
                           alpha=0.92, zorder=9))
    bar_lengths = [0, 250, 500]
    for i, (a, b) in enumerate(zip(bar_lengths[:-1], bar_lengths[1:])):
        c = "black" if i % 2 == 0 else "white"
        ax.add_patch(Rectangle((sb_x + a, sb_y), b - a, 25,
                               facecolor=c, edgecolor="black", lw=0.8, zorder=10))
    for v in bar_lengths:
        ax.text(sb_x + v, sb_y - 35, f"{v} m", ha="center", fontsize=9,
                fontweight="bold", zorder=10)
    ax.text(sb_x + 250, sb_y + 55, "Scale ≈ 1 : 8,000  (1 cm = 80 m)",
            ha="center", fontsize=9, fontweight="bold", zorder=10)

    # ----- North arrow (upper-right of map, with white backing panel)
    na_x = xmax - 130
    na_y = ymax - 280
    ax.add_patch(Rectangle((na_x - 70, na_y - 30), 140, 320,
                           facecolor="white", edgecolor="black", lw=0.8,
                           alpha=0.92, zorder=9))
    ax.annotate("", xy=(na_x, na_y + 220), xytext=(na_x, na_y),
                arrowprops=dict(arrowstyle="-|>", color="black",
                                lw=3, mutation_scale=28),
                zorder=10)
    ax.text(na_x, na_y + 260, "N", ha="center", fontsize=18,
            fontweight="bold", zorder=10)

    # ----- Colorbar on the right
    cax = fig.add_axes([0.83, 0.40, 0.022, 0.45])
    cbar = fig.colorbar(im, cax=cax, ticks=levels, extend="both")
    cbar.set_label("Mean radiant temperature (°C)", fontsize=11, labelpad=12)
    cbar.ax.tick_params(labelsize=10)
    # heat-stress category labels (right of colorbar)
    for tmrt_v, label in [(25, "cool"), (35, "warm"), (45, "hot"),
                          (55, "strong\nheat stress"), (65, "extreme")]:
        cax.text(3.5, tmrt_v, label, va="center", ha="left", fontsize=9,
                 color="#222", transform=cax.transData)

    # ----- Legend block (below colorbar)
    legend_ax = fig.add_axes([0.82, 0.10, 0.16, 0.22])
    legend_ax.set_axis_off()
    handles = [
        Patch(facecolor="#3a3a3a", edgecolor="black", label="Building footprint\n(Overture Maps)"),
        plt.Line2D([0], [0], marker="o", lw=0, markersize=10,
                   markerfacecolor="#39ff14", markeredgecolor="black",
                   label=f"Planned planting site\n(n={len(planting_in)},\n Durham Open Data)"),
        plt.Line2D([0], [0], color="#d62728", lw=2, label="2 km × 2 km AOI"),
    ]
    legend_ax.legend(handles=handles, loc="upper left", fontsize=9,
                     framealpha=0.95, edgecolor="#888", title="Map elements",
                     title_fontsize=10, labelspacing=1.2)

    # ----- Caption
    fig.text(0.04, 0.02,
             "Projection: UTM Zone 17N (EPSG:32617). Source rasters: SOLWEIG-GPU output (Kamath et al., JOSS 2026), "
             "1 m grid. Met forcing: NOAA HRRR analysis at AOI center, 24-hour run for 2025-06-23 (clear, KRDU max 99°F). "
             "Tmrt is masked transparent on building roofs (model output not physically valid for pedestrians).\n"
             "© Overture Maps Foundation buildings · © City of Durham Open Data Portal planting sites · © NC Phase 3 LiDAR (2015) DEM/DSM.",
             fontsize=8, color="#444")

    out = OUT / "topdown_tmrt_peak.png"
    plt.savefig(out, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  wrote {out}")


# ============================================================

def main() -> None:
    print(f"== Stage 8: slide visuals for {AOI_NAME} ==")
    print(f"   output dir: {OUT}")

    fig_study_site()
    fig_data_panels()
    fig_dsm_correction()
    fig_landcover_tmrt()
    fig_landcover_utci()
    fig_utci_three_panel()
    fig_utci_histogram()
    fig_methods_solweig()
    fig_scenario_design()
    fig_validation()
    fig_diurnal_dual()
    fig_topdown_map()

    print(f"\nDONE. {len(list(OUT.glob('*.png')))} figures in {OUT}")


if __name__ == "__main__":
    main()
