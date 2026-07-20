"""Load gate-approved edges into the graph. The only write path for Phase 3.

Accepts :class:`~graphrag_mtg.extraction.gate.GatedTriple` and nothing
else — a plain dict or a Pydantic candidate raises ``TypeError`` before
any Cypher runs. Combined with the sealed constructor on ``GatedTriple``,
this makes "zero ungated triples in the graph" enforceable by a unit test
instead of by code review.

Provenance on every edge (ontology v1): ``source`` ('deterministic' for
exact/loose linking, 'llm' for LLM-derived edges), ``method``,
``confidence``, the evidence span (offsets + verbatim text), and
``extractor_version`` so a prompt iteration can be told apart from the
previous one in the graph itself.
"""

from __future__ import annotations

from collections.abc import Iterable

from graphrag_mtg.extraction.gate import GatedTriple
from graphrag_mtg.graph.loader import DEFAULT_BATCH_SIZE, BatchResult, batched

# Deterministic-in-spirit linking methods; everything else is LLM-derived.
_DETERMINISTIC_METHODS = {"exact", "loose"}

MERGE_MENTIONS = """
UNWIND $rows AS row
MATCH (rl:Ruling {ruling_id: row.source_key})
MATCH (c:Card {oracle_id: row.target_key})
MERGE (rl)-[e:MENTIONS]->(c)
SET e.source = row.source,
    e.method = row.method,
    e.confidence = row.confidence,
    e.evidence_start = row.span_start,
    e.evidence_end = row.span_end,
    e.evidence_span = row.span_text,
    e.extractor_version = row.version
"""

MERGE_CITES_RULE = """
UNWIND $rows AS row
MATCH (rl:Ruling {ruling_id: row.source_key})
MATCH (r:Rule {number: row.target_key})
MERGE (rl)-[e:CITES_RULE]->(r)
SET e.source = row.source,
    e.method = row.method,
    e.confidence = row.confidence,
    e.evidence_start = row.span_start,
    e.evidence_end = row.span_end,
    e.evidence_span = row.span_text,
    e.rationale = row.rationale,
    e.extractor_version = row.version
"""

# ON CREATE only: an explicit "see rule X" cross-reference already exists as
# a deterministic edge, and an implicit LLM duplicate must never relabel it.
MERGE_IMPLICIT_REFERENCES = """
UNWIND $rows AS row
MATCH (a:Rule {number: row.source_key})
MATCH (b:Rule {number: row.target_key})
MERGE (a)-[e:REFERENCES]->(b)
ON CREATE SET
    e.source = row.source,
    e.method = row.method,
    e.confidence = row.confidence,
    e.evidence_start = row.span_start,
    e.evidence_end = row.span_end,
    e.evidence_span = row.span_text,
    e.rationale = row.rationale,
    e.extractor_version = row.version
"""

_STATEMENT_BY_EDGE = {
    "MENTIONS": MERGE_MENTIONS,
    "CITES_RULE": MERGE_CITES_RULE,
    "REFERENCES": MERGE_IMPLICIT_REFERENCES,
}


def _row(triple: GatedTriple, version: str) -> dict[str, object]:
    return {
        "source_key": triple.source_key,
        "target_key": triple.target_key,
        "source": "deterministic" if triple.method in _DETERMINISTIC_METHODS else "llm",
        "method": triple.method,
        "confidence": triple.confidence,
        "span_start": triple.span_start,
        "span_end": triple.span_end,
        "span_text": triple.span_text,
        "rationale": triple.rationale,
        "version": version,
    }


def load_gated_triples(
    session,
    triples: Iterable[GatedTriple],
    *,
    version: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, BatchResult]:
    """MERGE gated edges, batched, reporting Neo4j's own counters per type.

    Args:
        session: Open Neo4j session.
        triples: Gate output only. Anything that is not a
            :class:`GatedTriple` raises ``TypeError`` before any write.
        version: Extractor/linker version stamped on every edge.
        batch_size: UNWIND batch size.

    Returns:
        ``BatchResult`` per edge type actually written.

    Raises:
        TypeError: if any element did not come from the gate.
    """
    by_edge: dict[str, list[dict[str, object]]] = {}
    for triple in triples:
        if not isinstance(triple, GatedTriple):
            msg = (
                f"load_gated_triples() only accepts GatedTriple (got {type(triple).__name__}); "
                "run candidates through gate_candidates() first"
            )
            raise TypeError(msg)
        by_edge.setdefault(triple.edge_type, []).append(_row(triple, version))

    results: dict[str, BatchResult] = {}
    for edge_type, rows in by_edge.items():
        statement = _STATEMENT_BY_EDGE[edge_type]
        result = BatchResult()
        for batch in batched(rows, batch_size):
            counters = session.run(statement, rows=batch).consume().counters
            result.rows += len(batch)
            result.relationships_created += counters.relationships_created
        results[edge_type] = result
    return results
