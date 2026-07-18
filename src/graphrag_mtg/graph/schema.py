"""Graph schema as code: constraints and indexes for ontology v1.

Mirrors docs/ontology.md. All statements are idempotent
(``IF NOT EXISTS``), so applying the schema repeatedly is safe. Cypher
lives in the named constants below — never inline elsewhere.

Usage:
    python -m graphrag_mtg.graph.schema           # apply to the configured Neo4j
    python -m graphrag_mtg.graph.schema --dry-run # print the statements only
"""

from __future__ import annotations

import argparse

from graphrag_mtg.graph.connection import driver_session

# Node-key / uniqueness constraints (each also creates a backing index).
CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT card_oracle_id IF NOT EXISTS FOR (c:Card) REQUIRE c.oracle_id IS UNIQUE",
    "CREATE CONSTRAINT cardface_key IF NOT EXISTS FOR (f:CardFace) REQUIRE f.face_key IS UNIQUE",
    "CREATE CONSTRAINT format_name IF NOT EXISTS FOR (fm:Format) REQUIRE fm.name IS UNIQUE",
    "CREATE CONSTRAINT rule_number IF NOT EXISTS FOR (r:Rule) REQUIRE r.number IS UNIQUE",
    "CREATE CONSTRAINT keyword_name IF NOT EXISTS FOR (k:Keyword) REQUIRE k.name IS UNIQUE",
    "CREATE CONSTRAINT ruling_id IF NOT EXISTS FOR (rl:Ruling) REQUIRE rl.ruling_id IS UNIQUE",
)

# Secondary indexes for lookup / card-name linking at query time.
INDEXES: tuple[str, ...] = (
    "CREATE INDEX card_name IF NOT EXISTS FOR (c:Card) ON (c.name)",
    "CREATE INDEX cardface_name IF NOT EXISTS FOR (f:CardFace) ON (f.name)",
    "CREATE INDEX rule_level IF NOT EXISTS FOR (r:Rule) ON (r.level)",
)


def schema_statements() -> tuple[str, ...]:
    """Return every DDL statement, constraints before indexes."""
    return (*CONSTRAINTS, *INDEXES)


def apply_schema() -> int:
    """Apply all constraints and indexes to the configured Neo4j.

    Idempotent; returns the number of statements executed.
    """
    statements = schema_statements()
    with driver_session() as session:
        for stmt in statements:
            session.run(stmt)
    return len(statements)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print statements; apply nothing")
    args = parser.parse_args()

    if args.dry_run:
        for stmt in schema_statements():
            print(stmt)
        return 0

    n = apply_schema()
    print(f"Applied {n} schema statements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
