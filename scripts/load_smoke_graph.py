#!/usr/bin/env python
"""Load the smoke fixture into Neo4j, so arms B and C have something to walk.

Arm A's smoke needs no database — it indexes documents and reads them. Arms
B and C traverse, and a traversal over an empty graph produces `NO_MATCH`
for every question, which is a passing smoke that tested nothing.

This is the fixture's counterpart in the graph: the same three invented
cards, the same CR excerpt, loaded through the **real** loader statements
so that what CI exercises is the shipped merge logic rather than a second
implementation written to be convenient.

**It deletes nothing, ever.** `graph.loader.load_rules` normally prunes
rules the current document no longer contains, keyed on the CR hash. In a
CI container that holds only fixture data, "rules not in this document"
means every rule anything else created — including the namespaced nodes
`test_templates_integration.py` builds. Pruning is therefore off here, and
its absence costs nothing: a fixture has no withdrawn rules to clean up.
This is the same lesson as the compose teardown that named a profile and
took the corpus container with it — a delete predicate must be no broader
than what the command created.

Intended for a disposable database. Point it at a real corpus instance and
it will merge three fake cards into it; that is not destructive, but it is
not something anyone wants either.

Usage:
    python scripts/load_smoke_graph.py
    python scripts/load_smoke_graph.py --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from graphrag_mtg.etl.bulk import load_bulk
from graphrag_mtg.etl.cards import is_playable, parse_card
from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import (
    DEFAULT_BATCH_SIZE,
    graph_stats,
    load_cards,
    load_rules,
    load_rulings,
)
from graphrag_mtg.graph.schema import apply_schema

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FIXTURE = Path("tests/fixtures/smoke")
CR = Path("tests/fixtures/cr_excerpt.txt")

#: The fixture's own source hash namespace. Distinct from the real corpus's
#: so that a `SourceLoad` row from a fixture load can never be mistaken for
#: a record that the Comprehensive Rules were loaded.
SOURCE_PREFIX = "smoke-fixture"


def fixture_hash(path: Path) -> str:
    """A content hash, so a re-run of an unchanged fixture is idempotent."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cr", type=Path, default=CR)
    parser.add_argument("--cards", type=Path, default=FIXTURE / "cards.json")
    parser.add_argument("--rulings", type=Path, default=FIXTURE / "rulings.json")
    parser.add_argument("--stats", action="store_true", help="print counts and load nothing")
    args = parser.parse_args()

    with driver_session() as session:
        if args.stats:
            print(json.dumps(graph_stats(session), indent=2, sort_keys=True))
            return 0

    print(f"schema: {apply_schema()} statement(s)")

    doc = parse_cr(args.cr)
    raw_cards = load_bulk(args.cards)
    kept = [card for card in raw_cards if is_playable(card)]
    if len(kept) != len(raw_cards):
        # The fixture is three cards written by hand; if the shared
        # predicate rejects one, that is a fixture bug and it should stop
        # the load rather than quietly shrink the graph the smoke walks.
        raise SystemExit(
            f"{len(raw_cards) - len(kept)} fixture card(s) failed is_playable. "
            "The fixture is hand-written, so this is a defect in it, not a filter working."
        )
    cards = [parse_card(card) for card in kept]
    rulings = load_bulk(args.rulings)

    with driver_session() as session:
        rules = load_rules(
            session,
            doc,
            f"{SOURCE_PREFIX}-rules-{fixture_hash(args.cr)[:12]}",
            size=DEFAULT_BATCH_SIZE,
            prune=False,
        )
        merged = load_cards(
            session,
            cards,
            f"{SOURCE_PREFIX}-cards-{fixture_hash(args.cards)[:12]}",
            size=DEFAULT_BATCH_SIZE,
        )
        attached = load_rulings(
            session,
            rulings,
            f"{SOURCE_PREFIX}-rulings-{fixture_hash(args.rulings)[:12]}",
            size=DEFAULT_BATCH_SIZE,
        )
        stats = graph_stats(session)

    for label, counts in (("rules", rules), ("cards", merged), ("rulings", attached)):
        # `created / rows` spelled out rather than `BatchResult.__str__`,
        # whose empty-result branch reads "0 withdrawn rules deleted" — a
        # sentence about pruning, printed by a loader that never prunes.
        summary = ", ".join(f"{k}={v.created}/{v.rows}" for k, v in counts.items())
        print(f"{label}: {summary}")
    print(f"\nnodes: {stats['nodes']}")
    print(f"relationships: {stats['relationships']}")
    print("\nNothing was deleted. Pruning is off: this loader's delete predicate")
    print("would be broader than what it created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
