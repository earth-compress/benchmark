"""The quantiser shared by every configuration of the quantized family.

It rounds each value to a grid that keeps the budget, then hands the grid
indices to an unchanged lossless codec. Every lossless codec therefore sees
the same indices, so the quantized rows differ only by their lossless stage.

In lossy mode the grid starts as wide as a uniform rounding error allows
within a root-mean-square error of tau, the rule SZ3 applies in its L2-norm
mode, and narrows until the error of the sample is within tau. The width it
settles on is stored with the data.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from functools import partial

import numpy as np
import zstandard

from ..contract import Budget
from ..metrics import identical
from ..spec import ArraySpec
from .base import Codec, CodecConfiguration, Family, lossy, near_lossless

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

LOSSY_BACKENDS = ("pco",)
"""Lossless configurations behind the lossy quantiser. ClimateBenchPress found
rounding followed by PCO a reliable baseline."""

_MAGIC = b"ECQ2"
_HEADER = struct.Struct("<4sBqQ")  # magic, index width, index base, exception bytes
_REACH = struct.Struct("<d")  # lossy only, the tau the grid was built for
_NARROWINGS = 64
_UNSIGNED = tuple(np.dtype(f"u{width}") for width in (1, 2, 4, 8))


def _narrowest(largest: int) -> np.dtype:
    for dtype in _UNSIGNED:
        if largest <= np.iinfo(dtype).max:
            return dtype
    raise ValueError("grid indices do not fit 64 bits")


def _planes(array: np.ndarray, count: int):
    """The array as ``count`` planes along its first axis, or as one plane."""
    return (array,) if count == 1 else tuple(array[i] for i in range(count))


def rms_steps(spec: ArraySpec, tau: float) -> tuple[int, ...]:
    """The widest ``k`` per plane whose rounding error, uniform over ``2k + 1``
    codes, has a root-mean-square of at most tau, ``k (k + 1) / 3 <= (tau / scale)²``.
    """
    steps = []
    for scale in spec.scale:
        limit = 3.0 * (tau / scale) ** 2
        k = math.floor((math.sqrt(1.0 + 4.0 * limit) - 1.0) / 2.0)
        while k > 0 and k * (k + 1) > limit:
            k -= 1
        while (k + 1) * (k + 2) <= limit:
            k += 1
        steps.append(k)
    return tuple(steps)


class IntegerGrid:
    """Codes rounded to a grid of ``2k + 1`` codes, ``k`` the budget of the plane.

    A plane whose budget is below one step keeps its codes. A native zero sits
    on the grid, so it decodes exactly. A sentinel at the bottom of the type
    keeps index 0 to itself, and valid codes decode at or above the next code.
    """

    def __init__(self, spec: ArraySpec, steps: tuple[int, ...]):
        self.limits = np.iinfo(spec.dtype)
        self.sentinel = None if spec.sentinel is None else int(spec.sentinel)
        self.steps = steps
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
    """Values rounded to multiples of ``2 bound``, so zero stays exact.

    Rounding in the element type can move a value just past ``bound``; such
    values, and values that are not finite, are kept exactly beside the grid.
    """

    def __init__(self, spec: ArraySpec, bound: float):
        self.bound = bound
        self.step = 2.0 * bound

    def indices(self, array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = array.astype(np.float64)
        with np.errstate(invalid="ignore", over="ignore"):
            scaled = np.rint(values / self.step)
            fits = np.isfinite(scaled) & (np.abs(scaled) < 2.0**52)
            indices = np.where(fits, scaled, 0.0).astype(np.int64)
            restored = (indices * self.step).astype(array.dtype).astype(np.float64)
            kept = ~fits | ~(np.abs(restored - values) <= self.bound)
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
        self,
        spec: ArraySpec,
        budget: Budget,
        backend: Callable[[ArraySpec], Codec],
        rms: bool = False,
    ):
        if not supports(spec, budget):
            raise ValueError("unsupported array for the shared quantiser")
        self.spec = spec
        self.tau = budget.tau
        self.rms = rms
        self.grid = self._grid(budget.tau)
        self.backend = backend
        self._backends: dict[np.dtype, Codec] = {}
        self._compressor = zstandard.ZstdCompressor(level=3, write_checksum=False)
        self._decompressor = zstandard.ZstdDecompressor()

    def _lossless(self, dtype: np.dtype) -> Codec:
        if dtype not in self._backends:
            self._backends[dtype] = self.backend(ArraySpec(self.spec.shape, dtype))
        return self._backends[dtype]

    def _grid(self, reach: float) -> IntegerGrid | FloatGrid:
        """The grid for a budget of ``reach``, on every element or, in lossy mode,
        as a root-mean-square under a uniform rounding error."""
        if self.spec.is_integer:
            steps = (
                rms_steps(self.spec, reach)
                if self.rms
                else self.spec.plane_steps(reach)
            )
            return IntegerGrid(self.spec, steps)
        return FloatGrid(self.spec, math.sqrt(3.0) * reach if self.rms else reach)

    @staticmethod
    def _quantised(grid, array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Grid indices, and the positions kept exactly beside the grid."""
        if isinstance(grid, FloatGrid):
            return grid.indices(array)
        return grid.indices(array), np.empty(0, np.int64)

    def _error_rms(self, array: np.ndarray, approx: np.ndarray) -> float:
        """The root-mean-square error of the valid elements, in native units."""
        error = approx.astype(np.float64) - array.astype(np.float64)
        error[identical(array, approx)] = 0.0
        scale = np.asarray(self.spec.scale, dtype=np.float64)
        error *= (
            scale[0]
            if scale.size == 1
            else scale.reshape((-1,) + (1,) * (array.ndim - 1))
        )
        if self.spec.sentinel is not None:
            error = error[array != self.spec.sentinel]
        return float(np.sqrt(np.mean(np.square(error)))) if error.size else 0.0

    def _widest(self, array: np.ndarray):
        """The widest grid, from the uniform rule down, that keeps tau on ``array``."""
        reach = self.tau
        for _ in range(_NARROWINGS):
            grid = self._grid(reach)
            indices, kept = self._quantised(grid, array)
            approx = grid.values(indices, self.spec.dtype)
            approx.reshape(-1)[kept] = np.ascontiguousarray(array).reshape(-1)[kept]
            error = self._error_rms(array, approx)
            if error <= self.tau:
                return reach, grid, indices, kept
            reach *= 0.999 * self.tau / error
        raise RuntimeError("no grid keeps the root-mean-square error within tau")

    def encode(self, array: np.ndarray) -> bytes:
        if array.shape != self.spec.shape or array.dtype != self.spec.dtype:
            raise ValueError("array does not match the codec configuration")
        if self.rms:
            reach, _, indices, kept = self._widest(array)
            stated = _REACH.pack(reach)
        else:
            indices, kept = self._quantised(self.grid, array)
            stated = b""
        exceptions = b""
        if kept.size:
            exceptions = self._compressor.compress(
                kept.astype(np.uint64).tobytes()
                + np.ascontiguousarray(array).reshape(-1)[kept].tobytes()
            )
        base = int(indices.min())
        dtype = _narrowest(int(indices.max()) - base)
        payload = self._lossless(dtype).encode(
            np.ascontiguousarray(indices - base, dtype=dtype)
        )
        header = _HEADER.pack(_MAGIC, dtype.itemsize, base, len(exceptions))
        return header + stated + exceptions + payload

    def decode(self, compressed: bytes) -> np.ndarray:
        magic, width, base, extra = _HEADER.unpack_from(compressed)
        if magic != _MAGIC:
            raise ValueError("not a quantised payload")
        offset = _HEADER.size
        grid = self.grid
        if self.rms:
            (reach,) = _REACH.unpack_from(compressed, offset)
            offset += _REACH.size
            grid = self._grid(reach)
        dtype = np.dtype(f"u{width}")
        start = offset + extra
        indices = self._lossless(dtype).decode(compressed[start:])
        out = grid.values(indices.astype(np.int64) + base, self.spec.dtype)
        if extra:
            raw = self._decompressor.decompress(
                compressed[offset:start],
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


def rms_family(backend: CodecConfiguration):
    """The lossy quantised variant of the lossless configuration ``backend``."""

    def make(budget: Budget) -> CodecConfiguration:
        return lossy(
            f"quant-{backend.id}-rms",
            f"quantize+{backend.codec}",
            backend.version,
            partial(Quantized, budget=budget, backend=backend.factory, rms=True),
            budget,
            Family.QUANTIZED,
            supports=lambda spec: (
                supports(spec, budget)
                and backend.supports(ArraySpec(spec.shape, np.dtype(np.uint16)))
            ),
            grid="2k+1, widest with rms <= tau on the sample",
            **backend.parameters,
        )

    return make
