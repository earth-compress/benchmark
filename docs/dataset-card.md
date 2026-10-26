---
license: other
license_name: mixed
pretty_name: Earth Compress benchmark corpora
tags:
- geospatial
- earth-observation
- compression
- benchmark
size_categories:
- n<1K
configs:
- config_name: s2-l1c-10m-4
  data_files: s2-l1c-10m-4/manifest.csv
- config_name: s2-l1c-20m-6
  data_files: s2-l1c-20m-6/manifest.csv
- config_name: s2-l1c-60m-3
  data_files: s2-l1c-60m-3/manifest.csv
- config_name: lm-mss-4
  data_files: lm-mss-4/manifest.csv
- config_name: l5-tm-6
  data_files: l5-tm-6/manifest.csv
- config_name: l5-tm-tir
  data_files: l5-tm-tir/manifest.csv
- config_name: l7-etm-6
  data_files: l7-etm-6/manifest.csv
- config_name: l7-etm-pan
  data_files: l7-etm-pan/manifest.csv
- config_name: l7-etm-tir-2
  data_files: l7-etm-tir-2/manifest.csv
- config_name: l8-oli-8
  data_files: l8-oli-8/manifest.csv
- config_name: l8-oli-pan
  data_files: l8-oli-pan/manifest.csv
- config_name: l8-tirs-2
  data_files: l8-tirs-2/manifest.csv
- config_name: goes-abi-16
  data_files: goes-abi-16/manifest.csv
- config_name: s1-grd-iw-2
  data_files: s1-grd-iw-2/manifest.csv
- config_name: emit-l2a-285
  data_files: emit-l2a-285/manifest.csv
- config_name: cop-dem-glo30
  data_files: cop-dem-glo30/manifest.csv
- config_name: esa-wc-v200
  data_files: esa-wc-v200/manifest.csv
- config_name: imerg-pcp-12
  data_files: imerg-pcp-12/manifest.csv
- config_name: era5-msl-1h
  data_files: era5-msl-1h/manifest.csv
- config_name: era5-t2m-1h
  data_files: era5-t2m-1h/manifest.csv
- config_name: era5-tcc-1h
  data_files: era5-tcc-1h/manifest.csv
- config_name: era5-tp-1h
  data_files: era5-tp-1h/manifest.csv
- config_name: era5-u10-1h
  data_files: era5-u10-1h/manifest.csv
- config_name: alphaearth-v1-64
  data_files: alphaearth-v1-64/manifest.csv
- config_name: tessera-v2-codes
  data_files: tessera-v2-codes/manifest.csv
- config_name: tessera-v2-scales
  data_files: tessera-v2-scales/manifest.csv
- config_name: clay-embeddings
  data_files: clay-embeddings/manifest.csv
---

<p align="center">
  <img src="https://huggingface.co/datasets/earth-compress/benchmark/resolve/main/assets/earth-compress.svg" alt="Earth Compress" width="420" class="dark:hidden">
  <img src="https://huggingface.co/datasets/earth-compress/benchmark/resolve/main/assets/earth-compress-dark.svg" alt="Earth Compress" width="420" class="hidden dark:block">
</p>

# Earth Compress benchmark corpora

The 585 samples of the [Earth Compress benchmark](https://github.com/earth-compress/benchmark),
in 27 corpora of satellite imagery, reanalysis fields, elevation, land cover
and embeddings. Each sample is a window of a published product on
its native grid, with bands or time steps on the first axis; ERA5 samples are
whole global fields, and Clay samples are blocks of MajorTOM cells. A sample
holds the published integers, with their scale and offset, when these
reproduce the published values exactly, and the published floats otherwise.
The compressed files take 2.6 GB.

## Layout

```
{corpus}/manifest.csv
{corpus}/spec.md
{corpus}/npz/{sample}.npz.zst
{corpus}/png/{sample}.png
```

`manifest.csv` has one row per sample with its source asset, CRS, GDAL
geotransform, start and end dates, bands, shape, dtype, unit, scale, offset,
NoData and the SHA-256 of the array, which is enough to write the sample as a
GeoTIFF. `spec.md` describes the corpus and how its samples were chosen. The
PNG is a preview.

| corpus | contents | shape | dtype | samples |
| --- | --- | --- | --- | ---: |
| `s2-l1c-10m-4` | Sentinel-2 L1C, bands B2, B3, B4, B8 at 10 m | 4×512×512 | uint16 | 50 |
| `s2-l1c-20m-6` | Sentinel-2 L1C, red-edge, narrow NIR and SWIR bands at 20 m | 6×512×512 | uint16 | 50 |
| `s2-l1c-60m-3` | Sentinel-2 L1C, aerosol, water vapour and cirrus bands at 60 m | 3×512×512 | uint16 | 50 |
| `lm-mss-4` | Landsat 1–5 MSS, four bands at 60 m | 4×512×512 | uint8 | 15 |
| `l5-tm-6` | Landsat 5 TM, six reflective bands at 30 m | 6×512×512 | uint8 | 15 |
| `l5-tm-tir` | Landsat 5 TM, thermal band B6 | 512×512 | uint8 | 15 |
| `l7-etm-6` | Landsat 7 ETM+, six reflective bands at 30 m | 6×512×512 | uint8 | 15 |
| `l7-etm-pan` | Landsat 7 ETM+, panchromatic band at 15 m | 1024×1024 | uint8 | 15 |
| `l7-etm-tir-2` | Landsat 7 ETM+, thermal band at low and high gain | 2×512×512 | uint8 | 15 |
| `l8-oli-8` | Landsat 8 OLI, eight reflective bands at 30 m | 8×512×512 | uint16 | 15 |
| `l8-oli-pan` | Landsat 8 OLI, panchromatic band at 15 m | 1024×1024 | uint16 | 15 |
| `l8-tirs-2` | Landsat 8 TIRS, thermal bands B10 and B11 | 2×512×512 | uint16 | 15 |
| `goes-abi-16` | GOES-16 ABI, sixteen bands as counts with per-band scale and offset | 16×512×512 | uint16 | 15 |
| `s1-grd-iw-2` | Sentinel-1 GRD IW, VV and VH backscatter, linear | 2×512×512 | float32 | 50 |
| `emit-l2a-285` | EMIT L2A reflectance, 285 bands at 60 m | 285×128×128 | float32 | 10 |
| `cop-dem-glo30` | Copernicus DEM GLO-30 elevation | 512×512 | float32 | 50 |
| `esa-wc-v200` | ESA WorldCover 2021 land-cover class codes at 10 m | 512×512 | uint8 | 50 |
| `imerg-pcp-12` | GPM IMERG precipitation rate, 12 half-hourly fields | 12×512×512 | uint16 | 15 |
| `era5-msl-1h` | ERA5 mean sea-level pressure, 24 hourly global fields | 24×721×1440 | uint16 | 10 |
| `era5-t2m-1h` | ERA5 2 m temperature, 24 hourly global fields | 24×721×1440 | uint16 | 10 |
| `era5-tcc-1h` | ERA5 total cloud cover, 24 hourly global fields | 24×721×1440 | uint16 | 10 |
| `era5-tp-1h` | ERA5 total precipitation, 24 hourly global fields | 24×721×1440 | uint16 | 10 |
| `era5-u10-1h` | ERA5 10 m eastward wind, 24 hourly global fields | 24×721×1440 | uint16 | 10 |
| `alphaearth-v1-64` | AlphaEarth Foundations embeddings, 64 dimensions at 10 m | 64×512×512 | int8 | 15 |
| `tessera-v2-codes` | TESSERA v2 embedding codes, 128 dimensions | 128×512×512 | int8 | 15 |
| `tessera-v2-scales` | TESSERA v2 per-pixel scale of the codes | 512×512 | float32 | 15 |
| `clay-embeddings` | Clay v1.5 Sentinel-2 embeddings, 1024 dimensions on 32×32 MajorTOM cells of 2560 m | 1024×32×32 | float32 | 15 |

## Reading a sample

```python
import io
import numpy as np
import zstandard

raw = open("s2-l1c-10m-4/npz/s2-l1c-10m-4-00.npz.zst", "rb").read()
sample = np.load(io.BytesIO(zstandard.decompress(raw)))
data = sample["data"]  # "scale", "offset" and "nodata" when the corpus has them
```

The benchmark reads the corpora from its `corpora/` folder, which has the same
layout as this repository.

```bash
hf download earth-compress/benchmark --repo-type dataset --local-dir corpora
uv run earthcompress corpora/s2-l1c-10m-4
```

Each corpus can also be rebuilt from its manifest with the `build.py` of its
folder in the benchmark repository, which checks every sample against its
SHA-256.

## Licence and attribution

Each corpus keeps the licence of its source.

| source | corpora | licence and attribution |
| --- | --- | --- |
| Sentinel-1, Sentinel-2 | `s1-grd-iw-2`, `s2-l1c-*` | Copernicus data policy. Contains modified Copernicus Sentinel data 2023. |
| Landsat | `lm-mss-4`, `l5-*`, `l7-*`, `l8-*` | Public domain. Landsat data courtesy of the U.S. Geological Survey. |
| GOES-16 ABI | `goes-abi-16` | Public domain. GOES-16 imagery courtesy of NOAA/NESDIS. |
| GPM IMERG | `imerg-pcp-12` | No restrictions. Global Precipitation Measurement (GPM) IMERG data provided by the NASA/GSFC Precipitation Processing System. |
| EMIT | `emit-l2a-285` | No restrictions. EMIT L2A Estimated Surface Reflectance V001, NASA. |
| ERA5 | `era5-*` | Copernicus licence. Contains modified Copernicus Climate Change Service information 2023. Neither the European Commission nor ECMWF is responsible for any use of this data. |
| Copernicus DEM | `cop-dem-glo30` | Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA; all rights reserved. |
| ESA WorldCover | `esa-wc-v200` | CC BY 4.0. © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by the ESA WorldCover consortium. |
| AlphaEarth Foundations | `alphaearth-v1-64` | CC BY 4.0. The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind. |
| TESSERA | `tessera-v2-*` | CC0 1.0. |
| Clay | `clay-embeddings` | CC BY 4.0. Clay v1.5 embeddings produced by LGND with the Clay Foundation Model. |

## Development

Developed in the [Earth Compress](https://asterisk.coop/project-pages/earth-compress.html)
project, led by Asterisk Labs and the National Oceanography Centre.

## Funding

This work was funded by the Advanced Research and Invention Agency
(ARIA).

## Citation

```bibtex
@misc{earth_compress_benchmark,
  title  = {{Earth Compress benchmark corpora}},
  author = {{Asterisk Laboratories Co-operative Ltd.} and {National Oceanography Centre}},
  year   = {2026},
  url    = {https://huggingface.co/datasets/earth-compress/benchmark},
  note   = {Earth Compress project}
}
```
