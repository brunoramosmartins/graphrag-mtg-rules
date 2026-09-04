"""The judge: one rubric, both orderings, and a control for what a prompt cannot assert.

Every test here holds a property E-011 registered. The judge's threshold is
the lower bound of a human self-agreement interval measured on the same
rubric, so a drift between what the human read and what the model reads
would silently move the bar the judge is graded against.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.evaluation import judge
from graphrag_mtg.evaluation.judge import (
    CORRECTNESS_SYSTEM,
    JUDGE_PROMPT_VERSION,
    JudgeFormatError,
    Preference,
    compare,
    correctness_prompt,
    follows_key,
    order_disagreement_rate,
    parse_label,
    parse_winner,
    perturbed_key,
    resolve_pair,
    score,
)
from graphrag_mtg.evaluation.rubric import RUBRIC, Correctness, rubric_hash


def replying(text: str):
    """A generator that always answers `text`."""
    return lambda system, prompt: text


def pref(winner: str, *, qid: str = "q1", left: str = "A", right: str = "B") -> Preference:
    return Preference(question_id=qid, winner=winner, rationale="", left_arm=left, right_arm=right)


class TestOneRubric:
    def test_the_system_prompt_is_built_from_the_rubric_constant(self) -> None:
        # "The same rubric the judge uses" is a property only if there is
        # one object. A second copy is a second instrument.
        assert RUBRIC in CORRECTNESS_SYSTEM

    def test_every_verdict_carries_the_hash_it_ran_under(self) -> None:
        # A rubric drift becomes a hash mismatch rather than a silent
        # change of instrument.
        verdict = score("q1", "q", "a", "k", replying("LABEL: correct\nWHY: matches."))
        assert verdict.rubric_hash == rubric_hash()
        assert verdict.prompt_version == JUDGE_PROMPT_VERSION

    def test_the_answer_reaches_the_model_blinded(self) -> None:
        # The same stripping the human sees, so the ceiling and the judge
        # are measured on one rendering.
        prompt = correctness_prompt("q", "Yes [rule:702.19], it does.", "Yes.")
        assert "[rule:702.19]" not in prompt and "Yes, it does." in prompt


class TestParseLabel:
    def test_the_last_label_wins(self) -> None:
        # A model reasoning aloud writes "incorrect" on the way to
        # "correct". Reading the first match scores the reasoning rather
        # than the verdict — the failure metaqa.parse_prediction was
        # rewritten to avoid.
        text = "This looks incorrect at first.\nLABEL: correct\nWHY: the key agrees."
        assert parse_label(text)[0] is Correctness.CORRECT

    def test_reads_the_rationale(self) -> None:
        assert parse_label("LABEL: partial\nWHY: right verdict, wrong reason.")[1] == (
            "right verdict, wrong reason."
        )

    def test_an_unrecognised_label_is_skipped_for_a_real_one(self) -> None:
        text = "LABEL: maybe\nLABEL: incorrect\nWHY: contradicts the key."
        assert parse_label(text)[0] is Correctness.INCORRECT

    def test_no_label_raises_rather_than_defaulting(self) -> None:
        # A default would be a score. A run that cannot read a verdict
        # must stop and say so.
        with pytest.raises(JudgeFormatError, match="no LABEL line"):
            parse_label("I think the answer is fine.")

    def test_case_and_spacing_are_tolerated(self) -> None:
        assert parse_label("label:   Correct\nwhy: fine.")[0] is Correctness.CORRECT


class TestRefusalIsScoredByRule:
    def test_a_refusal_costs_no_call(self) -> None:
        # It is a rule, not a judgement, and paying for it would invite
        # the model to disagree with a registered scoring decision.
        def explode(system, prompt):
            raise AssertionError("the model must not be called for a refusal")

        verdict = score("q1", "q", "I cannot answer.", "Yes.", explode, refused=True)
        assert verdict.label is Correctness.INCORRECT and verdict.by_rule

    def test_an_empty_answer_is_the_same_case(self) -> None:
        def explode(system, prompt):
            raise AssertionError("the model must not be called for an empty answer")

        assert score("q1", "q", "   ", "Yes.", explode).by_rule

    def test_an_answer_that_is_only_handles_is_empty_once_blinded(self) -> None:
        def explode(system, prompt):
            raise AssertionError("blinding left nothing to judge")

        assert score("q1", "q", "[rule:1.1][card:X]", "Yes.", explode).by_rule


class TestBothOrderings:
    def test_agreeing_orderings_pick_the_arm(self) -> None:
        first = pref("left", left="A", right="B")
        second = pref("right", left="B", right="A")
        assert resolve_pair(first, second) == "A"

    def test_a_disagreeing_pair_is_a_tie(self) -> None:
        # Registered before any pair exists. Not a coin flip, not the
        # first ordering, not whichever matches the correctness labels: a
        # model that answers differently when the answers swap places has
        # told us it is reading position.
        first = pref("left", left="A", right="B")
        second = pref("left", left="B", right="A")
        assert resolve_pair(first, second) == "tie"

    def test_an_explicit_tie_in_both_orderings_stays_a_tie(self) -> None:
        assert resolve_pair(pref("tie"), pref("tie", left="B", right="A")) == "tie"

    def test_mismatched_questions_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same question"):
            resolve_pair(pref("left", qid="q1"), pref("left", qid="q2"))

    def test_mismatched_arms_are_refused(self) -> None:
        with pytest.raises(ValueError, match="different arms"):
            resolve_pair(pref("left", left="A", right="B"), pref("left", left="A", right="C"))

    def test_the_disagreement_rate_is_what_gates_publication(self) -> None:
        # Above 0.20 the pairwise win rate is not published as the
        # head-to-head; the per-stratum correctness comparison is.
        agree = (pref("left"), pref("right", left="B", right="A"))
        clash = (pref("left"), pref("left", left="B", right="A"))
        assert order_disagreement_rate([agree, agree, agree, clash]) == 0.25
        assert order_disagreement_rate([]) == 0.0


class TestCompare:
    def test_maps_the_winner_back_to_an_arm(self) -> None:
        result = compare(
            "q1", "q", "left text", "right text", "key",
            replying("WINNER: right\nWHY: matches the key."),
            left_arm="A", right_arm="C",
        )
        assert result.choice() == "C"

    def test_a_tie_is_not_an_arm(self) -> None:
        result = compare(
            "q1", "q", "l", "r", "k", replying("WINNER: tie\nWHY: same label."),
            left_arm="A", right_arm="B",
        )
        assert result.choice() == "tie"

    def test_no_winner_line_raises(self) -> None:
        with pytest.raises(JudgeFormatError, match="no WINNER line"):
            parse_winner("They are both quite good.")


class TestKeyFidelityControl:
    def test_a_perturbed_key_must_actually_differ(self) -> None:
        # A control that changes nothing measures nothing while looking
        # like evidence — the worst kind of guard.
        with pytest.raises(ValueError, match="identical"):
            perturbed_key("Yes, it triggers.", "Yes, it triggers.")

    def test_an_empty_perturbation_is_refused(self) -> None:
        with pytest.raises(ValueError, match="say something different"):
            perturbed_key("Yes.", "   ")

    def test_a_real_perturbation_passes_through(self) -> None:
        assert perturbed_key("Yes.", "No, it does not trigger.") == "No, it does not trigger."

    def test_following_the_key_is_what_is_measured(self) -> None:
        # A judge scoring from its own Magic knowledge disagrees here and
        # agrees everywhere else, which is why a prompt cannot establish
        # this property and a control can.
        verdict = score("q1", "q", "a", "k", replying("LABEL: correct\nWHY: follows the key."))
        assert follows_key(verdict, Correctness.CORRECT)
        assert not follows_key(verdict, Correctness.INCORRECT)


class TestRegisteredConstants:
    def test_a_refusal_scores_incorrect(self) -> None:
        assert judge.REFUSAL_LABEL is Correctness.INCORRECT

    def test_the_preference_prompt_also_carries_the_rubric(self) -> None:
        assert RUBRIC in judge.PREFERENCE_SYSTEM
