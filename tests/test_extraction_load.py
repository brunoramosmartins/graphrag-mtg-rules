"""The load path accepts gate output and nothing else — the ungated-zero test."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from graphrag_mtg.extraction.gate import gate_candidates
from graphrag_mtg.extraction.load import load_gated_triples
from graphrag_mtg.extraction.schemas import CardMention, EvidenceSpan, LinkMethod, RuleCitation

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


# Node ids are namespaced so the test only ever touches its own fixtures.
_R_ID = "pytest-ruling-1"
_C_ID = "pytest-card-1"
_RULE = "999.9z"  # implausible number; cleaned up explicitly, not by prefix
_INT_TEXT = "See 999.9z; also references pytest-card-1 behaviour."

_SEED_GRAPH = """
MERGE (rl:Ruling {ruling_id: $rid}) SET rl.text = $text
MERGE (c:Card {oracle_id: $cid})
MERGE (r:Rule {number: $rule})
"""

_CLEANUP = """
MATCH (n) WHERE n:Ruling AND n.ruling_id = $rid
   OR n:Card AND n.oracle_id = $cid
   OR n:Rule AND n.number = $rule
DETACH DELETE n
"""


def _int_triples():
    """A MENTIONS and a CITES_RULE triple, both gate-approved."""
    mention = CardMention(
        ruling_id=_R_ID,
        surface="pytest-card-1",
        oracle_id=_C_ID,
        span=EvidenceSpan(start=_INT_TEXT.index("pytest-card-1"), end=_INT_TEXT.index("pytest-card-1") + 13, text="pytest-card-1"),
        method=LinkMethod.EXACT,
        confidence=1.0,
    )
    # Span must contain the full rule number: a truncated "999.9" would
    # (correctly) trip the gate's explicit-number-disagrees check against
    # the "999.9z" citation.
    citation = RuleCitation(
        ruling_id=_R_ID,
        rule_number=_RULE,
        span=EvidenceSpan(start=0, end=10, text=_INT_TEXT[:10]),
        rationale="explicit reference in the fixture text",
        confidence=0.9,
    )
    result = gate_candidates(
        [mention, citation],
        source_texts={_R_ID: _INT_TEXT},
        known_rules=frozenset({_RULE}),
        known_cards=frozenset({_C_ID}),
    )
    return result.accepted


@pytest.mark.integration
class TestLoadIntoNeo4j:
    def test_edges_land_with_provenance_and_are_idempotent(self) -> None:
        from graphrag_mtg.graph.connection import driver_session

        params = {"rid": _R_ID, "cid": _C_ID, "rule": _RULE, "text": _INT_TEXT}
        triples = _int_triples()
        assert len(triples) == 2  # both candidates passed the gate

        with driver_session() as session:
            try:
                session.run(_SEED_GRAPH, **params)

                first = load_gated_triples(session, triples, version="itest")
                assert first["MENTIONS"].relationships_created == 1
                assert first["CITES_RULE"].relationships_created == 1

                # Provenance landed on the MENTIONS edge.
                rec = session.run(
                    "MATCH (:Ruling {ruling_id:$rid})-[e:MENTIONS]->(:Card {oracle_id:$cid}) "
                    "RETURN e.source AS source, e.method AS method, e.evidence_span AS span, "
                    "e.extractor_version AS version",
                    rid=_R_ID,
                    cid=_C_ID,
                ).single()
                assert rec["source"] == "deterministic"
                assert rec["method"] == "exact"
                assert rec["span"] == "pytest-card-1"
                assert rec["version"] == "itest"

                # MERGE means a second load creates no new edges.
                second = load_gated_triples(session, triples, version="itest")
                assert second["MENTIONS"].relationships_created == 0
                assert second["CITES_RULE"].relationships_created == 0
            finally:
                session.run(_CLEANUP, **params)
