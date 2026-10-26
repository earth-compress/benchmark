from __future__ import annotations

import imagecodecs
import numpy as np

from ..spec import ArraySpec
from .base import lossless


class Jpeg2000:
    """Reversible 5/3 wavelet, bands as components."""

    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def encode(self, array):
        pixels = np.moveaxis(array, 0, -1) if array.ndim == 3 else array
        return imagecodecs.jpeg2k_encode(
            np.ascontiguousarray(pixels), level=0, reversible=True, numthreads=1
        )

    def decode(self, data):
        pixels = imagecodecs.jpeg2k_decode(data, numthreads=1)
        array = np.moveaxis(pixels, -1, 0) if len(self.spec.shape) == 3 else pixels
        return np.ascontiguousarray(array, dtype=self.spec.dtype)


def integers(spec: ArraySpec) -> bool:
    return spec.is_integer and spec.dtype.itemsize <= 2


VERSION = (
    f"imagecodecs {imagecodecs.__version__} (OpenJPEG {imagecodecs.jpeg2k_version()})"
)
REFERENCE = (
    lossless(
        "jpeg2000", "jpeg2000", VERSION, Jpeg2000, wavelet="5/3", supports=integers
    ),
)
