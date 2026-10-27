from __future__ import annotations

from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, near_lossless

# For integers LERC floors the bound, and reads 777 as a request for another mode.
_RESERVED = 777.0


class Lerc:
    """LERC with ``maxZError`` as the bound, as GDAL writes it, and the sentinel as its mask."""

    def __init__(self, spec: ArraySpec, budget: Budget):
        self.spec = spec
        bound = code_bound(spec, budget)
        self.level = bound + 0.5 if spec.is_integer and bound == _RESERVED else bound
        self.planar = len(spec.shape) == 3

    def encode(self, array):
        masks = None if self.spec.sentinel is None else array != self.spec.sentinel
        return bytes(
            imagecodecs.lerc_encode(
                np.ascontiguousarray(array),
                level=self.level,
                masks=masks,
                planar=self.planar or None,
            )
        )

    def decode(self, data):
        if self.spec.sentinel is None:
            values = imagecodecs.lerc_decode(data)
        else:
            values, valid = imagecodecs.lerc_decode(data, masks=True)
            values = np.array(values)
            # LERC stores no mask when every pixel is valid, and one mask
            # stands for every band when the bands share it.
            if valid is not None:
                values[~np.broadcast_to(valid, values.shape)] = self.spec.sentinel
        return np.ascontiguousarray(values, dtype=self.spec.dtype).reshape(
            self.spec.shape
        )


def supports(spec: ArraySpec) -> bool:
    return len(spec.shape) in (2, 3) and spec.dtype.itemsize <= 8


VERSION = f"lerc {imagecodecs.lerc_version().split()[-1]} (imagecodecs {imagecodecs.__version__})"


def family(budget: Budget):
    return near_lossless(
        "lerc",
        "lerc",
        VERSION,
        partial(Lerc, budget=budget),
        budget,
        Family.NATIVE,
        supports=supports,
        maxZError="tau",
        mask="sentinel",
    )


FAMILIES = (family,)
