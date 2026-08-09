"""Adversarial validation of generated Cypher — the Phase 4 DoD's hard line.

"Text2cypher never executes a write" is a criterion, so it is tested as
one. These cases fail closed by design: a query this module cannot read
with confidence is rejected, never executed hopefully.

What they do *not* claim is completeness. String checks catch a model's
mistakes; an attacker is confined by running in a read transaction, where
Neo4j refuses writes server-side no matter what the string says.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.retrieval.text2cypher import (
    CANNOT_TRANSLATE,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    extract_query,
    schema_prompt,
    validate,
)

ATTACKS = [
    ("MATCH (n) DETACH DELETE n", "write_clause"),
    ("MATCH (c:Card) RETURN c LIMIT 5; MATCH (n) DELETE n", "multiple_statements"),
    ("MATCH (c:Card) RETURN c LIMIT 5 // then\nCREATE (x:Evil)", "comment"),
    ("MATCH (c:Card) /* CREATE */ RETURN c LIMIT 5", "comment"),
    ("MATCH (c:Card) SET c.name = 'x' RETURN c LIMIT 5", "write_clause"),
    ("MATCH (c:Card) REMOVE c.name RETURN c LIMIT 5", "write_clause"),
    ("MERGE (c:Card {name:'x'}) RETURN c LIMIT 1", "write_clause"),
    ("DROP INDEX card_name", "write_clause"),
    ("MATCH (c:Card) FOREACH (x IN [1] | SET c.n = 1) RETURN c LIMIT 1", "write_clause"),
    # Caught by the procedure allowlist, not the clause scan: the DELETE
    # rides inside a string literal, which is blanked first so that a card
    # named "Delete the Past" stays queryable. Two checks, one attack.
    (
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n','DELETE n',{}) RETURN 1 LIMIT 1",
        "procedure_not_allowed",
    ),
    ("CALL db.labels() YIELD label RETURN label LIMIT 5", "procedure_not_allowed"),
    ("USE system MATCH (c) RETURN c LIMIT 1", "unexpected_opening_clause"),
    ("MATCH (c:Card) LIMIT 5", "no_return"),
    ("   ", "empty"),
]


@pytest.mark.parametrize("cypher,expected", ATTACKS, ids=[a[0][:28] for a in ATTACKS])
def test_a_write_never_survives_validation(cypher: str, expected: str) -> None:
    verdict = validate(cypher)
    assert not verdict.ok
    assert verdict.reason.startswith(expected)
    assert verdict.cypher == ""


class TestBenignQueries:
    def test_a_read_query_passes_unchanged(self) -> None:
        query = "MATCH (c:Card {name:'Opt'}) RETURN c.name LIMIT 5"
        assert validate(query).cypher == query

    def test_a_card_named_like_a_clause_is_not_a_clause(self) -> None:
        """String literals are blanked first, or 'Delete the Past' is unqueryable."""
        query = "MATCH (c:Card {name:'Delete the Past'}) RETURN c.name LIMIT 5"
        assert validate(query).ok

    def test_optional_match_may_open_a_query(self) -> None:
        assert validate("OPTIONAL MATCH (c:Card) RETURN c LIMIT 3").ok

    def test_a_trailing_semicolon_is_tolerated(self) -> None:
        """One statement that merely ends in a semicolon is not two statements."""
        assert validate("MATCH (c:Card) RETURN c LIMIT 5;").ok


class TestLimits:
    def test_a_missing_limit_is_injected(self) -> None:
        verdict = validate("MATCH (c:Card) RETURN c.name")
        assert verdict.ok and verdict.cypher.endswith(f"LIMIT {DEFAULT_LIMIT}")

    def test_an_oversized_limit_is_clamped_not_rejected(self) -> None:
        """An over-eager bound is a mistake, not an attack."""
        verdict = validate("MATCH (c:Card) RETURN c.name LIMIT 99999")
        assert verdict.ok and f"LIMIT {MAX_LIMIT}" in verdict.cypher

    def test_a_reasonable_limit_is_left_alone(self) -> None:
        assert "LIMIT 7" in validate("MATCH (c:Card) RETURN c LIMIT 7").cypher


class TestResponseParsing:
    def test_declining_returns_nothing_to_run(self) -> None:
        """The honest outcome: better than a plausible query on the wrong nodes."""
        assert extract_query(CANNOT_TRANSLATE) == ""

    def test_a_declared_refusal_wins_over_surrounding_prose(self) -> None:
        assert extract_query("I am sorry, CANNOT TRANSLATE this one.") == ""

    def test_a_fenced_block_is_unwrapped(self) -> None:
        assert extract_query("```cypher\nMATCH (c) RETURN c LIMIT 1\n```") == (
            "MATCH (c) RETURN c LIMIT 1"
        )

    def test_a_bare_query_survives(self) -> None:
        assert extract_query("MATCH (c) RETURN c LIMIT 1") == "MATCH (c) RETURN c LIMIT 1"


class TestSchemaPrompt:
    def test_it_describes_the_graph_and_the_rules(self) -> None:
        prompt = schema_prompt({"Card": ["name", "oracle_id"]}, ["HAS_RULING"])
        assert "(:Card {name, oracle_id})" in prompt
        assert "-[:HAS_RULING]->" in prompt
        assert "read only" in prompt

    def test_it_offers_the_model_a_way_to_decline(self) -> None:
        prompt = schema_prompt({"Card": ["name"]}, [])
        assert CANNOT_TRANSLATE in prompt
