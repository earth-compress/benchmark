from __future__ import annotations

import math

import pytest

from earthcompress.codecs.base import CodecConfiguration, Family
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
        Promise.RMS,
        Promise.SENTINEL,
    }


@pytest.mark.parametrize("tau", [0.0, -1.0, math.inf, math.nan])
def test_a_budget_must_be_finite_and_above_zero(tau):
    with pytest.raises(ValueError):
        Budget(tau)


def test_a_budget_carries_its_level():
    assert Budget(2.0, Level.MATCHED).level is Level.MATCHED


@pytest.mark.parametrize("mode", [Mode.NEAR_LOSSLESS, Mode.LOSSY])
def test_only_bounded_modes_carry_a_budget(mode):
    common = dict(
        id="x", codec="x", version="0", parameters={}, factory=lambda spec: None
    )
    with pytest.raises(ValueError):
        CodecConfiguration(mode=mode, family=Family.NATIVE, **common)
    with pytest.raises(ValueError):
        CodecConfiguration(mode=Mode.LOSSLESS, budget=Budget(1.0), **common)
    CodecConfiguration(mode=mode, budget=Budget(1.0), family=Family.NATIVE, **common)


@pytest.mark.parametrize("mode", [Mode.NEAR_LOSSLESS, Mode.LOSSY])
def test_only_bounded_modes_belong_to_a_family(mode):
    common = dict(
        id="x", codec="x", version="0", parameters={}, factory=lambda spec: None
    )
    with pytest.raises(ValueError):
        CodecConfiguration(mode=mode, budget=Budget(1.0), **common)
    with pytest.raises(ValueError):
        CodecConfiguration(mode=Mode.LOSSLESS, family=Family.QUANTIZED, **common)
