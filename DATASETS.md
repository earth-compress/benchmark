# Datasets

The corpora measured by the benchmark. The sample files are stored in a Hugging Face dataset in the `earth-compress` organisation. This repository keeps, for each corpus, the script that builds it, its description, and its manifest.

Each sample is a window cut from a published product, on its native grid, with bands or time steps on the first axis.

## Corpora

| corpus | contents | shape | dtype | samples | MB | source |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| `s2-l1c-10m-4` | Sentinel-2 L1C, bands B2, B3, B4, B8 at 10 m | 4×512×512 | uint16 | 50 | 104.9 | `COPERNICUS/S2_HARMONIZED` |
| `s2-l1c-20m-6` | Sentinel-2 L1C, red-edge, narrow NIR and SWIR bands at 20 m | 6×512×512 | uint16 | 50 | 157.3 | `COPERNICUS/S2_HARMONIZED` |
| `s2-l1c-60m-3` | Sentinel-2 L1C, aerosol, water vapour and cirrus bands at 60 m | 3×512×512 | uint16 | 50 | 78.6 | `COPERNICUS/S2_HARMONIZED` |
| `lm-mss-4` | Landsat 1–5 MSS, four bands at 60 m | 4×512×512 | uint8 | 15 | 15.7 | `LANDSAT/LM01`–`LM05` C2 L1 |
| `l5-tm-6` | Landsat 5 TM, six reflective bands at 30 m | 6×512×512 | uint8 | 15 | 23.6 | `LANDSAT/LT05/C02/T1` |
| `l5-tm-tir` | Landsat 5 TM, thermal band B6 | 512×512 | uint8 | 15 | 3.9 | `LANDSAT/LT05/C02/T1` |
| `l7-etm-6` | Landsat 7 ETM+, six reflective bands at 30 m | 6×512×512 | uint8 | 15 | 23.6 | `LANDSAT/LE07/C02/T1` |
| `l7-etm-pan` | Landsat 7 ETM+, panchromatic band at 15 m | 1024×1024 | uint8 | 15 | 15.7 | `LANDSAT/LE07/C02/T1` |
| `l7-etm-tir-2` | Landsat 7 ETM+, thermal band at low and high gain | 2×512×512 | uint8 | 15 | 7.9 | `LANDSAT/LE07/C02/T1` |
| `l8-oli-8` | Landsat 8 OLI, eight reflective bands at 30 m | 8×512×512 | uint16 | 15 | 62.9 | `LANDSAT/LC08/C02/T1` |
| `l8-oli-pan` | Landsat 8 OLI, panchromatic band at 15 m | 1024×1024 | uint16 | 15 | 31.5 | `LANDSAT/LC08/C02/T1` |
| `l8-tirs-2` | Landsat 8 TIRS, thermal bands B10 and B11 | 2×512×512 | uint16 | 15 | 15.7 | `LANDSAT/LC08/C02/T1` |
| `goes-abi-16` | GOES-16 ABI, sixteen bands as counts with per-band scale and offset | 16×512×512 | uint16 | 15 | 125.8 | `NOAA/GOES/16/MCMIPF` |
| `s1-grd-iw-2` | Sentinel-1 GRD IW, VV and VH | 2×512×512 | int16 | 50 | 52.4 | `COPERNICUS/S1_GRD` |
| `emit-l2a-285` | EMIT L2A reflectance, 285 bands at 60 m | 285×128×128 | int16 | 10 | 93.4 | `NASA/EMIT/L2A/RFL` |
| `cop-dem-glo30` | Copernicus DEM GLO-30 elevation | 512×512 | int16 | 50 | 26.2 | `copernicus-dem-30m` |
| `esa-wc-v200` | ESA WorldCover 2021 land-cover class codes at 10 m | 512×512 | uint8 | 50 | 13.1 | `esa-worldcover` v200 |
| `imerg-pcp-12` | GPM IMERG precipitation rate, 12 half-hourly fields | 12×512×512 | uint16 | 15 | 94.4 | `NASA/GPM_L3/IMERG_V07` |
| `era5-msl-1h` | ERA5 mean sea-level pressure, 24 hourly global fields | 24×721×1440 | uint16 | 10 | 498.4 | ARCO-ERA5 |
| `era5-t2m-1h` | ERA5 2 m temperature, 24 hourly global fields | 24×721×1440 | uint16 | 10 | 498.4 | ARCO-ERA5 |
| `era5-tcc-1h` | ERA5 total cloud cover, 24 hourly global fields | 24×721×1440 | uint16 | 10 | 498.4 | ARCO-ERA5 |
| `era5-tp-1h` | ERA5 total precipitation, 24 hourly global fields | 24×721×1440 | uint16 | 10 | 498.4 | ARCO-ERA5 |
| `era5-u10-1h` | ERA5 10 m eastward wind, 24 hourly global fields | 24×721×1440 | int16 | 10 | 498.4 | ARCO-ERA5 |
| `alphaearth-v1-64` | AlphaEarth Foundations embeddings, 64 dimensions at 10 m | 64×512×512 | int8 | 15 | 251.7 | `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` |
| `tessera-v2-128` | TESSERA v2 embeddings, 128 code planes and 4 planes holding a float32 scale | 132×512×512 | int8 | 15 | 519.0 | GeoTessera 2.0 |
| `clay-embeddings` | Clay embeddings | to be defined | float32 | | | Clay |

Sources in capitals are Earth Engine collections.

Each corpus folder holds a `spec.md` with its native unit and licence.
