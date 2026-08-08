"""Lexical CR search: ranking by distinctive-term overlap, no network."""

from __future__ import annotations

from graphrag_mtg.etl.cr_parser import CRDocument, Rule
from graphrag_mtg.extraction.cite_search import CiteSearch, _fold, _terms


def rule(number: str, text: str) -> Rule:
    return Rule(number=number, level=2, text=text, parent="700", section="x")


def doc() -> CRDocument:
    return CRDocument(
        effective_date=None,
        rules=[
            rule("702.19", "Trample is a keyword ability that lets excess combat damage through."),
            rule("701.50", "To connive, a creature draws a card and then discards a card."),
            rule("608.2b", "A spell checks whether its targets are still legal on resolution."),
            rule("100.1", "These rules apply to any game with two or more players."),
        ],
        glossary=[],
    )


class TestTerms:
    def test_stopwords_and_short_words_dropped(self) -> None:
        terms = set(_terms("The creature draws a card and connives."))
        assert "connives" in terms
        assert "creature" not in terms  # ubiquitous MTG stopword
        assert "the" not in terms


class TestFold:
    """Rulings inflect where rule text does not; folding is what makes them meet."""

    def test_plural_and_third_person_s_are_folded(self) -> None:
        assert _fold("connives") == "connive"
        assert _fold("draws") == "draw"
        assert _fold("discards") == "discard"

    def test_es_and_ies_forms_are_folded(self) -> None:
        assert _fold("matches") == "match"
        assert _fold("abilities") == "ability"

    def test_words_that_merely_end_in_s_are_left_alone(self) -> None:
        assert _fold("loss") == "loss"
        assert _fold("its") == "its"


class TestSearch:
    def test_distinctive_term_ranks_the_right_rule_first(self) -> None:
        hits = CiteSearch(doc()).search("the creature connives to draw and discard", k=3)
        assert hits[0].number == "701.50"

    def test_trample_query_finds_trample_rule(self) -> None:
        hits = CiteSearch(doc()).search("does trample assign excess damage", k=3)
        assert hits[0].number == "702.19"

    def test_rules_sharing_no_distinctive_terms_are_absent(self) -> None:
        hits = CiteSearch(doc()).search("connive", k=8)
        assert all(h.number != "100.1" for h in hits)

    def test_empty_query_returns_nothing(self) -> None:
        assert CiteSearch(doc()).search("the a an of", k=5) == []

    def test_k_limits_results(self) -> None:
        hits = CiteSearch(doc()).search("card damage players legal", k=2)
        assert len(hits) <= 2
