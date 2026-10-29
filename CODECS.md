# Codecs

The tables list the configurations the benchmark can run, grouped by fidelity mode. `results.csv` shows which ones have been measured. `PROTOCOL.md` defines the fidelity checks and `TOLERANCE.md` the error budgets.

## Lossless

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
| `jpeg2000` | Reference | JPEG 2000 lossless with the reversible 5/3 wavelet, bands as components | imagecodecs (OpenJPEG 2.5.4) |

`jpeg2000` is a separate reference, measured only when requested, on integer corpora of up to 16 bits.

## Near-lossless

Near-lossless and lossy ids end with the budget level, as in `lerc-matched`. The `family` column describes how they use `tau`. `native` uses the codec's own error or quality setting, `quantized` uses the shared quantiser, `safeguarded` adds corrections, and `searched` tries settings on each sample. An empty NoData cell means no mask or sentinel is passed to the codec.

| id | family | definition | NoData | software |
| --- | --- | --- | --- | --- |
| `geozl-med-entropy-linear` | native | GeoZL `med>zigzag>transpose>entropy` with its `LINEAR` quantiser, `tau` as `error` | `nodata` | geozl 0.19.0 on openzl 0.3.0 |
| `lerc` | native | LERC with `tau` as `maxZError`, as GDAL writes it | valid mask | imagecodecs (LERC 4.2.0) |
| `jpegls-near` | native | JPEG-LS with `tau` as `NEAR`, one stream per plane | | imagecodecs (CharLS 2.4.4) |
| `sz3-abs` | native | SZ3 with `tau` as its absolute bound | | imagecodecs (SZ3 3.4.0) |
| `zfp-accuracy` | native | ZFP in fixed-accuracy mode, `tau` as the tolerance | | imagecodecs (zfp 1.0.1) |
| `sperr-pwe` | native | SPERR in point-wise error mode | | imagecodecs (SPERR 0.8.5) |
| `quant-<id>` | quantized | The quantiser, then the lossless configuration `<id>` | bottom of the type | that of `<id>` |
| `sg-<id>` | safeguarded | The native configuration `<id>` inside Compression Safeguards | kept | compression-safeguards 1.0.0rc5 and numcodecs-safeguards 0.1.0rc5 |
| `sg-zero` | safeguarded | Compression Safeguards around a codec that decodes to zeros | kept | compression-safeguards 1.0.0rc5 and numcodecs-safeguards 0.1.0rc5 |

The quantiser can feed `zstd-c3`, `pco`, `blosc-zstd3-bitshuffle`, `hdiff-zstd9`, `openzl-generic` or `geozl-med-entropy`.

## Lossy

| id | family | definition | NoData | software |
| --- | --- | --- | --- | --- |
| `jpeg2000-psnr` | native | JPEG 2000 with the irreversible 9/7 wavelet and no colour transform, at the PSNR whose root-mean-square error is `tau` | | imagecodecs (OpenJPEG 2.5.4) |
| `sperr-psnr` | native | SPERR in PSNR mode, at the PSNR whose root-mean-square error is `tau` | | imagecodecs (SPERR 0.8.5) |
| `sz3-l2norm` | native | SZ3 in its L2-norm mode | | imagecodecs (SZ3 3.4.0) |
| `jpegxl-distance` | searched | JPEG XL at effort 7, one grayscale frame per plane, the distance searched | | imagecodecs (libjxl 0.12.0) |
| `quant-pco-rms` | quantized | The quantiser with its lossy grid, then `pco` | bottom of the type | imagecodecs (pcodec 1.0.4) |

LERC, JPEG-LS, ZFP and GeoZL have no separate lossy configuration. A near-lossless row that meets its pointwise bound also meets the lossy bound at the same `tau`.

## The quantiser

The quantiser rounds each value to a grid and passes the grid indices, in the narrowest unsigned type that holds them, to an unchanged lossless configuration. Quantised rows keep every promise by construction, and rows of one mode differ only by their lossless stage.

Integer grids are `2k + 1` codes wide in each plane and anchored at the code of a native zero, so zeros stay exact. Near-lossless takes `k = floor(tau / scale)`. Lossy starts from the largest `k` with `k (k + 1) / 3 <= (tau / scale)²`, where a uniform rounding error has a root-mean-square of `tau`, the rule SZ3 uses for its L2-norm mode. A sentinel at the bottom of the type keeps index 0 to itself, and valid values decode above it.

Floats round to multiples of `2 tau` in near-lossless and of `2 sqrt(3) tau` in lossy, so zero stays exact. Values that rounding in the element type moves past the bound, and values that are not finite, are kept exactly beside the grid.

In lossy mode, a sample whose error is still above `tau` gets a narrower grid until it is not, and the width is stored with the data. ClimateBenchPress found rounding followed by PCO a reliable baseline (Reichelt et al., 2026), so `pco` is the lossless stage in lossy mode.

## Compression Safeguards

`sg-<id>` wraps a native near-lossless configuration in Compression Safeguards (Tyree et al., 2026), set to an absolute bound of `tau`, the sentinel kept to its own positions, and exact zeros kept. While encoding, the safeguards decode the native output and store the corrections that restore every promise, and decoding applies them. The native codec runs unchanged, so the difference from its own row is the cost of safety. In `sg-zero` every value comes from the corrections.

## Settings

- One thread for every codec.
- A codec receives `tau` in stored units, which for integers is whole steps of the largest `scale`, and the sentinel only where its interface takes one.
- SZ3, ZFP and SPERR take floats only. Integer codes reach them as floats that hold every code exactly, and their output is rounded to the nearest code and clipped to the type. Rounding cannot widen an error that is within a whole number of codes, but it can raise a root-mean-square error.
- Checksums are off for Zstandard and OpenZL. GeoZL writes a frame checksum that its Python API cannot turn off, and decoding skips its verification.
- Library versions not given here are pinned in `uv.lock`.

## Notes by codec

- `hdiff-zstd9` reproduces the codec inside a GeoTIFF, not the file. There is no TIFF container, each sample is one tile, bands are pixel-interleaved before differencing, and floating-point values are differenced as integers of the same width.
- GeoZL recipes drop `transpose` for one-byte elements. GeoZL takes its lossy domain from the raster a graph is built from, so `geozl-med-entropy-linear` builds the graph from each sample while encoding it. Its integer grid is `2k` codes wide where `2k + 1` would fit.
- LERC floors the bound for integers and reads 777 as a request for another mode, so a budget of 777 codes is passed as 777.5.
- CharLS accepts `NEAR` up to 127 for 8-bit and 255 for 16-bit data. Above that, `jpegls-near` does not run.
- SZ3 runs its L2-norm mode as an absolute bound of `sqrt(3 / n)` times the norm, which for a root-mean-square error of `tau` is `sqrt(3) tau`. imagecodecs exposes only the absolute mode, so `sz3-l2norm` passes that bound.
- SPERR takes two- and three-dimensional arrays only. It measures PSNR over the range of the data it receives and rejects a target of zero, so a sample whose range is within `tau` gets 0.001 dB.
- JPEG 2000 has no bounded mode, so it has no near-lossless configuration. OpenJPEG measures PSNR over all components together, against the largest value of the type. Both JPEG 2000 configurations take integers of up to 16 bits.
- JPEG XL takes a perceptual distance rather than an error. On each sample, `jpegxl-distance` tries 25, the largest distance libjxl accepts, then halves the logarithmic interval down to 0.01 eight times. It keeps the largest distance whose root-mean-square error over the whole sample, in stored units, is within `tau`, and falls back to lossless JPEG XL when none is. Every trial counts in the encode time. It takes 8- and 16-bit unsigned integers.

## Adding a configuration

Add a module to `earthcompress/codecs/` that defines `CONFIGURATIONS` for lossless configurations, `FAMILIES` for a native near-lossless codec, or `LOSSY` for a lossy one. A configuration builds, from the `ArraySpec` of a sample, an object with `encode` and `decode`. A family is a function from a budget to a configuration, made with `near_lossless` or `lossy` in `earthcompress/codecs/base.py`. Every native near-lossless family also gets a safeguarded variant.

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
