# imerg-pcp-12

## Source

Earth Engine `NASA/GPM_L3/IMERG_V07`, the half-hourly IMERG Final Run.

## Sample

12 consecutive half-hourly fields (6 hours) of 512×512 cells at 0.1 degree. The manifest gives the CRS, the geotransform, and the time of every sample.

## Representation

Precipitation rate counts as uint16 with `scale` = float32(0.01) mm/hr. The published float32 rates equal count × scale exactly.

## Licence

GPM IMERG is produced by NASA and distributed without restriction. Suggested
credit: "Global Precipitation Measurement (GPM) IMERG data provided by the
NASA/GSFC Precipitation Processing System."
