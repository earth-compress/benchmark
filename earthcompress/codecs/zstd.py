from __future__ import annotations

import numpy as np
import zstandard

from ..spec import ArraySpec
from .base import as_bits, lossless, unpack

VERSION = f"{'.'.join(map(str, zstandard.ZSTD_VERSION))} (python-zstandard {zstandard.__version__})"


def compressor(level: int) -> zstandard.ZstdCompressor:
    return zstandard.ZstdCompressor(level=level, threads=0, write_checksum=False)


class Zstd:
    def __init__(self, spec: ArraySpec, level: int = 3):
        self.spec = spec
        self.c = compressor(level)
        self.d = zstandard.ZstdDecompressor()

    def encode(self, array):
        return self.c.compress(np.ascontiguousarray(array))

    def decode(self, data):
        return unpack(
            self.d.decompress(data, max_output_size=self.spec.nbytes), self.spec
        )


class HorizontalDifference(Zstd):
    """TIFF ``PREDICTOR=2`` on pixel-interleaved bands, then Zstandard, as GDAL writes it."""

    def __init__(self, spec: ArraySpec):
        super().__init__(spec, level=9)

    def interleaved(self, array):
        bands = array if array.ndim == 3 else array[np.newaxis]
        return np.moveaxis(as_bits(bands), 0, -1)

    def encode(self, array):
        pixels = self.interleaved(array)
        diff = pixels.copy()
        diff[:, 1:] -= pixels[:, :-1]
        return self.c.compress(diff)

    def decode(self, data):
        shape = self.interleaved(np.empty(self.spec.shape, self.spec.dtype)).shape
        bits = as_bits(np.empty(0, self.spec.dtype)).dtype
        diff = np.frombuffer(self.d.decompress(data), dtype=bits).reshape(shape)
        pixels = np.cumsum(diff, axis=1, dtype=bits)
        bands = np.moveaxis(pixels, -1, 0).view(self.spec.dtype)
        return np.ascontiguousarray(bands.reshape(self.spec.shape))


CONFIGURATIONS = (
    lossless("zstd-c3", "zstd", VERSION, Zstd, level=3, checksum=False, nthreads=1),
    lossless(
        "hdiff-zstd9",
        "zstd",
        VERSION,
        HorizontalDifference,
        predictor="horizontal",
        level=9,
    ),
)
