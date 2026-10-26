# Codecs

The configurations measured in the official run, and one reference measured once. All are lossless.

## Official run

| id | group | definition | software |
| --- | --- | --- | --- |
| `zstd-c3` | Array stores | Zstandard level 3 over the raw bytes | python-zstandard |
| `blosc-zstd3-bitshuffle` | Array stores | Blosc with Zstandard level 3 and bit shuffle, the setting of the EOPF Sentinel Zarr products | numcodecs (c-blosc) |
| `deflate-c6` | Raster files | DEFLATE level 6 over the raw bytes | Python zlib |
| `lzw` | Raster files | LZW over the raw bytes, as in a TIFF written with LZW and no predictor | imagecodecs |
| `hdiff-zstd9` | Raster files | Horizontal differencing as TIFF `PREDICTOR=2`, then Zstandard level 9 as GDAL writes a ZSTD GeoTIFF | NumPy and python-zstandard |
| `openzl-generic` | OpenZL | `compress_generic` at level 7 | openzl 0.3.0 |
| `openzl-delta-fieldlz` | OpenZL | `delta>field_lz` | openzl 0.3.0 |
| `openzl-delta-pivco` | OpenZL | `delta>zigzag>transpose>huffman_pivco` | openzl 0.3.0 |
| `geozl-planar-pfor` | GeoZL | `planar>zigzag>pfor` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-planar-pivco` | GeoZL | `planar>zigzag>transpose>pivco` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-med-pivco` | GeoZL | `med>zigzag>transpose>pivco` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-planar-entropy` | GeoZL | `planar>zigzag>transpose>entropy` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-med-entropy` | GeoZL | `med>zigzag>transpose>entropy` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-average-entropy` | GeoZL | `average>zigzag>transpose>entropy` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-id-pfor` | GeoZL | `id>pfor` | geozl 0.19.0 on openzl 0.3.0 |

`hdiff-zstd9` reproduces the codec inside a GeoTIFF, not the file. There is no TIFF container, each sample is one tile, bands are pixel-interleaved before differencing, and floating-point values are differenced as integers of the same width.

For one-byte elements, the GeoZL recipes drop `transpose`, since there is nothing to transpose.

## Reference

| id | definition | software |
| --- | --- | --- |
| `jpeg2000` | JPEG 2000 lossless with the reversible 5/3 wavelet, bands as components | imagecodecs (OpenJPEG 2.5.4) |

It runs on integer corpora of up to 16 bits.

## Settings

- One thread for every codec.
- Checksums are disabled for Zstandard and OpenZL. GeoZL writes a frame checksum that its Python API cannot turn off; decoding skips its verification.
- Library versions not listed above are pinned in `uv.lock`.
