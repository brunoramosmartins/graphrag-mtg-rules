"""Tests for the Neo4j backbone loader.

Row builders are pure and tested without a database. The idempotency test is
marked ``integration``: it needs a live Neo4j and creates its own namespaced
fixture nodes, removing only those afterwards — it must never wipe a graph it
did not create.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.etl.cards import parse_card
from graphrag_mtg.etl.cr_parser import CRDocument, GlossaryEntry, Rule
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import (
    MERGE_CARDS,
    MERGE_LEGALITIES,
    batched,
    card_keyword_rows,
    card_rows,
    face_rows,
    keyword_definition_rows,
    legality_rows,
    rule_reference_rows,
    rule_rows,
    rule_tree_rows,
    ruling_id,
    ruling_rows,
)

CARD = {
    "oracle_id": "oid-1",
    "name": "Æther Vial",
    "layout": "normal",
    "mana_cost": "{1}",
    "cmc": 1.0,
    "type_line": "Artifact",
    "oracle_text": "text",
    "colors": [],
    "color_identity": [],
    "keywords": ["Flying", "Trample"],
    "legalities": {"modern": "legal", "standard": "banned"},
}

SPLIT_CARD = {
    "oracle_id": "oid-2",
    "name": "Fire // Ice",
    "layout": "split",
    "cmc": 2.0,
    "type_line": "Instant // Instant",
    "keywords": [],
    "legalities": {"modern": "legal"},
    "card_faces": [
        {"name": "Fire", "mana_cost": "{1}{R}", "oracle_text": "a", "type_line": "Instant"},
        {"name": "Ice", "mana_cost": "{1}{U}", "oracle_text": "b", "type_line": "Instant"},
    ],
}


def _doc() -> CRDocument:
    return CRDocument(
        effective_date="February 27, 2026",
        rules=[
            Rule(number="702", level=1, text="Keyword Abilities", parent=None, section="Additional"),
            Rule(number="702.2", level=2, text="Deathtouch", parent="702", section="Additional"),
            Rule(
                number="702.2c",
                level=3,
                text="lethal damage",
                parent="702.2",
                section="Additional",
                references=["702.2"],
            ),
        ],
        glossary=[
            GlossaryEntry(term="Deathtouch", definition="A keyword ability.", references=["702.2"]),
            # A general glossary term, not a keyword — must not become a Keyword.
            GlossaryEntry(term="Active Player", definition="The player whose turn.", references=["102.1"]),
        ],
    )


def test_batched_splits_and_keeps_the_remainder():
    assert list(batched([{"i": i} for i in range(5)], 2)) == [
        [{"i": 0}, {"i": 1}],
        [{"i": 2}, {"i": 3}],
        [{"i": 4}],
    ]
    assert list(batched([], 10)) == []


def test_ruling_id_is_stable_and_content_derived():
    raw = {"oracle_id": "o", "published_at": "2020-01-01", "source": "wotc", "comment": "text"}
    assert ruling_id(raw) == ruling_id(dict(raw))
    assert ruling_id({**raw, "comment": "other"}) != ruling_id(raw)
    assert len(ruling_id(raw)) == 32


def test_card_rows_carry_the_normalized_linking_key():
    rows = card_rows([parse_card(CARD)])
    assert rows[0]["oracle_id"] == "oid-1"
    assert rows[0]["normalized_name"] == "aether vial"


def test_face_rows_only_exist_for_multi_face_cards():
    assert face_rows([parse_card(CARD)]) == []
    rows = face_rows([parse_card(SPLIT_CARD)])
    assert [r["name"] for r in rows] == ["Fire", "Ice"]
    assert [r["face_key"] for r in rows] == ["oid-2#0", "oid-2#1"]


def test_legality_rows_are_one_per_format():
    rows = legality_rows([parse_card(CARD)])
    assert {(r["format"], r["status"]) for r in rows} == {("modern", "legal"), ("standard", "banned")}


def test_card_keyword_rows_are_one_per_keyword():
    rows = card_keyword_rows([parse_card(CARD)])
    # The merge key is normalized; the printed spelling is kept alongside it.
    assert [r["keyword"] for r in rows] == ["flying", "trample"]
    assert [r["display_name"] for r in rows] == ["Flying", "Trample"]


def test_rule_rows_and_tree_edges():
    doc = _doc()
    assert [r["number"] for r in rule_rows(doc)] == ["702", "702.2", "702.2c"]
    # Chapters have no parent, so they contribute no HAS_SUBRULE edge.
    assert rule_tree_rows(doc) == [
        {"number": "702.2", "parent": "702"},
        {"number": "702.2c", "parent": "702.2"},
    ]
    assert rule_reference_rows(doc) == [{"source": "702.2c", "target": "702.2"}]


def test_only_keyword_glossary_entries_become_keywords():
    # The bug this locks in: the glossary is far broader than keywords. Terms
    # citing rules outside 701/702 ("Active Player" -> 102.1) would inflate the
    # Keyword label and pollute the definition_1hop stratum.
    rows = keyword_definition_rows(_doc())
    assert [r["keyword"] for r in rows] == ["deathtouch"]
    assert rows[0]["display_name"] == "Deathtouch"
    assert rows[0]["rule"] == "702.2"


def test_card_and_glossary_keywords_share_one_normalized_key():
    # Scryfall writes "First strike", the CR glossary "First Strike". Keying on
    # the raw name split 19 keywords into two nodes each - one holding the card
    # edges, the other the rule definition - silently breaking the
    # Card -> Keyword -> Rule traversal that keyword_rule_2hop needs.
    card = parse_card({**CARD, "keywords": ["First strike"]})
    doc = CRDocument(
        effective_date=None,
        rules=[Rule(number="702.7", level=2, text="First Strike", parent="702", section="s")],
        glossary=[
            GlossaryEntry(term="First Strike", definition="A keyword.", references=["702.7"])
        ],
    )

    from_card = card_keyword_rows([card])[0]
    from_glossary = keyword_definition_rows(doc)[0]

    assert from_card["keyword"] == from_glossary["keyword"] == "first strike"
    # The original spelling survives for display.
    assert from_card["display_name"] == "First strike"
    assert from_glossary["display_name"] == "First Strike"


def test_ruling_rows_skip_records_without_an_oracle_id():
    raw = [
        {"oracle_id": "o1", "comment": "a", "published_at": "2020-01-01", "source": "wotc"},
        {"oracle_id": "", "comment": "b", "published_at": "2020-01-01", "source": "wotc"},
    ]
    rows = ruling_rows(raw)
    assert len(rows) == 1
    assert rows[0]["text"] == "a"


def test_batch_result_reports_prunes_as_deletions():
    # A prune carries deletions only. Rendering it as "0 created" would read as
    # though nothing happened on the very release where rules were withdrawn.
    from graphrag_mtg.graph.loader import BatchResult

    assert str(BatchResult(nodes_deleted=3)) == "3 withdrawn rules deleted"
    assert str(BatchResult(rows=10, nodes_created=4)) == "4 created / 10 rows"


def test_prune_statement_is_scoped_only_by_the_source_hash():
    """PRUNE_STALE_RULES is global by construction — assert that, do not run it.

    The statement deletes every :Rule whose source hash is not the current
    load's. That is correct for a CR release, where the load has just stamped
    the whole document, and catastrophic anywhere else: run against a populated
    database with an arbitrary hash it removes the entire rule tree. There is no
    safe way to exercise it in the unit suite, so its behaviour is verified by
    `scripts/simulate_cr_update.py`, which performs a real full-document load
    first. This test only pins the contract that makes it dangerous.
    """
    from graphrag_mtg.graph.loader import PRUNE_STALE_RULES

    assert "DETACH DELETE" in PRUNE_STALE_RULES
    assert "r.source_sha256 <> $sha256" in PRUNE_STALE_RULES
    # No other predicate narrows it; a future edit adding one should update the
    # simulation script and this contract together.
    assert PRUNE_STALE_RULES.count("WHERE") == 1


@pytest.mark.integration
def test_merge_is_idempotent():
    """Loading the same rows twice must create nothing the second time."""
    rows = card_rows([parse_card(CARD), parse_card(SPLIT_CARD)])
    for row in rows:  # namespace so we only ever touch our own fixture nodes
        row["oracle_id"] = f"pytest-{row['oracle_id']}"
    legalities = [
        {"oracle_id": "pytest-oid-1", "format": "pytest-format", "status": "legal"},
    ]

    with driver_session() as session:
        try:
            first = session.run(MERGE_CARDS, rows=rows, sha256="t").consume().counters
            first_edges = session.run(MERGE_LEGALITIES, rows=legalities, sha256="t").consume().counters
            second = session.run(MERGE_CARDS, rows=rows, sha256="t").consume().counters
            second_edges = session.run(MERGE_LEGALITIES, rows=legalities, sha256="t").consume().counters

            assert first.nodes_created == 2
            assert first_edges.relationships_created == 1
            assert second.nodes_created == 0
            assert second_edges.relationships_created == 0
        finally:
            session.run(
                "MATCH (c:Card) WHERE c.oracle_id STARTS WITH 'pytest-' DETACH DELETE c"
            )
            session.run("MATCH (f:Format {name: 'pytest-format'}) DETACH DELETE f")
