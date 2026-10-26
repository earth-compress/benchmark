from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

NANOSECONDS_PER_SECOND = 1_000_000_000
BYTES_PER_MEGABYTE = 1_000_000

DECODE_MAX_CALLS = 10
DECODE_MIN_CALLS = 3
DECODE_SECONDS = 0.5


def timed(operation: Callable[[], T]) -> tuple[int, T]:
    """One call of ``operation``, its time in nanoseconds and its value."""
    started = time.perf_counter_ns()
    value = operation()
    return time.perf_counter_ns() - started, value


def timed_series(
    operation: Callable[[], T],
    max_calls: int = DECODE_MAX_CALLS,
    min_calls: int = DECODE_MIN_CALLS,
    seconds: float = DECODE_SECONDS,
) -> tuple[list[int], list[T]]:
    """Call ``operation`` up to ``max_calls`` times, stopping after ``seconds``."""
    limit = int(seconds * NANOSECONDS_PER_SECOND)
    times: list[int] = []
    values: list[T] = []
    while len(times) < max_calls:
        elapsed, value = timed(operation)
        times.append(elapsed)
        values.append(value)
        if len(times) >= min_calls and sum(times) >= limit:
            break
    return times, values


def throughput_mb_s(input_bytes: int, elapsed_ns: float) -> float:
    """Decimal-megabyte throughput."""
    return input_bytes / BYTES_PER_MEGABYTE / (elapsed_ns / NANOSECONDS_PER_SECOND)
