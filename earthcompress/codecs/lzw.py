from __future__ import annotations

import imagecodecs
import numpy as np

from ..spec import ArraySpec
from .base import lossless, unpack


class Lzw:
    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def encode(self, array):
        return imagecodecs.lzw_encode(np.ascontiguousarray(array).tobytes())

    def decode(self, data):
        return unpack(imagecodecs.lzw_decode(data), self.spec)


CONFIGURATIONS = (
    lossless("lzw", "lzw", f"imagecodecs {imagecodecs.__version__}", Lzw),
)
