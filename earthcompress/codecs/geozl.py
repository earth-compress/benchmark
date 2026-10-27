from __future__ import annotations

from functools import partial
from importlib.metadata import version

import geozl
import numpy as np

from ..contract import Budget
from ..spec import ArraySpec
from .base import Family, code_bound, lossless, near_lossless


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


class GeoZLLinear:
    """GeoZL with its LINEAR quantiser, the bound as its error and the sentinel as NoData.

    The lossy domain comes from the raster a graph is built from, so the graph
    is built from each sample when it is encoded. Frames decode on their own.
    """

    def __init__(self, spec: ArraySpec, budget: Budget, recipe: str):
        self.spec = spec
        self.error = code_bound(spec, budget)
        self.recipe = (
            recipe.replace(">transpose", "") if spec.dtype.itemsize == 1 else recipe
        )

    def encode(self, array):
        graph = geozl.graph(
            array, self.recipe, error=self.error, nodata=self.spec.sentinel
        )
        return geozl.compress(array, graph=graph)

    def decode(self, data):
        return (
            geozl.decompress(data, verify=False)
            .view(self.spec.dtype)
            .reshape(self.spec.shape)
        )


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


NEAR_RECIPE = "geozl-med-entropy"
"""The recipe of the best lossless ratio on the corpora with a budget."""


def linear(budget: Budget):
    recipe = RECIPES[NEAR_RECIPE]
    return near_lossless(
        f"{NEAR_RECIPE}-linear",
        "geozl",
        VERSION,
        partial(GeoZLLinear, budget=budget, recipe=recipe),
        budget,
        Family.NATIVE,
        supports=rasters,
        graph=recipe,
        quantizer="LINEAR",
        nodata="sentinel",
    )


FAMILIES = (linear,)
