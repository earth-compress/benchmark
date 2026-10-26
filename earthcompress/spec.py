"""Description of the array a codec is configured for."""

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

    def steps(self, tau: float) -> int:
        """A budget in native units, as whole steps of the largest scale.

        Protocol section 3: budgets round down, which can only make them stricter.
        """
        return math.floor(tau / max(self.scale))

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
