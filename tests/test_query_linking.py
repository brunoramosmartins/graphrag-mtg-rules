"""Query-time linking: a question is not a ruling, and the policy differs."""

from __future__ import annotations

from itertools import pairwise
from typing import ClassVar

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


class TestCanonicalName:
    """A resolved card carries the node key, not a re-normalized surface."""

    def test_a_card_carries_its_normalized_name(self) -> None:
        (card,) = linker().link("What does Serra Angel do").cards
        assert card.normalized == "serra angel"

    def test_punctuation_in_the_surface_does_not_survive_into_it(self) -> None:
        (card,) = linker().link("Nico casts Humility, then passes.").cards
        assert card.surface.endswith(",")
        assert card.normalized == "humility"

    def test_a_keyword_has_none_because_its_key_is_the_node_key(self) -> None:
        (keyword,) = linker().link("What does Flying do").keywords
        assert keyword.normalized == ""


class TestClausePunctuation:
    """A mention mid-sentence arrives with the punctuation attached.

    The tokenizer keeps commas and periods because card names contain them,
    so "Humility," is a string in no lookup table. Multi-word names survive
    that through the loose table; single-word names had no rescue and simply
    failed to resolve, which from outside looks like a card the corpus does
    not hold. The surface as written is still tried first.
    """

    def test_a_single_word_name_survives_a_trailing_comma(self) -> None:
        (card,) = linker().link("Nico casts Humility, then passes.").cards
        assert card.key == "hum"

    def test_and_a_trailing_period(self) -> None:
        (card,) = linker().link("Nico casts Opalescence. Then what?").cards
        assert card.key == "opa"

    def test_a_multiword_name_still_resolves_the_same_way(self) -> None:
        (card,) = linker().link("Nico casts Lightning Bolt, then passes.").cards
        assert card.key == "bolt"

    def test_trimming_does_not_weaken_the_capitalization_gate(self) -> None:
        """A sentence-initial capital is not evidence of a proper noun."""
        entities = linker().link("Humility, and then what happens?")
        assert entities.cards == ()
        assert entities.ambiguous[0].candidates == ("hum",)

    def test_an_english_phrase_is_still_not_a_card(self) -> None:
        assert linker().link("extra card draw each turn, please").cards == ()


class TestAFaceIsWeakerThanAWholeName:
    """Both defects E-008's evidence check caught, before a token was spent.

    The lexicon indexes "Fire // Ice" under the combined name *and* each
    face, in the same tables and with equal standing. On the loaded corpus
    that made *Lightning Bolt* ambiguous against a face of "Emeritus of
    Conflict // Lightning Bolt", and made the word "what" resolve
    *Who // What // When // Where // Why* in any question containing it —
    23 of E-007's 42 subgraphs carried that card.
    """

    CARDS: ClassVar[list[tuple[str, str]]] = [
        ("Lightning Bolt", "bolt"),
        ("Emeritus of Conflict // Lightning Bolt", "emeritus"),
        ("Who // What // When // Where // Why", "wwwww"),
        ("Humility", "hum"),
    ]

    def linker(self) -> QueryLinker:
        return QueryLinker(Lexicon.build(self.CARDS), keywords=["Flying"])

    def cards(self, question: str) -> list[str]:
        return [c.key for c in self.linker().link(question).cards]

    def test_a_whole_name_outranks_a_face_of_another_card(self) -> None:
        assert self.cards("Ana casts Lightning Bolt at a creature.") == ["bolt"]

    def test_a_single_word_that_is_only_a_face_does_not_resolve(self) -> None:
        """It skipped the capitalization gate, so any 'what' pulled the card in."""
        assert self.cards("Ana casts Lightning Bolt. Who or what takes the damage?") == ["bolt"]

    def test_a_single_word_whole_name_still_resolves(self) -> None:
        assert self.cards("Nico casts Humility and passes.") == ["hum"]

    def test_the_face_is_still_indexed_for_the_ingestion_linker(self) -> None:
        """`Lexicon.build` was measured in E-003; only the query side changed."""
        lexicon = Lexicon.build(self.CARDS)
        assert "wwwww" in lexicon.single_word["what"]
        assert lexicon.faces["what"] == {"wwwww"}


class TestKeywordPunctuation:
    def test_a_keyword_followed_by_a_comma_still_resolves(self) -> None:
        """The trim the card path already had, missing from the keyword path."""
        linker = QueryLinker(Lexicon.build([("Humility", "hum")]), keywords=["Flying"])
        assert [k.key for k in linker.link("Does Flying, or trample, apply?").keywords] == ["Flying"]
