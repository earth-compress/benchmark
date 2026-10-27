from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

from ..contract import Budget, Mode
from ..spec import ArraySpec


class Family(StrEnum):
    """How a near-lossless configuration meets its bound."""

    NATIVE = "native"
    """The codec's own bounded mode, run as published."""
    QUANTIZED = "quantized"
    """The shared quantiser of this benchmark, then a lossless codec."""
    SAFEGUARDED = "safeguarded"
    """A native configuration wrapped in Compression Safeguards."""


class Codec(Protocol):
    def encode(self, array: np.ndarray) -> bytes: ...

    def decode(self, compressed: bytes) -> np.ndarray: ...


@dataclass(frozen=True)
class CodecConfiguration:
    id: str
    codec: str
    version: str
    mode: Mode
    parameters: Mapping[str, object]
    factory: Callable[[ArraySpec], Codec]
    budget: Budget | None = None
    supports: Callable[[ArraySpec], bool] = lambda spec: True
    family: Family | None = None

    def __post_init__(self) -> None:
        if (self.mode is Mode.NEAR_LOSSLESS) != (self.budget is not None):
            raise ValueError(f"{self.id}: only near-lossless carries a budget")
        if (self.mode is Mode.NEAR_LOSSLESS) != (self.family is not None):
            raise ValueError(f"{self.id}: only near-lossless belongs to a family")


def lossless(
    id: str, codec: str, version: str, factory, **parameters
) -> CodecConfiguration:
    supports = parameters.pop("supports", lambda spec: True)
    return CodecConfiguration(
        id, codec, version, Mode.LOSSLESS, parameters, factory, supports=supports
    )


def near_lossless(
    name: str,
    codec: str,
    version: str,
    factory,
    budget: Budget,
    family: Family,
    supports: Callable[[ArraySpec], bool] = lambda spec: True,
    **parameters,
) -> CodecConfiguration:
    """A configuration at ``budget``, named after its level or its tau."""
    suffix = budget.level if budget.level is not None else f"tau{budget.tau:g}"
    return CodecConfiguration(
        id=f"{name}-{suffix}",
        codec=codec,
        version=version,
        mode=Mode.NEAR_LOSSLESS,
        parameters=parameters,
        factory=factory,
        budget=budget,
        supports=supports,
        family=family,
    )


def unpack(raw, spec: ArraySpec) -> np.ndarray:
    return np.frombuffer(raw, dtype=spec.dtype).reshape(spec.shape)


def as_bits(array: np.ndarray) -> np.ndarray:
    """Floating-point values as unsigned integers of the same width."""
    if array.dtype.kind == "f":
        return array.view(f"u{array.dtype.itemsize}")
    return array
