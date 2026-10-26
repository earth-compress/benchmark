from __future__ import annotations

import math

import numpy as np

from earthcompress.contract import Budget, Mode, Promise
from earthcompress.promises import verify


def test_lossless_fails_on_any_difference_and_passes_on_identical_bytes():
    reference = np.arange(16, dtype=np.uint16)
    assert verify(Mode.LOSSLESS, None, reference, reference.copy()).ok
    changed = reference.copy()
    changed[3] += 1
    assert (
        verify(Mode.LOSSLESS, None, reference, changed).of(Promise.EXACTNESS) is False
    )


def test_structure_mismatch_stops_everything_else():
    reference = np.arange(16, dtype=np.uint16)
    report = verify(Mode.LOSSLESS, None, reference, reference.astype(np.int32))
    assert [v.promise for v in report.verdicts] == [Promise.STRUCTURE]
    assert not report.ok


def test_the_bound_is_in_native_units_with_the_scale_of_each_plane():
    reference = np.zeros((2, 4), dtype=np.uint16)
    decoded = np.full((2, 4), 3, dtype=np.uint16)
    # Three steps of 0.25 and of 0.5: 0.75 and 1.5 in native units.
    assert verify(
        Mode.NEAR_LOSSLESS, Budget(1.5), reference + 1, decoded + 1, scale=(0.25, 0.5)
    ).ok
    assert not verify(
        Mode.NEAR_LOSSLESS, Budget(1.0), reference + 1, decoded + 1, scale=(0.25, 0.5)
    ).ok


def test_equal_values_never_violate_a_bound():
    reference = np.array([math.inf, -math.inf, 1.0], dtype=np.float32)
    assert verify(Mode.NEAR_LOSSLESS, Budget(0.1), reference, reference.copy()).ok


def test_nodata_is_not_counted_by_the_bound_but_must_survive():
    reference = np.array([0, 100, 200], dtype=np.uint16)
    decoded = np.array([0, 101, 201], dtype=np.uint16)
    report = verify(Mode.NEAR_LOSSLESS, Budget(1.0), reference, decoded, sentinel=0)
    assert report.ok and report.of(Promise.SENTINEL) is True


def test_a_lost_sentinel_fails_and_an_invented_one_fails():
    reference = np.array([0, 5, 7], dtype=np.int16)
    lost = np.array([1, 5, 7], dtype=np.int16)
    invented = np.array([0, 0, 7], dtype=np.int16)
    for decoded in (lost, invented):
        report = verify(
            Mode.NEAR_LOSSLESS, Budget(10.0), reference, decoded, sentinel=0
        )
        assert report.of(Promise.SENTINEL) is False


def test_a_nan_sentinel_is_found_by_position():
    reference = np.array([np.nan, 1.0, 2.0], dtype=np.float32)
    assert (
        verify(Mode.LOSSY, None, reference, reference.copy(), sentinel=math.nan).of(
            Promise.SENTINEL
        )
        is True
    )
    moved = np.array([0.0, np.nan, 2.0], dtype=np.float32)
    assert (
        verify(Mode.LOSSY, None, reference, moved, sentinel=math.nan).of(
            Promise.SENTINEL
        )
        is False
    )


def test_no_sentinel_declared_is_not_run_rather_than_passed():
    reference = np.arange(4, dtype=np.int16)
    assert (
        verify(Mode.LOSSY, None, reference, reference.copy()).of(Promise.SENTINEL)
        is None
    )


def test_a_respected_bound_does_not_imply_surviving_zeros():
    reference = np.array([0, 0, 50], dtype=np.int16)
    decoded = np.array([1, 0, 50], dtype=np.int16)
    report = verify(Mode.NEAR_LOSSLESS, Budget(2.0), reference, decoded)
    assert report.of(Promise.BOUND) is True
    assert report.of(Promise.ZERO) is False


def test_zeros_are_found_in_native_units():
    # Code 40 with offset -10 and scale 0.25 is an exact zero.
    reference = np.array([40, 41, 80], dtype=np.uint16)
    decoded = np.array([41, 41, 80], dtype=np.uint16)
    report = verify(
        Mode.NEAR_LOSSLESS, Budget(1.0), reference, decoded, scale=0.25, offset=-10.0
    )
    assert report.of(Promise.ZERO) is False


def test_lossy_checks_structure_and_sentinels_only():
    reference = np.array([0, 5, 7], dtype=np.int16)
    decoded = np.array([0, 9, 1], dtype=np.int16)
    report = verify(Mode.LOSSY, None, reference, decoded, sentinel=0)
    assert report.ok
    assert {v.promise for v in report.verdicts} == {Promise.STRUCTURE, Promise.SENTINEL}
