# s2-l1c-60m-3

## Source

Earth Engine `COPERNICUS/S2`, the Level-1C top-of-atmosphere product as distributed by ESA. `COPERNICUS/S2_HARMONIZED` is not used, because it subtracts 1000 and sets valid values at or below 1000 to the NoData value 0.

## Sample

3 bands (B1, B9, B10) of 512×512 pixels at 60 m, on the native UTM grid of the granule.

## Representation

Level-1C digital numbers as uint16. NoData is 0. Since processing baseline 04.00, reflectance is `(DN + radio_add_offset) / 10000`; the manifest lists `radio_add_offset` per band.

## Licence

Copernicus Sentinel data 2023, under the Copernicus data policy. Required attribution: "Contains modified Copernicus Sentinel data 2023."
