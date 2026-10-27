from __future__ import annotations

import imagecodecs
import numpy as np

from ..spec import ArraySpec
from .base import lossless

LEVEL = 8


class Pco:
    """Pcodec, a lossless codec for numerical sequences, on the flattened array."""

    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def encode(self, array):
        return bytes(
            imagecodecs.pcodec_encode(np.ascontiguousarray(array), level=LEVEL)
        )

    def decode(self, data):
        return imagecodecs.pcodec_decode(
            data, shape=self.spec.shape, dtype=self.spec.dtype
        )


VERSION = f"pcodec {imagecodecs.pcodec_version().split()[-1]} (imagecodecs {imagecodecs.__version__})"
CONFIGURATIONS = (lossless("pco", "pco", VERSION, Pco, level=LEVEL),)
