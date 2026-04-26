"""Stage 7 — produce the three slide-ready figures + the headline statistic.

Reads the baseline + both scenario SOLWEIG outputs, computes diffs at peak hour,
writes:

  figures/fig1_three_panel_{scenario}.png   (baseline | scenario | Δ at peak)
  figures/fig2_near_tree_histogram.png      (ΔTmrt within 30 m of planted points)
  figures/fig3_diurnal.png                  (tile-mean Tmrt across the day)
  figures/headline.txt                      (one-line claim)

Also saves the per-scenario peak-hour diff rasters as GeoTIFFs under
  outputs/scenario_diffs/
so the web inspector can overlay them.

All pixel statistics mask out building roofs (Landcover==2 OR DSM-DEM>2.5m).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import matplotlib
matplotlib.use("Agg")  # no display
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import rasterio
import geopandas as gpd

from _aoi import AOI_NAME, SIM_DATE, TILE_BBOX

BASELINE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
TREES_GEOJSON = REPO / "inputs/raw/durham/trees_planting/durham_trees.geojson"
FIG_DIR = REPO / f"figures/{AOI_NAME}"
FIG_DIR.mkdir(parents=True, exist_ok=True)
DIFF_DIR = REPO / f"outputs/{AOI_NAME}_scenario_diffs"
DIFF_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["year10", "mature"]
PEAK_HOUR = 15
NEAR_TREE_RADIUS_M = 30.0


def load_planted_points() -> gpd.GeoDataFrame:
    trees = gpd.read_file(TREES_GEOJSON).to_crs("EPSG:32617")
    sites = trees[trees["present"] == "Planting Site"].copy()
    return sites.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]].reset_index(drop=True)


def building_mask() -> np.ndarray:
    with rasterio.open(BASELINE / "Landcover.tif") as ds:
        lc = ds.read(1)
    with rasterio.open(BASELINE / "Building_DSM.tif") as ds:
        dsm = ds.read(1)
    with rasterio.open(BASELINE / "DEM.tif") as ds:
        dem = ds.read(1)
    return (lc == 2) | ((dsm - dem) > 2.5)


def read_band(path: Path, band: int) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(band).astype("float32")


def write_diff_geotiff(diff: np.ndarray, ref_path: Path, dst: Path, nodata: float) -> None:
    with rasterio.open(ref_path) as ds:
        profile = ds.profile.copy()
    profile.update(dtype="float32", count=1, nodata=nodata, compress="lzw")
    with rasterio.open(dst, "w", **profile) as out:
        out.write(diff, 1)


# ----------------------------------------------------------- Figure 1

def fig1_three_panel(scenario: str, base_t: np.ndarray, scen_t: np.ndarray,
                      is_building: np.ndarray, planted_pts: gpd.GeoDataFrame,
                      bounds, label_extras: str = "") -> None:
    diff = scen_t - base_t
    # Mask roofs for display (Tmrt invalid)
    base_disp = np.where(is_building, np.nan, base_t)
    scen_disp = np.where(is_building, np.nan, scen_t)
    diff_disp = np.where(is_building, np.nan, diff)

    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5), constrained_layout=True)
    vmin, vmax = 25, 75

    im0 = axes[0].imshow(base_disp, cmap="inferno", vmin=vmin, vmax=vmax, extent=extent)
    axes[0].set_title(f"Baseline Tmrt @ {PEAK_HOUR}:00 local")
    fig.colorbar(im0, ax=axes[0], label="°C", shrink=0.7)

    im1 = axes[1].imshow(scen_disp, cmap="inferno", vmin=vmin, vmax=vmax, extent=extent)
    axes[1].set_title(f"Scenario ({scenario}) Tmrt @ {PEAK_HOUR}:00")
    fig.colorbar(im1, ax=axes[1], label="°C", shrink=0.7)

    # Diff: diverging blue→white→red, but here cooling = blue, warming = red
    vlim = max(2.0, np.nanpercentile(np.abs(diff_disp), 99) if np.isfinite(diff_disp).any() else 2.0)
    norm = mcolors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    im2 = axes[2].imshow(diff_disp, cmap="RdBu_r", norm=norm, extent=extent)
    axes[2].set_title(f"Δ (scenario − baseline)  {label_extras}")
    fig.colorbar(im2, ax=axes[2], label="ΔTmrt (°C)", shrink=0.7)

    # Overlay planted points on the diff panel
    axes[2].scatter(planted_pts.geometry.x, planted_pts.geometry.y,
                    s=18, marker="o", facecolor="none",
                    edgecolor="lime", linewidth=1.0, label="planned plantings")
    axes[2].legend(loc="lower left", fontsize=8, framealpha=0.7)

    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_aspect("equal")

    fig.suptitle(f"Durham downtown — {SIM_DATE} — '{scenario}' canopy scenario",
                 fontsize=12, y=1.02)
    out = FIG_DIR / f"fig1_three_panel_{scenario}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


# ----------------------------------------------------------- Figure 2

def fig2_histogram(diffs_by_scenario: dict[str, np.ndarray]) -> None:
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    bins = np.linspace(-15, 5, 81)
    colors = {"year10": "#5c8ed6", "mature": "#1d4f9c"}
    for scen, d in diffs_by_scenario.items():
        ax.hist(d, bins=bins, alpha=0.55, label=f"{scen}  (n={len(d):,})",
                color=colors.get(scen, "gray"), edgecolor="none")
    ax.axvline(0, color="k", linewidth=0.8, linestyle=":")
    ax.set_xlabel(f"ΔTmrt at peak hour h={PEAK_HOUR} local (°C)")
    ax.set_ylabel("number of pedestrian-accessible cells")
    ax.set_title(f"Tmrt change near planted sites (≤{NEAR_TREE_RADIUS_M:.0f} m, non-roof)\n"
                 f"Durham downtown · {SIM_DATE}")
    ax.legend()
    ax.set_yscale("log")
    out = FIG_DIR / "fig2_near_tree_histogram.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


# ----------------------------------------------------------- Figure 3

def fig3_diurnal(hourly: dict[str, list[float]]) -> None:
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    hours = list(range(24))
    style = {"baseline": dict(color="#222", linewidth=2.0, label="baseline"),
             "year10":   dict(color="#5c8ed6", linewidth=2.0, label="year10 scenario (5 m canopy)"),
             "mature":   dict(color="#1d4f9c", linewidth=2.0, label="mature scenario (12 m canopy)")}
    for k, vals in hourly.items():
        ax.plot(hours, vals, **style.get(k, {}))
    ax.axvspan(PEAK_HOUR - 0.4, PEAK_HOUR + 0.4, color="#fde0a8", alpha=0.5,
               label=f"peak hour ({PEAK_HOUR}:00)")
    ax.set_xlabel("Hour (local, EDT)")
    ax.set_ylabel("Tile-mean Tmrt, non-roof cells (°C)")
    ax.set_title(f"Diurnal mean radiant temperature — Durham downtown · {SIM_DATE}")
    ax.set_xticks(range(0, 24, 3))
    ax.grid(alpha=0.3, linestyle=":")
    ax.legend(loc="upper left")
    out = FIG_DIR / "fig3_diurnal.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


# ----------------------------------------------------------- main

def main() -> None:
    print(f"== reading rasters ==")
    is_building = building_mask()
    pts = load_planted_points()
    print(f"  {len(pts)} planted points; {is_building.sum():,} building cells")

    base_tmrt_path = BASELINE / "output_folder/0_0/TMRT_0_0.tif"
    base_peak = read_band(base_tmrt_path, PEAK_HOUR + 1)
    with rasterio.open(base_tmrt_path) as ds:
        bounds = ds.bounds; transform = ds.transform; shape = ds.shape

    # Near-tree mask: union of 30m buffers around planted points
    from rasterio.features import geometry_mask
    near = geometry_mask([pt.buffer(NEAR_TREE_RADIUS_M) for pt in pts.geometry],
                          transform=transform, out_shape=shape, invert=True)
    near_pedestrian = near & ~is_building
    print(f"  near-tree mask: {near.sum():,} cells; pedestrian: {near_pedestrian.sum():,}")

    print(f"\n== loading scenario rasters ==")
    scenario_data = {}
    for scen in SCENARIOS:
        path = REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}/output_folder/0_0/TMRT_0_0.tif"
        scen_peak = read_band(path, PEAK_HOUR + 1)
        scenario_data[scen] = {"peak": scen_peak, "tmrt_path": path}
        print(f"  {scen}: {path}")

    # Hourly tile-means for fig 3
    print(f"\n== computing hourly diurnal traces ==")
    hourly = {"baseline": []}
    for scen in SCENARIOS:
        hourly[scen] = []
    for h in range(24):
        with rasterio.open(base_tmrt_path) as ds:
            b = ds.read(h+1).astype("float32")
        m = np.isfinite(b) & (b > -100) & ~is_building
        hourly["baseline"].append(float(b[m].mean()))
        for scen in SCENARIOS:
            with rasterio.open(scenario_data[scen]["tmrt_path"]) as ds:
                s = ds.read(h+1).astype("float32")
            ms = m & np.isfinite(s) & (s > -100)
            hourly[scen].append(float(s[ms].mean()))

    print(f"\n== generating figures ==")
    diffs_for_hist = {}
    for scen in SCENARIOS:
        peak = scenario_data[scen]["peak"]
        # 1. three-panel + diff GeoTIFF
        diff = peak - base_peak
        diff_dst = DIFF_DIR / f"dtmrt_peak_{scen}.tif"
        write_diff_geotiff(np.where(is_building, np.nan, diff).astype("float32"),
                           base_tmrt_path, diff_dst, nodata=np.nan)
        print(f"  wrote {diff_dst}  (for the web inspector)")
        # Headline label for the diff panel
        nt = (near_pedestrian & np.isfinite(diff))
        label = (f"median Δ near-tree = {float(np.median(diff[nt])):+.2f} °C  "
                 f"min = {float(diff[nt].min()):+.2f} °C")
        fig1_three_panel(scen, base_peak, peak, is_building, pts, bounds, label)
        # Save the histogram-relevant slice
        diffs_for_hist[scen] = diff[nt]

    fig2_histogram(diffs_for_hist)
    fig3_diurnal(hourly)

    # ------- compute headline + write to file
    print(f"\n== headline ==")
    head = []
    for scen in SCENARIOS:
        peak = scenario_data[scen]["peak"]
        diff = peak - base_peak
        nt = near_pedestrian & np.isfinite(diff)
        # planted-disk pixels: where Trees was modified
        with rasterio.open(BASELINE / "Trees.tif") as ds:
            base_t = ds.read(1)
        with rasterio.open(REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}/Trees.tif") as ds:
            scen_t = ds.read(1)
        planted = (scen_t != base_t) & np.isfinite(diff) & ~is_building

        m_planted_med = float(np.median(diff[planted]))
        m_planted_min = float(diff[planted].min())
        m_near_med = float(np.median(diff[nt]))
        head.append({
            "scenario": scen,
            "planted_median_dtmrt": m_planted_med,
            "planted_min_dtmrt":    m_planted_min,
            "near_median_dtmrt":    m_near_med,
        })

    # UTCI at planted pixels for both scenarios — that's the pedestrian metric
    base_utci_path = BASELINE / "output_folder/0_0/UTCI_0_0.tif"
    base_u = read_band(base_utci_path, PEAK_HOUR + 1)
    for h in head:
        scen = h["scenario"]
        scen_u = read_band(REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}/output_folder/0_0/UTCI_0_0.tif",
                           PEAK_HOUR + 1)
        d_u = scen_u - base_u
        with rasterio.open(BASELINE / "Trees.tif") as ds:
            base_t = ds.read(1)
        with rasterio.open(REPO / f"inputs/processed/{AOI_NAME}_scenario_{scen}/Trees.tif") as ds:
            scen_t = ds.read(1)
        planted = (scen_t != base_t) & np.isfinite(d_u) & ~is_building
        h["planted_median_dutci"] = float(np.median(d_u[planted]))

    headline_lines = [
        f"== Durham planted-tree intervention — peak hour ({PEAK_HOUR}:00 local, "
        f"{SIM_DATE}) ==", "",
        f"At the {len(pts)} planned planting sites in the 1 km × 1 km downtown tile,",
        f"Durham's program delivers (median across planted pixels):", "",
    ]
    for h in head:
        headline_lines.append(
            f"  • {h['scenario']:<7s}  ΔTmrt {h['planted_median_dtmrt']:+.1f} °C "
            f"  ΔUTCI {h['planted_median_dutci']:+.1f} °C "
            f"  (worst pixel ΔTmrt {h['planted_min_dtmrt']:+.1f} °C)"
        )
    headline_lines += [
        "",
        f"Slide-ready: pedestrian heat-stress (UTCI) at planted spots drops",
        f"  {abs(head[0]['planted_median_dutci']):.1f}–{abs(head[1]['planted_median_dutci']):.1f} °C "
        f"at peak (5–10 yr → mature canopy range)",
    ]
    text = "\n".join(headline_lines)
    print(text)
    (FIG_DIR / "headline.txt").write_text(text + "\n")
    print(f"\n  wrote {FIG_DIR/'headline.txt'}")


if __name__ == "__main__":
    main()
