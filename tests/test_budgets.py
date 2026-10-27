from __future__ import annotations

from pathlib import Path

import pytest

from earthcompress.budgets import budgets_for, load_budgets
from earthcompress.contract import Level

LOSSLESS_ONLY = (
    "esa-wc-v200",
    "tessera-v2-codes",
    "tessera-v2-scales",
    "alphaearth-v1-64",
    "goes-abi-16",
    "s1-grd-iw-2",
)


def test_the_shipped_registry_loads():
    registry = load_budgets()
    assert "s2-l1c-10m-4" in registry
    assert all(
        budget.tau > 0 for levels in registry.values() for budget in levels.values()
    )


def test_budgets_come_back_in_level_order_and_rise_with_it():
    levels = budgets_for("s2-l1c-10m-4")
    assert list(levels) == [Level.CONSERVATIVE, Level.MATCHED, Level.AGGRESSIVE]
    taus = [budget.tau for budget in levels.values()]
    assert taus == sorted(taus)


@pytest.mark.parametrize(
    ("corpus", "levels"),
    [
        ("s2-l1c-60m-3", [Level.MATCHED, Level.AGGRESSIVE]),
        ("l5-tm-6", [Level.MATCHED, Level.AGGRESSIVE]),
        ("l5-tm-tir", [Level.AGGRESSIVE]),
    ],
)
def test_levels_below_one_step_are_left_out(corpus, levels):
    assert list(budgets_for(corpus)) == levels


@pytest.mark.parametrize("corpus", LOSSLESS_ONLY)
def test_lossless_only_corpora_have_no_budget(corpus):
    assert budgets_for(corpus) == {}


def test_a_duplicate_level_is_rejected(tmp_path: Path):
    path = tmp_path / "budgets.csv"
    path.write_text("corpus,level,tau\nx,matched,1\nx,matched,2\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_budgets(path)


def test_a_missing_registry_is_an_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_budgets(tmp_path / "absent.csv")


def test_only_era5_has_the_recommended_level():
    registry = load_budgets()
    recommended = {
        corpus for corpus, levels in registry.items() if Level.RECOMMENDED in levels
    }
    assert recommended == {
        "era5-t2m-1h",
        "era5-msl-1h",
        "era5-u10-1h",
        "era5-tcc-1h",
        "era5-tp-1h",
    }
    assert budgets_for("era5-msl-1h")[Level.RECOMMENDED].tau == 1.0
