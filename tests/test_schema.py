"""Tests for the graph schema (ontology v1).

Unit tests are pure (no Neo4j). The idempotency test needs a live Neo4j
and is marked ``integration`` (CI runs it against a service container).
"""

from __future__ import annotations

import pytest

from graphrag_mtg.graph.schema import CONSTRAINTS, INDEXES, apply_schema, schema_statements


def test_statements_are_ordered_constraints_then_indexes():
    stmts = schema_statements()
    assert stmts[: len(CONSTRAINTS)] == CONSTRAINTS
    assert stmts[len(CONSTRAINTS) :] == INDEXES
    assert len(stmts) == len(CONSTRAINTS) + len(INDEXES)


def test_all_statements_are_idempotent():
    # Every DDL statement must be safe to re-run.
    for stmt in schema_statements():
        assert "IF NOT EXISTS" in stmt, stmt


def test_constraints_declare_uniqueness():
    for stmt in CONSTRAINTS:
        assert stmt.startswith("CREATE CONSTRAINT ")
        assert "IS UNIQUE" in stmt


def test_indexes_are_create_index():
    for stmt in INDEXES:
        assert stmt.startswith("CREATE INDEX ")
        assert " ON " in stmt


def test_statement_names_are_unique():
    # The second token is the constraint/index name; names must not collide.
    names = [stmt.split()[2] for stmt in schema_statements()]
    assert len(names) == len(set(names))


@pytest.mark.integration
def test_apply_schema_is_idempotent():
    # Applying twice must not raise, and must report all statements both times.
    assert apply_schema() == len(schema_statements())
    assert apply_schema() == len(schema_statements())

    from graphrag_mtg.graph.connection import driver_session

    with driver_session() as session:
        present = {row["name"] for row in session.run("SHOW CONSTRAINTS YIELD name RETURN name")}
    assert {"card_oracle_id", "rule_number", "ruling_id"} <= present
