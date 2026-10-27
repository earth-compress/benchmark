from __future__ import annotations

import importlib
import pkgutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..budgets import budgets_for
from ..contract import Budget
from . import quantize
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


def reference() -> tuple[CodecConfiguration, ...]:
    """Configurations measured once, as a reference line, not in every run."""
    return _unique(
        [config for module in _modules() for config in getattr(module, "REFERENCE", ())]
    )


def natives() -> tuple[Family, ...]:
    """Near-lossless configurations of codecs with a bounded mode of their own."""
    found: list[Family] = []
    for module in _modules():
        found.extend(getattr(module, "FAMILIES", ()))
    return tuple(found)


def families() -> tuple[Family, ...]:
    """Every near-lossless configuration awaiting a budget.

    The native ones, then the shared quantiser in front of a few lossless
    configurations.
    """
    by_id = {config.id: config for config in fixed()}
    return natives() + tuple(quantize.family(by_id[name]) for name in quantize.BACKENDS)


def configurations_for(
    corpus: str, registry: Path | None = None
) -> tuple[CodecConfiguration, ...]:
    """Every configuration measurable on ``corpus``."""
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
    "natives",
]
