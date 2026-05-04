"""Generate slide-ready screenshots of the Hayti web inspector via headless Chrome.

Writes 3 variant index_*.html files into the live web bundle (each with the UI
overlay CSS-hidden and a specific layer-visibility set) and captures one PNG per
variant via google-chrome --headless --screenshot. Cleans up the variants on exit.

Outputs: figures/{AOI_NAME}/slides/webapp_{tag}.png
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from _aoi import AOI_NAME

WEB = REPO / f"inputs/processed/{AOI_NAME}_baseline/web"
OUT = REPO / f"figures/{AOI_NAME}/slides"
OUT.mkdir(parents=True, exist_ok=True)
PORT = 8767

# layer visibility per shot — keys are MANIFEST raster ids (or 'planted_disks_*' for the disk layer)
SHOTS = {
    "baseline_tmrt": {
        "rasters": {"tmrt_h15"},                  # Tmrt at peak, baseline only
        "show_planted_points": False,
        "show_disks": None,
    },
    "shadow_15h": {
        "rasters": {"shadow_h15"},                # Geometry verification: shadows at peak
        "show_planted_points": False,
        "show_disks": None,
    },
    "dtmrt_mature": {
        "rasters": {"dtmrt_mature"},              # The money shot — cooling map
        "show_planted_points": True,
        "show_disks": "mature",
    },
}

CSS_HIDE_UI = "<style>#ui, #info, #hover {display:none !important;} </style>"


def patch_index_for_shot(src_html: str, shot_name: str, cfg: dict) -> str:
    """Return a new HTML where (a) UI overlays are hidden via CSS, (b) MANIFEST
    raster `visible` flags match cfg['rasters'], (c) planted-points + disks layers
    have the right visibility set in the JS init."""
    html = src_html

    # 1) inject CSS hider at top of <head>
    html = html.replace("<head>", f"<head>\n{CSS_HIDE_UI}", 1)

    # 2) flip MANIFEST raster visibility — extract `const MANIFEST = {...};`,
    # parse it as JSON, mutate visible flags, write back. Treats the manifest
    # as data instead of trying to surgically regex through nested braces.
    target = cfg["rasters"]
    m = re.search(r'const\s+MANIFEST\s*=\s*(\{.*?\});\s*\n', html, flags=re.DOTALL)
    if not m:
        raise SystemExit("MANIFEST literal not found in index.html")
    manifest = json.loads(m.group(1))
    for r in manifest["rasters"]:
        r["visible"] = (r["id"] in target)
    new_literal = "const MANIFEST = " + json.dumps(manifest) + ";\n"
    html = html[:m.start()] + new_literal + html[m.end():]

    # 3) planted-points: the JS sets visibility unconditionally. Force it on/off
    #    by patching the addLayer call. Match `id:'planted-points'` block.
    if not cfg["show_planted_points"]:
        html = html.replace(
            "id:'planted-points', type:'circle', source:'planted',",
            "id:'planted-points', type:'circle', source:'planted', layout:{visibility:'none'},",
            1,
        )

    # 4) planted-disks: change which scenario disk layer is visible (overrides the
    #    default 'visibility: scen === mature ? visible : none' ternary)
    show_scen = cfg["show_disks"]
    if show_scen is None:
        # Hide both disk layers
        html = html.replace(
            "visibility: scen === 'mature' ? 'visible' : 'none'",
            "visibility: 'none'", 1)
    elif show_scen != "mature":
        html = html.replace(
            "visibility: scen === 'mature' ? 'visible' : 'none'",
            f"visibility: scen === '{show_scen}' ? 'visible' : 'none'", 1)
    # else default already shows 'mature' — leave alone

    return html


def main() -> None:
    src_html = (WEB / "index.html").read_text()

    # serve the web bundle
    print(f"== serving {WEB} on :{PORT}")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT)], cwd=WEB,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # wait for server
        for _ in range(10):
            try:
                urllib.request.urlopen(f"http://localhost:{PORT}/index.html", timeout=1).read()
                break
            except Exception:
                time.sleep(0.5)

        for tag, cfg in SHOTS.items():
            patched = patch_index_for_shot(src_html, tag, cfg)
            variant_path = WEB / f"_shot_{tag}.html"
            variant_path.write_text(patched)
            url = f"http://localhost:{PORT}/_shot_{tag}.html"
            out_png = OUT / f"webapp_{tag}.png"

            print(f"\n== capturing {tag} → {out_png}")
            print(f"   url: {url}")
            subprocess.run([
                "google-chrome", "--headless", "--disable-gpu", "--hide-scrollbars",
                "--no-sandbox", "--window-size=1600,1000",
                "--virtual-time-budget=15000",
                f"--screenshot={out_png}", url,
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            variant_path.unlink(missing_ok=True)
            print(f"   wrote {out_png}  ({out_png.stat().st_size//1024} KB)")

    finally:
        server.terminate()
        server.wait(timeout=5)
        # clean up any leftover variant html
        for p in WEB.glob("_shot_*.html"):
            p.unlink()


if __name__ == "__main__":
    main()
