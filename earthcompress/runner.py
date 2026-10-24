"""Measurement of codec configurations over a corpus. Protocol sections 5 to 8."""

from __future__ import annotations

import csv
import math
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .codecs.base import CodecConfiguration
from .contract import Mode, Promise
from .corpus import Sample, load_samples
from .environment import describe_environment, write_environment
from .metrics import Distortion, distortion
from .promises import Report, verify
from .timing import ci95_median, throughput_mb_s, timed_round

RESULTS_FILENAME = "results.csv"

RESULT_COLUMNS = (
    "sample_id",
    "codec",
    "codec_version",
    "configuration",
    "mode",
    "bound_kind",
    "tau",
    "budget_level",
    "input_bytes",
    "compressed_bytes",
    "compression_ratio",
    "bits_per_value",
    "encode_ns",
    "decode_ns",
    "encode_MB_s",
    "decode_MB_s",
    "encode_MB_s_ci95_low",
    "encode_MB_s_ci95_high",
    "decode_MB_s_ci95_low",
    "decode_MB_s_ci95_high",
    "max_abs_error",
    "mae",
    "rmse",
    "psnr_dB",
    "error_spread",
    "error_lag1",
    "exact",
    "sentinel_ok",
    "zero_ok",
    "subnormals_ok",
    "fidelity_ok",
    "converted",
)

_EXACT = Distortion(0.0, 0.0, 0.0, math.inf, math.nan, math.nan)


def _declaration(config: CodecConfiguration) -> dict[str, Any]:
    """The columns that record what the configuration declared."""
    budget = config.budget
    return {
        "codec": config.codec,
        "codec_version": config.version,
        "configuration": config.id,
        "mode": str(config.mode),
        "bound_kind": "" if budget is None else str(budget.kind),
        "tau": "" if budget is None else repr(budget.tau),
        "budget_level": ""
        if budget is None or budget.level is None
        else str(budget.level),
    }


def _flag(value: bool | None) -> str:
    """A tri-state check: empty means the check did not apply."""
    return "" if value is None else str(value)


def _measure(
    sample: Sample,
    config: CodecConfiguration,
    rounds: int,
    min_seconds: float,
) -> dict[str, Any]:
    array = sample.data
    codec = config.factory(sample.spec)

    # Untimed warm-up, and the first verification.
    compressed = codec.encode(array)
    report = _verified(config, array, codec.decode(compressed), sample)

    encode_times: list[float] = []
    for _ in range(rounds):
        elapsed, repeat = timed_round(lambda: codec.encode(array), min_seconds)
        encode_times.append(elapsed)
        if repeat != compressed:
            raise RuntimeError("encoding is not deterministic: bytes changed")

    decode_times: list[float] = []
    decoded = codec.decode(compressed)
    for _ in range(rounds):
        elapsed, repeat = timed_round(lambda: codec.decode(compressed), min_seconds)
        decode_times.append(elapsed)
        if not np.array_equal(repeat, decoded, equal_nan=True):
            raise RuntimeError("decoding is not deterministic: output changed")

    # Verify again on the last timed decode, as the protocol requires.
    report = _verified(config, array, decoded, sample)
    measured = _EXACT if config.mode is Mode.LOSSLESS else distortion(array, decoded)

    input_bytes = array.nbytes
    compressed_bytes = len(compressed)
    encode_ns = statistics.median(encode_times)
    decode_ns = statistics.median(decode_times)
    encode_low, encode_high = ci95_median(
        [throughput_mb_s(input_bytes, value) for value in encode_times]
    )
    decode_low, decode_high = ci95_median(
        [throughput_mb_s(input_bytes, value) for value in decode_times]
    )

    row = {"sample_id": sample.id, **_declaration(config)}
    row.update(
        input_bytes=input_bytes,
        compressed_bytes=compressed_bytes,
        compression_ratio=input_bytes / compressed_bytes,
        bits_per_value=compressed_bytes * 8 / array.size,
        encode_ns=round(encode_ns),
        decode_ns=round(decode_ns),
        encode_MB_s=throughput_mb_s(input_bytes, encode_ns),
        decode_MB_s=throughput_mb_s(input_bytes, decode_ns),
        encode_MB_s_ci95_low=encode_low,
        encode_MB_s_ci95_high=encode_high,
        decode_MB_s_ci95_low=decode_low,
        decode_MB_s_ci95_high=decode_high,
        max_abs_error=measured.max_abs_error,
        mae=measured.mae,
        rmse=measured.rmse,
        psnr_dB=measured.psnr_db,
        error_spread=measured.error_spread,
        error_lag1=measured.error_lag1,
        exact=measured.exact,
        sentinel_ok=_flag(report.of(Promise.SENTINEL)),
        zero_ok=_flag(report.of(Promise.ZERO)),
        subnormals_ok=_flag(report.subnormals_ok),
        fidelity_ok=True,
        converted=False,
    )
    return row


def _verified(
    config: CodecConfiguration,
    array: np.ndarray,
    decoded: np.ndarray,
    sample: Sample,
) -> Report:
    report = verify(
        config.mode, config.budget, array, decoded, sample.sentinel, sample.grid
    )
    if not report.ok:
        raise RuntimeError(
            "; ".join(f"{v.promise}: {v.detail}" for v in report.failures)
        )
    return report


def _failure(sample: Sample, config: CodecConfiguration) -> dict[str, Any]:
    row = dict.fromkeys(RESULT_COLUMNS, "")
    row.update(
        sample_id=sample.id,
        **_declaration(config),
        input_bytes=sample.data.nbytes,
        fidelity_ok=False,
    )
    return row


def _write_results(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _describe(row: dict[str, Any]) -> str:
    text = (
        f"ratio={row['compression_ratio']:.3f} "
        f"bpv={row['bits_per_value']:.2f} "
        f"enc={row['encode_MB_s']:.0f} dec={row['decode_MB_s']:.0f} MB/s"
    )
    if row["mode"] != str(Mode.LOSSLESS):
        text += (
            f" err={row['max_abs_error']:g}"
            f" spread={row['error_spread']:.2f}"
            f" lag1={row['error_lag1']:+.2f}"
        )
    return text


def _print_totals(rows: Sequence[dict[str, Any]], sample_count: int) -> None:
    """Corpus totals. Protocol section 8.1: from sums, never from averages."""
    print("\nCorpus totals")
    for configuration in sorted({str(row["configuration"]) for row in rows}):
        selected = [
            row
            for row in rows
            if row["configuration"] == configuration and row["fidelity_ok"] is True
        ]
        if len(selected) != sample_count:
            print(f"  {configuration}: incomplete")
            continue
        input_bytes = sum(int(row["input_bytes"]) for row in selected)
        compressed = sum(int(row["compressed_bytes"]) for row in selected)
        encode_ns = sum(int(row["encode_ns"]) for row in selected)
        decode_ns = sum(int(row["decode_ns"]) for row in selected)
        line = (
            f"  {configuration} [{selected[0]['mode']}"
            f"{'' if not selected[0]['tau'] else ' tau=' + selected[0]['tau']}]: "
            f"ratio={input_bytes / compressed:.3f} "
            f"enc={throughput_mb_s(input_bytes, encode_ns):.0f} "
            f"dec={throughput_mb_s(input_bytes, decode_ns):.0f} MB/s"
        )
        if selected[0]["mode"] != str(Mode.LOSSLESS):
            line += f" worst_err={max(float(r['max_abs_error']) for r in selected):g}"
        print(line)


def run_benchmark(
    corpus: Path,
    configs: Sequence[CodecConfiguration],
    *,
    rounds: int,
    min_seconds: float,
    limit: int | None = None,
) -> bool:
    """Measure ``configs`` over ``corpus`` and write results beside its samples."""
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    if min_seconds < 0:
        raise ValueError("min_seconds must be non-negative")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    samples = load_samples(corpus, limit=limit)
    specs = tuple(sample.spec for sample in samples)
    active: list[CodecConfiguration] = []
    for config in configs:
        if all(config.supports(spec) for spec in specs):
            active.append(config)
        else:
            print(f"Skipping {config.id}: incompatible with this corpus")

    rows: list[dict[str, Any]] = []
    all_ok = True
    for sample in samples:
        print(f"{sample.id}")
        for config in active:
            try:
                row = _measure(sample, config, rounds, min_seconds)
            except Exception as error:  # noqa: BLE001 - codec failures are data
                all_ok = False
                row = _failure(sample, config)
                print(f"  {config.id}: FAILED: {error}")
            else:
                print(f"  {config.id}: {_describe(row)}")
            rows.append(row)

    root = corpus.resolve()
    result_path = root / RESULTS_FILENAME
    _write_results(result_path, rows)
    environment_path = write_environment(
        root, describe_environment(rounds=rounds, min_seconds=min_seconds)
    )
    _print_totals(rows, len(samples))
    print(f"\nWrote {result_path}")
    print(f"Wrote {environment_path}")
    return all_ok
