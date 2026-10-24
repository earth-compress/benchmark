from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from conftest import write_corpus

from earthcompress.codecs.base import CodecConfiguration
from earthcompress.contract import Budget, Level, Mode
from earthcompress.corpus import load_samples
from earthcompress.runner import RESULT_COLUMNS, run_benchmark
from earthcompress.spec import ArraySpec


class Identity:
    """A lossless reference codec that stores the raw bytes."""

    def __init__(self, spec: ArraySpec):
        self._spec = spec

    def encode(self, array: np.ndarray) -> bytes:
        return np.ascontiguousarray(array).tobytes(order="C")

    def decode(self, compressed: bytes) -> np.ndarray:
        return np.frombuffer(compressed, dtype=self._spec.dtype).reshape(
            self._spec.shape
        )


class OffByOne(Identity):
    """Shifts every element by one grid step."""

    def decode(self, compressed: bytes) -> np.ndarray:
        return super().decode(compressed) + 1


class Restless(Identity):
    """Encodes differently every call: breaks determinism."""

    def __init__(self, spec: ArraySpec):
        super().__init__(spec)
        self._calls = 0

    def encode(self, array: np.ndarray) -> bytes:
        self._calls += 1
        return super().encode(array) + b"\x00" * self._calls


def _config(factory, mode, budget=None, config_id="demo") -> CodecConfiguration:
    return CodecConfiguration(
        id=config_id,
        codec="demo",
        version="0",
        mode=mode,
        parameters={},
        factory=factory,
        budget=budget,
    )


def _rows(corpus: Path) -> list[dict[str, str]]:
    with (corpus / "results.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def _run(corpus: Path, config: CodecConfiguration, **kwargs) -> bool:
    return run_benchmark(corpus, (config,), rounds=1, min_seconds=0.0, **kwargs)


def test_a_lossless_run_writes_results_and_environment(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS))

    rows = _rows(corpus)
    assert [row["sample_id"] for row in rows] == ["demo-00", "demo-01"]
    for row in rows:
        assert list(row) == list(RESULT_COLUMNS)
        assert row["mode"] == str(Mode.LOSSLESS)
        assert (
            row["tau"] == "" and row["bound_kind"] == "" and row["budget_level"] == ""
        )
        assert row["fidelity_ok"] == "True"
        assert row["exact"] == "True"
        assert float(row["compression_ratio"]) == pytest.approx(1.0)
        assert float(row["bits_per_value"]) == pytest.approx(16.0)
        # Lossless distortion is zero by construction, not recomputed.
        assert float(row["max_abs_error"]) == 0.0

    environment = json.loads((corpus / "environment.json").read_text())
    assert environment["threads"] == 1 and environment["rounds"] == 1


def test_a_near_lossless_run_records_its_declaration_and_error(corpus: Path):
    budget = Budget(tau=1.0, level=Level.MATCHED)
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, budget))

    for row in _rows(corpus):
        assert row["mode"] == str(Mode.NEAR_LOSSLESS)
        assert row["bound_kind"] == "absolute"
        assert row["tau"] == "1.0"
        assert row["budget_level"] == "matched"
        assert row["fidelity_ok"] == "True"
        assert float(row["max_abs_error"]) == 1.0
        assert float(row["mae"]) == 1.0
        # A constant error has no spread and perfect lag-1 correlation.
        assert (
            float(row["error_lag1"]) == pytest.approx(1.0) or row["error_lag1"] == "nan"
        )


def test_moving_an_exact_zero_fails_the_run(tmp_path: Path):
    """A respected bound does not imply surviving zeros: the IMERG case."""
    corpus = write_corpus(
        tmp_path / "zeros", {"z-00": np.array([[0, 0, 5, 9]], dtype=np.int16)}
    )
    assert not _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, Budget(tau=2.0)))
    assert _rows(corpus)[0]["fidelity_ok"] == "False"


def test_the_quantiser_keeps_exact_zeros(tmp_path: Path):
    """The shipped near-lossless baseline anchors its grid at zero."""
    from earthcompress.codecs import configurations_for

    generator = np.random.default_rng(0)
    data = generator.integers(0, 500, size=(2, 64, 64), dtype=np.uint16)
    data[0, 0, :16] = 0
    corpus = write_corpus(tmp_path / "quant", {"q-00": data})

    near = [
        config
        for config in configurations_for("s2-l1c-10m-4")
        if config.mode is Mode.NEAR_LOSSLESS
    ]
    assert run_benchmark(corpus, tuple(near), rounds=1, min_seconds=0.0)
    for row in _rows(corpus):
        assert row["zero_ok"] == "True", row["configuration"]


def test_a_broken_bound_fails_the_run(corpus: Path):
    budget = Budget(tau=0.5, level=Level.CONSERVATIVE)
    assert not _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, budget))

    for row in _rows(corpus):
        assert row["fidelity_ok"] == "False"
        assert row["compressed_bytes"] == ""
        # The declaration survives a failure, so the row says what was claimed.
        assert row["tau"] == "0.5" and row["budget_level"] == "conservative"


def test_lossy_mode_verifies_nothing_beyond_structure(corpus: Path):
    assert _run(corpus, _config(OffByOne, Mode.LOSSY))

    for row in _rows(corpus):
        assert row["mode"] == str(Mode.LOSSY)
        assert row["fidelity_ok"] == "True"
        assert float(row["max_abs_error"]) == 1.0
        assert row["zero_ok"] == "" and row["sentinel_ok"] == ""


def test_non_deterministic_encoding_fails_the_run(corpus: Path):
    assert not _run(corpus, _config(Restless, Mode.LOSSLESS))
    assert all(row["fidelity_ok"] == "False" for row in _rows(corpus))


def test_a_sentinel_is_checked_when_the_corpus_declares_one(tmp_path: Path):
    data = np.array([[0, 5, 7, 9]], dtype=np.int16)
    corpus = write_corpus(
        tmp_path / "sentinel",
        {"s-00": data},
        extra={"sentinel": np.array(0, dtype=np.int16)},
    )
    assert load_samples(corpus)[0].sentinel == 0.0

    # OffByOne moves the sentinel, so the sentinel promise breaks.
    assert not _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, Budget(tau=2.0)))
    assert _rows(corpus)[0]["fidelity_ok"] == "False"


def test_unsupported_configurations_are_skipped(corpus: Path):
    config = CodecConfiguration(
        id="unsupported",
        codec="demo",
        version="0",
        mode=Mode.LOSSLESS,
        parameters={},
        factory=Identity,
        supports=lambda spec: False,
    )
    assert run_benchmark(corpus, (config,), rounds=1, min_seconds=0.0)
    assert _rows(corpus) == []


def test_limit_selects_the_first_samples(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS), limit=1)
    assert [row["sample_id"] for row in _rows(corpus)] == ["demo-00"]


def test_invalid_timing_settings_are_rejected(corpus: Path):
    config = _config(Identity, Mode.LOSSLESS)
    with pytest.raises(ValueError, match="rounds"):
        run_benchmark(corpus, (config,), rounds=0, min_seconds=0.0)
    with pytest.raises(ValueError, match="min_seconds"):
        run_benchmark(corpus, (config,), rounds=1, min_seconds=-1.0)
    with pytest.raises(ValueError, match="limit"):
        run_benchmark(corpus, (config,), rounds=1, min_seconds=0.0, limit=0)


def test_the_corpus_checks_the_manifest_digest(corpus: Path):
    path = corpus / "manifest.csv"
    lines = path.read_text().splitlines()
    columns = lines[0].split(",")
    fields = lines[1].split(",")
    fields[columns.index("input_sha256")] = "0" * 64
    lines[1] = ",".join(fields)
    path.write_text("\n".join(lines) + "\n")

    with pytest.raises(ValueError, match="input_sha256"):
        load_samples(corpus)


def test_the_corpus_carries_the_grid_to_the_spec(tmp_path: Path):
    corpus = write_corpus(
        tmp_path / "fine",
        {"f-00": np.arange(8, dtype=np.uint16)},
        grid=0.01,
        grid_unit="mm/hr",
    )
    sample = load_samples(corpus)[0]
    assert sample.grid == 0.01
    assert sample.grid_unit == "mm/hr"
    assert sample.spec.grid == 0.01
    assert sample.spec.steps(0.04) == pytest.approx(4.0)
