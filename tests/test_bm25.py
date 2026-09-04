"""BM25: the tokenizer property the CR depends on, and length normalisation.

`extraction/cite_search.py` already has a TF-IDF index and is deliberately
not reused. These tests hold the two things that made a second index
necessary rather than lazy.
"""

from __future__ import annotations

from graphrag_mtg.evaluation.bm25 import Bm25Index, tokenize


class TestTokenize:
    def test_rule_numbers_survive_whole(self) -> None:
        # A tokenizer splitting `613.4b` into `613` and `4b` destroys the
        # one thing lexical retrieval is here to preserve: `613.4b` is not
        # approximately `613.4a`.
        assert "613.4b" in tokenize("See rule 613.4b for the sublayer.")

    def test_a_rule_number_is_not_also_split(self) -> None:
        assert "613" not in tokenize("rule 613.4b")

    def test_modal_verbs_are_kept(self) -> None:
        # `may`, `must` and `can` are what the rules turn on; an aggressive
        # stopword list would remove exactly the distinctions being asked
        # about.
        terms = tokenize("A player may pay the cost, but must announce it.")
        assert {"may", "must"} <= set(terms)

    def test_question_scaffolding_is_dropped(self) -> None:
        assert "what" not in tokenize("What does trample do?")

    def test_hyphenated_terms_survive(self) -> None:
        assert "state-based" in tokenize("state-based actions")


class TestBm25Index:
    def test_length_normalisation_prefers_the_short_exact_match(self) -> None:
        # The reason TF-IDF was not reused. Both documents mention the
        # term once; without `b` they would score identically, and the
        # one-line rule that answers the question would have no advantage
        # over a 300-word card that merely contains the word.
        index = Bm25Index(
            ["rule:702.19", "card:long"],
            [
                "702.19. Trample lets excess combat damage through.",
                "A long card with trample " + "unrelated " * 300,
            ],
        )
        assert index.search("trample", k=1)[0].doc_id == "rule:702.19"

    def test_length_normalisation_does_not_overturn_repeated_mentions(self) -> None:
        # The limit of the previous property, pinned so it is not
        # mistaken for a bug later: a document saying "trample" forty
        # times still outranks a short one saying it once. BM25 saturates
        # term frequency, it does not discard it, and forty mentions
        # genuinely are evidence. `b` decides between documents of
        # comparable term frequency, not between all long and all short.
        index = Bm25Index(
            ["rule:702.19", "card:long"],
            [
                "702.19. Trample lets excess combat damage through.",
                "A long card. " + "trample " * 40 + "unrelated " * 300,
            ],
        )
        assert index.search("trample", k=1)[0].doc_id == "card:long"

    def test_a_term_in_every_document_stops_contributing(self) -> None:
        # The unfloored IDF goes negative for a term in more than half the
        # corpus, which would make a common word actively lower a
        # document's score.
        index = Bm25Index(["a", "b"], ["creature flying", "creature trample"])
        assert index.search("creature", k=2) == [] or all(
            hit.score >= 0 for hit in index.search("creature", k=2)
        )

    def test_ties_break_by_id_so_runs_reproduce(self) -> None:
        index = Bm25Index(["b", "a"], ["trample", "trample"])
        assert [hit.doc_id for hit in index.search("trample", k=2)] == ["a", "b"]

    def test_an_unknown_term_scores_nothing(self) -> None:
        index = Bm25Index(["a"], ["trample"])
        assert index.search("banding") == []

    def test_a_rule_number_query_finds_its_rule(self) -> None:
        index = Bm25Index(
            ["rule:613.7", "rule:613.4"],
            ["613.7. Timestamp order.", "613.4. Within layer 7, apply sublayers."],
        )
        assert index.search("613.7", k=1)[0].doc_id == "rule:613.7"
