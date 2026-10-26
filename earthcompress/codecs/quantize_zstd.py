from __future__ import annotations

import struct

import numpy as np
import zstandard

from ..contract import Budget, Mode
from ..spec import ArraySpec
from .base import CodecConfiguration
from .zstd import VERSION, compressor

_LEVEL = 3
_MAGIC = b"ECQ1"
_HEADER = struct.Struct("<4sBqq")

_INDEX_DTYPES = {
    1: np.dtype(np.uint8),
    2: np.dtype(np.uint16),
    4: np.dtype(np.uint32),
    8: np.dtype(np.uint64),
}


def _supports(spec: ArraySpec, budget: Budget) -> bool:
    """Integers of four bytes or fewer, and a budget of at least one step."""
    if not spec.is_integer or spec.dtype.itemsize > 4:
        return False
    return spec.steps(budget.tau) >= 1


def _index_dtype(largest: int) -> np.dtype:
    for _, dtype in sorted(_INDEX_DTYPES.items()):
        if largest <= np.iinfo(dtype).max:
            return dtype
    raise ValueError("quantised indices do not fit a supported width")


class QuantizeZstd:
    """Uniform scalar quantisation with a hard bound, then Zstandard."""

    def __init__(self, spec: ArraySpec, budget: Budget):
        if not _supports(spec, budget):
            raise ValueError("unsupported array or budget for quantisation")
        self._spec = spec
        # The budget is in native units; the array is in steps of its scale.
        self._steps = spec.steps(budget.tau)
        self._width = 2 * self._steps + 1
        self._limits = np.iinfo(spec.dtype)
        self._compressor = compressor(_LEVEL)
        self._decompressor = zstandard.ZstdDecompressor()

    def encode(self, array: np.ndarray) -> bytes:
        if array.shape != self._spec.shape or array.dtype != self._spec.dtype:
            raise ValueError("array does not match the codec configuration")
        values = array.astype(np.int64, copy=False)
        # Grid anchored at zero: index 0 covers [-steps, +steps], so an exact
        # zero decodes to an exact zero whatever the rest of the sample holds.
        indices = (values + self._steps) // self._width
        # Indices can be negative; shift only for storage, not for the grid.
        base = int(indices.min())
        payload = np.ascontiguousarray(
            indices - base, dtype=_index_dtype(int(indices.max()) - base)
        )
        header = _HEADER.pack(_MAGIC, payload.dtype.itemsize, base, self._width)
        return header + self._compressor.compress(memoryview(payload).cast("B"))

    def decode(self, compressed: bytes) -> np.ndarray:
        magic, itemsize, base, width = _HEADER.unpack_from(compressed)
        if magic != _MAGIC:
            raise ValueError("not a quantised payload")
        dtype = _INDEX_DTYPES.get(itemsize)
        if dtype is None:
            raise ValueError(f"unknown index width {itemsize}")
        raw = self._decompressor.decompress(
            compressed[_HEADER.size :], max_output_size=self._spec.size * itemsize
        )
        indices = np.frombuffer(raw, dtype=dtype).reshape(self._spec.shape)
        values = (indices.astype(np.int64) + base) * width
        # Clipping can only move a value towards its reference, so the bound holds.
        np.clip(values, self._limits.min, self._limits.max, out=values)
        return values.astype(self._spec.dtype)


def family(budget: Budget) -> CodecConfiguration:
    """The configuration of this codec at ``budget``."""
    suffix = budget.level if budget.level is not None else f"tau{budget.tau:g}"
    return CodecConfiguration(
        id=f"quant-zstd-c3-{suffix}",
        codec="quantize+zstd",
        version=VERSION,
        mode=Mode.NEAR_LOSSLESS,
        parameters={"level": _LEVEL, "nthreads": 1},
        factory=lambda spec, budget=budget: QuantizeZstd(spec, budget),
        budget=budget,
        supports=lambda spec, budget=budget: _supports(spec, budget),
    )


FAMILIES = (family,)
