"""E-015's registered rule, and the check that says its grid is trustworthy.

Chain reach is monotone in both limits by construction: raising a frontier cap
or a token budget can only add evidence, and evidence is never subtracted by
having more room. So a cell where reach *falls* as a limit rises is a harness
bug, not a finding, and the entry says no number is read until it is explained.

That check has to be able to fire, which is what most of this file tests. The
branch rule is tested as a pure function, including the boundaries and the case
it exists to prevent — a single lucky cell above 0.20 being read as a licence to
change shipped trimming.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e015 as e015


def cell(
    frontier: int,
    budget: int,
    reached: int,
    n: int = 100,
    items: int = 200,
    kind_cap: int = 1000,
) -> dict:
    return {
        "frontier_cap": frontier,
        "token_budget": budget,
        "kind_cap": kind_cap,
        "n": n,
        "reached": reached,
        "reach": reached / n,
        "low": 0.0,
        "high": 1.0,
        "median_items": items,
        "median_tokens": items * 12,
    }


# --- monotonicity: the check that can return negative ------------------------


def test_a_monotone_grid_raises_nothing():
    rows = [
        cell(400, 6000, 3),
        cell(400, 24000, 12),
        cell(1600, 6000, 9),
        cell(1600, 24000, 40),
    ]
    assert e015.monotonicity(rows) == []


def test_reach_falling_as_the_budget_rises_is_reported():
    rows = [cell(400, 6000, 30), cell(400, 24000, 11)]
    complaints = e015.monotonicity(rows)
    assert len(complaints) == 1
    assert "falls from 30/100" in complaints[0]


def test_reach_falling_as_the_frontier_rises_is_reported():
    rows = [cell(400, 6000, 30), cell(1600, 6000, 11)]
    assert len(e015.monotonicity(rows)) == 1


def test_the_check_compares_across_both_limits_at_once():
    # (1600, 24000) dominates (400, 6000) on both axes, so it may not be lower
    # even though neither single axis was compared directly.
    rows = [cell(400, 6000, 30), cell(1600, 24000, 20)]
    assert len(e015.monotonicity(rows)) == 1


def test_incomparable_cells_are_not_compared():
    # Higher frontier, lower budget: neither dominates, so no claim is made.
    rows = [cell(400, 24000, 30), cell(1600, 6000, 11)]
    assert e015.monotonicity(rows) == []


def test_equal_reach_at_a_larger_limit_is_allowed():
    """A limit that buys nothing is a result, not a bug."""
    rows = [cell(400, 6000, 12), cell(1600, 96000, 12)]
    assert e015.monotonicity(rows) == []


# --- the registered branch rule ----------------------------------------------


def test_one_cell_above_the_upper_bound_is_branch_1():
    rows = [cell(400, 6000, 3), cell(1600, 96000, 61)]
    assert e015.branch(rows) == "1"


def test_every_cell_below_the_lower_bound_is_branch_2():
    rows = [cell(400, 6000, 3), cell(1600, 6000, 9), cell(1600, 96000, 19)]
    assert e015.branch(rows) == "2"


def test_a_single_cell_clearing_only_the_lower_bound_is_branch_3():
    """The case the middle band exists to prevent being read as branch 1."""
    rows = [cell(400, 6000, 3), cell(1600, 96000, 25)]
    assert e015.branch(rows) == "3"


def test_the_boundaries_are_exclusive_as_registered():
    # Branch 1 needs reach strictly above 0.50; branch 2 strictly below 0.20.
    assert e015.branch([cell(400, 6000, 50)]) == "3"
    assert e015.branch([cell(400, 6000, 51)]) == "1"
    assert e015.branch([cell(400, 6000, 20)]) == "3"
    assert e015.branch([cell(400, 6000, 19)]) == "2"


def test_the_shipped_measurement_so_far_would_read_branch_2():
    """10 of 300 on the confirmatory split is 0.033 — the number that
    motivated the entry must not already satisfy branch 1, or the rule was
    drawn around its own answer."""
    assert e015.branch([cell(400, 6000, 33, n=1000)]) == "2"


# --- median ------------------------------------------------------------------


def test_median_of_an_empty_cell_is_zero_not_an_error():
    assert e015.median([]) == 0


def test_median_ignores_arrival_order():
    assert e015.median([9, 1, 5]) == e015.median([1, 5, 9]) == 5


@pytest.mark.parametrize("values,expected", [([1, 2], 2), ([1, 2, 3, 4], 3)])
def test_the_even_case_takes_the_upper_middle(values, expected):
    # Documented rather than left to be discovered: it is the same rule
    # run_e010 uses, so the two entries report the same quantity.
    assert e015.median(values) == expected


# --- amendment 2026-09-13b: the third axis ------------------------------------


def test_kind_cap_is_part_of_the_monotonicity_key():
    """Two cells differing only in kind_cap must both be compared.

    Before the amendment the key named frontier and budget only, so a third
    axis would have collapsed two cells onto one entry and dropped the
    comparison without saying anything.
    """
    rows = [cell(400, 96000, 65, kind_cap=1000), cell(400, 96000, 40, kind_cap=4000)]
    complaints = e015.monotonicity(rows)
    assert len(complaints) == 1
    assert "kind_cap" in complaints[0]


def test_a_larger_kind_cap_with_equal_reach_is_allowed():
    rows = [cell(400, 96000, 65, kind_cap=1000), cell(400, 96000, 65, kind_cap=16000)]
    assert e015.monotonicity(rows) == []


def test_two_cells_at_the_same_setting_are_reported_rather_than_silently_dropped():
    rows = [cell(400, 96000, 65), cell(400, 96000, 65)]
    assert any("share the setting" in line for line in e015.monotonicity(rows))


def test_the_run_that_fired_branch_1_is_monotone_and_reads_branch_1():
    """The dev grid as it actually came back on 2026-09-13."""
    rows = [
        cell(f, b, r, items=i)
        for f in (400, 1600)
        for b, r, i in ((6000, 3, 207), (24000, 18, 837), (96000, 65, 2007))
    ]
    assert e015.monotonicity(rows) == []
    assert e015.branch(rows) == "1"
