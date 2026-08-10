"""Lexical CR retrieval for questions — the half of ADR-007 the graph cannot do."""

from __future__ import annotations

from graphrag_mtg.etl.cr_parser import CRDocument, Rule
from graphrag_mtg.extraction.cite_search import RuleHit
from graphrag_mtg.retrieval.rule_search import (
    RuleSearch,
    question_terms,
    significant,
)


def rule(number: str, text: str) -> Rule:
    return Rule(number=number, level=3, text=text, parent=number[:3], section="Test")


DOC = CRDocument(
    effective_date="2026-08-07",
    rules=[
        rule("702.19b", "The controller of an attacking creature with trample assigns damage."),
        rule("613.4b", "Layer 7b: Effects that set power and toughness to specific values."),
        rule("104.3a", "A player concedes the game at any time."),
        rule("205.2a", "The card types are artifact, enchantment, land and instant."),
    ],
    glossary=[],
)


class TestQuestionTerms:
    def test_interrogative_scaffolding_is_stripped(self) -> None:
        assert question_terms("What happens when a creature has trample?") == "creature has trample"

    def test_a_question_of_only_question_words_keeps_its_text(self) -> None:
        """Searching the empty string is worse than searching the noise."""
        assert question_terms("what does it do") == "what does it do"

    def test_content_words_survive_untouched(self) -> None:
        assert "deathtouch" in question_terms("how does deathtouch work")


class TestSignificance:
    def test_noise_far_below_the_top_hit_is_dropped(self) -> None:
        hits = [RuleHit("a", 20.0, ""), RuleHit("b", 18.0, ""), RuleHit("c", 1.0, "")]
        assert [h.number for h in significant(hits)] == ["a", "b"]

    def test_an_empty_result_stays_empty(self) -> None:
        assert significant([]) == []

    def test_results_come_back_ranked(self) -> None:
        hits = [RuleHit("low", 5.0, ""), RuleHit("high", 20.0, "")]
        assert [h.number for h in significant(hits)] == ["high", "low"]

    def test_lexical_search_always_returns_something_which_is_why_this_exists(self) -> None:
        """A ranked list is not evidence that any member is relevant."""
        hits = [RuleHit("top", 30.0, ""), *(RuleHit(f"n{i}", 2.0, "") for i in range(7))]
        assert len(significant(hits)) == 1


class TestRuleSearch:
    def test_distinctive_vocabulary_finds_the_rule(self) -> None:
        (hit, *_) = RuleSearch(DOC).search("How does trample assign damage?")
        assert hit.number == "702.19b"

    def test_a_question_sharing_nothing_returns_nothing(self) -> None:
        assert RuleSearch(DOC).search("how do i bake a cake") == []

    def test_oracle_text_reaches_what_the_question_cannot(self) -> None:
        """A question names cards; the CR never mentions one. Measured on dev: 6/15 -> 8/15."""
        question = "What happens with Humility out?"
        assert RuleSearch(DOC).search(question) == []
        hits = RuleSearch(DOC).search(
            question, ["All creatures lose all abilities and have base power and toughness 1/1"]
        )
        assert "613.4b" in {h.number for h in hits}

    def test_evidence_is_citable_and_provenanced(self) -> None:
        (item, *_) = RuleSearch(DOC).evidence("How does trample assign damage?")
        assert item.cite() == "rule:702.19b"
        assert item.template == "rule_search"

    def test_retrieved_rules_lose_budget_contests_to_named_ones(self) -> None:
        """A lexical hit was never *named* by the question, so distance is not 0."""
        (item, *_) = RuleSearch(DOC).evidence("How does trample assign damage?")
        assert item.distance > 0
