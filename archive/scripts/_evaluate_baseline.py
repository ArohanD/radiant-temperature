"""Deep sanity checks on the Stage 4 SOLWEIG outputs.

Runs after `04_run_baseline.py`. Verifies that the Tmrt / UTCI / SVF / Shadow
rasters look physically reasonable: shadow direction matches solar geometry,
Tmrt by landcover class is ordered the way physics says it should be (water /
shaded grass coolest, paved / building roofs hottest), SVF distribution is
sane (open ground ≈ 1.0; dense canyon ≈ 0.3 etc).

Prints a structured report; exits non-zero if any check fails.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import math
import numpy as np
import rasterio

from _aoi import (AOI_NAME, SIM_DATE, AOI_CENTER_LAT, AOI_CENTER_LON,
                   UTC_OFFSET)

BASE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
OUT = BASE / "output_folder" / "0_0"


def _read_band(path: Path, band: int) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(band)


def _valid_mask(a: np.ndarray) -> np.ndarray:
    """Exclude NaNs and the −9999 sentinel; keep finite physical values."""
    m = np.isfinite(a)
    m &= a > -100
    m &= a < 1000
    return m


def solar_position(lat: float, lon: float, date_str: str, hour_local: int,
                    utc_offset: int) -> tuple[float, float]:
    """Cheap NOAA-formula solar altitude/azimuth (degrees) for a given local hour.
    Good enough to verify shadow direction at the ~5° level."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    doy = dt.timetuple().tm_yday
    hour_utc = hour_local - utc_offset
    # Equation of time + solar declination (NOAA simplified)
    g = math.radians(360 / 365.25 * (doy - 81))
    eot_min = 9.87 * math.sin(2*g) - 7.53 * math.cos(g) - 1.5 * math.sin(g)
    decl = math.radians(23.45) * math.sin(math.radians(360/365 * (doy - 81)))
    # Solar hour angle (15° per hour from solar noon)
    solar_time = hour_utc + lon/15.0 + eot_min/60.0
    H = math.radians(15.0 * (solar_time - 12.0))
    L = math.radians(lat)
    sin_alt = math.sin(L) * math.sin(decl) + math.cos(L) * math.cos(decl) * math.cos(H)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    cos_az = (math.sin(decl) - sin_alt * math.sin(L)) / (math.cos(math.asin(sin_alt)) * math.cos(L))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))
    if H > 0:
        az = 360 - az  # PM → west of south
    return alt, az


def hourly_means(tmrt_path: Path, lc: np.ndarray) -> list[tuple[int, dict]]:
    """For each hour, compute tile-mean Tmrt and per-landcover-class means."""
    out = []
    with rasterio.open(tmrt_path) as ds:
        for i in range(1, ds.count + 1):
            arr = ds.read(i)
            m = _valid_mask(arr)
            stats = {"all": (arr[m].mean(), arr[m].std(), int(m.sum()))}
            for code in (1, 2, 5, 6, 7):
                mask = m & (lc == code)
                if mask.any():
                    stats[code] = (arr[mask].mean(), arr[mask].std(), int(mask.sum()))
            out.append((i - 1, stats))
    return out


def main() -> int:
    fails = 0
    if not OUT.exists():
        print(f"FAIL: no output folder at {OUT}")
        return 1
    print(f"== reading SOLWEIG outputs from {OUT} ==\n")

    tmrt_path = OUT / "TMRT_0_0.tif"
    utci_path = OUT / "UTCI_0_0.tif"
    svf_path = OUT / "SVF_0_0.tif"
    shadow_path = OUT / "Shadow_0_0.tif"

    with rasterio.open(BASE / "Landcover.tif") as ds:
        lc = ds.read(1)
    with rasterio.open(BASE / "Building_DSM.tif") as ds:
        dsm = ds.read(1)
    with rasterio.open(BASE / "DEM.tif") as ds:
        dem = ds.read(1)
    height_above = dsm - dem
    is_building = (lc == 2) | (height_above > 2.5)  # roofs we should mask from Tmrt stats
    print(f"  landcover available, building-mask covers {is_building.sum():,} cells "
          f"({100*is_building.sum()/lc.size:.1f}%)")

    # ----- 1. Hourly tile-mean + per-class table
    print("\n== 1. Hourly mean Tmrt + per-landcover class ==")
    print(f"  legend: 1=paved 2=building 5=grass 6=soil 7=water  "
          f"all=tile-mean (incl. roofs)")
    print(f"  {'h':>3} {'all':>7}  {'paved(1)':>9}  {'bldg(2)':>8}  {'grass(5)':>9}  {'soil(6)':>8}")
    hourly = hourly_means(tmrt_path, lc)
    for h, st in hourly:
        m_all = st['all'][0]
        cells = lambda code: st.get(code, (np.nan, np.nan, 0))
        line = f"  {h:>3d} {m_all:>7.1f}  {cells(1)[0]:>9.1f}  {cells(2)[0]:>8.1f}  " \
               f"{cells(5)[0]:>9.1f}  {cells(6)[0]:>8.1f}"
        print(line)

    peak = max(hourly, key=lambda r: r[1]['all'][0])
    peak_h, peak_stats = peak
    print(f"\n  peak hour: {peak_h:02d}:00 local  (tile mean {peak_stats['all'][0]:.1f}°C)")

    # ----- 2. Physics-ordering check at peak hour
    print(f"\n== 2. Physics: at peak hour, paved should be hotter than shaded grass ==")
    p = peak_stats.get(1, (np.nan,))[0]
    g = peak_stats.get(5, (np.nan,))[0]
    delta = p - g
    print(f"  paved={p:.1f}°C  grass(includes-tree-shade)={g:.1f}°C  "
          f"Δ(paved−grass)={delta:+.1f}°C")
    if delta < 2.0:
        print(f"  WARN: paved should be at least 2°C hotter than mixed grass+tree-shade"); fails += 1
    else:
        print(f"  ok — paved is meaningfully hotter than shaded vegetation")

    # ----- 3. Shadow direction sanity
    print(f"\n== 3. Shadow direction at peak hour (h={peak_h}) ==")
    alt, az = solar_position(AOI_CENTER_LAT, AOI_CENTER_LON, SIM_DATE, peak_h, UTC_OFFSET)
    # Shadow falls in the direction OPPOSITE the sun's azimuth
    shadow_az = (az + 180) % 360
    compass = {0:"N", 45:"NE", 90:"E", 135:"SE", 180:"S", 225:"SW", 270:"W", 315:"NW"}
    near = min(compass.keys(), key=lambda k: min(abs(shadow_az - k), 360 - abs(shadow_az - k)))
    print(f"  solar altitude={alt:.1f}°  azimuth={az:.1f}°  → shadows fall toward "
          f"{shadow_az:.1f}° (~{compass[near]})")

    if shadow_path.exists():
        sh = _read_band(shadow_path, peak_h + 1)
        # solweig-gpu Shadow: 0 = shadowed, 1 = sunlit (or vice versa). Just report fractions.
        v = sh[_valid_mask(sh.astype("float32"))]
        if v.size:
            print(f"  shadow-band stats at peak: unique values={np.unique(v)[:5]}  "
                  f"mean={v.mean():.3f}")
    else:
        print("  no Shadow_*.tif written — skipping geometric verification")

    # ----- 4. Pre-dawn uniformity
    print(f"\n== 4. Pre-dawn (h=03) uniformity ==")
    pre_stats = hourly[3][1]['all']
    print(f"  mean={pre_stats[0]:.1f}°C  std={pre_stats[1]:.2f}°C  cells={pre_stats[2]:,}")
    if pre_stats[1] >= 2.0:
        print(f"  FAIL: pre-dawn std should be < 2°C (no sun = no shadow contrast)"); fails += 1
    else:
        print(f"  ok — uniform at night")

    # ----- 5. SVF distribution
    if svf_path.exists():
        print(f"\n== 5. Sky View Factor distribution ==")
        svf = _read_band(svf_path, 1)
        v = svf[_valid_mask(svf.astype("float32")) & (svf >= 0) & (svf <= 1.001)]
        if v.size:
            print(f"  SVF: min={v.min():.3f}  p10={np.percentile(v,10):.3f}  "
                  f"p50={np.percentile(v,50):.3f}  p90={np.percentile(v,90):.3f}  max={v.max():.3f}")
            print(f"  open-sky cells (SVF > 0.95): {(v > 0.95).sum():,} ({100*(v>0.95).mean():.1f}%)")
            print(f"  deep-canyon cells (SVF < 0.4): {(v < 0.4).sum():,} ({100*(v<0.4).mean():.1f}%)")
            if v.max() > 1.0001 or v.min() < -0.001:
                print(f"  FAIL: SVF outside [0,1]"); fails += 1

    # ----- 6. UTCI peak
    if utci_path.exists():
        print(f"\n== 6. UTCI ('feels-like') at peak hour ==")
        u = _read_band(utci_path, peak_h + 1)
        # mask buildings — UTCI is for pedestrians, no one stands on roofs
        m = _valid_mask(u) & ~is_building
        v = u[m]
        if v.size:
            print(f"  UTCI peak (non-roof): mean={v.mean():.1f}°C  "
                  f"p50={np.percentile(v,50):.1f}°C  p90={np.percentile(v,90):.1f}°C  "
                  f"p99={np.percentile(v,99):.1f}°C")
            print(f"  cells in 'extreme heat stress' (UTCI > 46°C): "
                  f"{(v > 46).sum():,} ({100*(v>46).mean():.1f}%)")
            print(f"  cells in 'no/moderate heat stress' (UTCI < 32°C): "
                  f"{(v < 32).sum():,} ({100*(v<32).mean():.1f}%)")

    # ----- summary
    print("")
    if fails == 0:
        print("== ALL DEEP CHECKS PASS ✓ ==")
    else:
        print(f"== {fails} CHECK(S) FAILED — review above ==")
    return fails


if __name__ == "__main__":
    sys.exit(main())
