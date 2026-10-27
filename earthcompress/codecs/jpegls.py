from __future__ import annotations

import struct
from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, near_lossless

_COUNT = struct.Struct("<I")


def _largest_near(dtype: np.dtype) -> int:
    """CharLS accepts NEAR up to min(255, MAXVAL / 2)."""
    return min(255, (2 ** (8 * dtype.itemsize) - 1) // 2)


class JpegLs:
    """JPEG-LS near-lossless, ``NEAR`` the bound, one stream per plane."""

    def __init__(self, spec: ArraySpec, budget: Budget):
        self.spec = spec
        self.near = int(code_bound(spec, budget))

    def _planes(self, array):
        return array if array.ndim == 3 else array[np.newaxis]

    def encode(self, array):
        streams = [
            bytes(
                imagecodecs.jpegls_encode(np.ascontiguousarray(plane), level=self.near)
            )
            for plane in self._planes(array)
        ]
        header = _COUNT.pack(len(streams)) + b"".join(
            _COUNT.pack(len(stream)) for stream in streams
        )
        return header + b"".join(streams)

    def decode(self, data):
        (count,) = _COUNT.unpack_from(data)
        sizes = [
            _COUNT.unpack_from(data, _COUNT.size * (1 + i))[0] for i in range(count)
        ]
        start = _COUNT.size * (1 + count)
        planes = []
        for size in sizes:
            planes.append(imagecodecs.jpegls_decode(data[start : start + size]))
            start += size
        return np.ascontiguousarray(np.stack(planes), dtype=self.spec.dtype).reshape(
            self.spec.shape
        )


def supports(spec: ArraySpec, budget: Budget) -> bool:
    if spec.dtype not in (np.dtype(np.uint8), np.dtype(np.uint16)):
        return False
    if len(spec.shape) not in (2, 3):
        return False
    return 1 <= code_bound(spec, budget) <= _largest_near(spec.dtype)


VERSION = f"{imagecodecs.jpegls_version()} (imagecodecs {imagecodecs.__version__})"


def family(budget: Budget):
    return near_lossless(
        "jpegls-near",
        "jpegls",
        VERSION,
        partial(JpegLs, budget=budget),
        budget,
        Family.NATIVE,
        supports=partial(supports, budget=budget),
        NEAR="tau",
    )


FAMILIES = (family,)
