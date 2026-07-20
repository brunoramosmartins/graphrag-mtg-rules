"""The load path accepts gate output and nothing else — the ungated-zero test."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from graphrag_mtg.extraction.gate import gate_candidates
from graphrag_mtg.extraction.load import load_gated_triples
from graphrag_mtg.extraction.schemas import EvidenceSpan, RuleCitation

RULING_TEXT = "As per 613.4b, apply ability changes in timestamp order."


class FakeSession:
    """Records statements/rows; returns Neo4j-shaped counters."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict]]] = []

    def run(self, statement: str, *, rows: list[dict], **_: object) -> SimpleNamespace:
        self.calls.append((statement, rows))
        counters = SimpleNamespace(
            relationships_created=len(rows), nodes_created=0, nodes_deleted=0
        )
        return SimpleNamespace(consume=lambda: SimpleNamespace(counters=counters))


def gated_citation():
    text = "As per 613.4b"
    candidate = RuleCitation(
        ruling_id="r1",
        rule_number="613.4b",
        span=EvidenceSpan(start=0, end=len(text), text=text),
        rationale="explicit",
        confidence=0.9,
    )
    result = gate_candidates(
        [candidate],
        source_texts={"r1": RULING_TEXT},
        known_rules=frozenset({"613.4b"}),
        known_cards=frozenset(),
    )
    (triple,) = result.accepted
    return candidate, triple


class TestGateOnlyWritePath:
    def test_pydantic_candidate_is_refused(self) -> None:
        candidate, _ = gated_citation()
        session = FakeSession()
        with pytest.raises(TypeError, match="gate_candidates"):
            load_gated_triples(session, [candidate], version="v1")
        assert session.calls == []  # refused before any Cypher ran

    def test_plain_dict_is_refused(self) -> None:
        with pytest.raises(TypeError):
            load_gated_triples(FakeSession(), [{"edge_type": "MENTIONS"}], version="v1")

    def test_gated_triple_is_written_with_provenance(self) -> None:
        _, triple = gated_citation()
        session = FakeSession()
        results = load_gated_triples(session, [triple], version="v1")
        assert results["CITES_RULE"].relationships_created == 1
        ((statement, rows),) = session.calls
        assert "CITES_RULE" in statement
        (row,) = rows
        assert row["source"] == "llm"
        assert row["span_text"] == "As per 613.4b"
        assert row["version"] == "v1"
