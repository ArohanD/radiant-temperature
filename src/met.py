"""Meteorological forcing: HRRR analysis pull + UMEP own-met file writer.

Source is NOAA HRRR analysis via the dynamical-catalog icechunk store (anon
S3, no auth). Returns hourly (Ta, RH, wind, pressure, Kdn, ldown, rain) at the
HRRR cell nearest the requested (lat, lon) for one local date.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HRRR_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "pressure_surface",
    "precipitation_surface",
    "downward_short_wave_radiation_flux_surface",
    "downward_long_wave_radiation_flux_surface",
    "wind_u_10m",
    "wind_v_10m",
]


def fetch_hrrr_point(lat: float, lon: float, local_date: str, utc_offset: int) -> pd.DataFrame:
    """Pull 24 hours of HRRR analysis at the cell nearest (lat, lon) for `local_date`.
    Returns a DataFrame indexed by local hour 0..23 with the columns needed for the
    UMEP own-met file. utc_offset is hours-from-UTC for the local date (e.g. -4 = EDT).
    """
    import dynamical_catalog
    dynamical_catalog.identify("radiant-temperature/0.1")

    print(f"  opening HRRR analysis (icechunk, anon S3) …")
    ds = dynamical_catalog.open("noaa-hrrr-analysis")

    utc_start = datetime.fromisoformat(f"{local_date}T00:00:00") - timedelta(hours=utc_offset)
    utc_end = utc_start + timedelta(hours=23)
    print(f"  pulling UTC {utc_start.isoformat()} .. {utc_end.isoformat()}  "
          f"(local {local_date} 00:00..23:00, UTC offset {utc_offset:+d})")

    lat2d = ds["latitude"].values
    lon2d = ds["longitude"].values
    dlat = lat2d - lat
    dlon = (lon2d - lon) * math.cos(math.radians(lat))
    j, i = np.unravel_index(np.argmin(dlat ** 2 + dlon ** 2), lat2d.shape)
    cell_lat, cell_lon = float(lat2d[j, i]), float(lon2d[j, i])
    print(f"  nearest HRRR cell: lat={cell_lat:.4f}, lon={cell_lon:.4f}  "
          f"(target {lat:.4f}, {lon:.4f})  → y={j}, x={i}")

    point = ds[HRRR_VARS].isel(y=j, x=i).sel(time=slice(utc_start, utc_end)).load()
    print(f"  loaded {point.sizes['time']} timesteps")

    times_utc = pd.to_datetime(point["time"].values, utc=True)
    times_local = times_utc.tz_convert(None) + pd.Timedelta(hours=utc_offset)
    df = pd.DataFrame({
        "local_time": times_local,
        "Ta_C":      point["temperature_2m"].values,
        "RH_pct":    point["relative_humidity_2m"].values,
        "press_kPa": point["pressure_surface"].values / 1000.0,
        "rain_mmh":  point["precipitation_surface"].values * 3600.0,
        "Kdn_Wm2":   point["downward_short_wave_radiation_flux_surface"].values,
        "ldown_Wm2": point["downward_long_wave_radiation_flux_surface"].values,
        "u10":       point["wind_u_10m"].values,
        "v10":       point["wind_v_10m"].values,
    })
    df["Wind_ms"] = np.sqrt(df["u10"] ** 2 + df["v10"] ** 2)
    df = df.drop(columns=["u10", "v10"])
    df["hour"] = df["local_time"].dt.hour
    return df.sort_values("hour").reset_index(drop=True)


def write_umep_met(df: pd.DataFrame, dst: Path, local_date: str) -> None:
    """Write a UMEP 23-col own-met file. The 'Td' column is air temperature, not
    dewpoint — solweig-gpu maps it to T2 internally (preprocessor.py:655).
    """
    year, _, _ = local_date.split("-")
    doy = datetime.strptime(local_date, "%Y-%m-%d").timetuple().tm_yday

    header = ("%iy  id  it imin   Q*      QH      QE      Qs      Qf    Wind    "
              "RH     Td     press   rain    Kdn    snow    ldown   fcld    wuh     "
              "xsmd    lai_hr  Kdiff   Kdir    Wd")
    lines = [header]
    fill = "-999.00"
    for _, row in df.iterrows():
        cols = [
            f"{int(year):d}",
            f"{doy:d}",
            f"{int(row['hour']):d}",
            "0",
            fill, fill, fill, fill, fill,
            f"{row['Wind_ms']:.5f}",
            f"{row['RH_pct']:.2f}",
            f"{row['Ta_C']:.2f}",
            f"{row['press_kPa']:.2f}",
            f"{row['rain_mmh']:.2f}",
            f"{row['Kdn_Wm2']:.2f}",
            fill,
            f"{row['ldown_Wm2']:.2f}",
            fill, fill, fill, fill, fill, fill, fill,
        ]
        lines.append(" ".join(cols))
    dst.write_text("\n".join(lines) + "\n")
    print(f"  wrote {dst}  ({len(df)} rows)")


def write_umep_met_for_aoi(prefix: str, lat: float, lon: float, sim_date: str,
                           utc_offset: int) -> Path:
    """Convenience for notebooks: fetch HRRR + write own-met into the prefixed
    baseline folder. Idempotent — if `ownmet_<sim_date>.txt` already exists,
    return that path without refetching.
    """
    from src.aoi import baseline_dir
    base = baseline_dir(prefix)
    base.mkdir(parents=True, exist_ok=True)
    dst = base / f"ownmet_{sim_date}.txt"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    df = fetch_hrrr_point(lat, lon, sim_date, utc_offset)
    write_umep_met(df, dst, sim_date)
    return dst
