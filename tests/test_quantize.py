from __future__ import annotations

import numpy as np
import pytest

from earthcompress.codecs import configurations_for, fixed
from earthcompress.codecs.base import Family
from earthcompress.codecs.quantize import BACKENDS, Quantized, supports
from earthcompress.contract import Budget, Mode, Promise
from earthcompress.promises import verify
from earthcompress.spec import ArraySpec

UNSIGNED = (np.uint8, np.uint16, np.uint32)
SIGNED = (np.int8, np.int16, np.int32)


def _identity(spec: ArraySpec):
    class Raw:
        def encode(self, array):
            return np.ascontiguousarray(array).tobytes()

        def decode(self, data):
            return np.frombuffer(data, dtype=spec.dtype).reshape(spec.shape)

    return Raw()


def _round_trip(array, spec, budget, backend=_identity):
    codec = Quantized(spec, budget, backend)
    compressed = codec.encode(array)
    assert codec.encode(array) == compressed
    return codec.decode(compressed)


def _codes(dtype, shape=(3, 40, 40), seed=0):
    limits = np.iinfo(dtype)
    generator = np.random.default_rng(seed)
    values = generator.integers(limits.min, limits.max, size=shape, endpoint=True)
    # Both ends of the type, zero, and its neighbours, so clipping is exercised.
    edges = [limits.min, limits.min + 1, 0, 1, limits.max - 1, limits.max]
    values.reshape(-1)[: len(edges)] = edges
    return values.astype(dtype)


@pytest.mark.parametrize("dtype", UNSIGNED + SIGNED)
@pytest.mark.parametrize("tau", [1, 2, 7, 40, 300])
def test_integers_keep_the_bound_and_exact_zeros(dtype, tau):
    array = _codes(dtype)
    spec = ArraySpec(array.shape, array.dtype)
    decoded = _round_trip(array, spec, Budget(float(tau)))
    report = verify(Mode.NEAR_LOSSLESS, Budget(float(tau)), array, decoded)
    assert report.ok, report.failures
    assert decoded.dtype == array.dtype


@pytest.mark.parametrize("dtype", UNSIGNED)
@pytest.mark.parametrize("tau", [1, 4, 40])
def test_a_sentinel_at_the_bottom_stays_alone(dtype, tau):
    array = _codes(dtype)
    array[0, :5, :5] = 0  # NoData
    array[1, :5, :5] = 1  # valid values next to it
    spec = ArraySpec(array.shape, array.dtype, sentinel=0.0)
    decoded = _round_trip(array, spec, Budget(float(tau)))
    report = verify(Mode.NEAR_LOSSLESS, Budget(float(tau)), array, decoded, 0.0)
    assert report.ok, report.failures
    assert (decoded[array != 0] != 0).all()


def test_each_plane_gets_the_steps_of_its_own_scale():
    generator = np.random.default_rng(1)
    array = generator.integers(0, 4000, size=(2, 64, 64)).astype(np.uint16)
    scale = (2.0**-19, 2.0**-21)
    spec = ArraySpec(array.shape, array.dtype, scale=scale)
    tau = 26 * 2.0**-19
    decoded = _round_trip(array, spec, Budget(tau))
    error = np.abs(decoded.astype(np.int64) - array.astype(np.int64))
    assert spec.plane_steps(tau) == (26, 104)
    assert error[0].max() == 26 and error[1].max() == 104
    assert verify(Mode.NEAR_LOSSLESS, Budget(tau), array, decoded, scale=scale).ok


def test_the_grid_sits_on_the_code_of_a_native_zero():
    # Code 8 is a native zero: 8 * 0.5 - 4.0.
    array = np.array([[0, 7, 8, 9, 20, 255]], dtype=np.uint8)
    spec = ArraySpec(array.shape, array.dtype, scale=(0.5,), offset=(-4.0,))
    decoded = _round_trip(array, spec, Budget(1.5))
    assert decoded[0, 2] == 8
    report = verify(
        Mode.NEAR_LOSSLESS, Budget(1.5), array, decoded, scale=0.5, offset=-4.0
    )
    assert report.ok and report.of(Promise.ZERO) is True


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("tau", [1.25e-4, 0.25, 4.0])
def test_floats_keep_the_bound_zero_and_non_finite_values(dtype, tau):
    generator = np.random.default_rng(2)
    array = np.cumsum(generator.normal(0, 3 * tau, (2, 50, 50)), axis=-1).astype(dtype)
    array.reshape(-1)[:5] = [0.0, -0.0, np.nan, np.inf, -np.inf]
    spec = ArraySpec(array.shape, array.dtype)
    decoded = _round_trip(array, spec, Budget(tau))
    report = verify(Mode.NEAR_LOSSLESS, Budget(tau), array, decoded)
    assert report.ok, report.failures
    assert np.isnan(decoded.reshape(-1)[2]) and np.isinf(decoded.reshape(-1)[3:5]).all()


def test_float_rounding_past_the_bound_is_kept_exactly():
    # 0.1 is not a multiple of 2 * tau in binary, so some values land just past tau.
    tau = 0.1
    array = (np.arange(10_000, dtype=np.float32) * np.float32(0.0999999)).reshape(
        100, 100
    )
    spec = ArraySpec(array.shape, array.dtype)
    decoded = _round_trip(array, spec, Budget(tau))
    error = np.abs(decoded.astype(np.float64) - array.astype(np.float64))
    assert error.max() <= tau


def test_a_sentinel_elsewhere_in_the_range_is_not_supported():
    budget = Budget(2.0)
    assert supports(ArraySpec((4,), np.dtype(np.uint16), sentinel=0.0), budget)
    assert not supports(ArraySpec((4,), np.dtype(np.uint16), sentinel=65535.0), budget)
    assert not supports(ArraySpec((4,), np.dtype(np.float32), sentinel=-9999.0), budget)
    assert not supports(ArraySpec((4,), np.dtype(np.int64)), budget)


@pytest.mark.parametrize("name", BACKENDS)
@pytest.mark.parametrize("dtype", [np.uint8, np.uint16, np.float32])
def test_every_backend_keeps_the_promises_on_its_indices(name, dtype):
    backend = {config.id: config for config in fixed()}[name]
    if np.dtype(dtype).kind == "f":
        generator = np.random.default_rng(3)
        array = np.cumsum(generator.normal(0, 1, (3, 48, 40)), axis=-1).astype(dtype)
        tau, sentinel = 0.25, None
    else:
        array = _codes(dtype, (3, 48, 40))
        array[0, :4, :4] = 0
        tau, sentinel = 3.0, 0.0
    spec = ArraySpec(array.shape, array.dtype, sentinel=sentinel)
    decoded = _round_trip(array, spec, Budget(tau), backend.factory)
    report = verify(Mode.NEAR_LOSSLESS, Budget(tau), array, decoded, sentinel)
    assert report.ok, f"{name}: {report.failures}"


def test_the_registry_gives_each_backend_a_quantized_variant():
    quantized = {
        config.id.rsplit("-", 1)[0]
        for config in configurations_for("s2-l1c-10m-4")
        if config.family is Family.QUANTIZED
    }
    assert quantized == {f"quant-{name}" for name in BACKENDS}
