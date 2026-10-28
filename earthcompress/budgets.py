from __future__ import annotations

import csv
from pathlib import Path

from .contract import Budget, Level, Mode

BUDGETS_FILENAME = "budgets.csv"
_DEFAULT = Path(__file__).resolve().parent.parent / "docs" / BUDGETS_FILENAME
_BOUNDED = f"{Mode.NEAR_LOSSLESS} {Mode.LOSSY}"


def load_budgets(
    path: Path | None = None, mode: Mode = Mode.NEAR_LOSSLESS
) -> dict[str, dict[Level, Budget]]:
    """Read the budgets of ``mode``, keyed by corpus id and then by level.

    The ``modes`` column lists the modes a budget applies to. A registry
    without it applies every budget to both bounded modes.
    """
    source = path or _DEFAULT
    if not source.is_file():
        raise FileNotFoundError(f"missing budget registry: {source}")

    registry: dict[str, dict[Level, Budget]] = {}
    seen: set[tuple[str, Level]] = set()
    with source.open(newline="") as stream:
        for row in csv.DictReader(stream):
            corpus, level = row["corpus"], Level(row["level"])
            if (corpus, level) in seen:
                raise ValueError(f"{corpus}: duplicate level {level}")
            seen.add((corpus, level))
            modes = {Mode(name) for name in (row.get("modes") or _BOUNDED).split()}
            if Mode.LOSSLESS in modes:
                raise ValueError(f"{corpus}: lossless takes no budget")
            levels = registry.setdefault(corpus, {})
            if mode in modes:
                levels[level] = Budget(tau=float(row["tau"]), level=level)
    return registry


def budgets_for(
    corpus: str, path: Path | None = None, mode: Mode = Mode.NEAR_LOSSLESS
) -> dict[Level, Budget]:
    """The budgets ``mode`` uses on ``corpus``, in level order."""
    levels = load_budgets(path, mode).get(corpus, {})
    return {level: levels[level] for level in Level if level in levels}
