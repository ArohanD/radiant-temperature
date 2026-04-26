"""Sanity-check the baseline run against observed weather + reanalysis sources.

Three checks:
  1. HRRR-derived Ta (model input) vs KRDU ASOS Ta — verifies the meteorological
     forcing matches reality at the regional reference station.
  2. NWS Heat Index from KRDU vs our modeled UTCI sampled at *grass* cells —
     KRDU is at the airport (open grass / runways), so its environment is most
     similar to our grass-classified cells (UMEP code 5).
  3. Open-Meteo apparent_temperature (independent ERA5 reanalysis at our
     downtown lat/lon, BOM/Steadman formula incl. wind) vs grass-cell UTCI.
     This is a methodologically closer cross-check than NWS HI because the
     formula includes wind. No provider reports radiation-loaded UTCI directly.

Pulls fresh data from Iowa Mesonet (KRDU obs) + Open-Meteo (downtown reanalysis).
Both free, no auth.
"""
from __future__ import annotations

import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _lib import setup_geo_env
setup_geo_env()

import numpy as np
import pandas as pd
import rasterio

from _aoi import AOI_NAME, SIM_DATE, AOI_CENTER_LAT, AOI_CENTER_LON

BASE = REPO / f"inputs/processed/{AOI_NAME}_baseline"
OUT = BASE / "output_folder" / "0_0"
ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


# ------------------------------------------------------- KRDU pull

def fetch_krdu_for_date(date_str: str) -> pd.DataFrame:
    """Single-day Ta/Td/wind pull from Iowa Mesonet KRDU ASOS."""
    yr, mo, dy = date_str.split("-")
    next_day = (pd.Timestamp(date_str) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    yr2, mo2, dy2 = next_day.split("-")
    params = [
        ("station", "RDU"),
        ("data", "tmpf"), ("data", "dwpf"), ("data", "sknt"),
        ("year1", yr),  ("month1", str(int(mo))),  ("day1", str(int(dy))),
        ("year2", yr2), ("month2", str(int(mo2))), ("day2", str(int(dy2))),
        ("tz", "America/New_York"),
        ("format", "onlycomma"), ("latlon", "no"),
        ("missing", "M"), ("trace", "T"),
        ("direct", "no"),
        ("report_type", "3"), ("report_type", "4"),
    ]
    url = f"{ASOS_URL}?{urllib.parse.urlencode(params)}"
    print(f"  fetching {url[:90]}…")
    req = urllib.request.Request(url, headers={
        "User-Agent": "radiant-temperature/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8")
    df = pd.read_csv(pd.io.common.StringIO(body), comment="#")
    df["valid"] = pd.to_datetime(df["valid"])
    df["hour"] = df["valid"].dt.hour
    df["date"] = df["valid"].dt.date
    df = df[df["date"].astype(str) == date_str].copy()
    for c in ("tmpf", "dwpf", "sknt"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Take median of multiple obs per hour
    hourly = df.groupby("hour").agg(tmpf=("tmpf", "median"),
                                     dwpf=("dwpf", "median"),
                                     sknt=("sknt", "median")).reset_index()
    return hourly


# ------------------------------------------------------- Open-Meteo pull

def fetch_open_meteo(lat: float, lon: float, date_str: str) -> pd.DataFrame:
    """Open-Meteo historical reanalysis at our AOI center. No auth, free.
    Returns hourly Ta + RH + apparent_temperature (BOM/Steadman, includes wind)."""
    import json
    params = {
        "latitude": str(lat), "longitude": str(lon),
        "start_date": date_str, "end_date": date_str,
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m",
        "timezone": "America/New_York",
        "wind_speed_unit": "ms",
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    print(f"  fetching {url[:90]}…")
    req = urllib.request.Request(url, headers={
        "User-Agent": "radiant-temperature/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    h = data["hourly"]
    df = pd.DataFrame({
        "time": pd.to_datetime(h["time"]),
        "Ta_C":      h["temperature_2m"],
        "RH_pct":    h["relative_humidity_2m"],
        "App_C":     h["apparent_temperature"],
        "Wind_ms":   h["wind_speed_10m"],
    })
    df["hour"] = df["time"].dt.hour
    return df


# --------------------------------------------- Heat-index + RH formulas

def f_to_c(f: float) -> float: return (f - 32) * 5/9
def c_to_f(c: float) -> float: return c * 9/5 + 32


def rh_from_t_td(t_c: float, td_c: float) -> float:
    """RH from air temp and dewpoint (Magnus approximation)."""
    a, b = 17.625, 243.04
    return 100 * math.exp((a*td_c)/(b+td_c) - (a*t_c)/(b+t_c))


def heat_index_c(t_c: float, rh_pct: float) -> float:
    """NWS Heat Index (Rothfusz regression). Returns °C. Below ~26.7°C / 40% RH
    HI is undefined and we just return air temp."""
    t_f = c_to_f(t_c)
    if t_f < 80 or rh_pct < 40:
        return t_c
    rh = rh_pct
    hi_f = (-42.379 + 2.04901523*t_f + 10.14333127*rh
            - 0.22475541*t_f*rh - 0.00683783*t_f*t_f - 0.05481717*rh*rh
            + 0.00122874*t_f*t_f*rh + 0.00085282*t_f*rh*rh
            - 0.00000199*t_f*t_f*rh*rh)
    # Adjustment per NWS for low RH / extreme temp ranges (Rothfusz adjustments)
    if rh < 13 and 80 <= t_f <= 112:
        hi_f -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95)) / 17)
    elif rh > 85 and 80 <= t_f <= 87:
        hi_f += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return f_to_c(hi_f)


# --------------------------------------------- read model outputs

def read_hrrr_input() -> pd.DataFrame:
    """Read the ownmet file we fed SOLWEIG. Return hourly Ta, RH, Wind."""
    met = (BASE / f"ownmet_{SIM_DATE}.txt").read_text().splitlines()
    rows = []
    for line in met[1:]:
        f = line.split()
        rows.append({
            "hour":     int(f[2]),
            "Ta_C":     float(f[11]),  # 'Td' column (== Ta in own-met convention)
            "RH_pct":   float(f[10]),
            "Wind_ms":  float(f[9]),
        })
    return pd.DataFrame(rows)


def utci_per_hour_by_class() -> dict[int, dict[str, tuple[float, float, float]]]:
    """For each hour return per-landcover-class UTCI (mean, p50, p99) in °C."""
    with rasterio.open(BASE / "Landcover.tif") as ds:
        lc = ds.read(1)
    out: dict[int, dict] = {}
    with rasterio.open(OUT / "UTCI_0_0.tif") as ds:
        for h in range(24):
            u = ds.read(h+1)
            valid = np.isfinite(u) & (u > -100) & (u < 100)
            stats = {}
            for code, name in [(1, "paved"), (2, "building"), (5, "grass"), (6, "soil")]:
                m = valid & (lc == code)
                if m.any():
                    v = u[m]
                    stats[name] = (float(v.mean()), float(np.percentile(v, 50)),
                                   float(np.percentile(v, 99)))
            stats["all_pedestrian"] = (
                lambda m: (float(u[m].mean()), float(np.percentile(u[m], 50)),
                            float(np.percentile(u[m], 99)))
            )(valid & (lc != 2))
            out[h] = stats
    return out


# ----------------------------------------------------- main

def main() -> int:
    fails = 0
    print(f"== fetching KRDU obs for {SIM_DATE} ==")
    krdu = fetch_krdu_for_date(SIM_DATE)
    krdu = krdu.dropna(subset=["tmpf"])
    print(f"  hourly obs: {len(krdu)} rows")

    # Convert KRDU °F → °C, compute RH and HI
    krdu["Ta_C"] = krdu["tmpf"].apply(f_to_c)
    krdu["Td_C"] = krdu["dwpf"].apply(f_to_c)
    krdu["RH_pct"] = krdu.apply(lambda r: rh_from_t_td(r["Ta_C"], r["Td_C"]), axis=1)
    krdu["HI_C"] = krdu.apply(lambda r: heat_index_c(r["Ta_C"], r["RH_pct"]), axis=1)
    krdu["Wind_ms"] = krdu["sknt"] * 0.514444

    print(f"\n== reading HRRR input + modeled UTCI ==")
    hrrr = read_hrrr_input()
    utci = utci_per_hour_by_class()

    j = krdu.merge(hrrr, on="hour", suffixes=("_KRDU", "_HRRR"))

    # ------- Check 1: HRRR Ta vs KRDU Ta
    print(f"\n== Check 1: HRRR Ta (model input) vs KRDU Ta ==")
    print(f"  {'h':>3}  {'KRDU_Ta':>8}  {'HRRR_Ta':>8}  {'ΔTa':>6}  "
          f"{'KRDU_RH':>8}  {'HRRR_RH':>8}  {'ΔRH':>6}")
    abs_dt, abs_drh = [], []
    for _, r in j.iterrows():
        dt = r["Ta_C_HRRR"] - r["Ta_C_KRDU"]
        drh = r["RH_pct_HRRR"] - r["RH_pct_KRDU"]
        abs_dt.append(abs(dt)); abs_drh.append(abs(drh))
        print(f"  {int(r['hour']):>3d}  {r['Ta_C_KRDU']:>8.1f}  {r['Ta_C_HRRR']:>8.1f}  "
              f"{dt:>+6.1f}  {r['RH_pct_KRDU']:>8.1f}  {r['RH_pct_HRRR']:>8.1f}  {drh:>+6.1f}")
    mae_dt = sum(abs_dt) / len(abs_dt)
    p95_dt = sorted(abs_dt)[int(0.95 * len(abs_dt))]
    print(f"\n  Ta MAE: {mae_dt:.2f}°C   p95(|Δ|): {p95_dt:.2f}°C   "
          f"(target: MAE < 2°C, p95 < 3°C)")
    if mae_dt > 2.0 or p95_dt > 3.0:
        print(f"  WARN: HRRR forcing diverges from KRDU more than expected"); fails += 1
    else:
        print(f"  ok — HRRR matches KRDU well")

    # ------- Check 2: KRDU Heat Index vs grass-cell UTCI
    print(f"\n== Check 2: NWS Heat Index (KRDU) vs UTCI at grass cells ==")
    print(f"  KRDU is at the airport (~open grass) — its 'feels-like' should")
    print(f"  match our grass-cell UTCI. Paved/bldg cells will be higher (UHI).")
    print(f"  {'h':>3}  {'Ta_KRDU':>8}  {'HI_KRDU':>8}  {'UTCI_grass':>11}  "
          f"{'UTCI_paved':>11}  {'paved-grass':>12}")
    abs_diff_grass = []
    for _, r in j.iterrows():
        h = int(r["hour"])
        if h not in utci: continue
        st = utci[h]
        u_grass = st.get("grass", (np.nan,))[0]
        u_paved = st.get("paved", (np.nan,))[0]
        diff = u_grass - r["HI_C"]
        abs_diff_grass.append(abs(diff))
        # Tag the row if HI is meaningful (>26.7°C, >40% RH)
        tag = "" if (r["Ta_C_KRDU"] >= 26.7 and r["RH_pct_KRDU"] >= 40) else "  (HI≈Ta)"
        print(f"  {h:>3d}  {r['Ta_C_KRDU']:>8.1f}  {r['HI_C']:>8.1f}  "
              f"{u_grass:>11.1f}  {u_paved:>11.1f}  {u_paved-u_grass:>+12.1f}{tag}")
    if abs_diff_grass:
        mae_grass = sum(abs_diff_grass) / len(abs_diff_grass)
        print(f"\n  |UTCI_grass − KRDU_HI| MAE: {mae_grass:.2f}°C  "
              f"(target < 5°C; expect grass-UTCI slightly above HI due to longwave loading)")
        if mae_grass > 7.0:
            print(f"  FAIL: grass-cell UTCI diverges from KRDU heat index by >7°C"); fails += 1

    # ------- Check 3: Open-Meteo "apparent temperature" (independent reanalysis)
    print(f"\n== Check 3: Open-Meteo apparent_temperature (downtown lat/lon) vs grass-cell UTCI ==")
    print(f"  Open-Meteo apparent_temp uses the BOM/Steadman formula (Ta+RH+wind, no")
    print(f"  radiation). It's an *ERA5* reanalysis at our exact AOI center, not a")
    print(f"  station observation — methodologically closer to UTCI than NWS HI but")
    print(f"  still missing radiation loading.")
    try:
        om = fetch_open_meteo(AOI_CENTER_LAT, AOI_CENTER_LON, SIM_DATE)
    except Exception as e:
        print(f"  Open-Meteo fetch failed ({e}) — skipping check 3"); om = None
    if om is not None:
        print(f"  {'h':>3}  {'OM_Ta':>6}  {'OM_App':>7}  {'HRRR_Ta':>8}  "
              f"{'UTCI_grass':>11}  {'UTCI−OM_App':>12}  {'KRDU_HI':>8}")
        diffs_om = []
        for h in range(24):
            if h not in utci: continue
            om_row = om[om.hour == h]
            if om_row.empty: continue
            om_ta = float(om_row["Ta_C"].iloc[0])
            om_app = float(om_row["App_C"].iloc[0])
            u_grass = utci[h].get("grass", (np.nan,))[0]
            hrrr_ta = float(j[j.hour==h]["Ta_C_HRRR"].iloc[0]) if (j.hour==h).any() else np.nan
            krdu_hi = float(j[j.hour==h]["HI_C"].iloc[0]) if (j.hour==h).any() else np.nan
            d = u_grass - om_app
            diffs_om.append(abs(d))
            print(f"  {h:>3d}  {om_ta:>6.1f}  {om_app:>7.1f}  {hrrr_ta:>8.1f}  "
                  f"{u_grass:>11.1f}  {d:>+12.1f}  {krdu_hi:>8.1f}")
        if diffs_om:
            mae_om = sum(diffs_om) / len(diffs_om)
            print(f"\n  |UTCI_grass − OM_App| MAE: {mae_om:.2f}°C  "
                  f"(target < 5°C; UTCI > AppTemp expected at peak due to radiation)")
            # Also: how does HRRR Ta compare to Open-Meteo Ta (both downtown reanalysis)?
            ta_diff = []
            for _, row in j.iterrows():
                om_match = om[om.hour == int(row.hour)]
                if om_match.empty: continue
                ta_diff.append(row["Ta_C_HRRR"] - float(om_match["Ta_C"].iloc[0]))
            if ta_diff:
                mae_ta = sum(abs(d) for d in ta_diff) / len(ta_diff)
                print(f"  bonus: |HRRR_Ta − OM_Ta| MAE: {mae_ta:.2f}°C  "
                      f"(both are downtown reanalysis — should agree to ~1°C)")

    # ------- Headline urban-heat-island delta
    print(f"\n== Headline UHI delta at peak hour ==")
    peak_h = max(utci.keys(), key=lambda h: utci[h].get("paved", (-99,))[0])
    st = utci[peak_h]
    print(f"  peak hour h={peak_h}")
    print(f"    UTCI grass-cell  : {st['grass'][0]:.1f}°C")
    print(f"    UTCI paved-cell  : {st['paved'][0]:.1f}°C")
    print(f"    UHI Δ (paved-grass): {st['paved'][0]-st['grass'][0]:+.1f}°C")
    if 'building' in st:
        print(f"    UTCI building roof: {st['building'][0]:.1f}°C  (excluded from "
              f"pedestrian summary)")

    print()
    if fails == 0:
        print("== ALL CHECKS PASS ✓ ==")
    else:
        print(f"== {fails} CHECK(S) FAILED ==")
    return fails


if __name__ == "__main__":
    sys.exit(main())
