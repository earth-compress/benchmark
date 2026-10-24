from __future__ import annotations

from pathlib import Path

import pytest

from earthcompress.budgets import budgets_for, load_budgets
from earthcompress.contract import BoundKind, Level

REGISTRY = Path(__file__).resolve().parent.parent / "docs" / "budgets.csv"


def test_the_shipped_registry_loads():
    registry = load_budgets()
    assert registry
    for corpus, levels in registry.items():
        assert levels, corpus
        for level, budget in levels.items():
            assert budget.level is level
            assert budget.tau > 0


def test_budgets_come_back_in_level_order():
    levels = list(budgets_for("s2-l1c-10m-4"))
    assert levels == [Level.CONSERVATIVE, Level.MATCHED, Level.AGGRESSIVE]


def test_a_budget_rises_with_its_level():
    budgets = budgets_for("s2-l1c-10m-4")
    taus = [budgets[level].tau for level in budgets]
    assert taus == sorted(taus)
    assert taus[0] < taus[-1]


def test_low_headroom_corpora_lose_the_strict_levels():
    """Protocol 3: a level below one grid step does not exist."""
    # Headroom 4: conservative would be 0.8 m on a 1 m grid.
    assert set(budgets_for("cop-dem-glo30")) == {Level.MATCHED, Level.AGGRESSIVE}
    # Headroom 2: one count is already half the NEdT.
    assert set(budgets_for("goes-abi-16")) == {Level.MATCHED, Level.AGGRESSIVE}
    # Headroom 1: eight bits are already at the noise floor.
    for corpus in ("lm-mss-4", "l5-tm-6", "l7-etm-pan"):
        assert set(budgets_for(corpus)) == {Level.AGGRESSIVE}, corpus


def test_corpora_whose_values_are_not_quantities_have_no_budget():
    for corpus in ("esa-wc-v200", "tessera-v2-128", "alphaearth-v1-64"):
        assert budgets_for(corpus) == {}, corpus


def test_an_unknown_corpus_has_no_budget_rather_than_raising():
    assert budgets_for("not-a-corpus") == {}


def test_every_registry_bound_is_a_near_lossless_kind():
    for levels in load_budgets().values():
        for budget in levels.values():
            assert budget.kind in {BoundKind.ABSOLUTE, BoundKind.RELATIVE}


def test_a_duplicate_level_is_rejected(tmp_path: Path):
    path = tmp_path / "budgets.csv"
    path.write_text(
        "corpus,level,tau,kind,grid_steps\n"
        "demo,matched,1,absolute,1\n"
        "demo,matched,2,absolute,2\n"
    )
    with pytest.raises(ValueError, match="duplicate level"):
        load_budgets(path)


def test_a_missing_registry_is_an_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_budgets(tmp_path / "absent.csv")
