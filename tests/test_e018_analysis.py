"""E-018's decision rule, exercised against outcomes that did not happen.

A rule only ever run against the single result it was written for is a rule
nobody has checked. Every branch here is reached by a constructed run, including
the three that the real one did not take, so a later edit to the thresholds
trips a test rather than changing a published verdict.

The other subject is the noise floor. The floor run announces its discordance
over three labels; the contrasts are scored on two. Comparing a two-label
signal against a three-label floor compares a number to somebody else's noise,
and on this run those two figures are 1 and 2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e018_analysis as ana


def labels(**by_question: tuple[str, str, str]) -> dict[str, dict[str, str]]:
    """Questions as (control, placebo, treatment) label triples."""
    return {
        qid: dict(zip(("control", "placebo", "treatment"), triple, strict=True))
        for qid, triple in by_question.items()
    }


def adjusted(treatment: bool, placebo: bool) -> dict[str, tuple[float, bool]]:
    """A Holm result carrying only what `decide` reads: the reject flags."""
    return {"treatment": (0.01 if treatment else 1.0, treatment),
            "placebo": (0.01 if placebo else 1.0, placebo)}


def result(point: float, low: float, high: float) -> dict:
    return {"point": point, "low": low, "high": high}


class TestTheCollapseIsTheRegisteredOutcome:
    """`partial` is not half a point. The entry registered a two-way outcome."""

    def test_only_correct_counts_as_correct(self) -> None:
        table = labels(a=("correct", "partial", "incorrect"))
        after, before, ids = ana.aligned(table, "treatment", "control")
        assert ids == ["a"]
        assert before == [True]
        assert after == [False]

    def test_a_question_missing_a_condition_is_dropped_from_both_vectors(self) -> None:
        # Dropping it from one and not the other would leave two vectors of
        # different lengths describing different question sets, which is what
        # a paired test cannot survive.
        table = labels(a=("correct", "correct", "correct"))
        table["b"] = {"control": "correct"}
        after, before, ids = ana.aligned(table, "treatment", "control")
        assert ids == ["a"]
        assert len(after) == len(before) == 1

    def test_the_three_label_distribution_is_reported_beside_it(self) -> None:
        table = labels(
            a=("correct", "partial", "correct"),
            b=("incorrect", "incorrect", "partial"),
        )
        assert ana.distribution(table, "treatment") == {
            "incorrect": 0,
            "partial": 1,
            "correct": 1,
        }


class TestTheOrdinalShiftTheCollapseHides:
    """An intervention turning `incorrect` into `partial` is not nothing."""

    def test_a_rise_toward_the_key_is_counted_in_steps(self) -> None:
        table = labels(
            a=("incorrect", "incorrect", "correct"),
            b=("partial", "partial", "correct"),
            c=("incorrect", "incorrect", "partial"),
        )
        shift = ana.ordinal_shift(table, "treatment", "control")
        assert shift["steps"] == 4
        assert len(shift["up"]) == 3
        assert shift["down"] == []

    def test_a_fall_is_subtracted_not_ignored(self) -> None:
        table = labels(
            a=("incorrect", "incorrect", "correct"),
            b=("partial", "partial", "incorrect"),
        )
        shift = ana.ordinal_shift(table, "treatment", "control")
        assert shift["steps"] == 1
        assert len(shift["down"]) == 1

    def test_no_movement_is_zero_steps(self) -> None:
        table = labels(a=("correct", "correct", "correct"))
        assert ana.ordinal_shift(table, "treatment", "control")["steps"] == 0


class TestTheFloorIsScoredTheWayTheContrastIs:
    """A two-label signal measured against a three-label floor is a mismatch."""

    def rows(self) -> list[dict]:
        return [
            {"question_id": "a", "condition": "control_a", "label": "partial"},
            {"question_id": "a", "condition": "control_b", "label": "incorrect"},
            {"question_id": "b", "condition": "control_a", "label": "incorrect"},
            {"question_id": "b", "condition": "control_b", "label": "correct"},
            {"question_id": "c", "condition": "control_a", "label": "correct"},
            {"question_id": "c", "condition": "control_b", "label": "correct"},
        ]

    def test_partial_against_incorrect_is_discordant_on_three_labels_only(self) -> None:
        # This is the real run: the floor announced two discordant pairs and
        # only one of them survives the collapse the contrasts use.
        floor = ana.noise_floor(self.rows())
        assert floor["three_label"] == ["a", "b"]
        assert floor["collapsed"] == ["b"]

    def test_both_figures_are_returned_so_neither_has_to_be_recomputed(self) -> None:
        floor = ana.noise_floor(self.rows())
        assert floor["n"] == 3
        assert set(floor) == {"n", "three_label", "collapsed"}


class TestEveryRegisteredBranch:
    """Including the ones this run did not take."""

    def test_a_significant_treatment_over_the_construct_bar_is_branch_one(self) -> None:
        branch, blocked = ana.decide(
            result(0.35, 0.1, 0.6), result(0.0, -0.1, 0.1), 0.20,
            {"steps": 0}, 0.9, adjusted(treatment=True, placebo=False),
        )
        assert (branch, blocked) == ("1", [])

    def test_a_significant_treatment_under_the_bar_does_not_adopt_the_objective(self) -> None:
        # E-016's lesson, carried here: significance without the registered
        # effect size reports the result, it does not act on it.
        branch, _ = ana.decide(
            result(0.35, 0.1, 0.6), result(0.30, 0.05, 0.55), 0.05,
            {"steps": 0}, 0.9, adjusted(treatment=True, placebo=False),
        )
        assert branch == "1-bar"

    def test_a_significant_placebo_alone_is_branch_two(self) -> None:
        branch, _ = ana.decide(
            result(0.10, -0.05, 0.3), result(0.30, 0.05, 0.55), 0.0,
            {"steps": 0}, 0.9, adjusted(treatment=False, placebo=True),
        )
        assert branch == "2"

    def test_a_significant_negative_contrast_is_branch_four(self) -> None:
        branch, _ = ana.decide(
            result(-0.30, -0.55, -0.05), result(0.0, -0.1, 0.1), -0.3,
            {"steps": -2}, 0.9, adjusted(treatment=True, placebo=False),
        )
        assert branch == "4"

    def test_an_interval_covering_the_bound_is_inconclusive_not_absence(self) -> None:
        # The amendment that mattered most: branch 3 used to fire on failure
        # to reject and cancel a phase for it.
        branch, _ = ana.decide(
            result(0.10, 0.0, 0.25), result(0.0, -0.1, 0.1), 0.10,
            {"steps": 0}, 0.9, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3a"

    def test_only_an_interval_excluding_the_bound_is_evidence_of_absence(self) -> None:
        branch, _ = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": 0}, 0.9, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3b"


class TestTheTwoConditionsThatStopBranchThree:
    """Both registered before the run; one of them fired on the real one."""

    def test_low_uptake_blocks_branch_three(self) -> None:
        branch, blocked = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": 0}, 0.30, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3-blocked"
        assert "uptake" in blocked[0]

    def test_uptake_exactly_on_the_floor_does_not_block(self) -> None:
        # The rule says *below*. At n = 20 uptake moves in steps of 0.05, so
        # landing exactly on 0.50 is a likely outcome, not a near miss, and
        # reading it either way after the fact is the move the entry forbids.
        branch, _ = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": 0}, ana.UPTAKE_FLOOR, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3b"

    def test_an_ordinal_shift_toward_the_key_blocks_branch_three(self) -> None:
        branch, blocked = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": 3}, 0.9, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3-blocked"
        assert "three-label" in blocked[0]

    def test_an_ordinal_shift_away_from_the_key_does_not_block(self) -> None:
        # The blocker exists for improvement below the outcome's resolution.
        # A worsening is not that and must not buy the entry a reprieve.
        branch, _ = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": -3}, 0.9, adjusted(treatment=False, placebo=False),
        )
        assert branch == "3b"

    def test_both_blockers_are_reported_not_just_the_first(self) -> None:
        _, blocked = ana.decide(
            result(0.0, -0.05, 0.05), result(0.0, -0.1, 0.1), 0.0,
            {"steps": 2}, 0.10, adjusted(treatment=False, placebo=False),
        )
        assert len(blocked) == 2


class TestTheConstantsCameFromTheEntry:
    """Kept where an edit trips a test rather than moving a published verdict."""

    @pytest.mark.parametrize(
        ("name", "value"),
        [("CONSTRUCT_BAR", 0.15), ("ABSENCE_BOUND", 0.20), ("UPTAKE_FLOOR", 0.50)],
    )
    def test_the_registered_thresholds(self, name: str, value: float) -> None:
        assert getattr(ana, name) == value

    def test_the_ordinal_scale_runs_worst_to_best(self) -> None:
        # Reversing it would turn every improvement into a blocker's opposite.
        assert ana.ORDINAL == ("incorrect", "partial", "correct")

    def test_the_ceiling_comes_from_the_runner(self) -> None:
        from run_e018 import CEILING

        assert ana.CEILING == CEILING
