"""Timing primitives. Protocol section 5."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import TypeVar

import numpy as np

T = TypeVar("T")

NANOSECONDS_PER_SECOND = 1_000_000_000
BYTES_PER_MEGABYTE = 1_000_000
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 0


def timed_round(operation: Callable[[], T], min_seconds: float) -> tuple[float, T]:
    """Repeat ``operation`` for ``min_seconds``; return mean time and last value."""
    minimum_ns = int(min_seconds * NANOSECONDS_PER_SECOND)
    count = 0
    started = time.perf_counter_ns()
    while True:
        value = operation()
        count += 1
        elapsed = time.perf_counter_ns() - started
        if elapsed > 0 and elapsed >= minimum_ns:
            return elapsed / count, value


def ci95_median(values: Sequence[float]) -> tuple[float, float]:
    """Percentile-bootstrap 95% confidence interval for the median."""
    samples = np.asarray(values, dtype=np.float64)
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    indices = generator.integers(
        0, len(samples), size=(BOOTSTRAP_SAMPLES, len(samples))
    )
    low, high = np.quantile(np.median(samples[indices], axis=1), (0.025, 0.975))
    return float(low), float(high)


def throughput_mb_s(input_bytes: int, elapsed_ns: float) -> float:
    """Decimal-megabyte throughput."""
    return input_bytes / BYTES_PER_MEGABYTE / (elapsed_ns / NANOSECONDS_PER_SECOND)
