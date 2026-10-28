"""Error-bounded compressors for floating-point scientific data.

SZ3, ZFP and SPERR take floats only. Integer samples are passed as floats that
hold every code exactly, and the output is rounded back to the stored type.

SZ3 and SPERR also hold a root-mean-square error, which the lossy
configurations use.
"""

from __future__ import annotations

import math
from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, lossy, near_lossless, to_stored, working_float


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


class Sz3L2(Sz3):
    """SZ3 in its L2-norm mode.

    SZ3 runs that mode as an absolute bound of ``sqrt(3 / n)`` times the norm,
    which for a root-mean-square error of tau is ``sqrt(3) tau``. imagecodecs
    exposes only the absolute mode, so the bound is passed to it that way.
    """

    def __init__(self, spec: ArraySpec, budget: Budget):
        super().__init__(spec, budget)
        self.bound = math.sqrt(3.0) * self.bound


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


class SperrPsnr(_Bounded):
    """SPERR in its PSNR mode, the target set so the root-mean-square error is tau.

    SPERR measures PSNR over the range of the data it receives. A sample whose
    range is within tau meets the bound with any target, and SPERR rejects a
    target of zero, so it gets a small positive one.
    """

    def encode(self, array):
        values = self._floats(array)
        span = float(values.max() - values.min()) if values.size else 0.0
        psnr = 20.0 * math.log10(span / self.bound) if span > self.bound else 1e-3
        return bytes(imagecodecs.sperr_encode(values, psnr, "psnr", numthreads=1))

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


def _family(name, codec, factory, dims, build=near_lossless, **parameters):
    def make(budget: Budget):
        return build(
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

LOSSY = (
    _family("sz3-l2norm", "sz3", Sz3L2, (1, 2, 3, 4), build=lossy, mode="l2norm"),
    _family("sperr-psnr", "sperr", SperrPsnr, (2, 3), build=lossy, mode="psnr"),
)
