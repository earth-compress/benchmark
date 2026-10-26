# goes-abi-16

## Source

Earth Engine `NOAA/GOES/16/MCMIPF`, the ABI L2 Cloud and Moisture Imagery full-disk product.

## Sample

16 ABI channels of 512×512 cells of the 2 km fixed grid, read north up. Earth Engine stores the grid south up; only the row order changes.

## Representation

Packed counts as uint16, with the `scale` and `offset` of each channel. Channels 1 to 6 give a reflectance factor and 7 to 16 a brightness temperature in K. Windows hold no fill value.

## Licence

GOES-R series data are produced by NOAA and are in the public domain, with no restrictions on use. Suggested credit: "GOES-16 imagery courtesy of NOAA/NESDIS."
