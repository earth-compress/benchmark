"""Steps shared by the use cases in ``usecases/``."""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from .codecs import families
from .codecs.base import CodecConfiguration
from .contract import Budget
from .spec import ArraySpec


def configurations(
    budgets: Iterable[Budget], spec: ArraySpec
) -> list[CodecConfiguration]:
    """Every near-lossless configuration at each budget that accepts ``spec``."""
    found = []
    for budget in budgets:
        for make in families():
            config = make(budget)
            if config.supports(spec):
                found.append(config)
    return found


def roundtrip(
    config: CodecConfiguration, array: np.ndarray, spec: ArraySpec
) -> np.ndarray:
    """``array`` as ``config`` decodes it."""
    codec = config.factory(spec)
    return codec.decode(codec.encode(array))


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union of two masks, 1 when both are empty."""
    union = np.count_nonzero(a | b)
    return 1.0 if union == 0 else np.count_nonzero(a & b) / union


def run(
    task: Callable[[Any], list[dict[str, Any]]],
    items: Sequence[Any],
    path: Path,
) -> list[dict[str, Any]]:
    """``task`` on every item in parallel, its rows written to ``path``."""
    with ProcessPoolExecutor() as pool:
        rows = [row for rows in pool.map(task, items) for row in rows]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows
