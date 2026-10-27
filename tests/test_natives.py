"""Native bounded codecs run as published, so these tests check that each one
runs and is deterministic, not that it keeps its promises: the benchmark
measures that."""

from __future__ import annotations

import numpy as np
import pytest

from earthcompress.codecs import natives
from earthcompress.codecs.base import to_stored
from earthcompress.contract import Budget, Level, Mode, Promise
from earthcompress.metrics import same_bytes
from earthcompress.promises import verify
from earthcompress.spec import ArraySpec

BUDGET = Budget(10.0, Level.MATCHED)


def _configs(spec: ArraySpec, budget: Budget = BUDGET):
    configs = [make(budget) for make in natives()]
    return [config for config in configs if config.supports(spec)]


def _integers(dtype=np.uint16, shape=(3, 64, 48)):
    generator = np.random.default_rng(0)
    walk = np.cumsum(generator.normal(0, 20, shape), axis=-1) + 120
    array = np.clip(walk, 1, np.iinfo(dtype).max).astype(dtype)
    array[..., :6, :6] = 0
    return array


def _floats(dtype=np.float32, shape=(3, 64, 48)):
    generator = np.random.default_rng(1)
    return np.cumsum(generator.normal(0, 0.5, shape), axis=-1).astype(dtype)


def test_every_native_codec_is_registered():
    names = {make(BUDGET).id.rsplit("-", 1)[0] for make in natives()}
    assert names == {
        "lerc",
        "jpegls-near",
        "sz3-abs",
        "zfp-accuracy",
        "sperr-pwe",
        "geozl-med-entropy-linear",
    }


@pytest.mark.parametrize(
    "array,sentinel",
    [
        (_integers(np.uint16), 0.0),
        (_integers(np.uint8), 0.0),
        (_integers(np.uint16, (64, 48)), None),
        (_floats(np.float32), None),
        (_floats(np.float32, (64, 48)), None),
    ],
    ids=["uint16-3d", "uint8-3d", "uint16-2d", "float32-3d", "float32-2d"],
)
def test_every_native_codec_runs_and_decodes_the_same_bytes_again(array, sentinel):
    spec = ArraySpec(array.shape, array.dtype, sentinel=sentinel)
    budget = Budget(0.25) if array.dtype.kind == "f" else Budget(4.0)
    configs = _configs(spec, budget)
    assert configs
    for config in configs:
        codec = config.factory(spec)
        compressed = codec.encode(array)
        decoded = codec.decode(compressed)
        assert decoded.shape == array.shape and decoded.dtype == array.dtype, config.id
        assert same_bytes(codec.decode(compressed), decoded), config.id
        assert codec.encode(array) == compressed, config.id


def test_codecs_with_a_nodata_parameter_keep_the_sentinel():
    array = _integers(np.uint16)
    array[1, 20:24, 20:24] = 1
    spec = ArraySpec(array.shape, array.dtype, sentinel=0.0)
    kept = {}
    for config in _configs(spec):
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(Mode.NEAR_LOSSLESS, BUDGET, array, decoded, 0.0)
        kept[config.codec] = report.of(Promise.SENTINEL)
    assert kept["lerc"] is True and kept["geozl"] is True


def test_jpegls_takes_no_more_than_255_steps():
    spec = ArraySpec((16, 16), np.dtype(np.uint16))
    assert _configs(spec, Budget(255.0))
    assert not any(c.codec == "jpegls" for c in _configs(spec, Budget(256.0)))
    small = ArraySpec((16, 16), np.dtype(np.uint8))
    assert not any(c.codec == "jpegls" for c in _configs(small, Budget(128.0)))


def test_lerc_keeps_integer_bounds_including_the_reserved_value():
    array = _integers(np.uint16)
    array[array == 0] = 1
    spec = ArraySpec(array.shape, array.dtype)
    for tau in (1.0, 7.0, 777.0):
        config = next(c for c in _configs(spec, Budget(tau)) if c.codec == "lerc")
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        assert verify(Mode.NEAR_LOSSLESS, Budget(tau), array, decoded).of(Promise.BOUND)


def test_float_output_returns_to_the_stored_codes():
    spec = ArraySpec((4,), np.dtype(np.uint8))
    values = np.array([-3.2, 0.49, 254.6, 300.0])
    assert to_stored(values, spec).tolist() == [0, 0, 255, 255]
