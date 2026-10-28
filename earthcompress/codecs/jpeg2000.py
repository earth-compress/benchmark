from __future__ import annotations

import math
from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, lossless, lossy


class Jpeg2000:
    """Reversible 5/3 wavelet, bands as components."""

    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def _pixels(self, array):
        pixels = np.moveaxis(array, 0, -1) if array.ndim == 3 else array
        return np.ascontiguousarray(pixels)

    def encode(self, array):
        return imagecodecs.jpeg2k_encode(
            self._pixels(array), level=0, reversible=True, numthreads=1
        )

    def decode(self, data):
        pixels = imagecodecs.jpeg2k_decode(data, numthreads=1)
        array = np.moveaxis(pixels, -1, 0) if len(self.spec.shape) == 3 else pixels
        return np.ascontiguousarray(array, dtype=self.spec.dtype)


class Jpeg2000Psnr(Jpeg2000):
    """Irreversible 9/7 wavelet, bands as components with no colour transform.

    OpenJPEG takes a target PSNR over every component together, against the
    largest value of the sample type. The target is the one whose mean squared
    error is tau squared.
    """

    def __init__(self, spec: ArraySpec, budget: Budget):
        super().__init__(spec)
        peak = 2 ** (8 * spec.dtype.itemsize) - 1
        self.psnr = 20.0 * math.log10(peak / code_bound(spec, budget))

    def encode(self, array):
        return imagecodecs.jpeg2k_encode(
            self._pixels(array),
            level=self.psnr,
            reversible=False,
            mct=False,
            numthreads=1,
        )


def integers(spec: ArraySpec) -> bool:
    return spec.is_integer and spec.dtype.itemsize <= 2


VERSION = f"imagecodecs {imagecodecs.__version__} ({imagecodecs.jpeg2k_version()})"
REFERENCE = (
    lossless(
        "jpeg2000", "jpeg2000", VERSION, Jpeg2000, wavelet="5/3", supports=integers
    ),
)


def psnr(budget: Budget):
    return lossy(
        "jpeg2000-psnr",
        "jpeg2000",
        VERSION,
        partial(Jpeg2000Psnr, budget=budget),
        budget,
        Family.NATIVE,
        supports=integers,
        wavelet="9/7",
        quality="psnr",
    )


LOSSY = (psnr,)
