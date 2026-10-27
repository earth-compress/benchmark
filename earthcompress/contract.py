from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """How faithfully a configuration claims to reproduce its input."""

    LOSSLESS = "lossless"
    NEAR_LOSSLESS = "near-lossless"
    LOSSY = "lossy"


class Level(StrEnum):
    """Which budget level of `TOLERANCE.md` this is."""

    CONSERVATIVE = "conservative"
    MATCHED = "matched"
    AGGRESSIVE = "aggressive"
    RECOMMENDED = "recommended"
    """A bound recommended by domain experts, where one exists."""


class Promise(StrEnum):
    """A commitment the benchmark verifies on every sample."""

    STRUCTURE = "structure"
    DETERMINISM = "determinism"
    EXACTNESS = "exactness"
    BOUND = "bound"
    SENTINEL = "sentinel"
    ZERO = "zero"


PROMISES: dict[Mode, frozenset[Promise]] = {
    Mode.LOSSLESS: frozenset(
        {Promise.STRUCTURE, Promise.DETERMINISM, Promise.EXACTNESS}
    ),
    Mode.NEAR_LOSSLESS: frozenset(
        {
            Promise.STRUCTURE,
            Promise.DETERMINISM,
            Promise.BOUND,
            Promise.SENTINEL,
            Promise.ZERO,
        }
    ),
    Mode.LOSSY: frozenset({Promise.STRUCTURE, Promise.DETERMINISM, Promise.SENTINEL}),
}


@dataclass(frozen=True)
class Budget:
    """An absolute error bound ``|x - x̂| <= tau``, in the native unit of the sample."""

    tau: float
    level: Level | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.tau):
            raise ValueError("tau must be finite")
        if self.tau <= 0.0:
            raise ValueError("tau must be above zero; use Mode.LOSSLESS for exactness")
