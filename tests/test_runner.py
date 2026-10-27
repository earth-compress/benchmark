from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from conftest import write_corpus

from earthcompress import corpus as corpus_module
from earthcompress.codecs.base import CodecConfiguration, Family
from earthcompress.contract import Budget, Level, Mode
from earthcompress.corpus import load_samples
from earthcompress.runner import (
    RESULT_COLUMNS,
    aggregate,
    determinism_samples,
    run_benchmark,
)
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
    """Shifts every element by one step."""

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

    def decode(self, compressed: bytes) -> np.ndarray:
        return super().decode(compressed[: self._spec.nbytes])


class Raising(Identity):
    """Fails to encode at all."""

    def encode(self, array: np.ndarray) -> bytes:
        raise ValueError("unsupported input")


class Counting(Identity):
    calls = 0

    def decode(self, compressed: bytes) -> np.ndarray:
        Counting.calls += 1
        return super().decode(compressed)


def _config(factory, mode, budget=None, config_id="demo") -> CodecConfiguration:
    return CodecConfiguration(
        id=config_id,
        codec="demo",
        version="0",
        mode=mode,
        parameters={},
        factory=factory,
        budget=budget,
        family=Family.NATIVE if mode is Mode.NEAR_LOSSLESS else None,
    )


def _rows(corpus: Path) -> list[dict[str, str]]:
    with (corpus / "results.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def _run(corpus: Path, config: CodecConfiguration, **kwargs) -> bool:
    return run_benchmark(corpus, (config,), **kwargs)


def test_a_lossless_run_writes_results_and_environment(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS))

    rows = _rows(corpus)
    assert [row["sample_id"] for row in rows] == [f"demo-{i:02d}" for i in range(4)]
    for row in rows:
        assert list(row) == list(RESULT_COLUMNS)
        assert row["tau"] == "" and row["budget_level"] == ""
        assert row["fidelity_ok"] == "True"
        assert float(row["compression_ratio"]) == pytest.approx(1.0)
        assert float(row["bits_per_value"]) == pytest.approx(16.0)
        assert (
            int(row["decode_ns_min"])
            <= int(row["decode_ns"])
            <= int(row["decode_ns_max"])
        )

    environment = json.loads((corpus / "environment.json").read_text())
    assert environment["threads"] == 1 and environment["encode_calls"] == 1


def test_decode_runs_between_three_and_ten_times_plus_the_warm_up(corpus: Path):
    Counting.calls = 0
    assert _run(corpus, _config(Counting, Mode.LOSSLESS), limit=1)
    assert 1 + 3 <= Counting.calls <= 1 + 10


def test_a_near_lossless_run_records_its_declaration_and_error(corpus: Path):
    budget = Budget(tau=1.0, level=Level.MATCHED)
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, budget))

    for row in _rows(corpus):
        assert row["tau"] == "1.0" and row["budget_level"] == "matched"
        assert row["fidelity_ok"] == "True"
        assert float(row["max_abs_error"]) == 1.0
        assert float(row["mean_error"]) == 1.0


def test_the_bound_uses_the_scale_of_the_corpus(tmp_path: Path):
    data = np.arange(1, 65, dtype=np.uint16).reshape(8, 8)
    corpus = write_corpus(tmp_path / "fine", {"f-00": data}, scale="0.01", unit="mm/hr")
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, Budget(0.01)))
    assert float(_rows(corpus)[0]["max_abs_error"]) == pytest.approx(0.01)
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, Budget(0.005)))
    row = _rows(corpus)[0]
    assert row["status"] == "violation" and row["bound_violations"] == "64"


def test_moving_an_exact_zero_is_reported(tmp_path: Path):
    corpus = write_corpus(
        tmp_path / "zeros", {"z-00": np.array([[0, 0, 5, 9]], dtype=np.int16)}
    )
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, Budget(tau=2.0)))
    row = _rows(corpus)[0]
    assert row["fidelity_ok"] == "False" and row["zero_ok"] == "False"
    assert row["zero_violations"] == "2" and row["bound_violations"] == "0"


def test_the_quantiser_keeps_exact_zeros(tmp_path: Path):
    from earthcompress.codecs import configurations_for

    generator = np.random.default_rng(0)
    data = generator.integers(0, 500, size=(2, 64, 64), dtype=np.uint16)
    data[0, 0, :16] = 0
    corpus = write_corpus(tmp_path / "quant", {"q-00": data})
    near = [
        c
        for c in configurations_for("s2-l1c-10m-4")
        if c.mode is Mode.NEAR_LOSSLESS and c.family is not Family.NATIVE
    ]
    assert run_benchmark(corpus, tuple(near))
    for row in _rows(corpus):
        assert row["zero_ok"] == "True", row["configuration"]


def test_a_broken_promise_keeps_its_measurements(corpus: Path):
    budget = Budget(tau=0.5, level=Level.CONSERVATIVE)
    assert _run(corpus, _config(OffByOne, Mode.NEAR_LOSSLESS, budget))
    for row in _rows(corpus):
        assert row["fidelity_ok"] == "False" and row["status"] == "violation"
        assert float(row["compression_ratio"]) == pytest.approx(1.0)
        assert float(row["max_abs_error"]) == 1.0
        assert row["bound_violations"] == str(2 * 32 * 32)
        assert row["tau"] == "0.5" and row["budget_level"] == "conservative"


def test_a_crash_keeps_the_declaration_and_no_measurement(corpus: Path):
    budget = Budget(tau=0.5, level=Level.CONSERVATIVE)
    assert not _run(corpus, _config(Raising, Mode.NEAR_LOSSLESS, budget))
    for row in _rows(corpus):
        assert row["status"] == "crash" and row["fidelity_ok"] == "False"
        assert row["compressed_bytes"] == "" and row["tau"] == "0.5"


def test_a_run_replaces_only_the_rows_of_its_configurations(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS, config_id="kept"))
    assert _run(corpus, _config(Identity, Mode.LOSSLESS, config_id="new"), limit=1)
    assert _run(corpus, _config(Identity, Mode.LOSSLESS, config_id="new"), limit=2)
    rows = _rows(corpus)
    assert [row["configuration"] for row in rows] == ["kept"] * 4 + ["new"] * 2


def test_lossy_mode_checks_sentinels(tmp_path: Path):
    corpus = write_corpus(
        tmp_path / "lossy",
        {"l-00": np.array([[0, 5, 7, 9]], dtype=np.int16)},
        nodata="0",
    )
    assert _run(corpus, _config(OffByOne, Mode.LOSSY))
    row = _rows(corpus)[0]
    assert row["sentinel_ok"] == "False" and row["sentinel_violations"] == "1"
    corpus = write_corpus(
        tmp_path / "plain", {"p-00": np.array([[3, 5, 7, 9]], dtype=np.int16)}
    )
    assert _run(corpus, _config(OffByOne, Mode.LOSSY))


def test_a_second_encode_runs_on_the_first_middle_and_last_sample(corpus: Path):
    assert determinism_samples(4) == {0, 2, 3}
    assert not _run(corpus, _config(Restless, Mode.LOSSLESS))
    flags = [row["fidelity_ok"] for row in _rows(corpus)]
    assert flags == ["False", "True", "False", "False"]


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
    assert run_benchmark(corpus, (config,))
    assert _rows(corpus) == []


def test_limit_selects_the_first_samples(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS), limit=1)
    assert [row["sample_id"] for row in _rows(corpus)] == ["demo-00"]
    with pytest.raises(ValueError, match="limit"):
        _run(corpus, _config(Identity, Mode.LOSSLESS), limit=0)


def test_totals_come_from_sums_and_need_every_sample(corpus: Path):
    assert _run(corpus, _config(Identity, Mode.LOSSLESS))
    rows = [
        {**row, "fidelity_ok": row["fidelity_ok"] == "True"} for row in _rows(corpus)
    ]
    total = aggregate(rows, len(rows))["demo"]
    assert total["complete"] and total["compression_ratio"] == pytest.approx(1.0)
    assert aggregate(rows[:-1], len(rows))["demo"] == {"complete": False}


def test_the_corpus_checks_the_manifest_digest(corpus: Path):
    path = corpus / "manifest.csv"
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["input_sha256"] = "0" * 64
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="input_sha256"):
        load_samples(corpus)


def test_the_corpus_carries_scale_offset_and_sentinel_to_the_sample(tmp_path: Path):
    corpus = write_corpus(
        tmp_path / "planes",
        {"p-00": np.arange(16, dtype=np.uint16).reshape(2, 2, 4)},
        scale="0.25|0.5",
        offset="10|-3",
        nodata="0",
    )
    sample = load_samples(corpus)[0]
    assert sample.scale == (0.25, 0.5) and sample.offset == (10.0, -3.0)
    assert sample.sentinel == 0.0
    assert sample.spec.steps(1.0) == 2


def test_the_corpus_downloads_only_the_missing_samples(corpus: Path, monkeypatch):
    removed = corpus / "npz" / "demo-01.npz.zst"
    kept = removed.read_bytes()
    removed.unlink()
    calls = []

    def fake(repo_id, *, repo_type, allow_patterns, local_dir):
        calls.append((repo_id, repo_type, allow_patterns, Path(local_dir)))
        removed.write_bytes(kept)

    monkeypatch.setattr(corpus_module, "snapshot_download", fake)
    assert len(load_samples(corpus)) == 4
    assert calls == [
        (
            "earth-compress/benchmark",
            "dataset",
            ["demo/npz/demo-01.npz.zst"],
            corpus.parent,
        )
    ]
