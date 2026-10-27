"""The quantiser shared by every configuration of the quantized family.

It rounds each value to a grid that keeps the budget, then hands the grid
indices to an unchanged lossless codec. Every lossless codec therefore sees
the same indices, so the quantized rows differ only by their lossless stage.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from functools import partial

import numpy as np
import zstandard

from ..contract import Budget
from ..spec import ArraySpec
from .base import Codec, CodecConfiguration, Family, near_lossless

BACKENDS = (
    "zstd-c3",
    "pco",
    "blosc-zstd3-bitshuffle",
    "hdiff-zstd9",
    "openzl-generic",
    "geozl-med-entropy",
)
"""Lossless configurations that get a quantized variant: the plainest codec,
PCO, and the best ratio of each group of the lossless run."""

_MAGIC = b"ECQ2"
_HEADER = struct.Struct("<4sBqQ")  # magic, index width, index base, exception bytes
_UNSIGNED = tuple(np.dtype(f"u{width}") for width in (1, 2, 4, 8))


def _narrowest(largest: int) -> np.dtype:
    for dtype in _UNSIGNED:
        if largest <= np.iinfo(dtype).max:
            return dtype
    raise ValueError("grid indices do not fit 64 bits")


def _planes(array: np.ndarray, count: int):
    """The array as ``count`` planes along its first axis, or as one plane."""
    return (array,) if count == 1 else tuple(array[i] for i in range(count))


class IntegerGrid:
    """Codes rounded to a grid of ``2k + 1`` codes, ``k`` the budget of the plane.

    A plane whose budget is below one step keeps its codes. A native zero sits
    on the grid, so it decodes exactly. A sentinel at the bottom of the type
    keeps index 0 to itself, and valid codes decode at or above the next code.
    """

    def __init__(self, spec: ArraySpec, budget: Budget):
        self.limits = np.iinfo(spec.dtype)
        self.sentinel = None if spec.sentinel is None else int(spec.sentinel)
        self.steps = spec.plane_steps(budget.tau)
        self.anchors = tuple(
            0
            if code is None or not self.limits.min <= code <= self.limits.max
            else code
            for code in spec.zero_codes()
        )

    def indices(self, array: np.ndarray) -> np.ndarray:
        out = np.empty(array.shape, np.int64)
        for plane, k, anchor, target in zip(
            _planes(array, len(self.steps)),
            self.steps,
            self.anchors,
            _planes(out, len(self.steps)),
            strict=True,
        ):
            codes = plane.astype(np.int64)
            width = 2 * k + 1
            if self.sentinel is None:
                target[...] = (codes - anchor + k) // width
            else:
                valid = codes != self.sentinel
                target[...] = np.where(
                    valid, 1 + (codes - self.sentinel - 1) // width, 0
                )
        return out

    def values(self, indices: np.ndarray, dtype: np.dtype) -> np.ndarray:
        out = np.empty(indices.shape, dtype)
        for plane, k, anchor, target in zip(
            _planes(indices, len(self.steps)),
            self.steps,
            self.anchors,
            _planes(out, len(self.steps)),
            strict=True,
        ):
            width = 2 * k + 1
            if self.sentinel is None:
                codes = anchor + plane * width
                low = self.limits.min
            else:
                codes = self.sentinel + 1 + k + (plane - 1) * width
                low = self.sentinel + 1
            # Clipping moves a value towards its input, so the bound holds.
            np.clip(codes, low, self.limits.max, out=codes)
            if self.sentinel is not None:
                codes[plane == 0] = self.sentinel
            target[...] = codes
        return out


class FloatGrid:
    """Values rounded to multiples of ``2 tau``, so zero stays exact.

    Rounding in the element type can move a value just past ``tau``; such
    values, and values that are not finite, are kept exactly beside the grid.
    """

    def __init__(self, spec: ArraySpec, budget: Budget):
        self.tau = budget.tau
        self.step = 2.0 * budget.tau

    def indices(self, array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = array.astype(np.float64)
        with np.errstate(invalid="ignore", over="ignore"):
            scaled = np.rint(values / self.step)
            fits = np.isfinite(scaled) & (np.abs(scaled) < 2.0**52)
            indices = np.where(fits, scaled, 0.0).astype(np.int64)
            restored = (indices * self.step).astype(array.dtype).astype(np.float64)
            kept = ~fits | ~(np.abs(restored - values) <= self.tau)
        indices[kept] = 0
        return indices, np.flatnonzero(kept)

    def values(self, indices: np.ndarray, dtype: np.dtype) -> np.ndarray:
        return (indices * self.step).astype(dtype)


def supports(spec: ArraySpec, budget: Budget) -> bool:
    """Integers with no sentinel or one at the bottom of the type, or floats."""
    if spec.is_integer:
        if spec.dtype.itemsize > 4:
            return False
        return spec.sentinel is None or spec.sentinel == np.iinfo(spec.dtype).min
    return spec.dtype.kind == "f" and spec.sentinel is None


class Quantized:
    """The shared quantiser, then one lossless codec on the grid indices."""

    def __init__(
        self, spec: ArraySpec, budget: Budget, backend: Callable[[ArraySpec], Codec]
    ):
        if not supports(spec, budget):
            raise ValueError("unsupported array for the shared quantiser")
        self.spec = spec
        self.grid = (
            IntegerGrid(spec, budget) if spec.is_integer else FloatGrid(spec, budget)
        )
        self.backend = backend
        self._backends: dict[np.dtype, Codec] = {}
        self._compressor = zstandard.ZstdCompressor(level=3, write_checksum=False)
        self._decompressor = zstandard.ZstdDecompressor()

    def _lossless(self, dtype: np.dtype) -> Codec:
        if dtype not in self._backends:
            self._backends[dtype] = self.backend(ArraySpec(self.spec.shape, dtype))
        return self._backends[dtype]

    def encode(self, array: np.ndarray) -> bytes:
        if array.shape != self.spec.shape or array.dtype != self.spec.dtype:
            raise ValueError("array does not match the codec configuration")
        exceptions = b""
        if isinstance(self.grid, FloatGrid):
            indices, kept = self.grid.indices(array)
            if kept.size:
                exceptions = self._compressor.compress(
                    kept.astype(np.uint64).tobytes()
                    + np.ascontiguousarray(array).reshape(-1)[kept].tobytes()
                )
        else:
            indices = self.grid.indices(array)
        base = int(indices.min())
        dtype = _narrowest(int(indices.max()) - base)
        payload = self._lossless(dtype).encode(
            np.ascontiguousarray(indices - base, dtype=dtype)
        )
        header = _HEADER.pack(_MAGIC, dtype.itemsize, base, len(exceptions))
        return header + exceptions + payload

    def decode(self, compressed: bytes) -> np.ndarray:
        magic, width, base, extra = _HEADER.unpack_from(compressed)
        if magic != _MAGIC:
            raise ValueError("not a quantised payload")
        dtype = np.dtype(f"u{width}")
        start = _HEADER.size + extra
        indices = self._lossless(dtype).decode(compressed[start:])
        out = self.grid.values(indices.astype(np.int64) + base, self.spec.dtype)
        if extra:
            raw = self._decompressor.decompress(
                compressed[_HEADER.size : start],
                max_output_size=self.spec.size * (8 + self.spec.dtype.itemsize),
            )
            count = len(raw) // (8 + self.spec.dtype.itemsize)
            where = np.frombuffer(raw[: count * 8], np.uint64)
            out.reshape(-1)[where] = np.frombuffer(raw[count * 8 :], self.spec.dtype)
        return out


def family(backend: CodecConfiguration):
    """The quantized variant of the lossless configuration ``backend``."""

    def make(budget: Budget) -> CodecConfiguration:
        return near_lossless(
            f"quant-{backend.id}",
            f"quantize+{backend.codec}",
            backend.version,
            partial(Quantized, budget=budget, backend=backend.factory),
            budget,
            Family.QUANTIZED,
            supports=lambda spec: (
                supports(spec, budget)
                and backend.supports(ArraySpec(spec.shape, np.dtype(np.uint16)))
            ),
            grid="2k+1",
            **backend.parameters,
        )

    return make
