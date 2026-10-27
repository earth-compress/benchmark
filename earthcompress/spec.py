from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class ArraySpec:
    """Shape, element type, sentinel, and scale of the arrays a codec instance sees."""

    shape: tuple[int, ...]
    dtype: np.dtype
    sentinel: float | None = None
    scale: tuple[float, ...] = field(default=(1.0,))
    """Value of one step of the stored integers, in the native unit, per plane.

    One value applies to the whole array; several apply to the planes of the
    first axis. Floating-point data have a scale of 1.
    """
    offset: tuple[float, ...] = field(default=(0.0,))
    """Native value of the stored zero, per plane like ``scale``."""

    def steps(self, tau: float) -> int:
        """A budget in native units, as whole steps of the largest scale."""
        return math.floor(tau / max(self.scale))

    def plane_steps(self, tau: float) -> tuple[int, ...]:
        """A budget in native units, as whole steps of the scale of each plane."""
        return tuple(math.floor(tau / scale) for scale in self.scale)

    def zero_codes(self) -> tuple[int | None, ...]:
        """The stored value of a native zero per plane, None where none is whole."""
        codes = []
        for scale, offset in zip(self.scale, self._offsets(), strict=True):
            code = -offset / scale
            codes.append(int(code) if code == int(code) else None)
        return tuple(codes)

    def _offsets(self) -> tuple[float, ...]:
        if len(self.offset) == len(self.scale):
            return self.offset
        if len(self.offset) == 1:
            return self.offset * len(self.scale)
        if len(self.scale) == 1:
            raise ValueError("per-plane offsets need per-plane scales")
        raise ValueError(f"{len(self.offset)} offsets for {len(self.scale)} scales")

    def plane_scale(self) -> np.ndarray:
        """The scale broadcastable against the array."""
        values = np.asarray(self.scale, dtype=np.float64)
        if values.size == 1:
            return values.reshape(())
        if not self.shape or values.size != self.shape[0]:
            raise ValueError(f"{values.size} scales for an array of shape {self.shape}")
        return values.reshape((-1,) + (1,) * (len(self.shape) - 1))

    @property
    def size(self) -> int:
        """Number of elements."""
        return math.prod(self.shape)

    @property
    def nbytes(self) -> int:
        """Uncompressed size in bytes. This is protocol `input_bytes`."""
        return self.size * self.dtype.itemsize

    @property
    def is_integer(self) -> bool:
        """Whether the element type is a signed or unsigned integer."""
        return np.issubdtype(self.dtype, np.integer)
