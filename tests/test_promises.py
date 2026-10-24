from __future__ import annotations

import numpy as np
import pytest

from earthcompress.contract import BoundKind, Budget, Mode, Promise
from earthcompress.promises import verify


def test_lossless_fails_on_any_difference():
    reference = np.arange(16, dtype=np.int16)
    report = verify(Mode.LOSSLESS, None, reference, reference + 1)

    assert not report.ok
    assert report.of(Promise.EXACTNESS) is False


def test_lossless_passes_on_identical_bytes():
    reference = np.arange(16, dtype=np.int16)
    assert verify(Mode.LOSSLESS, None, reference, reference.copy()).ok


def test_structure_mismatch_stops_everything_else():
    reference = np.zeros((4, 4), dtype=np.int16)
    report = verify(Mode.LOSSLESS, None, reference, np.zeros((16,), dtype=np.int16))

    assert report.of(Promise.STRUCTURE) is False
    assert report.of(Promise.EXACTNESS) is None


def test_an_absolute_bound_converts_with_the_grid():
    """The budget is in native units; the array is in grid steps.

    This is the bug the IMERG smoke test caught: a budget of 0.04 mm/hr on a
    grid of 0.01 mm/hr allows four steps, not 0.04 of one.
    """
    # No zeros in the reference, so this isolates the bound from the zero check.
    reference = np.full(16, 500, dtype=np.int16)
    decoded = reference.copy()
    decoded[0] = 504  # four grid steps away
    budget = Budget(tau=0.04, kind=BoundKind.ABSOLUTE)

    assert verify(Mode.NEAR_LOSSLESS, budget, reference, decoded, grid=0.01).ok
    # Five steps is 0.05 mm/hr and must fail.
    decoded[0] = 505
    assert not verify(Mode.NEAR_LOSSLESS, budget, reference, decoded, grid=0.01).ok


def test_a_relative_bound_needs_no_grid_conversion():
    """The scale cancels on both sides of |x - x̂| <= tau · |x|."""
    reference = np.array([100, 1000], dtype=np.int16)
    decoded = np.array([101, 1010], dtype=np.int16)
    budget = Budget(tau=0.01, kind=BoundKind.RELATIVE)

    for grid in (1.0, 0.01, 1000.0):
        assert verify(Mode.NEAR_LOSSLESS, budget, reference, decoded, grid=grid).ok


def test_a_relative_bound_forces_exact_zeros():
    reference = np.array([0, 100], dtype=np.int16)
    budget = Budget(tau=0.5, kind=BoundKind.RELATIVE)

    assert verify(Mode.NEAR_LOSSLESS, budget, reference, reference.copy()).ok
    # tau * |0| is 0, so any movement off zero breaks the bound.
    report = verify(
        Mode.NEAR_LOSSLESS, budget, reference, np.array([1, 100], dtype=np.int16)
    )
    assert report.of(Promise.BOUND) is False


def test_equal_values_never_violate_a_bound():
    """Without the equivalence clause, a preserved infinity fails: inf-inf is NaN."""
    reference = np.array([np.inf, -np.inf, 1.0], dtype=np.float32)
    report = verify(
        Mode.NEAR_LOSSLESS,
        Budget(tau=0.5),
        reference,
        reference.copy(),
    )
    assert report.of(Promise.BOUND) is True


def test_a_lost_sentinel_fails_and_an_invented_one_fails():
    reference = np.array([0, 5, 7], dtype=np.int16)

    lost = verify(
        Mode.NEAR_LOSSLESS,
        Budget(tau=2.0),
        reference,
        np.array([1, 5, 7], dtype=np.int16),
        sentinel=0,
    )
    assert lost.of(Promise.SENTINEL) is False
    assert "lost" in lost.failures[0].detail

    invented = verify(
        Mode.NEAR_LOSSLESS,
        Budget(tau=6.0),
        reference,
        np.array([0, 0, 7], dtype=np.int16),
        sentinel=0,
    )
    assert invented.of(Promise.SENTINEL) is False


def test_no_sentinel_declared_is_not_run_rather_than_passed():
    reference = np.array([3, 5], dtype=np.int16)
    report = verify(Mode.NEAR_LOSSLESS, Budget(tau=1.0), reference, reference.copy())

    assert report.of(Promise.SENTINEL) is None
    assert report.ok


def test_a_respected_bound_does_not_imply_surviving_zeros():
    """The IMERG case: the bound holds and the zeros do not."""
    reference = np.array([0, 0, 3], dtype=np.int16)
    decoded = np.array([2, 0, 3], dtype=np.int16)
    report = verify(Mode.NEAR_LOSSLESS, Budget(tau=2.0), reference, decoded)

    assert report.of(Promise.BOUND) is True
    assert report.of(Promise.ZERO) is False
    assert not report.ok


def test_lossy_verifies_nothing_beyond_structure():
    reference = np.array([0, 100], dtype=np.int16)
    decoded = np.array([99, 0], dtype=np.int16)
    report = verify(Mode.LOSSY, None, reference, decoded, sentinel=0)

    assert report.ok
    assert report.of(Promise.BOUND) is None
    assert report.of(Promise.ZERO) is None


def test_subnormals_are_recorded_not_enforced():
    tiny = np.finfo(np.float32).tiny
    reference = np.array([tiny / 4, 1.0], dtype=np.float32)

    survived = verify(Mode.LOSSY, None, reference, reference.copy())
    assert survived.subnormals_ok is True

    flattened = verify(
        Mode.LOSSY, None, reference, np.array([0.0, 1.0], dtype=np.float32)
    )
    assert flattened.subnormals_ok is False
    # Recorded, not enforced: the run is still valid.
    assert flattened.ok


def test_integer_input_has_no_subnormal_verdict():
    reference = np.arange(4, dtype=np.int16)
    assert verify(Mode.LOSSY, None, reference, reference.copy()).subnormals_ok is None


def test_near_lossless_without_a_budget_is_a_programming_error():
    reference = np.arange(4, dtype=np.int16)
    with pytest.raises(ValueError, match="requires a budget"):
        verify(Mode.NEAR_LOSSLESS, None, reference, reference.copy())
