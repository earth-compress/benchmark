"""Lossy configurations. Codecs with a target of their own run as published, so
only the quantiser and the JPEG XL search are held to the rms bound here."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from earthcompress.budgets import budgets_for, load_budgets
from earthcompress.codecs import fixed, lossy
from earthcompress.codecs.base import Family, pack_frames, unpack_frames
from earthcompress.codecs.jpeg2000 import Jpeg2000Psnr
from earthcompress.codecs.jpegxl import JpegXl
from earthcompress.codecs.quantize import Quantized, rms_family, rms_steps
from earthcompress.codecs.scientific import Sz3L2
from earthcompress.contract import Budget, Level, Mode, Promise
from earthcompress.metrics import same_bytes
from earthcompress.promises import verify
from earthcompress.spec import ArraySpec

BUDGET = Budget(10.0, Level.MATCHED)
PCO = next(config for config in fixed() if config.id == "pco")


def _integers(dtype=np.uint16, shape=(3, 64, 48), seed=0):
    generator = np.random.default_rng(seed)
    walk = np.cumsum(generator.normal(0, 20, shape), axis=-1) + 120
    array = np.clip(walk, 1, np.iinfo(dtype).max).astype(dtype)
    array[..., :6, :6] = 0
    return array


def _floats(dtype=np.float32, shape=(3, 64, 48), seed=1):
    generator = np.random.default_rng(seed)
    return np.cumsum(generator.normal(0, 0.5, shape), axis=-1).astype(dtype)


def test_every_lossy_configuration_is_registered():
    configs = [make(BUDGET) for make in lossy()]
    assert {config.id for config in configs} == {
        "jpeg2000-psnr-matched",
        "jpegxl-distance-matched",
        "sz3-l2norm-matched",
        "sperr-psnr-matched",
        "quant-pco-rms-matched",
    }
    assert all(config.mode is Mode.LOSSY for config in configs)
    families = {config.id: config.family for config in configs}
    assert families["jpegxl-distance-matched"] is Family.SEARCHED
    assert families["quant-pco-rms-matched"] is Family.QUANTIZED


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
def test_every_lossy_configuration_runs_and_is_deterministic(array, sentinel):
    budget = Budget(1.0 if array.dtype.kind == "f" else 4.0)
    spec = ArraySpec(array.shape, array.dtype, sentinel=sentinel)
    ran = 0
    for config in (make(budget) for make in lossy()):
        if not config.supports(spec):
            continue
        codec = config.factory(spec)
        compressed = codec.encode(array)
        assert codec.encode(array) == compressed, config.id
        decoded = codec.decode(compressed)
        assert decoded.shape == array.shape and decoded.dtype == array.dtype
        assert same_bytes(codec.decode(compressed), decoded), config.id
        ran += 1
    assert ran >= 3


@pytest.mark.parametrize("tau", [1.0, 2.5, 10.0, 300.0])
def test_rms_steps_are_the_widest_uniform_grid_within_tau(tau):
    (k,) = rms_steps(ArraySpec((8,), np.dtype(np.uint16)), tau)
    assert k * (k + 1) / 3 <= tau**2 < (k + 1) * (k + 2) / 3


def test_rms_steps_follow_the_scale_of_each_plane():
    spec = ArraySpec((2, 4, 4), np.dtype(np.uint16), scale=(0.5, 2.0))
    assert rms_steps(spec, 10.0) == (34, 8)


@pytest.mark.parametrize(
    "array,sentinel,scale",
    [
        (_integers(np.uint16), None, (1.0,)),
        (_integers(np.uint16), 0.0, (1.0,)),
        (_integers(np.uint8, seed=3), None, (1.0,)),
        (_integers(np.uint16), None, (0.25, 0.5, 1.0)),
        (_floats(np.float32), None, (1.0,)),
        (np.full((4, 4), 7, np.uint16), None, (1.0,)),
    ],
    ids=["uint16", "uint16-nodata", "uint8", "per-plane", "float32", "constant"],
)
def test_the_lossy_quantiser_always_keeps_tau(array, sentinel, scale):
    spec = ArraySpec(array.shape, array.dtype, scale=scale, sentinel=sentinel)
    tau = 0.5 if array.dtype.kind == "f" else 4.0
    codec = rms_family(PCO)(Budget(tau)).factory(spec)
    decoded = codec.decode(codec.encode(array))
    report = verify(Mode.LOSSY, Budget(tau), array, decoded, sentinel, scale)
    assert report.ok, report.failures
    if array.dtype.kind != "f":
        zero = array == 0
        assert (decoded[zero] == 0).all()


def test_the_lossy_quantiser_narrows_a_grid_that_misses_tau():
    # Codes on one residue of the uniform grid all round by the widest step.
    k = rms_steps(ArraySpec((8,), np.dtype(np.uint16)), 4.0)[0]
    array = ((2 * k + 1) * (10 + np.arange(64)) + k).astype(np.uint16)
    spec = ArraySpec(array.shape, array.dtype)
    codec = Quantized(spec, Budget(4.0), PCO.factory, rms=True)
    decoded = codec.decode(codec.encode(array))
    assert verify(Mode.LOSSY, Budget(4.0), array, decoded).of(Promise.RMS)


def test_jpegxl_falls_back_to_lossless_when_no_distance_keeps_tau():
    array = _integers(np.uint16, (64, 48))
    spec = ArraySpec(array.shape, array.dtype)
    codec = JpegXl(spec, Budget(0.5))
    assert same_bytes(codec.decode(codec.encode(array)), array)


def test_jpegxl_keeps_tau_in_stored_units():
    array = _integers(np.uint16, (2, 64, 48))
    spec = ArraySpec(array.shape, array.dtype)
    codec = JpegXl(spec, Budget(6.0))
    decoded = codec.decode(codec.encode(array))
    assert verify(Mode.LOSSY, Budget(6.0), array, decoded).of(Promise.RMS)


def test_the_targets_of_the_native_lossy_codecs():
    spec = ArraySpec((3, 8, 8), np.dtype(np.uint16), scale=(0.5,))
    assert Jpeg2000Psnr(spec, Budget(5.0)).psnr == pytest.approx(
        20 * math.log10(65535 / 10)
    )
    assert Sz3L2(spec, Budget(5.0)).bound == pytest.approx(math.sqrt(3) * 10)


def test_frames_pack_and_unpack():
    frames = [b"", b"a", b"bcd" * 100]
    assert unpack_frames(pack_frames(frames)) == frames


def test_lossy_budgets_leave_out_pointwise_expert_bounds():
    assert Level.RECOMMENDED in budgets_for("era5-t2m-1h")
    assert Level.RECOMMENDED not in budgets_for("era5-t2m-1h", mode=Mode.LOSSY)
    assert Level.RECOMMENDED in budgets_for("era5-u10-1h", mode=Mode.LOSSY)
    assert budgets_for("s2-l1c-10m-4", mode=Mode.LOSSY) == budgets_for("s2-l1c-10m-4")


def test_a_registry_without_modes_applies_to_both_bounded_modes(tmp_path: Path):
    path = tmp_path / "budgets.csv"
    path.write_text("corpus,level,tau\nx,matched,1\n")
    for mode in (Mode.NEAR_LOSSLESS, Mode.LOSSY):
        assert load_budgets(path, mode)["x"][Level.MATCHED].tau == 1.0


def test_a_lossless_budget_is_rejected(tmp_path: Path):
    path = tmp_path / "budgets.csv"
    path.write_text("corpus,level,tau,modes\nx,matched,1,lossless\n")
    with pytest.raises(ValueError, match="lossless"):
        load_budgets(path)
