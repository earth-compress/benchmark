# s1-grd-iw-2

## Source

Earth Engine `COPERNICUS/S1_GRD_FLOAT`, Sentinel-1 GRD IW after the Earth Engine preprocessing (thermal noise removal, radiometric calibration, terrain correction). `COPERNICUS/S1_GRD` holds the same values in dB, computed in float64.

## Sample

VV and VH, 512×512 pixels at 10 m on the native UTM grid of the scene. The manifest gives the CRS, the geotransform, and the time of every sample.

## Representation

Linear backscatter coefficient sigma0 as stored, float32. Windows hold no masked pixel.

## Licence

Copernicus Sentinel data 2023, under the Copernicus data policy. Required
attribution: "Contains modified Copernicus Sentinel data 2023."
