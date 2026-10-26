# era5-u10-1h

## Source

ERA5 hourly data on single levels from the Copernicus Climate Data Store, requested as GRIB on the 0.25 degree regular grid. CDS interpolates this grid from the native reduced Gaussian grid before packing.

## Sample

24 hourly global fields of the 10 m eastward wind, 721×1440 cells.

## Representation

The GRIB packing codes as uint16, with the `scale` (`2^E`) and `offset` (reference value) of each hour. Value = code × scale + offset, exact in float64. Unit m/s.

## Licence

Contains modified Copernicus Climate Change Service information 2023. Neither the European Commission nor ECMWF is responsible for any use of this data.
