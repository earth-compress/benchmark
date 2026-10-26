"""Zstandard over the raw array bytes, without a predictor."""

from __future__ import annotations

import numpy as np

from ..contract import Mode
from ..spec import ArraySpec
from . import _zstd
from .base import CodecConfiguration

_LEVEL = 3


class ZstdRaw:
    """Zstandard level 3 over the array bytes in C order."""

    def __init__(self, spec: ArraySpec):
        self._spec = spec
        self._compressor = _zstd.compressor(_LEVEL)
        self._decompressor = _zstd.decompressor()

    def encode(self, array: np.ndarray) -> bytes:
        if array.shape != self._spec.shape or array.dtype != self._spec.dtype:
            raise ValueError("array does not match the codec configuration")
        return self._compressor.compress(
            memoryview(np.ascontiguousarray(array)).cast("B")
        )

    def decode(self, compressed: bytes) -> np.ndarray:
        raw = self._decompressor.decompress(
            compressed, max_output_size=self._spec.nbytes
        )
        if len(raw) != self._spec.nbytes:
            raise ValueError("Zstandard output size does not match the input array")
        return np.frombuffer(raw, dtype=self._spec.dtype).reshape(self._spec.shape)


CONFIGURATIONS = (
    CodecConfiguration(
        id="zstd-c3",
        codec="zstd",
        version=_zstd.VERSION,
        mode=Mode.LOSSLESS,
        parameters={"level": _LEVEL, "checksum": False, "nthreads": 1},
        factory=ZstdRaw,
    ),
)
