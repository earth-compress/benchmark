"""Discovery of codec configurations.

A module declares `CONFIGURATIONS` for operating points that stand on their own
(lossless and lossy), and `FAMILIES` for near-lossless codecs, whose budget is a
property of the corpus and so cannot be registered globally.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..budgets import budgets_for
from ..contract import Budget
from .base import Codec, CodecConfiguration

Family = Callable[[Budget], CodecConfiguration]


def _modules():
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if info.name == "base" or info.name.startswith("_"):
            continue
        yield importlib.import_module(f"{__name__}.{info.name}")


def _unique(discovered: list[CodecConfiguration]) -> tuple[CodecConfiguration, ...]:
    counts = Counter(config.id for config in discovered)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        raise RuntimeError(f"duplicate codec configuration: {', '.join(duplicates)}")
    return tuple(discovered)


def fixed() -> tuple[CodecConfiguration, ...]:
    """Configurations that do not depend on a corpus."""
    discovered: list[CodecConfiguration] = []
    for module in _modules():
        discovered.extend(getattr(module, "CONFIGURATIONS", ()))
    return _unique(discovered)


def families() -> tuple[Family, ...]:
    """Near-lossless codecs awaiting a budget."""
    found: list[Family] = []
    for module in _modules():
        found.extend(getattr(module, "FAMILIES", ()))
    return tuple(found)


def configurations_for(
    corpus: str, registry: Path | None = None
) -> tuple[CodecConfiguration, ...]:
    """Every configuration measurable on ``corpus``.

    The fixed ones, plus one per near-lossless family and declared budget. A
    corpus with no budgets yields only the fixed ones, which is the correct
    answer for a corpus whose values are not quantities.
    """
    discovered = list(fixed())
    budgets = budgets_for(corpus, registry)
    for make in families():
        for budget in budgets.values():
            discovered.append(make(budget))
    return _unique(discovered)


__all__ = [
    "Codec",
    "CodecConfiguration",
    "configurations_for",
    "families",
    "fixed",
]
