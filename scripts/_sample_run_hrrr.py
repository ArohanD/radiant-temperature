"""Day-1 trust test, HRRR variant: pull NOAA HRRR analysis from dynamical.org for the
SAME Austin tile + SAME date as `_sample_run.py`, build a UMEP met forcing file from
HRRR variables, and re-run SOLWEIG. Compare against the run that used the bundled
Zenodo met file.

Goal: confirm switching from CDS-API ERA5 → dynamical HRRR for the Durham project
gives a physically equivalent answer (no drastic Tmrt shifts) when the underlying
rasters are held constant. If this passes, Day 2 met fetching becomes ~20 lines
of xarray instead of ~100 lines of CDS-API + GRIB parsing.

Naming convention to keep the two runs distinguishable:
  inputs/processed/sample_crop/        ← run #1, bundled met
  inputs/processed/sample_crop_hrrr/   ← run #2, HRRR-derived met
  outputs/sample_validation/           ← side-by-side copies with explicit suffixes

Why HRRR analysis, not forecast: we want a hindcast for a specific past day. HRRR
analysis is the data-assimilated state at each cycle's F00 — what HRRR thinks the
atmosphere was doing at that hour. Coverage starts 2014-10-01 (good for our 2020 date).
"""
from __future__ import annotations

import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
SRC_CROP_DIR = REPO / "inputs/processed/sample_crop"          # run #1 inputs (cropped rasters + bundled met)
HRRR_CROP_DIR = REPO / "inputs/processed/sample_crop_hrrr"    # run #2 inputs (same rasters, HRRR met)
COMPARE_DIR = REPO / "outputs/sample_validation"

# Austin tile center — derived from sample_crop bounds (EPSG:32614)
LAT, LON = 30.33228, -97.72141

# Local date we're hindcasting. Austin is on CDT (UTC-5) in August.
LOCAL_DATE = "2020-08-13"
UTC_OFFSET_HOURS = -5
DOY = datetime.strptime(LOCAL_DATE, "%Y-%m-%d").timetuple().tm_yday  # 226 for 2020-08-13


def fetch_hrrr_point() -> pd.DataFrame:
    """Open dynamical's HRRR analysis Zarr, select 24h at the Austin point, return a
    pandas DataFrame indexed by local hour (0..23) with the columns we need to write
    a UMEP met file."""
    import dynamical_catalog
    dynamical_catalog.identify("radiant-temperature/0.1 (arohandutt@live.com)")

    print("Opening HRRR analysis dataset (icechunk, anonymous S3)...")
    ds = dynamical_catalog.open("noaa-hrrr-analysis")
    print(f"  vars available: {len(ds.data_vars)}, dims: {dict(ds.sizes)}")
    print(f"  coord names: {list(ds.coords)}")

    # Need 24 LOCAL hours covering 2020-08-13 00:00..23:00 CDT.
    # CDT = UTC-5  →  UTC 2020-08-13 05:00 .. 2020-08-14 04:00.
    utc_start = datetime.fromisoformat(f"{LOCAL_DATE}T00:00:00") - timedelta(hours=UTC_OFFSET_HOURS)
    utc_end = utc_start + timedelta(hours=23)
    print(f"  pulling UTC {utc_start.isoformat()} .. {utc_end.isoformat()}")

    # The HRRR grid uses Lambert Conformal Conic projection with `x`,`y` dims and
    # 2D `latitude`/`longitude` coordinate variables. Find nearest cell by hand,
    # then index by the resulting integer x/y.
    lat2d = ds["latitude"].values
    lon2d = ds["longitude"].values
    # haversine-ish: small-area approx is fine for finding nearest 3km cell
    dlat = lat2d - LAT
    dlon = (lon2d - LON) * math.cos(math.radians(LAT))
    j, i = np.unravel_index(np.argmin(dlat**2 + dlon**2), lat2d.shape)
    cell_lat, cell_lon = float(lat2d[j, i]), float(lon2d[j, i])
    print(f"  nearest HRRR cell: lat={cell_lat:.4f}, lon={cell_lon:.4f}  "
          f"(target {LAT:.4f}, {LON:.4f})  → y={j}, x={i}")

    needed = [
        "temperature_2m",
        "relative_humidity_2m",
        "pressure_surface",
        "precipitation_surface",
        "downward_short_wave_radiation_flux_surface",
        "downward_long_wave_radiation_flux_surface",
        "wind_u_10m",
        "wind_v_10m",
    ]
    point = ds[needed].isel(y=j, x=i).sel(time=slice(utc_start, utc_end)).load()
    print(f"  loaded {point.sizes['time']} timesteps")

    # Convert UTC index → local hour 0..23
    times_utc = pd.to_datetime(point["time"].values, utc=True)
    times_local = times_utc.tz_convert(None) + pd.Timedelta(hours=UTC_OFFSET_HOURS)
    df = pd.DataFrame({
        "local_time": times_local,
        "Ta_C": point["temperature_2m"].values,                                  # already °C
        "RH_pct": point["relative_humidity_2m"].values,                          # %
        "press_kPa": point["pressure_surface"].values / 1000.0,                  # Pa → kPa
        "rain_mmh": point["precipitation_surface"].values * 3600.0,              # kg/m²/s → mm/h
        "Kdn_Wm2": point["downward_short_wave_radiation_flux_surface"].values,   # W/m²
        "ldown_Wm2": point["downward_long_wave_radiation_flux_surface"].values,  # W/m²
        "u10": point["wind_u_10m"].values,
        "v10": point["wind_v_10m"].values,
    })
    df["Wind_ms"] = np.sqrt(df["u10"] ** 2 + df["v10"] ** 2)
    df = df.drop(columns=["u10", "v10"])
    df["hour"] = df["local_time"].dt.hour
    return df


def write_umep_met(df: pd.DataFrame, dst: Path) -> None:
    """Write a UMEP 23-col own-met file matching the bundled file's layout exactly.

    Quirk: the column labeled 'Td' in UMEP own-met format is consumed as 2-meter air
    temperature by solweig-gpu (see env/.../preprocessor.py:655 — `'Td': 'T2'`).
    We follow the same convention.
    """
    header = ("%iy  id  it imin   Q*      QH      QE      Qs      Qf    Wind    "
              "RH     Td     press   rain    Kdn    snow    ldown   fcld    wuh     "
              "xsmd    lai_hr  Kdiff   Kdir    Wd")
    lines = [header]
    fill = "-999.00"
    for _, row in df.sort_values("hour").iterrows():
        cols = [
            f"{2020:d}",                          # iy
            f"{DOY:d}",                           # id  (day of year)
            f"{int(row['hour']):d}",              # it  (local hour)
            "0",                                  # imin
            fill, fill, fill, fill, fill,         # Q* QH QE Qs Qf
            f"{row['Wind_ms']:.5f}",              # Wind  (m/s)
            f"{row['RH_pct']:.2f}",               # RH    (%)
            f"{row['Ta_C']:.2f}",                 # Td    (= air temp in °C, per solweig-gpu convention)
            f"{row['press_kPa']:.2f}",            # press (kPa)
            f"{row['rain_mmh']:.2f}",             # rain  (mm/h)
            f"{row['Kdn_Wm2']:.2f}",              # Kdn   (W/m²)
            fill,                                 # snow
            f"{row['ldown_Wm2']:.2f}",            # ldown (W/m²)
            fill, fill, fill, fill, fill, fill, fill,  # fcld wuh xsmd lai_hr Kdiff Kdir Wd
        ]
        lines.append(" ".join(cols))
    dst.write_text("\n".join(lines) + "\n")
    print(f"  wrote {dst}  ({len(df)} rows)")


def stage_inputs() -> Path:
    """Mirror the cropped raster set into HRRR_CROP_DIR so the only diff vs the
    original run is the met file."""
    HRRR_CROP_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif"):
        src = SRC_CROP_DIR / name
        dst = HRRR_CROP_DIR / name
        shutil.copyfile(src, dst)
    print(f"  staged 4 rasters into {HRRR_CROP_DIR}")
    return HRRR_CROP_DIR


def stash_results() -> None:
    """Copy the key TMRT/UTCI rasters from both runs into outputs/sample_validation/
    with explicit suffixes so they're easy to compare in QGIS."""
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [
        (SRC_CROP_DIR / "output_folder/0_0/TMRT_0_0.tif", COMPARE_DIR / "TMRT_bundled_met.tif"),
        (SRC_CROP_DIR / "output_folder/0_0/UTCI_0_0.tif", COMPARE_DIR / "UTCI_bundled_met.tif"),
        (HRRR_CROP_DIR / "output_folder/0_0/TMRT_0_0.tif", COMPARE_DIR / "TMRT_hrrr_met.tif"),
        (HRRR_CROP_DIR / "output_folder/0_0/UTCI_0_0.tif", COMPARE_DIR / "UTCI_hrrr_met.tif"),
    ]
    for src, dst in pairs:
        if src.exists():
            shutil.copyfile(src, dst)
            print(f"  {dst.name}  ({dst.stat().st_size // 1024} KB)")
        else:
            print(f"  MISSING: {src}")


def compare_runs() -> None:
    """Per-band stats on TMRT (bundled vs HRRR), then a focused look at peak hour."""
    import rasterio
    bundled = SRC_CROP_DIR / "output_folder/0_0/TMRT_0_0.tif"
    hrrr = HRRR_CROP_DIR / "output_folder/0_0/TMRT_0_0.tif"
    print("\n=== TMRT comparison: bundled met vs HRRR met (same rasters) ===")
    print(f"{'hr':>4} {'B_min':>7} {'B_mean':>7} {'B_max':>7} {'B_std':>6}  "
          f"{'H_min':>7} {'H_mean':>7} {'H_max':>7} {'H_std':>6}  {'Δmean':>6}")
    with rasterio.open(bundled) as b, rasterio.open(hrrr) as h:
        for band in range(1, b.count + 1):
            ba = b.read(band); ba = ba[np.isfinite(ba)]
            ha = h.read(band); ha = ha[np.isfinite(ha)]
            print(f"{band-1:>4} "
                  f"{ba.min():>7.2f} {ba.mean():>7.2f} {ba.max():>7.2f} {ba.std():>6.2f}  "
                  f"{ha.min():>7.2f} {ha.mean():>7.2f} {ha.max():>7.2f} {ha.std():>6.2f}  "
                  f"{ha.mean()-ba.mean():>+6.2f}")


def main() -> None:
    print("== 1. Pull HRRR analysis at Austin tile center ==")
    df = fetch_hrrr_point()
    print("\nHRRR diurnal cycle (local time):")
    cols = ["hour", "Ta_C", "RH_pct", "Wind_ms", "press_kPa", "Kdn_Wm2", "ldown_Wm2", "rain_mmh"]
    print(df[cols].sort_values("hour").to_string(index=False, float_format=lambda x: f"{x:7.2f}"))

    print("\n== 2. Stage rasters + write UMEP met file ==")
    base = stage_inputs()
    met_path = HRRR_CROP_DIR / "ownmet_HRRR.txt"
    write_umep_met(df, met_path)

    print("\n== 3. Run thermal_comfort() with HRRR met ==")
    from solweig_gpu import thermal_comfort
    thermal_comfort(
        base_path=str(base),
        selected_date_str=LOCAL_DATE,
        building_dsm_filename="Building_DSM.tif",
        dem_filename="DEM.tif",
        trees_filename="Trees.tif",
        landcover_filename="Landcover.tif",
        tile_size=500,
        overlap=50,
        use_own_met=True,
        own_met_file=str(met_path),
        save_tmrt=True,
        save_svf=False, save_kup=False, save_kdown=False,
        save_lup=False, save_ldown=False, save_shadow=False,
    )

    print("\n== 4. Stash both runs' outputs side-by-side ==")
    stash_results()

    print("\n== 5. Compare TMRT, hour by hour ==")
    compare_runs()


if __name__ == "__main__":
    main()
