"""Geo env setup. Sets PROJ_DATA / GDAL_DATA when the local conda env actually
has them (laptop case, bypasses conda activate hooks). On a non-conda machine
(pod, CI) leave the env vars alone so libgdal/libproj find their system data
dirs. Always force `fork` so dynamical_catalog × ProcessPoolExecutor don't
re-import __main__ in workers.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def setup_geo_env() -> None:
    proj_dir = REPO / "env/share/proj"
    gdal_dir = REPO / "env/share/gdal"
    if proj_dir.is_dir():
        os.environ.setdefault("PROJ_DATA", str(proj_dir))
        os.environ.setdefault("PROJ_LIB",  str(proj_dir))
    if gdal_dir.is_dir():
        os.environ.setdefault("GDAL_DATA", str(gdal_dir))
    try:
        mp.set_start_method("fork", force=True)
    except RuntimeError:
        pass
