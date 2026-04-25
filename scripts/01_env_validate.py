"""Day-1 gate: verify the ./env conda environment has all dependencies wired up.

Run: `conda activate ./env && python scripts/01_env_validate.py`

If anything here fails, fix the env before touching Durham data.
"""
import importlib

PKGS = [
    "numpy",
    "rasterio",
    "geopandas",
    "pdal",
    "osgeo.gdal",
    "torch",
    "xarray",
    "zarr",
    "icechunk",
    "dynamical_catalog",
    "solweig_gpu",
]


def main() -> None:
    for name in PKGS:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "n/a")
        print(f"{name:20s} {version}")

    from solweig_gpu import thermal_comfort
    print("\nthermal_comfort imported:", thermal_comfort)

    import torch
    print("CUDA available:", torch.cuda.is_available())  # expect False on this machine


if __name__ == "__main__":
    main()
