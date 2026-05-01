"""Day-1 trust test: crop the Zenodo sample rasters to a small central window
and run solweig_gpu.thermal_comfort() end-to-end on CPU.

Not part of the numbered pipeline — underscore prefix signals "bootstrap scratch".

Inputs (fetched earlier from https://doi.org/10.5281/zenodo.18561860):
    inputs/raw/sample/Input_rasters/{Building_DSM,DEM,Trees,Landcover}.tif
    inputs/raw/sample/ownmet_Forcing_data.txt

Outputs:
    inputs/processed/sample_crop/{Building_DSM,DEM,Trees,Landcover}.tif  (500x500)
    inputs/processed/sample_crop/Output/... (whatever solweig_gpu writes)
"""
from pathlib import Path
import shutil

import rasterio
from rasterio.windows import Window

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "inputs/raw/sample/Input_rasters"
CROP_DIR = REPO / "inputs/processed/sample_crop"
MET_FILE = REPO / "inputs/raw/sample/ownmet_Forcing_data.txt"

CROP_SIZE = 500  # pixels; square central window


def crop_central(src_path: Path, dst_path: Path, size: int) -> None:
    with rasterio.open(src_path) as src:
        h, w = src.shape
        row_off = (h - size) // 2
        col_off = (w - size) // 2
        window = Window(col_off, row_off, size, size)
        transform = src.window_transform(window)
        data = src.read(1, window=window)
        profile = src.profile
        profile.update(
            height=size,
            width=size,
            transform=transform,
            compress="lzw",
        )
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(data, 1)
    print(f"  {src_path.name} -> {dst_path}  ({data.min():.2f}..{data.max():.2f})")


def main() -> None:
    CROP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Cropping rasters to central {CROP_SIZE}x{CROP_SIZE} window...")
    for name in ("Building_DSM.tif", "DEM.tif", "Trees.tif", "Landcover.tif"):
        crop_central(RAW / name, CROP_DIR / name, CROP_SIZE)

    # Keep the met file alongside the rasters for tidiness
    met_dst = CROP_DIR / MET_FILE.name
    shutil.copy(MET_FILE, met_dst)
    print(f"  met file -> {met_dst}")

    print("\nRunning thermal_comfort() — CPU, single ~500x500 tile...")
    from solweig_gpu import thermal_comfort

    thermal_comfort(
        base_path=str(CROP_DIR),
        selected_date_str="2020-08-13",  # per Zenodo README example 3
        building_dsm_filename="Building_DSM.tif",
        dem_filename="DEM.tif",
        trees_filename="Trees.tif",
        landcover_filename="Landcover.tif",
        tile_size=500,
        overlap=50,
        use_own_met=True,
        own_met_file=str(met_dst),
        save_tmrt=True,
        save_svf=False,
        save_kup=False,
        save_kdown=False,
        save_lup=False,
        save_ldown=False,
        save_shadow=False,
    )

    print("\nDone. Listing files in crop dir:")
    for p in sorted(CROP_DIR.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(REPO)}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
