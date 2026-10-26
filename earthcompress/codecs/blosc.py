from __future__ import annotations

import numcodecs
import numcodecs.blosc
from numcodecs import Blosc

from ..spec import ArraySpec
from .base import lossless, unpack

numcodecs.blosc.use_threads = False
numcodecs.blosc.set_nthreads(1)


class BloscZstdBitshuffle:
    """The compressor of the EOPF Sentinel Zarr products."""

    def __init__(self, spec: ArraySpec):
        self.spec = spec
        self.codec = Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE)

    def encode(self, array):
        return bytes(self.codec.encode(array))

    def decode(self, data):
        return unpack(self.codec.decode(data), self.spec)


VERSION = (
    f"c-blosc {numcodecs.blosc.VERSION_STRING} (numcodecs {numcodecs.__version__})"
)
CONFIGURATIONS = (
    lossless(
        "blosc-zstd3-bitshuffle",
        "blosc",
        VERSION,
        BloscZstdBitshuffle,
        cname="zstd",
        clevel=3,
        shuffle="bitshuffle",
    ),
)
