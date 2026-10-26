from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..contract import Budget, Mode
from ..spec import ArraySpec


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

    def __post_init__(self) -> None:
        if (self.mode is Mode.NEAR_LOSSLESS) != (self.budget is not None):
            raise ValueError(f"{self.id}: only near-lossless carries a budget")


def lossless(
    id: str, codec: str, version: str, factory, **parameters
) -> CodecConfiguration:
    supports = parameters.pop("supports", lambda spec: True)
    return CodecConfiguration(
        id, codec, version, Mode.LOSSLESS, parameters, factory, supports=supports
    )


def unpack(raw, spec: ArraySpec) -> np.ndarray:
    return np.frombuffer(raw, dtype=spec.dtype).reshape(spec.shape)


def as_bits(array: np.ndarray) -> np.ndarray:
    """Floating-point values as unsigned integers of the same width."""
    if array.dtype.kind == "f":
        return array.view(f"u{array.dtype.itemsize}")
    return array
