"""The error budgets of `TOLERANCE.md`, in machine-readable form.

Protocol section 3: a budget is declared before the run and is identical for
every sample of the corpus. It is therefore a property of the corpus, not of a
codec, which is why a near-lossless configuration is built per corpus rather
than registered globally.

A corpus absent from the registry has no near-lossless point, either because
its values are not quantities or because its headroom is one grid step. That is
a result, not an omission.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .contract import BoundKind, Budget, Level

BUDGETS_FILENAME = "budgets.csv"
_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / BUDGETS_FILENAME


def load_budgets(path: Path | None = None) -> dict[str, dict[Level, Budget]]:
    """Read the budget registry, keyed by corpus id and then by level."""
    source = path or _DEFAULT
    if not source.is_file():
        raise FileNotFoundError(f"missing budget registry: {source}")

    registry: dict[str, dict[Level, Budget]] = {}
    with source.open(newline="") as stream:
        for row in csv.DictReader(stream):
            level = Level(row["level"])
            budget = Budget(
                tau=float(row["tau"]),
                kind=BoundKind(row["kind"]),
                level=level,
            )
            levels = registry.setdefault(row["corpus"], {})
            if level in levels:
                raise ValueError(f"{row['corpus']}: duplicate level {level}")
            levels[level] = budget
    return registry


def budgets_for(corpus: str, path: Path | None = None) -> dict[Level, Budget]:
    """The budgets declared for ``corpus``, in level order."""
    levels = load_budgets(path).get(corpus, {})
    return {level: levels[level] for level in Level if level in levels}
