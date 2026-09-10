"""The control that agreement figures cannot replace.

A judge and a human who share the same Magic knowledge agree beautifully,
so a high agreement figure is consistent with a judge that never read the
key at all. E-011 point 6 registered a key-fidelity control for that
reason, `judge.py` has carried `perturbed_key` and `follows_key` since it
was written, and until 2026-09-10 the fixture they need did not exist —
which is how a registered control stays unrun for a month while looking,
in the code, exactly like a control that runs.

These tests cover the harness's refusals rather than its arithmetic. Every
one of them is a way the fixture can look like evidence while measuring
nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_key_fidelity as kf
from graphrag_mtg.evaluation.judge import Verdict, follows_key
from graphrag_mtg.evaluation.rubric import Correctness


def item(**kw) -> kf.Item:
    defaults = {
        "question_id": "rg-1",
        "direction": "A",
        "expected": Correctness.CORRECT,
        "real_key": "The creature dies.",
        "perturbed": "The creature survives.",
        "question": "What happens?",
        "answer": "It survives.",
    }
    return kf.Item(**{**defaults, **kw})


class TestTheFixtureCannotLieQuietly:
    def test_a_perturbation_identical_to_the_key_is_refused(self) -> None:
        # A control that changes nothing measures nothing while looking
        # like evidence: the judge agrees, fidelity reads 1.000, and no
        # domain knowledge was ever put under pressure.
        with pytest.raises(ValueError):
            kf.verify([item(perturbed="The creature dies.")])

    def test_an_empty_perturbation_is_refused(self) -> None:
        with pytest.raises(ValueError):
            kf.verify([item(perturbed="   ")])

    def test_a_direction_that_disagrees_with_its_expected_label_is_refused(self) -> None:
        # Direction A rewrites the key to endorse a wrong answer, so a
        # key-following judge must say `correct`. A fixture row claiming
        # otherwise inverts the item without changing how it looks.
        with pytest.raises(SystemExit):
            kf.verify([item(direction="A", expected=Correctness.INCORRECT)])

    def test_a_well_formed_item_passes(self) -> None:
        kf.verify([item(), item(direction="B", expected=Correctness.INCORRECT)])


class TestBothDirectionsAreNeeded:
    """One direction cannot fail a constant judge."""

    def test_a_judge_that_always_says_correct_passes_a_and_fails_b(self) -> None:
        always = Verdict("rg-1", Correctness.CORRECT, "", "fake")
        assert follows_key(always, kf.DIRECTIONS["A"][1])
        assert not follows_key(always, kf.DIRECTIONS["B"][1])

    def test_a_judge_that_always_says_incorrect_does_the_reverse(self) -> None:
        always = Verdict("rg-1", Correctness.INCORRECT, "", "fake")
        assert not follows_key(always, kf.DIRECTIONS["A"][1])
        assert follows_key(always, kf.DIRECTIONS["B"][1])

    def test_the_two_directions_expect_opposite_labels(self) -> None:
        assert kf.DIRECTIONS["A"][1] is not kf.DIRECTIONS["B"][1]


class TestRegisteredConstants:
    def test_the_pass_mark_is_the_registered_one(self) -> None:
        # E-011 point 6. Changing it here would be choosing a threshold
        # from a result, which is what the 2026-08-15b amendment withdrew
        # the hand-picked 0.90 / 0.85 for.
        assert kf.PASS_MARK == 0.90

    def test_the_subset_is_versioned_and_the_key_text_is_not(self) -> None:
        # A perturbed key is derived from a licensed answer key. The ids
        # are checkable by anyone; the text is not redistributed.
        assert kf.SUBSET_PATH.parts[:2] == ("data", "golden")
        assert kf.FIXTURE_PATH.parts[:2] == ("data", "interim")

    def test_fifteen_per_direction(self) -> None:
        assert kf.PER_DIRECTION == 15
