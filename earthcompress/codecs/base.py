"""The codec contract. Protocol sections 2 and 5."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..contract import Budget, Mode
from ..spec import ArraySpec


class Codec(Protocol):
    """A single-array codec, configured for one shape and element type."""

    def encode(self, array: np.ndarray) -> bytes: ...

    def decode(self, compressed: bytes) -> np.ndarray: ...


def _supports_every_array(spec: ArraySpec) -> bool:
    return True


@dataclass(frozen=True)
class CodecConfiguration:
    """One measurable operating point of one codec.

    The mode is declared, not inferred. A near-lossless configuration carries a
    budget; the other two modes carry none, because neither has anything to
    declare one about.
    """

    id: str
    codec: str
    version: str
    mode: Mode
    parameters: Mapping[str, object]
    factory: Callable[[ArraySpec], Codec]
    budget: Budget | None = None
    supports: Callable[[ArraySpec], bool] = _supports_every_array

    def __post_init__(self) -> None:
        if self.mode is Mode.NEAR_LOSSLESS and self.budget is None:
            raise ValueError(f"{self.id}: a near-lossless configuration needs a budget")
        if self.mode is not Mode.NEAR_LOSSLESS and self.budget is not None:
            raise ValueError(
                f"{self.id}: only a near-lossless configuration has a budget"
            )
