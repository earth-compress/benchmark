from __future__ import annotations

from functools import partial
from importlib.metadata import version

import geozl
import numpy as np

from ..spec import ArraySpec
from .base import lossless


class GeoZL:
    def __init__(self, spec: ArraySpec, recipe: str):
        self.spec = spec
        # One-byte elements have nothing to transpose.
        if spec.dtype.itemsize == 1:
            recipe = recipe.replace(">transpose", "")
        self.graph = geozl.graph(np.zeros(spec.shape, spec.dtype), recipe)

    def encode(self, array):
        return geozl.compress(array, graph=self.graph)

    def decode(self, data):
        return (
            geozl.decompress(data, verify=False)
            .view(self.spec.dtype)
            .reshape(self.spec.shape)
        )


RECIPES = {
    "geozl-planar-pfor": "planar>zigzag>pfor",
    "geozl-planar-pivco": "planar>zigzag>transpose>pivco",
    "geozl-med-pivco": "med>zigzag>transpose>pivco",
    "geozl-planar-entropy": "planar>zigzag>transpose>entropy",
    "geozl-med-entropy": "med>zigzag>transpose>entropy",
    "geozl-average-entropy": "average>zigzag>transpose>entropy",
    "geozl-id-pfor": "id>pfor",
}


def rasters(spec: ArraySpec) -> bool:
    """GeoZL predicts along rows, so it needs at least two axes."""
    return len(spec.shape) >= 2


VERSION = f"geozl {geozl.__version__} (openzl {version('openzl')})"
CONFIGURATIONS = tuple(
    lossless(
        name,
        "geozl",
        VERSION,
        partial(GeoZL, recipe=recipe),
        graph=recipe,
        supports=rasters,
    )
    for name, recipe in RECIPES.items()
)
