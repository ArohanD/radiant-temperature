"""Build the 4 co-registered input rasters + met forcing for SOLWEIG.

Target CRS/grid: EPSG:32617, 1m resolution, identical extent (~1400x1400 px after 200m buffer).

Output directory: inputs/processed/durham_baseline/
Filenames MUST match solweig_gpu's expectations (no renaming later):
  - Building_DSM.tif    Building+terrain DSM (m a.s.l.)
  - DEM.tif             Bare-earth DEM (m a.s.l.)
  - Trees.tif           Tree canopy heights above ground (m), zero elsewhere
  - Landcover.tif       UMEP codes: 1=dark asphalt/paved, 2=roofs/buildings, 5=grass,
                        6=bare soil, 7=water  (0=cobble, 99=walls also allowed)
  - ownmet_<date>.txt   Met forcing in UMEP 23-col format (see below)

Sources:
1. DEM:        NC Phase 3 bare-earth from sdd.nc.gov. Native units: US Survey Feet → meters.
2. Building_DSM: PDAL pipeline on classified LAZ first returns → 1m grid. US Survey Feet → meters.
3. Trees:      (DSM - DEM), masked to tree pixels from land cover, zero elsewhere.
4. Landcover:  EnviroAtlas Durham MULC, reclassified to UMEP codes above.
5. Met:        ERA5 hourly → UMEP text format. Header row:
                 iy id it imin Q* QH QE Qs Qf Wind RH Td press rain Kdn snow ldown
                 fcld wuh xsmd lai_hr Kdiff Kdir Wd
               Populate Wind (m/s), RH (%), Td (°C), press (kPa), rain (mm/h),
               Kdn (W/m² downwelling SW), ldown (W/m² downwelling LW) from ERA5.
               Leave remaining columns as -999.00.

CRITICAL: NC Phase 3 LiDAR is US Survey Feet. Verify unit conversion before downstream steps.
"""

# TODO: Day 2-3 — implement after data downloaded.
