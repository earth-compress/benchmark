# Codecs

The configurations measured in the official run, and one reference measured once. All are lossless.

## Official run

| id | group | definition | software |
| --- | --- | --- | --- |
| `zstd-c3` | baseline | Zstandard level 3 over the raw bytes | python-zstandard |
| `blosc-zstd3-bitshuffle` | baseline | Blosc with Zstandard level 3 and bit shuffle, the setting of the EOPF Sentinel Zarr products | python-blosc (c-blosc) |
| `deflate-c6` | baseline | DEFLATE level 6 over the raw bytes | Python zlib |
| `lzw` | baseline | LZW over the raw bytes, as in a TIFF written with LZW and no predictor | imagecodecs |
| `hdiff-zstd9` | baseline | horizontal differencing as TIFF `PREDICTOR=2`, then Zstandard level 9 as GDAL writes a ZSTD GeoTIFF | NumPy and python-zstandard |
| `openzl-generic` | OpenZL | `compress_generic` at level 7 | openzl 0.3.0 |
| `openzl-delta-fieldlz` | OpenZL | `delta>field_lz` | openzl 0.3.0 |
| `openzl-delta-pivco` | OpenZL | `delta>zigzag>transpose>huffman_pivco` | openzl 0.3.0 |
| `geozl-planar-pfor` | GeoZL | `planar>zigzag>pfor` | geozl 0.19.0 on openzl 0.3.0 |
| `geozl-planar-pivco` | GeoZL | `planar>zigzag>transpose>pivco` | geozl 0.19.0 on openzl 0.3.0 |

`hdiff-zstd9` reproduces the codec inside a GeoTIFF, not the file. There is no TIFF container, each sample is one tile, and bands are pixel-interleaved before differencing.

The OpenZL configurations use no GeoZL codec.

## Reference

| id | definition | software |
| --- | --- | --- |
| `jpeg2000` | JPEG 2000 lossless with the reversible 5/3 wavelet, bands as components | imagecodecs (OpenJPEG 2.5.4) |

It is measured once and reported as a reference line, not in every run.

## Settings

- One thread for every codec.
- Checksums are disabled for every codec that has them, which covers the Zstandard frame checksum and the OpenZL and GeoZL content and compressed checksums.
- Library versions not listed above are pinned in `uv.lock`.
