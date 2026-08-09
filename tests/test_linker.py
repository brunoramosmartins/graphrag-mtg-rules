"""Deterministic linking cascade: exact, loose, and the homonym tail."""

from __future__ import annotations

from graphrag_mtg.extraction.linker import Lexicon, scan_ruling
from graphrag_mtg.extraction.schemas import LinkMethod

CARDS = [
    ("Giant Growth", "gg-1"),
    ("Lim-Dul's Vault", "ldv-1"),
    ("Opt", "opt-1"),
    ("Fire // Ice", "fi-1"),
    ("Nissa, Who Shakes the World", "nissa-1"),
    ("Card Draw", "cd-1"),  # a real card whose name is a generic phrase
    ("The Ring", "ring-1"),
]


def lexicon() -> Lexicon:
    return Lexicon.build(CARDS)


class TestLexicon:
    def test_single_word_names_are_segregated(self) -> None:
        lex = lexicon()
        assert "opt" in lex.single_word
        assert "opt" not in lex.exact

    def test_faces_indexed_individually(self) -> None:
        lex = lexicon()
        # "Fire" and "Ice" are single words; the combined name is multi-word.
        assert lex.single_word["fire"] == {"fi-1"}
        assert "fire // ice" in lex.exact


class TestScanExact:
    def test_exact_match_with_verbatim_span(self) -> None:
        text = "This works like Giant Growth in combat."
        resolved, pending = scan_ruling("r1", text, lexicon())
        assert pending == []
        (m,) = resolved
        assert m.oracle_id == "gg-1"
        assert m.method == LinkMethod.EXACT
        assert text[m.span.start : m.span.end] == m.span.text == "Giant Growth"

    def test_longest_match_wins(self) -> None:
        text = "Compare with Nissa, Who Shakes the World here."
        resolved, _ = scan_ruling("r1", text, lexicon())
        assert [m.oracle_id for m in resolved] == ["nissa-1"]

    def test_host_card_self_mention_skipped(self) -> None:
        text = "Giant Growth targets a single creature."
        resolved, pending = scan_ruling("r1", text, lexicon(), host_oracle_id="gg-1")
        assert resolved == [] and pending == []


class TestMultiwordCapitalization:
    def test_all_lowercase_generic_phrase_is_not_a_mention(self) -> None:
        # "card draw" collides with the card "Card Draw" but names nothing.
        text = "This gives you extra card draw each turn."
        resolved, pending = scan_ruling("r1", text, lexicon())
        assert resolved == [] and pending == []

    def test_capitalized_significant_word_survives_lowercase_article(self) -> None:
        # "the Ring" — the article stays lowercase, but "Ring" is the name.
        text = "Abilities that cause the Ring to tempt you trigger."
        resolved, _ = scan_ruling("r1", text, lexicon())
        (m,) = resolved
        assert m.oracle_id == "ring-1"
        assert m.span.text == "the Ring"

    def test_titlecase_phrase_still_matches(self) -> None:
        text = "Extra Card Draw is the theme here."
        resolved, _ = scan_ruling("r1", text, lexicon())
        assert [m.oracle_id for m in resolved] == ["cd-1"]


class TestScanLoose:
    def test_punctuation_insensitive_match(self) -> None:
        # loose_name removes punctuation without inserting spaces, so the
        # deliberate collision is "LimDuls Vault" (see test_normalize.py).
        text = "See the ruling on LimDuls Vault for details."
        resolved, _ = scan_ruling("r1", text, lexicon())
        (m,) = resolved
        assert m.oracle_id == "ldv-1"
        assert m.method == LinkMethod.LOOSE


class TestScanHomonyms:
    def test_capitalized_single_word_goes_to_pending(self) -> None:
        text = "This interacts with Opt when cast."
        resolved, pending = scan_ruling("r1", text, lexicon())
        assert resolved == []
        (p,) = pending
        assert p.mention.oracle_id is None
        assert p.mention.method == LinkMethod.SURFACE
        assert p.candidate_oracle_ids == ("opt-1",)

    def test_lowercase_occurrence_is_not_a_candidate(self) -> None:
        text = "You may opt to draw a card."
        resolved, pending = scan_ruling("r1", text, lexicon())
        assert resolved == [] and pending == []

    def test_pending_span_is_verbatim(self) -> None:
        text = "Opt resolves first."
        _, (p,) = scan_ruling("r1", text, lexicon())
        span = p.mention.span
        assert text[span.start : span.end] == span.text == "Opt"


class TestHostFragmentSuppression:
    """A match inside a longer occurrence of the host's own name is not a mention.

    The narrowness is the point. Every broader rule tried on the E-003 dev
    subset cost real mentions: a substring test would drop "The Ring" on the
    host *Call of the Ring*, and a prefix test would drop "Brutal Cathar" on
    the host *Brutal Cathar // Moonrage Brute*. Both are gold mentions.
    """

    def lexicon(self) -> Lexicon:
        return Lexicon.build(
            [
                ("Kemba's Legion", "host-kemba"),
                ("Legion", "oid-legion"),
                ("Brutal Cathar // Moonrage Brute", "host-cathar"),
                ("The Ring", "oid-ring"),
                ("Call of the Ring", "host-call"),
            ]
        )

    def test_fragment_of_the_host_name_is_dropped(self) -> None:
        text = "The number of creatures Kemba's Legion can block is fixed."
        resolved, pending = scan_ruling("r1", text, self.lexicon(), host_oracle_id="host-kemba")
        assert all(m.oracle_id != "oid-legion" for m in resolved)
        assert all(p.mention.surface != "Legion" for p in pending)

    def test_the_host_named_in_full_is_still_a_mention(self) -> None:
        """Equality is not containment: the gold records these as true positives."""
        text = "Brutal Cathar returns transformed."
        resolved, pending = scan_ruling("r2", text, self.lexicon(), host_oracle_id="host-cathar")
        surfaces = [m.surface for m in resolved] + [p.mention.surface for p in pending]
        assert "Brutal Cathar" in surfaces

    def test_a_card_whose_name_the_host_contains_survives(self) -> None:
        text = "The Ring won't tempt you."
        resolved, pending = scan_ruling("r3", text, self.lexicon(), host_oracle_id="host-call")
        surfaces = [m.surface for m in resolved] + [p.mention.surface for p in pending]
        assert "The Ring" in surfaces

    def test_no_host_means_no_suppression(self) -> None:
        text = "Kemba's Legion can block."
        resolved, pending = scan_ruling("r4", text, self.lexicon())
        assert resolved or pending
