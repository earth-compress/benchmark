"""Error-bounded compressors for floating-point scientific data.

SZ3, ZFP and SPERR take floats only. Integer samples are passed as floats that
hold every code exactly, and the output is rounded back to the stored type.
"""

from __future__ import annotations

from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, near_lossless, to_stored, working_float


class _Bounded:
    def __init__(self, spec: ArraySpec, budget: Budget):
        self.spec = spec
        self.bound = code_bound(spec, budget)
        self.work = working_float(spec.dtype)

    def _floats(self, array):
        return np.ascontiguousarray(array, dtype=self.work)


class Sz3(_Bounded):
    """SZ3 with an absolute bound."""

    def encode(self, array):
        return bytes(
            imagecodecs.sz3_encode(self._floats(array), mode="abs", abs=self.bound)
        )

    def decode(self, data):
        return to_stored(
            imagecodecs.sz3_decode(data, self.spec.shape, self.work), self.spec
        )


class Zfp(_Bounded):
    """ZFP in fixed-accuracy mode, the tolerance as the bound."""

    def encode(self, array):
        return bytes(
            imagecodecs.zfp_encode(
                self._floats(array), level=self.bound, mode="accuracy", numthreads=1
            )
        )

    def decode(self, data):
        return to_stored(imagecodecs.zfp_decode(data, numthreads=1), self.spec)


class Sperr(_Bounded):
    """SPERR in point-wise error mode."""

    def encode(self, array):
        return bytes(
            imagecodecs.sperr_encode(
                self._floats(array), self.bound, "pwe", numthreads=1
            )
        )

    def decode(self, data):
        return to_stored(imagecodecs.sperr_decode(data, numthreads=1), self.spec)


def _numeric(spec: ArraySpec, dims: tuple[int, ...]) -> bool:
    return (
        len(spec.shape) in dims
        and spec.dtype.kind in "iuf"
        and spec.dtype.itemsize <= 8
    )


def _version(name: str) -> str:
    return f"{getattr(imagecodecs, f'{name}_version')()} (imagecodecs {imagecodecs.__version__})"


def _family(name, codec, factory, dims, **parameters):
    def make(budget: Budget):
        return near_lossless(
            name,
            codec,
            _version(codec),
            partial(factory, budget=budget),
            budget,
            Family.NATIVE,
            supports=partial(_numeric, dims=dims),
            **parameters,
        )

    return make


FAMILIES = (
    _family("sz3-abs", "sz3", Sz3, (1, 2, 3, 4), mode="abs"),
    _family("zfp-accuracy", "zfp", Zfp, (1, 2, 3, 4), mode="fixed-accuracy"),
    _family("sperr-pwe", "sperr", Sperr, (2, 3), mode="pwe"),
)
