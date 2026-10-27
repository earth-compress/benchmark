from __future__ import annotations

import numpy as np
import pytest

from earthcompress.codecs import families, natives
from earthcompress.codecs.base import Family
from earthcompress.codecs.safeguards import rules
from earthcompress.contract import Budget, Mode
from earthcompress.promises import verify
from earthcompress.spec import ArraySpec


def _safeguarded(spec: ArraySpec, budget: Budget):
    configs = [make(budget) for make in families()]
    return [c for c in configs if c.family is Family.SAFEGUARDED and c.supports(spec)]


def _integers(dtype):
    generator = np.random.default_rng(0)
    walk = np.cumsum(generator.normal(0, 20, (3, 48, 40)), axis=-1) + 60
    array = np.clip(walk, 0, np.iinfo(dtype).max).astype(dtype)
    array[0, :6, :6] = 0
    return array


def test_every_native_codec_has_a_safeguarded_variant_and_the_zero_row():
    budget = Budget(4.0)
    names = {c.id for c in (make(budget) for make in families())}
    for make in natives():
        assert f"sg-{make(budget).id}" in names
    assert "sg-zero-tau4" in names


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_safeguarded_rows_keep_the_bound_the_sentinel_and_zeros(dtype):
    array = _integers(dtype)
    array[1, 10:14, 10:14] = 1  # valid values next to the sentinel
    spec = ArraySpec(array.shape, array.dtype, sentinel=0.0)
    budget = Budget(3.0)
    configs = _safeguarded(spec, budget)
    assert len(configs) >= 6
    for config in configs:
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(Mode.NEAR_LOSSLESS, budget, array, decoded, 0.0)
        assert report.ok, f"{config.id}: {report.failures}"


def test_safeguarded_rows_keep_exact_zeros_without_a_sentinel():
    array = _integers(np.uint16)
    spec = ArraySpec(array.shape, array.dtype)
    budget = Budget(5.0)
    for config in _safeguarded(spec, budget):
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(Mode.NEAR_LOSSLESS, budget, array, decoded)
        assert report.ok, f"{config.id}: {report.failures}"


def test_safeguarded_rows_keep_float_bounds():
    generator = np.random.default_rng(1)
    array = np.cumsum(generator.normal(0, 1e-3, (3, 48, 40)), axis=-1)
    array = array.astype(np.float32)
    array[0, :4, :4] = 0.0
    spec = ArraySpec(array.shape, array.dtype)
    budget = Budget(1.25e-4)
    for config in _safeguarded(spec, budget):
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(Mode.NEAR_LOSSLESS, budget, array, decoded)
        assert report.ok, f"{config.id}: {report.failures}"


def test_the_rules_follow_the_promises_of_the_sample():
    budget = Budget(10.0)
    plain = ArraySpec((4,), np.dtype(np.uint16))
    assert rules(plain, budget) == [
        dict(kind="eb", type="abs", eb=10),
        dict(kind="same", value=0),
    ]
    nodata = ArraySpec((4,), np.dtype(np.uint16), sentinel=0.0)
    assert rules(nodata, budget) == [
        dict(kind="eb", type="abs", eb=10),
        dict(kind="same", value=0, exclusive=True),
    ]
    # Offsets per hour put no native zero on a whole code: no zero rule.
    era5 = ArraySpec(
        (2, 4), np.dtype(np.uint16), scale=(0.25, 0.25), offset=(93538.1, 93477.3)
    )
    assert rules(era5, Budget(15.0)) == [dict(kind="eb", type="abs", eb=60)]
