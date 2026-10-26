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
from .metrics import Distortion, distortion, same_bytes
from .promises import Report, verify
from .timing import throughput_mb_s, timed, timed_series

RESULTS_FILENAME = "results.csv"

RESULT_COLUMNS = (
    "sample_id",
    "codec",
    "codec_version",
    "configuration",
    "mode",
    "tau",
    "budget_level",
    "input_bytes",
    "compressed_bytes",
    "compression_ratio",
    "bits_per_value",
    "encode_ns",
    "decode_ns",
    "decode_ns_min",
    "decode_ns_max",
    "encode_MB_s",
    "decode_MB_s",
    "max_abs_error",
    "mae",
    "rmse",
    "mean_error",
    "psnr_dB",
    "error_spread",
    "error_lag1",
    "sentinel_ok",
    "zero_ok",
    "fidelity_ok",
)

_EXACT = Distortion(0.0, 0.0, 0.0, 0.0, math.inf, math.nan, math.nan)


def _declaration(config: CodecConfiguration) -> dict[str, Any]:
    """The columns that record what the configuration declared."""
    budget = config.budget
    return {
        "codec": config.codec,
        "codec_version": config.version,
        "configuration": config.id,
        "mode": str(config.mode),
        "tau": "" if budget is None else repr(budget.tau),
        "budget_level": ""
        if budget is None or budget.level is None
        else str(budget.level),
    }


def _flag(value: bool | None) -> str:
    """A tri-state check: empty means the check did not apply."""
    return "" if value is None else str(value)


def determinism_samples(count: int) -> set[int]:
    """The first, middle, and last sample of the manifest."""
    return {0, count // 2, count - 1}


def _measure(
    sample: Sample, config: CodecConfiguration, reencode: bool
) -> dict[str, Any]:
    array = sample.data
    codec = config.factory(sample.spec)

    # Size, error, and an indicative encode time, from one call without warm-up.
    encode_ns, compressed = timed(lambda: codec.encode(array))
    decoded = codec.decode(compressed)
    report = _verified(config, array, decoded, sample)

    # Decode time on every sample; the decode above was the warm-up.
    decode_times, outputs = timed_series(lambda: codec.decode(compressed))
    for output in outputs:
        if not same_bytes(output, decoded):
            raise RuntimeError("determinism: repeated decodes differ")
    if reencode and codec.encode(array) != compressed:
        raise RuntimeError("determinism: a second encode gave different bytes")

    measured = (
        _EXACT
        if config.mode is Mode.LOSSLESS
        else distortion(array, decoded, sample.scale, sample.offset, sample.sentinel)
    )
    input_bytes = array.nbytes
    compressed_bytes = len(compressed)
    decode_ns = statistics.median(decode_times)

    row = {"sample_id": sample.id, **_declaration(config)}
    row.update(
        input_bytes=input_bytes,
        compressed_bytes=compressed_bytes,
        compression_ratio=input_bytes / compressed_bytes,
        bits_per_value=compressed_bytes * 8 / array.size,
        encode_ns=encode_ns,
        decode_ns=round(decode_ns),
        decode_ns_min=min(decode_times),
        decode_ns_max=max(decode_times),
        encode_MB_s=throughput_mb_s(input_bytes, encode_ns),
        decode_MB_s=throughput_mb_s(input_bytes, decode_ns),
        max_abs_error=measured.max_abs_error,
        mae=measured.mae,
        rmse=measured.rmse,
        mean_error=measured.mean_error,
        psnr_dB=measured.psnr_db,
        error_spread=measured.error_spread,
        error_lag1=measured.error_lag1,
        sentinel_ok=_flag(report.of(Promise.SENTINEL)),
        zero_ok=_flag(report.of(Promise.ZERO)),
        fidelity_ok=True,
    )
    return row


def _verified(
    config: CodecConfiguration,
    array: np.ndarray,
    decoded: np.ndarray,
    sample: Sample,
) -> Report:
    report = verify(
        config.mode,
        config.budget,
        array,
        decoded,
        sample.sentinel,
        sample.scale,
        sample.offset,
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


def _count(row: dict[str, Any]) -> int:
    """Element count of a result row."""
    return round(int(row["compressed_bytes"]) * 8 / float(row["bits_per_value"]))


def aggregate(rows: Sequence[dict[str, Any]], sample_count: int) -> dict[str, dict]:
    """Corpus totals per configuration. Protocol section 8: from sums, not averages."""
    totals: dict[str, dict] = {}
    for configuration in sorted({str(row["configuration"]) for row in rows}):
        selected = [
            row
            for row in rows
            if row["configuration"] == configuration and row["fidelity_ok"] is True
        ]
        if len(selected) != sample_count:
            totals[configuration] = {"complete": False}
            continue
        input_bytes = sum(int(row["input_bytes"]) for row in selected)
        compressed = sum(int(row["compressed_bytes"]) for row in selected)
        counts = [_count(row) for row in selected]
        count = sum(counts)
        totals[configuration] = {
            "complete": True,
            "mode": selected[0]["mode"],
            "tau": selected[0]["tau"],
            "budget_level": selected[0]["budget_level"],
            "compression_ratio": input_bytes / compressed,
            "bits_per_value": compressed * 8 / count,
            "encode_MB_s": throughput_mb_s(
                input_bytes, sum(int(r["encode_ns"]) for r in selected)
            ),
            "decode_MB_s": throughput_mb_s(
                input_bytes, sum(int(r["decode_ns"]) for r in selected)
            ),
            "max_abs_error": max(float(r["max_abs_error"]) for r in selected),
            "rmse": math.sqrt(
                sum(
                    float(r["rmse"]) ** 2 * n
                    for r, n in zip(selected, counts, strict=True)
                )
                / count
            ),
        }
    return totals


def _print_totals(rows: Sequence[dict[str, Any]], sample_count: int) -> None:
    print("\nCorpus totals")
    for configuration, total in aggregate(rows, sample_count).items():
        if not total["complete"]:
            print(f"  {configuration}: incomplete")
            continue
        line = (
            f"  {configuration} [{total['mode']}"
            f"{'' if not total['tau'] else ' tau=' + total['tau']}]: "
            f"ratio={total['compression_ratio']:.3f} "
            f"bpv={total['bits_per_value']:.3f} "
            f"enc={total['encode_MB_s']:.0f} "
            f"dec={total['decode_MB_s']:.0f} MB/s"
        )
        if total["mode"] != str(Mode.LOSSLESS):
            line += f" max_err={total['max_abs_error']:g} rmse={total['rmse']:g}"
        print(line)


def run_benchmark(
    corpus: Path,
    configs: Sequence[CodecConfiguration],
    *,
    limit: int | None = None,
) -> bool:
    """Measure ``configs`` over ``corpus`` and write results beside its samples."""
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

    reencode = determinism_samples(len(samples))
    rows: list[dict[str, Any]] = []
    all_ok = True
    for index, sample in enumerate(samples):
        print(f"{sample.id}")
        for config in active:
            try:
                row = _measure(sample, config, index in reencode)
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
    environment_path = write_environment(root, describe_environment())
    _print_totals(rows, len(samples))
    print(f"\nWrote {result_path}")
    print(f"Wrote {environment_path}")
    return all_ok
