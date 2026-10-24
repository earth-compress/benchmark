"""Description of the array a codec is configured for."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ArraySpec:
    """Shape, element type and sentinel of the arrays a codec instance sees."""

    shape: tuple[int, ...]
    dtype: np.dtype
    sentinel: float | None = None
    grid: float = 1.0
    """Quantisation step of the published data, in the native unit.

    A budget is declared in native units and the array is stored in grid steps,
    so a codec converts between them with this.
    """

    def steps(self, tau: float) -> float:
        """A budget in native units, expressed in grid steps."""
        return tau / self.grid

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
