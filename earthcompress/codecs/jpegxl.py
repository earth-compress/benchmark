"""JPEG XL, which takes a perceptual distance rather than an error target.

The lossy configuration searches the distance on each sample. It keeps the
largest distance whose root-mean-square error, over the whole sample in stored
units, is within tau, and falls back to lossless JPEG XL when none is. Every
trial is part of the encode, so the encode time includes the search.
"""

from __future__ import annotations

import math
from functools import partial

import imagecodecs
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, code_rms, lossy, pack_frames, unpack_frames

EFFORT = 7
"""The libjxl default."""
FARTHEST = 25.0
"""The largest distance libjxl accepts."""
NEAREST = 0.01
TRIALS = 8
"""Halvings of the logarithmic interval between the two distances."""


class JpegXl:
    """One grayscale JPEG XL frame per plane, the distance searched per sample."""

    def __init__(self, spec: ArraySpec, budget: Budget):
        self.spec = spec
        self.bound = code_bound(spec, budget)

    def _planes(self, array):
        return array.reshape((-1,) + array.shape[-2:])

    def _frames(self, planes, distance: float | None) -> list[bytes]:
        settings = dict(lossless=True) if distance is None else dict(distance=distance)
        return [
            bytes(
                imagecodecs.jpegxl_encode(
                    np.ascontiguousarray(plane), effort=EFFORT, numthreads=1, **settings
                )
            )
            for plane in planes
        ]

    def _within(self, array, frames) -> bool:
        return code_rms(array, self._decoded(frames)) <= self.bound

    def encode(self, array):
        planes = self._planes(array)
        frames = self._frames(planes, FARTHEST)
        if self._within(array, frames):
            return pack_frames(frames)
        best = None
        low, high = math.log(NEAREST), math.log(FARTHEST)
        for _ in range(TRIALS):
            middle = (low + high) / 2.0
            frames = self._frames(planes, math.exp(middle))
            if self._within(array, frames):
                best, low = frames, middle
            else:
                high = middle
        if best is None:
            frames = self._frames(planes, NEAREST)
            best = frames if self._within(array, frames) else self._frames(planes, None)
        return pack_frames(best)

    def _decoded(self, frames) -> np.ndarray:
        planes = [imagecodecs.jpegxl_decode(frame, numthreads=1) for frame in frames]
        return np.ascontiguousarray(np.stack(planes), dtype=self.spec.dtype).reshape(
            self.spec.shape
        )

    def decode(self, data):
        return self._decoded(unpack_frames(data))


def supports(spec: ArraySpec) -> bool:
    return spec.dtype in (np.dtype(np.uint8), np.dtype(np.uint16)) and len(
        spec.shape
    ) in (2, 3)


VERSION = f"{imagecodecs.jpegxl_version()} (imagecodecs {imagecodecs.__version__})"


def distance(budget: Budget):
    return lossy(
        "jpegxl-distance",
        "jpegxl",
        VERSION,
        partial(JpegXl, budget=budget),
        budget,
        Family.SEARCHED,
        supports=supports,
        effort=EFFORT,
        distance="searched",
    )


LOSSY = (distance,)
