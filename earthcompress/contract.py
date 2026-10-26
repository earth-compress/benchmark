"""What a configuration declares, and what that commits it to.

Protocol section 2. A configuration declares a mode; the mode fixes the set of
promises, and the promises fix what the benchmark verifies.
"""

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
    """Which of the three budget levels of `TOLERANCE.md` this is."""

    CONSERVATIVE = "conservative"
    MATCHED = "matched"
    AGGRESSIVE = "aggressive"


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
    """An absolute error bound ``|x - x̂| <= tau``, in the native unit of the sample.

    ``level`` names which of the three levels of `TOLERANCE.md` this is. A
    result quoted without a level is not a result from the protocol.
    """

    tau: float
    level: Level | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.tau):
            raise ValueError("tau must be finite")
        if self.tau <= 0.0:
            raise ValueError("tau must be above zero; use Mode.LOSSLESS for exactness")
