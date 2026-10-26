from __future__ import annotations

import math

import numpy as np
import pytest

from earthcompress.metrics import check_structure, distortion, same_bytes


def test_identical_arrays_are_exact():
    reference = np.arange(256, dtype=np.uint16).reshape(16, 16)
    measured = distortion(reference, reference.copy())

    assert measured.exact
    assert measured.max_abs_error == 0.0
    assert measured.psnr_db == math.inf
    # Nothing to describe the shape of, so neither shape metric is defined.
    assert math.isnan(measured.error_spread)


def test_metrics_use_native_units_and_the_sample_range():
    reference = np.array([[0, 100]], dtype=np.int16)
    decoded = np.array([[2, 100]], dtype=np.int16)
    measured = distortion(reference, decoded)

    assert measured.max_abs_error == 2.0
    assert measured.mae == 1.0
    assert measured.rmse == math.sqrt(2.0)
    # peak is the sample range, 100, not the int16 range.
    assert measured.psnr_db == pytest.approx(20.0 * math.log10(100 / math.sqrt(2.0)))


def test_unsigned_underflow_is_not_wrapped():
    assert (
        distortion(
            np.array([0, 5], dtype=np.uint8), np.array([3, 5], dtype=np.uint8)
        ).max_abs_error
        == 3.0
    )


def test_constant_sample_has_no_psnr_when_inexact():
    measured = distortion(
        np.full((4, 4), 7, dtype=np.uint8), np.full((4, 4), 8, dtype=np.uint8)
    )
    assert math.isnan(measured.psnr_db)


def test_error_spread_separates_a_filled_budget_from_a_wasted_one():
    generator = np.random.default_rng(0)
    reference = np.zeros((64, 64), dtype=np.int16)

    # Uniform through the budget: a codec that spends what it was given.
    uniform = generator.integers(-8, 9, size=reference.shape).astype(np.int16)
    # Concentrated at zero with one outlier: the same maximum, far less used.
    concentrated = np.zeros_like(uniform)
    concentrated[0, 0] = 8

    spread_uniform = distortion(reference, uniform).error_spread
    spread_concentrated = distortion(reference, concentrated).error_spread

    assert spread_uniform > 0.9
    assert spread_concentrated < 0.1
    # Both have the same maximum, so a maximum alone cannot tell them apart.
    assert distortion(reference, uniform).max_abs_error == 8.0
    assert distortion(reference, concentrated).max_abs_error == 8.0


def test_error_lag1_separates_white_noise_from_spatial_structure():
    generator = np.random.default_rng(0)
    reference = np.zeros((64, 64), dtype=np.int16)

    white = generator.integers(-4, 5, size=reference.shape).astype(np.int16)
    # A smooth ramp along the last axis: adjacent errors are nearly equal.
    structured = np.tile(np.linspace(-4, 4, 64), (64, 1)).astype(np.int16)

    assert abs(distortion(reference, white).error_lag1) < 0.2
    assert distortion(reference, structured).error_lag1 > 0.9


def test_metrics_span_several_row_blocks():
    rows = (1 << 12) + 7
    reference = np.zeros((rows, 8), dtype=np.int16)
    decoded = np.zeros_like(reference)
    reference[0, 0] = -300
    decoded[-1, -1] = 4

    measured = distortion(reference, decoded)
    assert measured.max_abs_error == 300.0
    assert measured.mae == pytest.approx(304 / reference.size)


def test_structure_mismatch_is_rejected():
    reference = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        check_structure(reference, np.zeros((4,), dtype=np.uint8))
    with pytest.raises(ValueError, match="dtype"):
        check_structure(reference, np.zeros((2, 2), dtype=np.uint16))


def test_same_bytes_distinguishes_dtype_and_shape():
    values = np.arange(4, dtype=np.uint8)
    assert same_bytes(values, values.copy())
    assert not same_bytes(values, values.astype(np.uint16))
    assert not same_bytes(values, values.reshape(2, 2))


def test_errors_convert_to_native_units_per_plane():
    reference = np.zeros((2, 1, 4), dtype=np.uint16)
    decoded = np.ones((2, 1, 4), dtype=np.uint16)
    measured = distortion(reference, decoded, scale=(0.5, 2.0), offset=(100.0, -3.0))

    assert measured.max_abs_error == 2.0
    assert measured.mae == pytest.approx(1.25)
    # The offset does not enter the error, but it does enter the peak.
    assert measured.mean_error == pytest.approx(1.25)


def test_mean_error_has_the_sign_of_the_bias():
    reference = np.full((4, 4), 10, dtype=np.int16)
    assert distortion(reference, reference - 1).mean_error == -1.0
    assert distortion(reference, reference + 1).mean_error == 1.0


def test_nodata_is_left_out_of_the_error_and_the_peak():
    reference = np.array([[0, 100, 104, 0]], dtype=np.uint16)
    decoded = np.array([[0, 102, 104, 0]], dtype=np.uint16)
    measured = distortion(reference, decoded, nodata=0)
    assert measured.mae == 1.0
    assert measured.psnr_db == pytest.approx(20 * math.log10(4 / math.sqrt(2)))
