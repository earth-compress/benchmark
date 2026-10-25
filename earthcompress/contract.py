"""What a configuration declares, and what that commits it to.

Protocol section 2. A configuration declares a mode; the mode fixes the set of
promises, and the promises fix what the benchmark verifies. Modes are different
claims, not points on a scale.
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


class BoundKind(StrEnum):
    """The kind of error bound a near-lossless configuration declares.

    There is no standard meaning of "relative" in this literature, so the kind
    is always named. ``RANGE_RELATIVE`` is defined here only to be rejected:
    its bound depends on the content of whatever block the codec saw, so the
    protocol does not accept it as a near-lossless claim.
    """

    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    RANGE_RELATIVE = "range-relative"


class Level(StrEnum):
    """Which of the three budget levels of protocol section 3 this is."""

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
    Mode.LOSSY: frozenset({Promise.STRUCTURE, Promise.DETERMINISM}),
}


@dataclass(frozen=True)
class Budget:
    """An error budget, in the native unit of the sample.

    ``level`` names which of the three levels of `TOLERANCE.md` this is.
    It is optional, because an ablation may measure a budget that is not one of
    them, but a result quoted without a level is not a result from the protocol.
    """

    tau: float
    kind: BoundKind = BoundKind.ABSOLUTE
    level: Level | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.tau):
            raise ValueError("tau must be finite")
        if self.tau <= 0.0:
            raise ValueError("tau must be above zero; use Mode.LOSSLESS for exactness")
        if self.kind is BoundKind.RANGE_RELATIVE:
            raise ValueError(
                "a range-relative bound is not a near-lossless claim: its bound "
                "depends on the block the codec saw. Declare Mode.LOSSY instead."
            )
