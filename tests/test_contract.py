from __future__ import annotations

import math

import pytest

from earthcompress.codecs.base import CodecConfiguration
from earthcompress.contract import PROMISES, Budget, Level, Mode, Promise


def test_each_mode_declares_the_promises_of_the_protocol():
    assert PROMISES[Mode.LOSSLESS] == {
        Promise.STRUCTURE,
        Promise.DETERMINISM,
        Promise.EXACTNESS,
    }
    assert PROMISES[Mode.NEAR_LOSSLESS] == {
        Promise.STRUCTURE,
        Promise.DETERMINISM,
        Promise.BOUND,
        Promise.SENTINEL,
        Promise.ZERO,
    }
    assert PROMISES[Mode.LOSSY] == {
        Promise.STRUCTURE,
        Promise.DETERMINISM,
        Promise.SENTINEL,
    }


@pytest.mark.parametrize("tau", [0.0, -1.0, math.inf, math.nan])
def test_a_budget_must_be_finite_and_above_zero(tau):
    with pytest.raises(ValueError):
        Budget(tau)


def test_a_budget_carries_its_level():
    assert Budget(2.0, Level.MATCHED).level is Level.MATCHED


def test_only_near_lossless_carries_a_budget():
    common = dict(
        id="x", codec="x", version="0", parameters={}, factory=lambda spec: None
    )
    with pytest.raises(ValueError):
        CodecConfiguration(mode=Mode.NEAR_LOSSLESS, **common)
    with pytest.raises(ValueError):
        CodecConfiguration(mode=Mode.LOSSLESS, budget=Budget(1.0), **common)
    CodecConfiguration(mode=Mode.NEAR_LOSSLESS, budget=Budget(1.0), **common)
