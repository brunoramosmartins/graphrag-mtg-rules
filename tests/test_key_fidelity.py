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

import argparse
import json
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


class TestVerificationIsRecorded:
    """The one check a machine cannot make is the one that must be logged."""

    def test_an_unverified_row_stops_the_score(self, tmp_path, monkeypatch) -> None:
        # The guard that fired on the author's first run. It is the whole
        # reason the fixture has a `verified` field: `perturbed_key` can
        # only catch a perturbation identical to the key, and a
        # perturbation that is accidentally right about Magic is invisible
        # to every mechanical check in this file.
        fixture = tmp_path / "fixture.jsonl"
        subset = tmp_path / "subset.json"
        subset.write_text(
            json.dumps({"items": [{"question_id": "rg-1", "direction": "A",
                                   "expected": "correct"}]}),
            encoding="utf-8",
        )
        fixture.write_text(
            json.dumps({"question_id": "rg-1", "real_key": "It dies.",
                        "perturbed": "It survives.", "question": "q",
                        "answer": "a", "verified": False}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(kf, "SUBSET_PATH", subset)
        monkeypatch.setattr(kf, "FIXTURE_PATH", fixture)
        with pytest.raises(SystemExit) as caught:
            kf.score(argparse.Namespace(model=None, max_tokens=400, dry_run=True))
        assert "unverified" in str(caught.value)

    def test_a_rejection_keeps_its_reason(self, tmp_path, monkeypatch) -> None:
        # A rejected item that records no reason is an item that will be
        # rewritten into the same mistake.
        fixture = tmp_path / "fixture.jsonl"
        subset = tmp_path / "subset.json"
        subset.write_text(
            json.dumps({"items": [{"question_id": "rg-1", "direction": "A",
                                   "expected": "correct"}]}),
            encoding="utf-8",
        )
        fixture.write_text(
            json.dumps({"question_id": "rg-1", "real_key": "k", "perturbed": "p",
                        "question": "q", "answer": "a", "verified": True}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(kf, "SUBSET_PATH", subset)
        monkeypatch.setattr(kf, "FIXTURE_PATH", fixture)
        kf.mark(argparse.Namespace(question_id=["rg-1"], accept=False,
                                   why="the perturbation is true in Magic"))
        row = kf.load_fixture()["rg-1"]
        assert row["verified"] is False
        assert row["rejected_why"] == "the perturbation is true in Magic"


class TestTheToolDoesNotNameACauseItCannotSee:
    """It did once, and it was wrong.

    On 2026-09-10 the first run printed "the judge scored against its own
    knowledge of Magic" over five items whose rationales all cited the
    supplied key. The perturbed keys endorsed each answer's verdict while
    contradicting its reasoning, which the rubric scores `partial` by
    tie-break 3, so the fixture expected the wrong label — and the tool
    blamed the judge for its own defect.
    """

    def test_a_low_rate_names_both_explanations(self, capsys) -> None:
        verdict = Verdict("rg-1", Correctness.INCORRECT, "contradicts the key", "fake")
        kf.report([(item(), verdict)])
        printed = capsys.readouterr().out
        assert "does not actually imply the label" in printed
        assert "own knowledge of Magic" in printed
        assert "Read each rationale" in printed

    def test_a_passing_rate_claims_nothing_about_the_bound(self, capsys) -> None:
        verdict = Verdict("rg-1", Correctness.CORRECT, "follows the key", "fake")
        assert kf.report([(item(), verdict)]) == 0
        assert "lower bound" in capsys.readouterr().out
