"""Query-time linking: a question is not a ruling, and the policy differs."""

from __future__ import annotations

from itertools import pairwise

from graphrag_mtg.extraction.linker import Lexicon
from graphrag_mtg.retrieval.linking import (
    EntityKind,
    QueryLinker,
    carries_capitalization,
    find_rules,
)

CARDS = [
    ("Humility", "hum"),
    ("Opalescence", "opa"),
    ("Card Draw", "cd"),
    ("Opt", "opt-1"),
    ("Lightning Bolt", "bolt"),
    ("Serra Angel", "serra"),
    ("Fear", "fear-card"),
]
ALIASES = [("Bolt", "bolt")]
KEYWORDS = ["Flying", "Deathtouch", "First Strike"]
KEYWORDS_BY_ORACLE = {"serra": ["Flying", "Vigilance"], "bolt": []}


def linker() -> QueryLinker:
    return QueryLinker(
        Lexicon.build(CARDS, aliases=ALIASES),
        keywords=KEYWORDS,
        keywords_by_oracle=KEYWORDS_BY_ORACLE,
    )


class TestCapitalizationSignal:
    def test_a_sentence_capital_alone_is_no_signal(self) -> None:
        """Every sentence has a first capital; only later ones inform."""
        assert not carries_capitalization("how does humility work")

    def test_a_later_capital_is_signal(self) -> None:
        assert carries_capitalization("how does Humility work")

    def test_empty_text(self) -> None:
        assert not carries_capitalization("")


class TestRuleNumbers:
    def test_a_dotted_number_stands_alone(self) -> None:
        (ref,) = find_rules("What does 613.4b say?")
        assert (ref.kind, ref.key) == (EntityKind.RULE, "613.4b")

    def test_a_bare_chapter_needs_a_cue_word(self) -> None:
        """Otherwise 'I have 100 life' cites chapter 100."""
        assert find_rules("I have 100 life and 3 cards") == []
        (ref,) = find_rules("Explain rule 613 please")
        assert ref.key == "613"

    def test_the_span_is_verbatim(self) -> None:
        question = "See rule 704.5g for details"
        (ref,) = find_rules(question)
        assert question[ref.start : ref.end] == ref.surface == "704.5g"

    def test_a_cued_chapter_does_not_double_count_a_dotted_hit(self) -> None:
        assert [r.key for r in find_rules("rule 613.4b applies")] == ["613.4b"]


class TestCapitalizedQuestions:
    def test_card_names_resolve(self) -> None:
        entities = linker().link("How does Humility interact with Opalescence?")
        assert [c.key for c in entities.cards] == ["hum", "opa"]
        assert entities.ambiguous == ()

    def test_a_lowercase_phrase_is_not_the_card_of_that_name(self) -> None:
        """The gate that Phase 3 measured: 'card draw' is words, not Card Draw."""
        entities = linker().link("Does Serra Angel give extra card draw?")
        assert [c.key for c in entities.cards] == ["serra"]

    def test_the_same_phrase_capitalized_is_the_card(self) -> None:
        entities = linker().link("This gives extra Card Draw each turn")
        assert [c.key for c in entities.cards] == ["cd"]

    def test_an_alias_reaches_the_card(self) -> None:
        entities = linker().link("Is Bolt legal in Modern?")
        assert [c.key for c in entities.cards] == ["bolt"]


class TestLowercaseQuestions:
    def test_nothing_from_the_open_vocabulary_is_asserted(self) -> None:
        """Without capitalization there is no signal, so nothing is claimed."""
        entities = linker().link("how does humility interact with opalescence")
        assert entities.cards == ()
        assert {a.surface for a in entities.ambiguous} == {"humility", "opalescence"}

    def test_the_candidates_are_handed_back_for_confirmation(self) -> None:
        entities = linker().link("how does humility work")
        (ref,) = entities.ambiguous
        assert ref.candidates == ("hum",)

    def test_the_generic_phrase_does_not_silently_become_a_card(self) -> None:
        entities = linker().link("this gives me extra card draw each turn")
        assert entities.cards == ()

    def test_closed_vocabularies_still_resolve(self) -> None:
        """Keywords and rule numbers cannot be wrong about themselves."""
        entities = linker().link("what does deathtouch do under rule 613")
        assert [k.key for k in entities.keywords] == ["Deathtouch"]
        assert [r.key for r in entities.rules] == ["613"]


class TestGraphSeed:
    """The routing signal ADR-007 rests on."""

    def test_a_keyword_seeds_the_rule_graph(self) -> None:
        assert linker().link("what does deathtouch do").has_graph_seed

    def test_a_rule_number_seeds_it(self) -> None:
        assert linker().link("What does rule 613.4b say?").has_graph_seed

    def test_a_card_with_keywords_seeds_it(self) -> None:
        assert linker().link("Does Serra Angel fly?").has_graph_seed

    def test_cards_without_keywords_do_not(self) -> None:
        """Humility and Opalescence: 15 of 30 interaction_multihop questions."""
        assert not linker().link("How does Humility interact with Opalescence?").has_graph_seed

    def test_an_empty_question_does_not(self) -> None:
        assert not linker().link("").has_graph_seed


class TestSpans:
    def test_overlapping_matches_do_not_double_claim(self) -> None:
        entities = linker().link("Does Serra Angel have Flying?")
        spans = [(e.start, e.end) for e in entities.resolved]
        assert all(a[1] <= b[0] for a, b in pairwise(spans))

    def test_resolved_is_ordered_by_position(self) -> None:
        entities = linker().link("Under rule 613, does Serra Angel have Flying?")
        starts = [e.start for e in entities.resolved]
        assert starts == sorted(starts)

    def test_surfaces_are_verbatim(self) -> None:
        question = "Does Serra Angel have Flying?"
        entities = linker().link(question)
        assert all(question[e.start : e.end] == e.surface for e in entities.resolved)
