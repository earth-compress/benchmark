# Codecs

A codec can run in more than one fidelity mode, and each run of it is a configuration. The table below lists every codec by mode. The sections after it define the configurations of each mode.

| codec | lossless | near-lossless | lossy |
| --- | --- | --- | --- |
| Zstandard | `zstd-c3`, `hdiff-zstd9` | `quant-zstd-c3`, `quant-hdiff-zstd9` | |
| Blosc | `blosc-zstd3-bitshuffle` | `quant-blosc-zstd3-bitshuffle` | |
| PCO | `pco` | `quant-pco` | `quant-pco-rms` |
| DEFLATE | `deflate-c6` | | |
| LZW | `lzw` | | |
| OpenZL | `openzl-generic`, `openzl-delta-fieldlz`, `openzl-delta-pivco` | `quant-openzl-generic` | |
| GeoZL | seven recipes | `geozl-med-entropy-linear`, `quant-geozl-med-entropy` | |
| LERC | | `lerc` | |
| JPEG-LS | | `jpegls-near` | |
| SZ3 | | `sz3-abs` | `sz3-l2norm` |
| ZFP | | `zfp-accuracy` | |
| SPERR | | `sperr-pwe` | `sperr-psnr` |
| JPEG 2000 | `jpeg2000`, as a reference | | `jpeg2000-psnr` |
| JPEG XL | | | `jpegxl-distance` |
| Compression Safeguards | | `sg-` before each native configuration, and `sg-zero` | |

## Official run

The lossless configurations of the published run.

| id | group | definition | software |
| --- | --- | --- | --- |
| `zstd-c3` | Array stores | Zstandard level 3 over the raw bytes | python-zstandard |
| `blosc-zstd3-bitshuffle` | Array stores | Blosc with Zstandard level 3 and bit shuffle, the setting of the EOPF Sentinel Zarr products | numcodecs (c-blosc) |
| `pco` | Array stores | Pcodec level 8 over the flattened array, a lossless codec for numerical sequences | imagecodecs (pcodec 1.0.4) |
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

## Near-lossless

Each near-lossless configuration runs at every level that `TOLERANCE.md` gives the corpus, and its id ends with the level, as in `lerc-matched`. It belongs to one of three families, recorded in the `family` column of `results.csv`. A row that breaks a promise is a result and keeps its measurements, as `PROTOCOL.md` sets out.

### Native

The codec's own bounded mode, run as published.

| id | definition | NoData | software |
| --- | --- | --- | --- |
| `geozl-med-entropy-linear` | GeoZL `med>zigzag>transpose>entropy` with its `LINEAR` quantiser, the budget as `error` | `nodata` | geozl 0.19.0 on openzl 0.3.0 |
| `lerc` | LERC with the budget as `maxZError`, as GDAL writes it | valid mask | imagecodecs (LERC 4.2.0) |
| `jpegls-near` | JPEG-LS with the budget as `NEAR`, one stream per plane | | imagecodecs (CharLS 2.4.4) |
| `sz3-abs` | SZ3 with an absolute bound | | imagecodecs (SZ3 3.4.0) |
| `zfp-accuracy` | ZFP in fixed-accuracy mode, the budget as tolerance | | imagecodecs (zfp 1.0.1) |
| `sperr-pwe` | SPERR in point-wise error mode | | imagecodecs (SPERR 0.8.5) |

A codec receives the budget in the units of the stored values, which for integers is the number of whole steps of the largest `scale`, and the sentinel only where its interface takes one. SZ3, ZFP and SPERR take floats only, so integer codes reach them as floats that hold every code exactly, and their output is rounded to the nearest code and clipped to the type. Rounding to a whole code cannot widen an error that is within a whole number of codes.

- GeoZL takes its lossy domain from the raster a graph is built from, so the graph is built from each sample while it is encoded. Its integer grid is `2k` codes wide where `2k + 1` would fit.
- LERC floors the bound for integers and reads 777 as a request for another mode, so a budget of 777 codes is passed as 777.5.
- CharLS accepts `NEAR` up to 127 for 8-bit and 255 for 16-bit data. Above that, `jpegls-near` does not run.
- SPERR takes two- and three-dimensional arrays only.
- JPEG 2000 has no bounded mode, so it has no near-lossless configuration.

### Quantized

The shared quantiser of this benchmark, then an unchanged lossless configuration on the grid indices.

- **Integers.** Each plane gets `k = floor(tau / scale)` steps of its own scale, and values round to a grid `2k + 1` codes wide, anchored at the code of a native zero. A sentinel at the bottom of the type keeps index 0 to itself, and valid values decode above it.
- **Floats.** Values round to multiples of `2 tau`, so zero stays exact. Values that rounding in the element type moves just past `tau`, and values that are not finite, are kept exactly beside the grid.

The indices reach the lossless configuration in the narrowest unsigned type that holds them. Every quantized row keeps the promises by construction, and differs from the others only by its lossless stage. The lossless configurations are `zstd-c3`, `pco`, and the best ratio of each group in the lossless run, `blosc-zstd3-bitshuffle`, `hdiff-zstd9`, `openzl-generic` and `geozl-med-entropy`.

### Safeguarded

Each native configuration wrapped in Compression Safeguards (Tyree et al., 2026), as `sg-<id>`. The safeguards are an absolute bound equal to the budget, the sentinel kept to its own positions, and exact zeros kept. While encoding, the safeguards decode the native output and store the corrections that restore every promise; decoding applies them. The native codec runs unchanged, so the difference from its native row is the cost of safety. `sg-zero` wraps a codec that decodes to zeros, so every value comes from the corrections.

The software is compression-safeguards 1.0.0rc5 and numcodecs-safeguards 0.1.0rc5, with their own lossless coding of the corrections.

## Lossy

Each lossy configuration runs at every lossy level that `TOLERANCE.md` gives the corpus, and its id ends with the level, as in `jpeg2000-psnr-matched`. It holds the root-mean-square error of each sample within `tau` rather than every element, so its maximum error is not bounded. The `zero` check is reported but is not a promise. The `family` column records how the configuration reaches `tau`.

| id | family | definition | NoData | software |
| --- | --- | --- | --- | --- |
| `jpeg2000-psnr` | native | JPEG 2000 with the irreversible 9/7 wavelet, bands as components with no colour transform, its quality layer set to the PSNR whose mean squared error is `tau` squared | | imagecodecs (OpenJPEG 2.5.4) |
| `sperr-psnr` | native | SPERR in PSNR mode, the target set from the range of the sample so that the root-mean-square error is `tau` | | imagecodecs (SPERR 0.8.5) |
| `sz3-l2norm` | native | SZ3 in its L2-norm mode, passed as the absolute bound `sqrt(3) tau` that SZ3 derives from it | | imagecodecs (SZ3 3.4.0) |
| `jpegxl-distance` | searched | JPEG XL at effort 7, one grayscale frame per plane, the largest distance found whose error is within `tau` | | imagecodecs (libjxl 0.12.0) |
| `quant-pco-rms` | quantized | The shared quantiser on a grid as wide as `tau` allows, then `pco` | bottom of the type | imagecodecs (pcodec 1.0.4) |

- OpenJPEG measures PSNR over every component together, against the largest value of the sample type, so the target is the root-mean-square error of the sample. `jpeg2000-psnr` runs on integer corpora of up to 16 bits.
- SPERR measures PSNR over the range of the data it receives. A sample whose range is within `tau` gets a target of 0.001 dB, since SPERR rejects zero.
- imagecodecs exposes only the absolute mode of SZ3. SZ3 runs its L2-norm mode as an absolute bound of `sqrt(3 / n)` times the norm, which for a root-mean-square error of `tau` is `sqrt(3) tau`, so `sz3-l2norm` passes that bound. Integer output is rounded to whole codes, which can move the error past `tau`.
- JPEG XL takes a perceptual distance rather than an error. On each sample the wrapper tries 25, the largest distance libjxl accepts, then halves the logarithmic interval down to 0.01 eight times and keeps the largest distance whose error is within `tau`. It measures that error over the whole sample in stored units, since the codec does not know NoData, and falls back to lossless JPEG XL when no distance holds. Every trial is part of the encode time. `jpegxl-distance` runs on 8- and 16-bit unsigned integers.
- The quantiser starts from the widest grid whose rounding error, if uniform, has a root-mean-square of `tau`, the rule SZ3 uses for its L2-norm mode. For integers that is the largest `k` with `k (k + 1) / 3 <= (tau / scale)²` in each plane, and for floats a step of `2 sqrt(3) tau`. If the error of the sample is still above `tau`, the grid narrows until it is not, and the width it settles on is stored with the data. Zeros and a sentinel at the bottom of the type stay exact. ClimateBenchPress found rounding followed by PCO a reliable baseline (Reichelt et al., 2026).
- LERC, JPEG-LS, ZFP and GeoZL bound every element and have no lossy configuration. Their near-lossless rows at the same `tau` already meet the lossy bound.

## Settings

- One thread for every codec.
- Checksums are disabled for Zstandard and OpenZL. GeoZL writes a frame checksum that its Python API cannot turn off; decoding skips its verification.
- Library versions not listed above are pinned in `uv.lock`.

## Adding a configuration

Add a module to `earthcompress/codecs/` that defines `CONFIGURATIONS` for lossless configurations, `FAMILIES` for a native near-lossless codec, or `LOSSY` for a lossy one. A configuration builds, from the `ArraySpec` of a sample, an object with `encode` and `decode`. A family is a function from a budget to a configuration, made with `near_lossless` or `lossy` in `earthcompress/codecs/base.py`. The benchmark gives every near-lossless family a safeguarded variant.

```python
import mycodec

from ..spec import ArraySpec
from .base import lossless, unpack


class MyCodec:
    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def encode(self, array):
        return mycodec.compress(array.tobytes())

    def decode(self, data):
        return unpack(mycodec.decompress(data), self.spec)


CONFIGURATIONS = (lossless("mycodec", "mycodec", mycodec.__version__, MyCodec),)
```

```bash
uv run earthcompress corpora/s2-l1c-10m-4 --codec mycodec
```

## References

- Reichelt, T., et al. (2026). ClimateBenchPress (v1.0), a benchmark for lossy compression of climate data. *Geosci. Model Dev.*, 19, 5933–5960.
- Tyree, J., et al. (2026). [Compression Safeguards, building trust into lossy data compression](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-4266/). *EGUsphere* preprint, egusphere-2026-4266.
