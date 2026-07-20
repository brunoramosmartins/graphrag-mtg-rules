"""Idempotent, incremental load of the deterministic backbone into Neo4j.

Everything here is ``MERGE``-based and batched through ``UNWIND``, so a full
re-run is a no-op rather than a second copy of the graph — the Phase 2 DoD.
Cypher lives in the named constants below and is always parameterized; no
statement is ever built by string interpolation.

**Change detection lives in the graph, not on disk.** ``etl/download.py``
keeps a manifest of what was *downloaded*; that cannot answer whether a source
was *loaded* (wipe the database and the manifest still claims it is current).
So each load records a ``:SourceLoad`` node holding the source's SHA-256, and
a source whose hash already matches is skipped. ``:SourceLoad`` is operational
metadata, deliberately outside the domain ontology.

**Ruling identity is synthesized.** Scryfall rulings ship with no id at all
(only ``oracle_id``, ``published_at``, ``source`` and ``comment``), while the
ontology keys ``Ruling`` on ``ruling_id``. A content hash of those four fields
gives a stable key, so re-loading the same ruling merges onto the same node
instead of creating a duplicate.

**Keywords are keyed on a normalized name.** Scryfall writes keywords in
sentence case ("First strike") and the CR glossary in title case ("First
Strike"). Merging on the raw name split 19 keywords across two nodes each —
one holding the card edges, the other the rule definition — silently breaking
the ``Card -> Keyword -> Rule`` traversal the ``keyword_rule_2hop`` stratum
depends on. Both sides now merge on :func:`normalize_name`, with the original
spelling kept as ``display_name``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphrag_mtg.etl.cards import Card, load_oracle_cards
from graphrag_mtg.etl.cr_parser import CRDocument, parse_cr
from graphrag_mtg.etl.download import MANIFEST_PATH, load_manifest
from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.graph.connection import driver_session

DEFAULT_BATCH_SIZE = 1_000
RULINGS_PATH = Path("data/raw/scryfall_rulings.json")

# CR chapters that define keywords: 701 keyword actions, 702 keyword abilities.
# A glossary entry citing anything else is a general definition, not a keyword.
KEYWORD_RULE_CHAPTERS = frozenset({"701", "702"})

# ─── Cypher ──────────────────────────────────────────────────────────────────
# Every statement is idempotent and parameterized. Batches arrive as $rows.

MERGE_CARDS = """
UNWIND $rows AS row
MERGE (c:Card {oracle_id: row.oracle_id})
SET c.name = row.name,
    c.normalized_name = row.normalized_name,
    c.layout = row.layout,
    c.cmc = row.cmc,
    c.type_line = row.type_line,
    c.oracle_text = row.oracle_text,
    c.mana_cost = row.mana_cost,
    c.colors = row.colors,
    c.color_identity = row.color_identity,
    c.source_sha256 = $sha256
"""

MERGE_FACES = """
UNWIND $rows AS row
MATCH (c:Card {oracle_id: row.oracle_id})
MERGE (f:CardFace {face_key: row.face_key})
SET f.name = row.name,
    f.normalized_name = row.normalized_name,
    f.index = row.index,
    f.mana_cost = row.mana_cost,
    f.oracle_text = row.oracle_text,
    f.type_line = row.type_line
MERGE (c)-[:HAS_FACE]->(f)
"""

MERGE_LEGALITIES = """
UNWIND $rows AS row
MATCH (c:Card {oracle_id: row.oracle_id})
MERGE (fmt:Format {name: row.format})
MERGE (c)-[e:HAS_LEGALITY]->(fmt)
SET e.status = row.status, e.source = 'deterministic'
"""

MERGE_CARD_KEYWORDS = """
UNWIND $rows AS row
MATCH (c:Card {oracle_id: row.oracle_id})
MERGE (k:Keyword {name: row.keyword})
SET k.display_name = coalesce(k.display_name, row.display_name)
MERGE (c)-[e:HAS_KEYWORD]->(k)
SET e.source = 'deterministic'
"""

MERGE_RULES = """
UNWIND $rows AS row
MERGE (r:Rule {number: row.number})
SET r.level = row.level,
    r.text = row.text,
    r.section = row.section,
    r.examples = row.examples,
    r.source_sha256 = $sha256
"""

MERGE_RULE_TREE = """
UNWIND $rows AS row
MATCH (parent:Rule {number: row.parent})
MATCH (child:Rule {number: row.number})
MERGE (parent)-[e:HAS_SUBRULE]->(child)
SET e.source = 'deterministic'
"""

MERGE_RULE_REFERENCES = """
UNWIND $rows AS row
MATCH (src:Rule {number: row.source})
MATCH (dst:Rule {number: row.target})
MERGE (src)-[e:REFERENCES]->(dst)
SET e.source = 'deterministic'
"""

MERGE_KEYWORD_DEFINITIONS = """
UNWIND $rows AS row
MATCH (r:Rule {number: row.rule})
MERGE (k:Keyword {name: row.keyword})
SET k.glossary_text = row.definition,
    k.display_name = row.display_name
MERGE (k)-[e:DEFINED_BY]->(r)
SET e.source = 'deterministic'
"""

MERGE_RULINGS = """
UNWIND $rows AS row
MATCH (c:Card {oracle_id: row.oracle_id})
MERGE (rl:Ruling {ruling_id: row.ruling_id})
SET rl.text = row.text,
    rl.published_at = row.published_at,
    rl.source = row.source,
    rl.source_sha256 = $sha256
MERGE (c)-[:HAS_RULING]->(rl)
"""

READ_SOURCE_LOAD = "MATCH (s:SourceLoad {name: $name}) RETURN s.sha256 AS sha256"

MERGE_SOURCE_LOAD = """
MERGE (s:SourceLoad {name: $name})
SET s.sha256 = $sha256, s.loaded_at = datetime(), s.node_count = $node_count
"""

COUNT_NODES_BY_LABEL = """
MATCH (n) UNWIND labels(n) AS label
RETURN label, count(*) AS count ORDER BY count DESC
"""

COUNT_RELATIONSHIPS = """
MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC
"""


@dataclass
class BatchResult:
    """What a batched statement actually changed in the graph.

    Reports Neo4j's own counters rather than the number of rows sent. The two
    differ sharply and the distinction matters: a MERGE that matches nothing
    (a ruling for a card we filtered out) still consumes its row, and a second
    identical load consumes every row while creating nothing. Row counts would
    claim work that never happened; ``nodes_created == 0`` on a re-run is the
    direct evidence of idempotency.
    """

    rows: int = 0
    nodes_created: int = 0
    relationships_created: int = 0

    @property
    def created(self) -> int:
        """Total entities created."""
        return self.nodes_created + self.relationships_created

    def __str__(self) -> str:
        return f"{self.created:,} created / {self.rows:,} rows"


@dataclass
class LoadReport:
    """What one source's load did."""

    source: str
    skipped: bool
    reason: str = ""
    counts: dict[str, BatchResult] = field(default_factory=dict)


def ruling_id(raw: dict[str, Any]) -> str:
    """Return a stable id for a Scryfall ruling, which ships without one.

    Hashes the fields that identify the ruling's content, so the same ruling
    merges onto the same node across reloads.
    """
    payload = "|".join(
        [
            raw.get("oracle_id", ""),
            raw.get("published_at", ""),
            raw.get("source", ""),
            raw.get("comment", ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def batched(rows: Iterable[dict[str, Any]], size: int = DEFAULT_BATCH_SIZE) -> Iterator[list[dict]]:
    """Yield ``rows`` in lists of at most ``size``."""
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _run_batches(session, statement: str, rows, *, sha256: str = "", size: int) -> BatchResult:
    """Execute ``statement`` over ``rows`` in batches, accumulating real counters."""
    result = BatchResult()
    for batch in batched(rows, size):
        counters = session.run(statement, rows=batch, sha256=sha256).consume().counters
        result.rows += len(batch)
        result.nodes_created += counters.nodes_created
        result.relationships_created += counters.relationships_created
    return result


def _source_is_current(session, name: str, sha256: str) -> bool:
    """Whether the graph already holds this exact version of ``name``."""
    record = session.run(READ_SOURCE_LOAD, name=name).single()
    return record is not None and record["sha256"] == sha256


def _record_source_load(session, name: str, sha256: str, node_count: int) -> None:
    session.run(MERGE_SOURCE_LOAD, name=name, sha256=sha256, node_count=node_count)


# ─── Row builders (pure; unit-testable without Neo4j) ────────────────────────


def card_rows(cards: list[Card]) -> list[dict[str, Any]]:
    """Card node properties."""
    return [
        {
            "oracle_id": c.oracle_id,
            "name": c.name,
            "normalized_name": c.normalized_name,
            "layout": c.layout,
            "cmc": c.cmc,
            "type_line": c.type_line,
            "oracle_text": c.oracle_text,
            "mana_cost": c.mana_cost,
            "colors": c.colors,
            "color_identity": c.color_identity,
        }
        for c in cards
    ]


def face_rows(cards: list[Card]) -> list[dict[str, Any]]:
    """CardFace rows for multi-face cards only."""
    return [
        {
            "oracle_id": c.oracle_id,
            "face_key": f.face_key,
            "index": f.index,
            "name": f.name,
            "normalized_name": f.normalized_name,
            "mana_cost": f.mana_cost,
            "oracle_text": f.oracle_text,
            "type_line": f.type_line,
        }
        for c in cards
        for f in c.faces
    ]


def legality_rows(cards: list[Card]) -> list[dict[str, Any]]:
    """One row per (card, format) legality edge."""
    return [
        {"oracle_id": c.oracle_id, "format": fmt, "status": str(status)}
        for c in cards
        for fmt, status in c.legalities.items()
    ]


def card_keyword_rows(cards: list[Card]) -> list[dict[str, Any]]:
    """One row per (card, keyword) edge, keyed on the normalized keyword name."""
    return [
        {"oracle_id": c.oracle_id, "keyword": normalize_name(kw), "display_name": kw}
        for c in cards
        for kw in c.keywords
    ]


def rule_rows(doc: CRDocument) -> list[dict[str, Any]]:
    """Rule node properties."""
    return [
        {
            "number": r.number,
            "level": r.level,
            "text": r.text,
            "section": r.section,
            "examples": r.examples,
        }
        for r in doc.rules
    ]


def rule_tree_rows(doc: CRDocument) -> list[dict[str, Any]]:
    """HAS_SUBRULE edges (chapters have no parent, so they are skipped)."""
    return [{"number": r.number, "parent": r.parent} for r in doc.rules if r.parent]


def rule_reference_rows(doc: CRDocument) -> list[dict[str, Any]]:
    """REFERENCES edges, already validated against the tree by the parser."""
    return [
        {"source": r.number, "target": target} for r in doc.rules for target in r.references
    ]


def keyword_definition_rows(doc: CRDocument) -> list[dict[str, Any]]:
    """Keyword -> DEFINED_BY -> Rule, for glossary entries that define a keyword.

    Only entries citing chapter 701 (keyword actions) or 702 (keyword abilities)
    qualify. The glossary is much broader than keywords: of its 772 (term, rule)
    pairs, 476 point at general rules — "Ability" -> 113, "Active Player" ->
    102.1, "Additional Cost" -> 118. Turning those into ``Keyword`` nodes would
    inflate the label the ontology reserves for ability keywords and pollute the
    ``definition_1hop`` stratum, where "what does X do?" must not retrieve
    "Active Player".

    The remaining glossary definitions are deliberately not modeled: no
    golden-set question needs a general glossary node, and the ontology's rule
    is that only what a question uses enters the schema.
    """
    return [
        {
            "keyword": normalize_name(entry.term),
            "display_name": entry.term,
            "definition": entry.definition,
            "rule": rule,
        }
        for entry in doc.glossary
        for rule in entry.references
        if rule.split(".")[0] in KEYWORD_RULE_CHAPTERS
    ]


def ruling_rows(raw_rulings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ruling node rows with a synthesized stable id."""
    return [
        {
            "ruling_id": ruling_id(raw),
            "oracle_id": raw["oracle_id"],
            "text": raw.get("comment", ""),
            "published_at": raw.get("published_at"),
            "source": raw.get("source"),
        }
        for raw in raw_rulings
        if raw.get("oracle_id")
    ]


# ─── Loaders ─────────────────────────────────────────────────────────────────


def load_cards(session, cards: list[Card], sha256: str, *, size: int) -> dict[str, BatchResult]:
    """Merge cards, faces, legality edges and keyword edges."""
    return {
        "Card": _run_batches(session, MERGE_CARDS, card_rows(cards), sha256=sha256, size=size),
        "CardFace": _run_batches(session, MERGE_FACES, face_rows(cards), size=size),
        "HAS_LEGALITY": _run_batches(session, MERGE_LEGALITIES, legality_rows(cards), size=size),
        "HAS_KEYWORD": _run_batches(
            session, MERGE_CARD_KEYWORDS, card_keyword_rows(cards), size=size
        ),
    }


def load_rules(session, doc: CRDocument, sha256: str, *, size: int) -> dict[str, BatchResult]:
    """Merge the CR tree, its cross-references, and glossary keyword definitions.

    Order matters: every node must exist before the edge statements MATCH it.
    """
    return {
        "Rule": _run_batches(session, MERGE_RULES, rule_rows(doc), sha256=sha256, size=size),
        "HAS_SUBRULE": _run_batches(session, MERGE_RULE_TREE, rule_tree_rows(doc), size=size),
        "REFERENCES": _run_batches(
            session, MERGE_RULE_REFERENCES, rule_reference_rows(doc), size=size
        ),
        "DEFINED_BY": _run_batches(
            session, MERGE_KEYWORD_DEFINITIONS, keyword_definition_rows(doc), size=size
        ),
    }


def load_rulings(session, raw_rulings, sha256: str, *, size: int) -> dict[str, BatchResult]:
    """Merge rulings and attach them to their cards.

    Rulings whose ``oracle_id`` names a card we did not load (tokens and other
    filtered layouts) simply do not match, and are silently not attached.
    """
    rows = ruling_rows(raw_rulings)
    return {"Ruling": _run_batches(session, MERGE_RULINGS, rows, sha256=sha256, size=size)}


def graph_stats(session) -> dict[str, dict[str, int]]:
    """Return node counts by label and relationship counts by type."""
    nodes = {r["label"]: r["count"] for r in session.run(COUNT_NODES_BY_LABEL)}
    rels = {r["type"]: r["count"] for r in session.run(COUNT_RELATIONSHIPS)}
    return {"nodes": nodes, "relationships": rels}


# ─── Orchestration ───────────────────────────────────────────────────────────

CARDS_SOURCE = "scryfall_oracle_cards"
RULES_SOURCE = "comprehensive_rules"
RULINGS_SOURCE = "scryfall_rulings"


def _hash_of(manifest: dict[str, dict], source: str) -> str:
    """Return the recorded SHA-256 for ``source``.

    Raises:
        KeyError: if the source was never downloaded — loading a file the
            manifest does not describe would leave the graph unattributable.
    """
    if source not in manifest:
        msg = f"{source!r} is not in the download manifest; run etl.download first."
        raise KeyError(msg)
    return manifest[source]["sha256"]


def load_all(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    limit: int | None = None,
    manifest_path: Path = MANIFEST_PATH,
) -> list[LoadReport]:
    """Load every deterministic source into Neo4j, skipping unchanged ones.

    Args:
        batch_size: Rows per ``UNWIND`` batch.
        force: Reload even when the graph already holds the source's hash.
        limit: Cap the number of cards, for smoke runs.
        manifest_path: The download manifest recording each source's hash.

    Returns:
        One :class:`LoadReport` per source, in load order. Cards load before
        rulings because rulings attach to existing cards.
    """
    manifest = load_manifest(manifest_path)
    reports: list[LoadReport] = []

    with driver_session() as session:
        # 1. Cards — rulings and (later) linking all hang off these.
        sha = _hash_of(manifest, CARDS_SOURCE)
        if not force and limit is None and _source_is_current(session, CARDS_SOURCE, sha):
            reports.append(LoadReport(CARDS_SOURCE, skipped=True, reason="unchanged"))
        else:
            cards = list(load_oracle_cards(limit=limit))
            counts = load_cards(session, cards, sha, size=batch_size)
            if limit is None:
                _record_source_load(session, CARDS_SOURCE, sha, counts["Card"].rows)
            reports.append(LoadReport(CARDS_SOURCE, skipped=False, counts=counts))

        # 2. The CR tree.
        sha = _hash_of(manifest, RULES_SOURCE)
        if not force and _source_is_current(session, RULES_SOURCE, sha):
            reports.append(LoadReport(RULES_SOURCE, skipped=True, reason="unchanged"))
        else:
            doc = parse_cr()
            counts = load_rules(session, doc, sha, size=batch_size)
            _record_source_load(session, RULES_SOURCE, sha, counts["Rule"].rows)
            reports.append(LoadReport(RULES_SOURCE, skipped=False, counts=counts))

        # 3. Rulings, which MATCH the cards loaded in step 1.
        sha = _hash_of(manifest, RULINGS_SOURCE)
        if not force and limit is None and _source_is_current(session, RULINGS_SOURCE, sha):
            reports.append(LoadReport(RULINGS_SOURCE, skipped=True, reason="unchanged"))
        else:
            raw = json.loads(RULINGS_PATH.read_text(encoding="utf-8"))
            counts = load_rulings(session, raw, sha, size=batch_size)
            if limit is None:
                _record_source_load(session, RULINGS_SOURCE, sha, counts["Ruling"].rows)
            reports.append(LoadReport(RULINGS_SOURCE, skipped=False, counts=counts))

    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="reload even if unchanged")
    parser.add_argument("--limit", type=int, help="load at most N cards (smoke run)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--stats", action="store_true", help="print graph counts and exit")
    args = parser.parse_args()

    if args.stats:
        with driver_session() as session:
            stats = graph_stats(session)
        for group, counts in stats.items():
            print(f"\n{group}:")
            for name, count in counts.items():
                print(f"  {name:<16} {count:>10,}")
        return 0

    for report in load_all(batch_size=args.batch_size, force=args.force, limit=args.limit):
        if report.skipped:
            print(f"{report.source:<22} skipped ({report.reason})")
            continue
        print(f"{report.source:<22} loaded")
        for name, result in report.counts.items():
            print(f"    {name:<14} {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
