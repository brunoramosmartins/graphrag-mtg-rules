"""The E-001 corpus: pin 8's parity, in both directions.

Pin 8 was written to stop arm A being unable to answer a stratum the graph
sweeps. The tests here hold that, and also the direction the pin was not
written to catch — arm A holding documents no other arm can cite.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.etl.cr_parser import CRDocument, Rule
from graphrag_mtg.evaluation.corpus import (
    LEGALITY_FORMATS,
    Document,
    build_corpus,
    card_documents,
    corpus_sha256,
    counts_by_kind,
    legality_sentences,
    ruling_documents,
    window_chunks,
)


@pytest.fixture
def cr_fixture() -> CRDocument:
    """A two-rule CR, enough for the corpus builder's ordering and hashing."""
    return CRDocument(
        effective_date=None,
        rules=[
            Rule(
                number="702.19",
                level=2,
                text="Trample lets excess combat damage through.",
                parent="702",
                section="7",
            ),
            Rule(
                number="613.7",
                level=2,
                text="Timestamp order determines which effect applies first.",
                parent="613",
                section="6",
            ),
        ],
        glossary=[],
    )


def card(oracle_id: str, name: str, **kw) -> dict:
    return {
        "oracle_id": oracle_id,
        "name": name,
        "layout": kw.pop("layout", "normal"),
        "type_line": kw.pop("type_line", "Creature — Elemental"),
        "oracle_text": kw.pop("oracle_text", "First strike."),
        "legalities": kw.pop("legalities", {"modern": "legal", "pauper": "not_legal"}),
        **kw,
    }


class TestLegalitySentences:
    def test_writes_the_enum_as_prose(self) -> None:
        # `{"modern": "legal"}` is a fact no retriever can match against
        # "Is Mindsparker legal in Modern?" — the question is a sentence
        # and the field is an enum.
        sentences = legality_sentences("Mindsparker", {"modern": "legal"})
        assert sentences == ["Mindsparker is legal in Modern."]

    def test_not_legal_gets_a_sentence_too(self) -> None:
        # A stratum that is half unanswerable is not parity: the negative
        # answer has to be retrievable, not merely absent.
        assert legality_sentences("X", {"pauper": "not_legal"}) == ["X is not legal in Pauper."]

    def test_banned_says_both_things(self) -> None:
        # "Banned" and "not legal" are different words for a question that
        # may use either, and the answer key uses the second.
        sentence = legality_sentences("X", {"modern": "banned"})[0]
        assert "banned in Modern" in sentence and "not legal in Modern" in sentence

    def test_restricted_is_legal(self) -> None:
        sentence = legality_sentences("X", {"vintage": "restricted"})[0]
        assert "restricted" in sentence and "is legal in Vintage" in sentence

    def test_formats_outside_the_list_are_skipped(self) -> None:
        assert legality_sentences("X", {"gladiator": "legal"}) == []


class TestCardDocuments:
    def test_carries_the_legality_facts_pin_8_requires(self) -> None:
        [document] = card_documents([card("o1", "Mindsparker")])
        assert "Mindsparker is legal in Modern." in document.text
        assert "Mindsparker is not legal in Pauper." in document.text
        assert document.legalities["modern"] == "legal"

    def test_drops_the_records_the_graph_drops(self) -> None:
        # Indexing tokens for arm A only would give one arm documents the
        # others cannot cite — the asymmetry pin 8 forbids, running the
        # other way.
        documents = card_documents(
            [card("o1", "Real Card"), card("o2", "A Token", type_line="Token Creature")]
        )
        assert [d.title for d in documents] == ["Real Card"]

    def test_keeps_only_the_formats_the_golden_set_uses(self) -> None:
        [document] = card_documents(
            [card("o1", "X", legalities={"modern": "legal", "gladiator": "legal"})]
        )
        assert set(document.legalities) <= set(LEGALITY_FORMATS)


class TestRulingDocuments:
    def test_prefixes_the_card_name(self) -> None:
        # Scryfall rulings are written as if the card name were already on
        # screen. Indexed bare, such a document matches nothing a question
        # asks, because a question names the card.
        [document] = ruling_documents(
            [{"oracle_id": "o1", "comment": "This ability triggers once.", "published_at": "2020"}],
            {"o1": "Mindsparker"},
        )
        assert document.text.startswith("Mindsparker: ")

    def test_skips_a_ruling_with_no_text(self) -> None:
        assert ruling_documents([{"oracle_id": "o1", "comment": "  "}], {"o1": "X"}) == []


class TestBuildCorpus:
    def test_drops_rulings_whose_card_is_not_indexed(self, cr_fixture) -> None:
        # The graph attaches rulings to loaded cards; a ruling for a token
        # would be a document with no counterpart and no name to be found by.
        documents = build_corpus(
            cr_fixture,
            [card("o1", "Real"), card("o2", "A Token", type_line="Token Creature")],
            [
                {"oracle_id": "o1", "comment": "Kept."},
                {"oracle_id": "o2", "comment": "Dropped."},
            ],
        )
        rulings = [d for d in documents if d.kind == "ruling"]
        assert len(rulings) == 1 and rulings[0].text.startswith("Real: ")

    def test_is_deterministically_ordered(self, cr_fixture) -> None:
        # Two builds of the same sources must produce the same list, or
        # `corpus_sha256` names nothing.
        args = (cr_fixture, [card("o2", "B"), card("o1", "A")], [])
        first, second = build_corpus(*args), build_corpus(*args)
        assert [d.doc_id for d in first] == [d.doc_id for d in second]
        assert corpus_sha256(first) == corpus_sha256(second)

    def test_the_hash_moves_when_text_moves(self, cr_fixture) -> None:
        before = build_corpus(cr_fixture, [card("o1", "A")], [])
        after = build_corpus(cr_fixture, [card("o1", "A", oracle_text="Flying.")], [])
        assert corpus_sha256(before) != corpus_sha256(after)

    def test_the_hash_ignores_a_title_change(self) -> None:
        # A title is presentation; the text is the index.
        base = Document(doc_id="rule:1", kind="rule", title="CR 1", text="Body.")
        renamed = Document(doc_id="rule:1", kind="rule", title="Rule 1", text="Body.")
        assert corpus_sha256([base]) == corpus_sha256([renamed])

    def test_counts_report_every_kind(self, cr_fixture) -> None:
        counts = counts_by_kind(build_corpus(cr_fixture, [card("o1", "A")], []))
        assert counts["card"] == 1 and "ruling" in counts


class TestWindowChunks:
    def test_short_documents_pass_through_whole(self) -> None:
        document = Document(doc_id="rule:1", kind="rule", title="t", text="a b c")
        assert list(window_chunks([document], size=10)) == [document]

    def test_windows_carry_the_grading_fields(self) -> None:
        # A window landing on the half of a rule that does not repeat its
        # own number must still be gradeable at rule-number granularity.
        document = Document(
            doc_id="rule:613.7",
            kind="rule",
            title="CR 613.7",
            text=" ".join(str(i) for i in range(50)),
            rule_number="613.7",
        )
        chunks = list(window_chunks([document], size=20, overlap=5))
        assert len(chunks) > 1
        assert all(chunk.rule_number == "613.7" for chunk in chunks)
        assert chunks[0].doc_id == "rule:613.7#0"

    def test_overlap_must_be_smaller_than_the_window(self) -> None:
        # Otherwise the generator never advances and the ablation hangs.
        with pytest.raises(ValueError, match="smaller than"):
            list(window_chunks([], size=10, overlap=10))
