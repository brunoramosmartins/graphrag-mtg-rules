"""The gate that binds E-010 to E-001, and the median it reads.

E-010 amendment item 7 registered a consequence that lands on a *different*
experiment: past a 3x median ratio in retrieved items at matched token budget,
E-001's retrieval comparison is published as budget-confounded. A rule stored
in one entry's amendment and due to fire on another entry's result is the kind
that gets lost, so `run_e010.py proxy` applies it itself and prints the verdict.

These tests pin the gate's arithmetic and its boundary. The boundary matters:
"more than 3x" and "3x or more" differ by exactly the case most likely to occur.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e010 as e010


class TestMedian:
    def test_odd_length_takes_the_middle(self) -> None:
        assert e010.median([5, 1, 3]) == 3.0

    def test_even_length_averages_the_two_middles(self) -> None:
        assert e010.median([1, 2, 3, 4]) == 2.5

    def test_it_does_not_assume_sorted_input(self) -> None:
        assert e010.median([40, 1, 2, 39]) == 20.5

    def test_empty_is_zero_not_a_crash(self) -> None:
        # An arm that retrieved nothing on every question is a defect to
        # report, not an exception to raise inside a reporting function.
        assert e010.median([]) == 0.0


class TestBudgetGate:
    def test_it_fires_above_three(self, capsys) -> None:
        confounded = e010.budget_confound({"A": [40, 41], "B": [12, 12]})
        assert confounded is True
        assert "BUDGET-CONFOUNDED" in capsys.readouterr().out

    def test_it_does_not_fire_at_exactly_three(self, capsys) -> None:
        # Registered as "exceeds by more than 3x". Equality is not exceeding,
        # and this is the case a sloppy `>=` would silently flip.
        confounded = e010.budget_confound({"A": [36, 36], "B": [12, 12]})
        assert confounded is False
        assert "not flagged confounded" in capsys.readouterr().out

    def test_it_compares_every_pair_not_just_the_first(self, capsys) -> None:
        # The ratio that matters is the largest one present, whichever arms it
        # falls between — checking only A-vs-B would miss a confound between
        # the hybrid and the graph.
        confounded = e010.budget_confound({"A": [13], "B": [12], "C": [50]})
        assert confounded is True
        assert "4.17x" in capsys.readouterr().out

    def test_a_zero_median_is_reported_not_divided_by(self, capsys) -> None:
        """An arm that retrieved nothing on half its questions is the story.

        The first version divided anyway, found no valid pair, compared arm A
        against itself for a tidy 1.00x, and returned "not confounded" — which
        is the gate reporting *clean* for the most confounded run this harness
        can produce. It now says so and returns True.
        """
        assert e010.budget_confound({"A": [10], "B": []}) is True
        out = capsys.readouterr().out
        assert "retrieved nothing" in out
        assert "A / A" not in out

    def test_self_pairs_are_never_the_largest_ratio(self, capsys) -> None:
        e010.budget_confound({"A": [12], "B": [12]})
        assert "A / A" not in capsys.readouterr().out

    def test_the_registered_ratio_is_three(self) -> None:
        # Concepts transfer, constants do not — but this constant is registered
        # rather than borrowed, and changing it changes a published verdict.
        assert e010.BUDGET_CONFOUND_RATIO == 3.0


def test_use_side_switches_which_run_is_read() -> None:
    """Part (a) is frozen on dev; part (b) is registered on eval.

    A proxy computed on the rehearsal and one computed on the single draw are
    different claims, so the side is a parameter and every run prints it.
    """
    e010.use_side("eval")
    assert all("_eval.jsonl" in str(path) for path in e010.ARMS.values())
    e010.use_side("dev")
    assert all("_dev.jsonl" in str(path) for path in e010.ARMS.values())
    assert set(e010.ARMS) == {"A", "B", "C"}


@pytest.fixture(autouse=True)
def _restore_side():
    yield
    e010.use_side("dev")
