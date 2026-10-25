# Codecs

The configurations measured in the official run, and one reference measured once. All are lossless.

## Official run

| id | group | definition |
| --- | --- | --- |
| `zstd-c3` | baseline | Zstandard level 3 over the raw bytes |
| `eopf` | baseline | Blosc with Zstandard level 3 and bit shuffle, the setting of the EOPF Sentinel Zarr products |
| `deflate-c6` | baseline | DEFLATE level 6 over the raw bytes |
| `lzw` | baseline | LZW over the raw bytes, as in a TIFF written with LZW and no predictor |
| `gtiff-zstd` | baseline | horizontal differencing, as TIFF `PREDICTOR=2`, then Zstandard level 9, as GDAL writes a ZSTD GeoTIFF |
| `openzl-generic` | OpenZL | `compress_generic` at level 7 |
| `openzl-delta-fieldlz` | OpenZL | `delta>field_lz` |
| `openzl-delta-pivco` | OpenZL | `delta>zigzag>transpose>huffman_pivco` |
| `geozl-planar-pfor` | GeoZL | `planar>zigzag>pfor` |
| `geozl-planar-pivco` | GeoZL | `planar>zigzag>transpose>pivco` |

`gtiff-zstd` reproduces the codec inside the file, not the file: there is no TIFF container, each sample is one tile, and bands are pixel-interleaved before differencing.

The OpenZL configurations use no GeoZL codec.

## Reference

| id | definition |
| --- | --- |
| `jpeg2000` | JPEG 2000 lossless with the reversible 5/3 wavelet, OpenJPEG, bands as components |

It is measured once and reported as a reference line, not in every run.

## Settings

- One thread for every codec.
- Checksums are disabled for every codec that has them: the Zstandard frame checksum, and the OpenZL and GeoZL content and compressed checksums.
- Versions: OpenZL 0.3.0, GeoZL 0.19.0 built on OpenZL 0.3.0, OpenJPEG 2.5.4. All other library versions are pinned in `uv.lock`.
