from __future__ import annotations

from importlib.metadata import version

import geozl
import numpy as np

from ..spec import ArraySpec
from .base import lossless


class GeoZL:
    recipe = "planar>zigzag>pfor"

    def __init__(self, spec: ArraySpec):
        self.spec = spec
        self.graph = geozl.graph(np.zeros(spec.shape, spec.dtype), self.method())

    def method(self):
        return self.recipe

    def encode(self, array):
        return geozl.compress(array, graph=self.graph)

    def decode(self, data):
        return (
            geozl.decompress(data, verify=False)
            .view(self.spec.dtype)
            .reshape(self.spec.shape)
        )


class PlanarPivco(GeoZL):
    recipe = "planar>zigzag>transpose>pivco"

    def method(self):
        # One-byte elements have nothing to transpose.
        return "planar>zigzag>pivco" if self.spec.dtype.itemsize == 1 else self.recipe


VERSION = f"geozl {geozl.__version__} (openzl {version('openzl')})"
CONFIGURATIONS = (
    lossless("geozl-planar-pfor", "geozl", VERSION, GeoZL, graph=GeoZL.recipe),
    lossless(
        "geozl-planar-pivco", "geozl", VERSION, PlanarPivco, graph=PlanarPivco.recipe
    ),
)
