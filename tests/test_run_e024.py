"""E-024 asks whether the target is reachable from the question, so the tests
are about not letting the key leak into the arm that must not have it.

The other subject is the parse. E-014 measured what happens when a missing
format marker scores as a wrong answer: a format failure gets reported as a
reasoning failure and nobody can tell them apart afterwards. `None` stays
distinct from a wrong chapter all the way to the report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e024 as e024


class TestTheKeyReachesOnlyTheControl:
    """The whole design is the contrast between having the answer and not."""

    def test_the_question_only_prompt_has_no_answer_section(self) -> None:
        prompt = e024.build_prompt("Does it die?", None)
        assert "## QUESTION" in prompt
        assert "## ANSWER" not in prompt

    def test_the_control_prompt_carries_the_key(self) -> None:
        prompt = e024.build_prompt("Does it die?", "Yes, damage stays marked.")
        assert "## ANSWER" in prompt
        assert "damage stays marked" in prompt

    def test_the_key_text_never_appears_in_the_question_only_prompt(self) -> None:
        # The failure this prevents is subtle and total: a key that leaks into
        # question_only makes both arms the control and the entry measures
        # nothing while reporting a number.
        key = "Yes. It stopped being a creature for a short while."
        assert key not in e024.build_prompt("Does it die?", None)

    def test_both_conditions_are_the_two_registered_ones(self) -> None:
        assert e024.CONDITIONS == ("question_only", "question_and_key")


class TestAMissingMarkerIsNotAWrongAnswer:
    def test_a_well_formed_reply_parses(self) -> None:
        assert e024.parse_chapter("CHAPTER: 613") == "613"

    def test_the_marker_is_found_with_surrounding_prose(self) -> None:
        assert e024.parse_chapter("Sure.\nCHAPTER: 400\nHope that helps.") == "400"

    def test_case_does_not_matter(self) -> None:
        assert e024.parse_chapter("chapter: 705") == "705"

    def test_a_reply_with_no_marker_is_none_and_not_a_guess(self) -> None:
        assert e024.parse_chapter("I think it is about layers.") is None

    def test_a_subrule_is_read_as_its_chapter_and_not_rejected(self) -> None:
        # The prompt asks for three digits; a model that answers 613.4b still
        # named a chapter and scoring that as unparseable would throw away a
        # hit over formatting, which tie-break 6 of the rubric refuses
        # elsewhere in this project for the same reason.
        assert e024.parse_chapter("CHAPTER: 613.4b") == "613"


class TestTheChapterOfARule:
    @pytest.mark.parametrize(
        ("rule", "chapter"),
        [("613.4b", "613"), ("613", "613"), ("702.19e", "702"), ("120.6", "120")],
    )
    def test_the_leading_three_digits(self, rule: str, chapter: str) -> None:
        assert e024.chapter_of(rule) == chapter


class TestNoNumberIsReadAgainstZero:
    def test_the_baseline_is_the_modal_chapter(self) -> None:
        rows = [
            {"gold_chapters": ["613"]},
            {"gold_chapters": ["613"]},
            {"gold_chapters": ["400"]},
            {"gold_chapters": ["500"]},
        ]
        top, rate = e024.baseline(rows)
        assert top == "613"
        assert rate == 0.5

    def test_a_question_with_two_gold_chapters_counts_for_both(self) -> None:
        # A question whose key cites 613 and 614 is a hit under either, so the
        # baseline has to see both or it understates what guessing achieves.
        top, rate = e024.baseline([{"gold_chapters": ["613", "614"]}])
        assert rate == 1.0
        assert top in {"613", "614"}

    def test_the_registered_population_figures_are_the_counted_ones(self) -> None:
        # Counted 2026-09-14. A first draft of the entry said nine chapters
        # from memory; these three constants are what the guard compares
        # against, so an edit here is an edit to the experiment.
        assert (e024.EXPECTED_QUESTIONS, e024.EXPECTED_CHAPTERS) == (22, 17)
        assert e024.EXPECTED_BASELINE == (6, 22)

    def test_three_samples_because_one_is_not_a_reading(self) -> None:
        assert e024.SAMPLES == 3
