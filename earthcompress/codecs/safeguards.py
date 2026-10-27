"""Native configurations wrapped in Compression Safeguards (Tyree et al. 2026).

While encoding, the safeguards decode the wrapped codec's output, compare it
with the input, and store the corrections that make every element keep the
promises of near-lossless mode: the bound, the sentinel, and exact zeros.
Decoding applies the corrections. The wrapped codec runs unchanged, so the
difference from its native row is the cost of making it safe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from importlib.metadata import version

import numcodecs.abc
import numpy as np
from numcodecs_safeguards import SafeguardedCodec

from ..contract import Budget
from ..spec import ArraySpec
from .base import Codec, CodecConfiguration, Family, code_bound, near_lossless

VERSION = (
    f"compression-safeguards {version('compression-safeguards')}"
    f" (numcodecs-safeguards {version('numcodecs-safeguards')})"
)


class _Wrapped(numcodecs.abc.Codec):
    """A benchmark codec seen through the numcodecs interface the safeguards use."""

    codec_id = "earthcompress-wrapped"

    def __init__(self, codec: Codec, spec: ArraySpec):
        self._codec = codec
        self._spec = spec

    def encode(self, buf):
        array = np.asarray(buf).reshape(self._spec.shape)
        return self._codec.encode(array.astype(self._spec.dtype, copy=False))

    def decode(self, buf, out=None):
        decoded = self._codec.decode(bytes(buf))
        if out is None:
            return decoded
        out[...] = decoded.reshape(np.shape(out))
        return out

    def get_config(self):
        return {"id": self.codec_id}


def rules(spec: ArraySpec, budget: Budget) -> list[dict]:
    """The promises of near-lossless mode, as safeguards."""
    bound = code_bound(spec, budget)
    found: list[dict] = [
        dict(kind="eb", type="abs", eb=int(bound) if spec.is_integer else bound)
    ]
    if spec.sentinel is not None:
        sentinel = int(spec.sentinel) if spec.is_integer else spec.sentinel
        found.append(dict(kind="same", value=sentinel, exclusive=True))
    zeros = set(spec.zero_codes())
    if len(zeros) == 1 and None not in zeros:
        (zero,) = zeros
        if spec.sentinel is None or zero != spec.sentinel:
            found.append(dict(kind="same", value=zero))
    return found


class Safeguarded:
    def __init__(
        self,
        spec: ArraySpec,
        budget: Budget,
        inner: Callable[[ArraySpec], Codec] | None,
    ):
        self.spec = spec
        codec = dict(id="zero") if inner is None else _Wrapped(inner(spec), spec)
        self.codec = SafeguardedCodec(codec=codec, safeguards=rules(spec, budget))

    def encode(self, array):
        return bytes(self.codec.encode(np.ascontiguousarray(array)))

    def decode(self, data):
        decoded = np.asarray(self.codec.decode(data))
        return np.ascontiguousarray(decoded, dtype=self.spec.dtype).reshape(
            self.spec.shape
        )


def family(native: Callable[[Budget], CodecConfiguration]):
    """The safeguarded variant of a native configuration."""

    def make(budget: Budget) -> CodecConfiguration:
        inner = native(budget)
        return replace(
            inner,
            id=f"sg-{inner.id}",
            codec=f"safeguards+{inner.codec}",
            version=f"{inner.version}; {VERSION}",
            parameters={**inner.parameters, "safeguards": "bound, sentinel, zero"},
            factory=partial(Safeguarded, budget=budget, inner=inner.factory),
            family=Family.SAFEGUARDED,
        )

    return make


def zero(budget: Budget) -> CodecConfiguration:
    """Only the safeguards: a codec that decodes to zeros, every value corrected."""
    return near_lossless(
        "sg-zero",
        "safeguards",
        VERSION,
        partial(Safeguarded, budget=budget, inner=None),
        budget,
        Family.SAFEGUARDED,
        supports=lambda spec: spec.dtype.kind in "iuf" and spec.dtype.itemsize <= 8,
        safeguards="bound, sentinel, zero",
    )
