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
    Text2Cypher,
    check_plan,
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
    # Not an attack — a crash. Nothing binds parameters in this layer, so an
    # obedient model following the old prompt produced a query that raised
    # inside the pipeline. Refused with a name instead.
    ("MATCH (c:Card {name: $name}) RETURN c.name AS key, c.oracle_text AS text", "unbound_parameter"),
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

    def test_it_does_not_ask_for_parameters_it_cannot_bind(self) -> None:
        """The prompt used to request parameters that the executor never supplies."""
        assert "no parameters" in schema_prompt({"Card": ["name"]}, [])


class DriverError(Exception):
    """Stands in for a Neo4j error, which carries a dotted `code`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TestServerPlan:
    """EXPLAIN — the only check that knows whether the Cypher is real.

    The string checks reason about text. A query can be read-only, bounded,
    citable and still be unparseable or name a label that does not exist;
    the server is the only thing that can say so, and planning touches no
    data.
    """

    QUERY = "MATCH (c:Card) RETURN c.name AS key, c.oracle_text AS text LIMIT 5"

    def test_an_accepted_plan_reports_nothing(self) -> None:
        assert check_plan(self.QUERY, lambda cypher, params: []) == ""

    def test_the_query_is_planned_not_run(self) -> None:
        seen: list[str] = []

        def run(cypher: str, params):
            seen.append(cypher)
            return []

        check_plan(self.QUERY, run)
        assert seen == [f"EXPLAIN {self.QUERY}"]

    def test_a_rejected_plan_names_the_server_s_reason(self) -> None:
        def run(cypher: str, params):
            raise DriverError("Neo.ClientError.Statement.SyntaxError")

        assert check_plan(self.QUERY, run) == "explain:SyntaxError"

    def test_an_error_without_a_code_still_gets_a_name(self) -> None:
        def run(cypher: str, params):
            raise TimeoutError("took too long")

        assert check_plan(self.QUERY, run) == "explain:TimeoutError"


class TestPlanningBeforeExecution:
    QUERY = "MATCH (c:Card) RETURN c.name AS key, c.oracle_text AS text LIMIT 5"

    def layer(self, response: str) -> Text2Cypher:
        return Text2Cypher(lambda q, s: response, {"Card": ["name"]}, ["HAS_RULING"])

    def test_a_query_the_server_refuses_to_plan_is_never_executed(self) -> None:
        seen: list[str] = []

        def run(cypher: str, params):
            seen.append(cypher)
            raise DriverError("Neo.ClientError.Statement.SyntaxError")

        found, why = self.layer(self.QUERY).evidence("anything", run)
        assert found == []
        assert why == "explain:SyntaxError"
        assert seen == [f"EXPLAIN {self.QUERY}"]

    def test_a_planned_query_runs_and_cites(self) -> None:
        def run(cypher: str, params):
            return [] if cypher.startswith("EXPLAIN") else [{"key": "Opt", "text": "Draw a card."}]

        found, why = self.layer(self.QUERY).evidence("anything", run)
        assert why == ""
        assert [(item.kind, item.key) for item in found] == [("row", "Opt")]

    def test_a_failure_after_planning_is_named_not_swallowed(self) -> None:
        """Planning succeeds and execution still dies: timeouts, memory ceilings."""

        def run(cypher: str, params):
            if cypher.startswith("EXPLAIN"):
                return []
            raise DriverError("Neo.TransientError.General.MemoryPoolOutOfMemoryError")

        found, why = self.layer(self.QUERY).evidence("anything", run)
        assert found == []
        assert why == "execution:MemoryPoolOutOfMemoryError"
