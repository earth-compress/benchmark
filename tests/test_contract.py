from __future__ import annotations

import pytest

from earthcompress.codecs.base import CodecConfiguration
from earthcompress.contract import PROMISES, BoundKind, Budget, Level, Mode, Promise


def test_each_mode_declares_its_promises():
    assert PROMISES[Mode.LOSSLESS] == {
        Promise.STRUCTURE,
        Promise.DETERMINISM,
        Promise.EXACTNESS,
    }
    assert Promise.BOUND in PROMISES[Mode.NEAR_LOSSLESS]
    assert Promise.SENTINEL in PROMISES[Mode.NEAR_LOSSLESS]
    assert Promise.ZERO in PROMISES[Mode.NEAR_LOSSLESS]
    assert PROMISES[Mode.LOSSY] == {Promise.STRUCTURE, Promise.DETERMINISM}


def test_lossless_promises_more_than_near_lossless_on_values():
    # Exactness is not in the near-lossless set, and a bound is not in lossless.
    assert Promise.EXACTNESS not in PROMISES[Mode.NEAR_LOSSLESS]
    assert Promise.BOUND not in PROMISES[Mode.LOSSLESS]


def test_a_range_relative_bound_is_not_a_near_lossless_claim():
    with pytest.raises(ValueError, match="range-relative"):
        Budget(tau=0.1, kind=BoundKind.RANGE_RELATIVE)


def test_a_budget_must_be_finite_and_above_zero():
    with pytest.raises(ValueError, match="finite"):
        Budget(tau=float("inf"))
    with pytest.raises(ValueError, match="above zero"):
        Budget(tau=0.0)
    with pytest.raises(ValueError, match="above zero"):
        Budget(tau=-1.0)


def _config(mode: Mode, budget: Budget | None) -> CodecConfiguration:
    return CodecConfiguration(
        id="demo",
        codec="demo",
        version="0",
        mode=mode,
        parameters={},
        factory=lambda spec: None,
        budget=budget,
    )


def test_only_near_lossless_carries_a_budget():
    _config(Mode.NEAR_LOSSLESS, Budget(tau=1.0, level=Level.MATCHED))
    _config(Mode.LOSSLESS, None)
    _config(Mode.LOSSY, None)

    with pytest.raises(ValueError, match="needs a budget"):
        _config(Mode.NEAR_LOSSLESS, None)
    with pytest.raises(ValueError, match="only a near-lossless"):
        _config(Mode.LOSSLESS, Budget(tau=1.0))
    with pytest.raises(ValueError, match="only a near-lossless"):
        _config(Mode.LOSSY, Budget(tau=1.0))
