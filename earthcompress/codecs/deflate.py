from __future__ import annotations

import zlib

import numpy as np

from ..spec import ArraySpec
from .base import lossless, unpack


class Deflate:
    def __init__(self, spec: ArraySpec):
        self.spec = spec

    def encode(self, array):
        return zlib.compress(np.ascontiguousarray(array), level=6, wbits=-15)

    def decode(self, data):
        return unpack(zlib.decompress(data, wbits=-15), self.spec)


CONFIGURATIONS = (
    lossless("deflate-c6", "deflate", zlib.ZLIB_RUNTIME_VERSION, Deflate, level=6),
)
