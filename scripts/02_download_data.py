"""Stage 1 — acquire Durham inputs that don't depend on the AOI bbox.

Pulls (in order):
  1. Durham Trees & Planting Sites GeoJSON  (whole city, paginated; ~28k points)
  2. EnviroAtlas Durham 1m MULC GeoTIFF      (county-scale zip)
  3. Iowa Mesonet KRDU hourly observations  (summer 2025) → pick the simulation date

Then runs an AOI sanity check: how many planting-site (future) points fall inside
the configured AOI bbox? If <10 the scenario story is too thin — bump AOI_SIZE_KM
or shift the center in scripts/_aoi.py and re-run.

Cache: every download is keyed by destination filename. If the file exists we skip.
Delete the file (or its parent dir) to force a refresh.

Stage-1 gate:
  - inputs/raw/durham/trees_planting/durham_trees.geojson opens and has features
  - inputs/raw/durham/enviroatlas_mulc/DNC_MULC.tif opens with a discoverable LUT
  - scripts/_aoi.SIM_DATE rewritten to a hot, clear summer-2025 ISO date
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "inputs/raw/durham"
TREES_DIR = RAW / "trees_planting"
MULC_DIR = RAW / "enviroatlas_mulc"
KRDU_DIR = RAW / "krdu_asos"

TREES_LAYER = "https://webgis2.durhamnc.gov/server/rest/services/PublicServices/Environmental/FeatureServer/11"
MULC_ZIP_URL = "https://enviroatlas.epa.gov/download/DNC_MULC_tif.zip"
ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

# EnviroAtlas MULC class codes (per metadata at edg.epa.gov)
MULC_CODES = {
    0: "unclassified", 10: "water", 20: "impervious",
    30: "soil", 40: "trees", 70: "grass",
    80: "agriculture", 91: "woody_wetlands", 92: "emergent_wetlands",
}

UA = {"User-Agent": "radiant-temperature/0.1 (arohandutt@live.com)"}


def _http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# -------------------------------------------------------------------- 1. Trees

def fetch_trees() -> Path:
    dst = TREES_DIR / "durham_trees.geojson"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    TREES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  fetching trees from {TREES_LAYER} …")

    features: list[dict] = []
    last_oid = -1
    page = 0
    while True:
        params = {
            "where": f"OBJECTID > {last_oid}",
            "outFields": "OBJECTID,present,program,commonname,plantingdate,contractplantingyr",
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "OBJECTID ASC",
            "resultRecordCount": "2000",
            "f": "geojson",
        }
        url = f"{TREES_LAYER}/query?{urllib.parse.urlencode(params)}"
        body = _http_get(url, timeout=120)
        obj = json.loads(body)
        feats = obj.get("features", [])
        if not feats:
            break
        features.extend(feats)
        last_oid = max(f["properties"]["OBJECTID"] for f in feats)
        page += 1
        print(f"    page {page}: +{len(feats):>5d}  total {len(features):>6d}  (last OID {last_oid})")
        if len(feats) < 2000:
            break

    out = {"type": "FeatureCollection", "features": features}
    dst.write_text(json.dumps(out))
    print(f"  wrote {len(features):,} features → {dst}")
    return dst


# ---------------------------------------------------------------------- 2. MULC

def fetch_mulc() -> Path:
    dst = MULC_DIR / "DNC_MULC.tif"
    if dst.exists():
        print(f"  [cached] {dst}")
        return dst
    MULC_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = MULC_DIR / "DNC_MULC_tif.zip"
    if not zip_path.exists():
        print(f"  downloading {MULC_ZIP_URL} (this is ~50–150 MB) …")
        body = _http_get(MULC_ZIP_URL, timeout=600)
        zip_path.write_bytes(body)
        print(f"  wrote {len(body):,} bytes → {zip_path}")

    print(f"  unzipping {zip_path} …")
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        print(f"    members: {members}")
        for m in members:
            if m.endswith("/"):
                continue
            data = zf.read(m)
            target = MULC_DIR / Path(m).name
            target.write_bytes(data)
            print(f"    extracted {Path(m).name}  ({len(data):,} bytes)")
    if not dst.exists():
        # EnviroAtlas zips name the tif differently sometimes — find it by extension
        cands = sorted(MULC_DIR.glob("*.tif"))
        if cands:
            cands[0].rename(dst)
            print(f"  renamed {cands[0].name} → {dst.name}")
    print(f"  MULC ready → {dst}")
    return dst


# ----------------------------------------------------------------- 3. KRDU date

def pick_sim_date() -> str:
    """Query KRDU hourly obs for summer 2025; pick the hottest clear-sky day."""
    cache = KRDU_DIR / "krdu_2025_summer.csv"
    if not cache.exists():
        KRDU_DIR.mkdir(parents=True, exist_ok=True)
        params = [
            ("station", "RDU"),
            ("data", "tmpf"), ("data", "skyc1"),
            ("year1", "2025"), ("month1", "6"), ("day1", "1"),
            ("year2", "2025"), ("month2", "9"), ("day2", "15"),
            ("tz", "America/New_York"),
            ("format", "onlycomma"),
            ("latlon", "no"),
            ("missing", "M"),
            ("trace", "T"),
            ("direct", "no"),
            ("report_type", "3"),
            ("report_type", "4"),
        ]
        url = f"{ASOS_URL}?{urllib.parse.urlencode(params)}"
        print(f"  fetching KRDU obs …")
        body = _http_get(url, timeout=120)
        cache.write_bytes(body)
        print(f"  wrote {len(body):,} bytes → {cache}")
    else:
        print(f"  [cached] {cache}")

    import pandas as pd
    df = pd.read_csv(cache, comment="#")
    df["valid"] = pd.to_datetime(df["valid"])
    df["date"] = df["valid"].dt.date
    df["hour"] = df["valid"].dt.hour
    df["tmpf"] = pd.to_numeric(df["tmpf"], errors="coerce")
    sky_score = {"CLR": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4, "VV ": 4}
    df["sky"] = df["skyc1"].map(sky_score)

    midday = df[df["hour"].between(10, 15)]
    daily = df.groupby("date").agg(max_tmpf=("tmpf", "max")).join(
        midday.groupby("date").agg(midday_sky=("sky", "mean"))
    ).dropna()

    hot_clear = daily[(daily["max_tmpf"] >= 95) & (daily["midday_sky"] <= 1.5)]
    if hot_clear.empty:
        chosen = daily.sort_values("max_tmpf", ascending=False).head(1)
        print(f"  no hot+clear day found; falling back to the hottest:\n{chosen}")
    else:
        print(f"  top hot+clear days:\n{hot_clear.sort_values('max_tmpf', ascending=False).head(5)}")
        chosen = hot_clear.sort_values("max_tmpf", ascending=False).head(1)
    sim_date = str(chosen.index[0])
    row = chosen.iloc[0]
    print(f"  → SIM_DATE = {sim_date}  (max_tmpf={row['max_tmpf']:.1f}°F, midday_sky={row['midday_sky']:.2f})")
    return sim_date


def update_aoi_sim_date(date_str: str) -> None:
    """Rewrite SIM_DATE in scripts/_aoi.py."""
    path = REPO / "scripts/_aoi.py"
    text = path.read_text()
    new = re.sub(r'^SIM_DATE\s*=\s*.*$', f'SIM_DATE = "{date_str}"', text, count=1, flags=re.M)
    if new == text:
        raise RuntimeError("Could not find SIM_DATE line in _aoi.py")
    path.write_text(new)
    print(f"  updated {path} → SIM_DATE = \"{date_str}\"")


# ------------------------------------------------------------- 4. AOI sanity

def aoi_planting_count(trees_geojson: Path) -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    from _aoi import TILE_BBOX
    import geopandas as gpd

    trees = gpd.read_file(trees_geojson).to_crs("EPSG:32617")
    print(f"  trees loaded: {len(trees):,} total")
    statuses = trees["present"].value_counts(dropna=False).to_dict()
    print(f"  status values: {statuses}")
    planted = trees[trees["present"] == "Planting Site"]
    in_aoi = planted.cx[TILE_BBOX[0]:TILE_BBOX[2], TILE_BBOX[1]:TILE_BBOX[3]]
    print(f"  planting sites in AOI {TILE_BBOX}: {len(in_aoi):,}")
    return len(in_aoi)


def main() -> None:
    print("== 1. Durham Trees & Planting Sites ==")
    trees = fetch_trees()

    print("\n== 2. EnviroAtlas Durham MULC ==")
    fetch_mulc()

    print("\n== 3. Pick SIM_DATE from KRDU summer 2025 ==")
    sim_date = pick_sim_date()
    update_aoi_sim_date(sim_date)

    print("\n== 4. AOI sanity: planting sites inside TILE_BBOX ==")
    n = aoi_planting_count(trees)
    if n < 10:
        print(f"  WARN: only {n} planting sites in AOI — bump AOI_SIZE_KM or shift center.")
    else:
        print(f"  OK: {n} planting sites — proceed to stage 2 gate check.")


if __name__ == "__main__":
    main()
