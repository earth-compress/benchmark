from __future__ import annotations

from importlib.metadata import version

import numpy as np
import openzl.ext as zl

from ..spec import ArraySpec
from .base import lossless

DISABLE = 2  # ZL_TernaryParam_disable
N = zl.nodes


def generic(c):
    return c.get_graph("zl.compress_generic")


def delta_field_lz(c):
    return N.DeltaInt()(c, c.get_graph("zl.field_lz"))


def delta_pivco(c):
    pivco = N.TransposeSplit()(c, c.get_graph("zl.huffman_pivco"))
    return N.DeltaInt()(c, N.Zigzag()(c, N.ConvertNumToStructLE()(c, pivco)))


class OpenZL:
    graph = staticmethod(generic)
    level = 6

    def __init__(self, spec: ArraySpec):
        self.spec = spec
        self.compressor = zl.Compressor()
        self.compressor.set_parameter(zl.CParam.CompressionLevel, self.level)
        self.compressor.select_starting_graph(self.graph(self.compressor))

    def encode(self, array):
        cctx = zl.CCtx()
        cctx.ref_compressor(self.compressor)
        cctx.set_parameter(zl.CParam.FormatVersion, zl.MAX_FORMAT_VERSION)
        cctx.set_parameter(zl.CParam.ContentChecksum, DISABLE)
        cctx.set_parameter(zl.CParam.CompressedChecksum, DISABLE)
        flat = np.ascontiguousarray(array).reshape(-1)
        return bytes(cctx.compress([zl.Input(zl.Type.Numeric, flat)]))

    def decode(self, data):
        out = zl.DCtx().decompress(data)[0].content.as_nparray()
        return out.view(self.spec.dtype).reshape(self.spec.shape)


class Generic(OpenZL):
    level = 7


class DeltaFieldLz(OpenZL):
    graph = staticmethod(delta_field_lz)


class DeltaPivco(OpenZL):
    graph = staticmethod(delta_pivco)


VERSION = version("openzl")
CONFIGURATIONS = (
    lossless(
        "openzl-generic", "openzl", VERSION, Generic, graph="compress_generic", level=7
    ),
    lossless(
        "openzl-delta-fieldlz", "openzl", VERSION, DeltaFieldLz, graph="delta>field_lz"
    ),
    lossless(
        "openzl-delta-pivco",
        "openzl",
        VERSION,
        DeltaPivco,
        graph="delta>zigzag>transpose>huffman_pivco",
    ),
)
