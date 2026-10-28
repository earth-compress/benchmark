from __future__ import annotations

import numpy as np
import pytest

from earthcompress.budgets import budgets_for
from earthcompress.codecs import configurations_for, families, fixed, lossy, reference
from earthcompress.codecs.base import Family
from earthcompress.contract import Level, Mode, Promise
from earthcompress.metrics import same_bytes
from earthcompress.promises import verify
from earthcompress.spec import ArraySpec

DTYPES = (np.uint8, np.int8, np.uint16, np.int16, np.uint32, np.int32)
ALL = (*DTYPES, np.float32, np.float64)


def _sample(dtype: np.dtype, shape: tuple[int, ...] = (3, 64, 64)) -> np.ndarray:
    if np.dtype(dtype).kind == "f":
        generator = np.random.default_rng(0)
        return np.cumsum(generator.normal(0, 1, shape), axis=-1).astype(dtype)
    limits = np.iinfo(dtype)
    generator = np.random.default_rng(0)
    size = int(np.prod(shape))
    ramp = np.linspace(limits.min, limits.max, size)
    noise = generator.normal(0.0, (limits.max - limits.min) / 512, size)
    return np.clip(ramp + noise, limits.min, limits.max).astype(dtype).reshape(shape)


def test_configuration_ids_are_unique_per_corpus():
    for corpus in ("s2-l1c-10m-4", "imerg-pcp-12", "esa-wc-v200"):
        ids = [config.id for config in configurations_for(corpus)]
        assert len(ids) == len(set(ids)), corpus


def test_a_corpus_without_budgets_gets_only_fixed_configurations():
    assert configurations_for("esa-wc-v200") == fixed()


@pytest.mark.parametrize("corpus", ["s2-l1c-10m-4", "era5-t2m-1h", "era5-tp-1h"])
def test_a_corpus_with_budgets_gets_one_configuration_per_family_and_level(corpus):
    expected = (
        len(fixed())
        + len(families()) * len(budgets_for(corpus, mode=Mode.NEAR_LOSSLESS))
        + len(lossy()) * len(budgets_for(corpus, mode=Mode.LOSSY))
    )
    assert len(configurations_for(corpus)) == expected


def test_the_mode_decides_whether_a_budget_is_present():
    for config in configurations_for("s2-l1c-10m-4"):
        assert (config.budget is not None) == (config.mode is not Mode.LOSSLESS)


def test_lossy_has_no_recommended_level_where_experts_bound_every_point():
    levels = {
        corpus: {
            config.budget.level
            for config in configurations_for(corpus)
            if config.mode is Mode.LOSSY
        }
        for corpus in ("era5-t2m-1h", "era5-tp-1h")
    }
    assert Level.RECOMMENDED not in levels["era5-t2m-1h"]
    assert Level.RECOMMENDED in levels["era5-tp-1h"]


@pytest.mark.parametrize("dtype", ALL)
@pytest.mark.parametrize("shape", [(64, 48), (3, 64, 48)])
def test_every_lossless_codec_is_exact_and_deterministic(dtype, shape):
    array = _sample(np.dtype(dtype), shape)
    spec = ArraySpec(array.shape, array.dtype)
    for config in fixed() + reference():
        if not config.supports(spec):
            continue
        codec = config.factory(spec)
        compressed = codec.encode(array)
        assert same_bytes(codec.decode(compressed), array), config.id
        assert codec.encode(array) == compressed, config.id


def test_the_official_run_has_the_configurations_of_codecs_md():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "CODECS.md").read_text()
    official = text.split("## Official run", 1)[1].split("## Reference", 1)[0]
    listed = {
        line.split("|")[1].strip().strip("`")
        for line in official.splitlines()
        if line.startswith("| `")
    }
    assert listed == {config.id for config in fixed()}
    assert [config.id for config in reference()] == ["jpeg2000"]


@pytest.mark.parametrize("dtype", DTYPES)
def test_every_configuration_keeps_the_promises_of_its_mode(dtype):
    array = _sample(np.dtype(dtype))
    spec = ArraySpec(array.shape, array.dtype)

    for config in configurations_for("s2-l1c-10m-4"):
        if config.family is Family.NATIVE or not config.supports(spec):
            continue
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(config.mode, config.budget, array, decoded, scale=spec.scale)
        assert report.ok, f"{config.id} on {dtype}: {report.failures}"


@pytest.mark.parametrize("dtype", DTYPES)
def test_the_bound_holds_on_adversarial_input(dtype):
    limits = np.iinfo(dtype)
    # Both ends of the range, so decoding has to clip, plus a run of extremes.
    array = np.array(
        [limits.min, limits.min + 1, 0, 1, limits.max - 1, limits.max] * 4, dtype=dtype
    )
    spec = ArraySpec(array.shape, array.dtype)

    for config in configurations_for("s2-l1c-10m-4"):
        if config.mode is not Mode.NEAR_LOSSLESS or not config.supports(spec):
            continue
        if config.family is Family.NATIVE:
            continue
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        report = verify(config.mode, config.budget, array, decoded, scale=spec.scale)

        assert decoded.dtype == array.dtype
        assert report.of(Promise.BOUND) is True


def test_a_budget_in_native_units_is_honoured_on_a_fine_scale():
    """A 0.06 mm/hr budget on a scale of 0.01 is six steps, and must stay inside it."""
    generator = np.random.default_rng(0)
    array = generator.integers(0, 500, size=(4, 64, 64), dtype=np.uint16)
    spec = ArraySpec(array.shape, array.dtype, None, (0.01,))

    for config in configurations_for("imerg-pcp-12"):
        if config.mode is not Mode.NEAR_LOSSLESS or not config.supports(spec):
            continue
        if config.family is Family.NATIVE:
            continue
        codec = config.factory(spec)
        decoded = codec.decode(codec.encode(array))
        steps = spec.steps(config.budget.tau)
        assert (
            int(np.abs(array.astype(np.int64) - decoded.astype(np.int64)).max())
            <= steps
        )


def test_steps_round_down_with_the_largest_scale():
    spec = ArraySpec((2, 4), np.dtype(np.uint16), None, (2.0**-21, 2.0**-20))
    assert spec.steps(2e-5) == 20


def test_codecs_md_lists_the_native_and_quantized_configurations():
    from pathlib import Path

    from earthcompress.codecs import natives
    from earthcompress.codecs.quantize import BACKENDS
    from earthcompress.contract import Budget

    text = (Path(__file__).resolve().parent.parent / "CODECS.md").read_text()
    native = text.split("### Native", 1)[1].split("### Quantized", 1)[0]
    listed = {
        line.split("|")[1].strip().strip("`")
        for line in native.splitlines()
        if line.startswith("| `")
    }
    budget = Budget(1.0)
    assert listed == {make(budget).id.removesuffix("-tau1") for make in natives()}
    quantized = text.split("### Quantized", 1)[1].split("### Safeguarded", 1)[0]
    assert all(f"`{name}`" in quantized for name in BACKENDS)


def test_codecs_md_lists_the_lossy_configurations():
    from pathlib import Path

    from earthcompress.contract import Budget

    text = (Path(__file__).resolve().parent.parent / "CODECS.md").read_text()
    section = text.split("## Lossy", 1)[1].split("## Settings", 1)[0]
    listed = {
        line.split("|")[1].strip().strip("`")
        for line in section.splitlines()
        if line.startswith("| `")
    }
    budget = Budget(1.0)
    assert listed == {make(budget).id.removesuffix("-tau1") for make in lossy()}
    matrix = text.split("## Official run", 1)[0]
    assert all(f"`{name}`" in matrix for name in listed)
