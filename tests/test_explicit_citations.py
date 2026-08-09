"""Deterministic CITES_RULE: only what the ruling actually states."""

from __future__ import annotations

from graphrag_mtg.extraction.explicit_citations import explicit_citations
from graphrag_mtg.extraction.schemas import LinkMethod

PARENTHESIZED = "Creatures you control shrug off deathtouch. (704.5h)"


class TestFinding:
    def test_the_parenthesized_form_is_found(self) -> None:
        """How the corpus actually writes them; the Phase 2 pattern missed it."""
        (citation,) = explicit_citations("r1", PARENTHESIZED)
        assert citation.rule_number == "704.5h"

    def test_the_span_reproduces_the_source(self) -> None:
        """The gate re-reads the source and rejects a span that does not."""
        (citation,) = explicit_citations("r1", PARENTHESIZED)
        span = citation.span
        assert PARENTHESIZED[span.start : span.end] == span.text == "704.5h"

    def test_several_numbers_in_one_ruling(self) -> None:
        text = "Check all of 704.5 and 704.6 for anything relevant."
        assert [c.rule_number for c in explicit_citations("r1", text)] == ["704.5", "704.6"]

    def test_a_ruling_naming_nothing_yields_nothing(self) -> None:
        assert explicit_citations("r1", "This creature can't be blocked.") == []

    def test_repeats_are_left_for_the_gate_to_dedupe(self) -> None:
        """Proposing twice keeps the accounting honest; the gate collapses it."""
        text = "See 704.5h. As 704.5h says, deathtouch is ignored."
        assert len(explicit_citations("r1", text)) == 2


class TestNarrowness:
    def test_a_bare_chapter_number_is_not_a_citation(self) -> None:
        """A quantity is not a chapter: gaining 100 life cites nothing."""
        assert explicit_citations("r1", "You gain 100 life and draw a card.") == []

    def test_a_two_digit_number_is_not_a_citation(self) -> None:
        assert explicit_citations("r1", "Put 20.5 counters on it.") == []

    def test_a_number_absent_from_the_cr_is_still_proposed(self) -> None:
        """Existence is the gate's check, not this module's — one owner per rule."""
        (citation,) = explicit_citations("r1", "As stated in 999.9z, this works.")
        assert citation.rule_number == "999.9z"


class TestProvenance:
    def test_the_method_says_where_it_came_from(self) -> None:
        (citation,) = explicit_citations("r1", PARENTHESIZED)
        assert citation.method == LinkMethod.EXPLICIT

    def test_a_deterministic_stage_asserts_full_confidence(self) -> None:
        (citation,) = explicit_citations("r1", PARENTHESIZED)
        assert citation.confidence == 1.0

    def test_the_rationale_quotes_the_surrounding_ruling(self) -> None:
        (citation,) = explicit_citations("r1", PARENTHESIZED)
        assert "shrug off deathtouch" in citation.rationale
