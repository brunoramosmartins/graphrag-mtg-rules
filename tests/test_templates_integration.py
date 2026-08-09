"""Every template against a live Neo4j, on a graph these tests build.

Marked ``integration``: CI runs it against a service container. It creates
its own ``pytest-`` namespaced fixture and removes only that — it must
never wipe a graph it did not create, and it must not depend on the full
corpus being loaded.

This is where the template contract is actually checked. The unit tests
assert that a query is read-only, bounded and mapped; only a real server
says whether it *runs*, whether its rows have the shape the mapping
expects, and whether the planner can execute it without exhausting
memory. The `card_interaction` case is here for that last reason: its
first version was correct Cypher that killed the server.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.retrieval.rows import to_evidence
from graphrag_mtg.retrieval.templates import BY_NAME

NS = "pytest-retrieval-"

FIXTURE = f"""
CREATE (a:Card {{oracle_id: '{NS}a', name: '{NS}Alpha', normalized_name: '{NS}alpha',
                 oracle_text: 'Alpha has flying.'}})
CREATE (b:Card {{oracle_id: '{NS}b', name: '{NS}Beta', normalized_name: '{NS}beta',
                 oracle_text: 'Beta has flying too.'}})
CREATE (k:Keyword {{name: '{NS}flying', display_name: '{NS}Flying',
                    glossary_text: 'A keyword ability.'}})
CREATE (r:Rule {{number: '{NS}702.9', text: 'Flying is a static ability.', level: 2}})
CREATE (sub:Rule {{number: '{NS}702.9a', text: 'A creature with flying.', level: 3}})
CREATE (other:Rule {{number: '{NS}509.1', text: 'Declare blockers.', level: 2}})
CREATE (fmt:Format {{name: '{NS}modern'}})
CREATE (rl:Ruling {{ruling_id: '{NS}rl1', text: 'Alpha interacts with Beta.',
                    published_at: '2020-01-01'}})
CREATE (a)-[:HAS_KEYWORD]->(k)
CREATE (b)-[:HAS_KEYWORD]->(k)
CREATE (k)-[:DEFINED_BY]->(r)
CREATE (r)-[:HAS_SUBRULE]->(sub)
CREATE (r)-[:REFERENCES]->(other)
CREATE (a)-[:HAS_LEGALITY {{status: 'banned'}}]->(fmt)
CREATE (a)-[:HAS_RULING]->(rl)
CREATE (rl)-[:MENTIONS]->(b)
CREATE (rl)-[:CITES_RULE]->(r)
"""

CLEANUP = [
    f"MATCH (n:Card) WHERE n.oracle_id STARTS WITH '{NS}' DETACH DELETE n",
    f"MATCH (n:Keyword) WHERE n.name STARTS WITH '{NS}' DETACH DELETE n",
    f"MATCH (n:Rule) WHERE n.number STARTS WITH '{NS}' DETACH DELETE n",
    f"MATCH (n:Format) WHERE n.name STARTS WITH '{NS}' DETACH DELETE n",
    f"MATCH (n:Ruling) WHERE n.ruling_id STARTS WITH '{NS}' DETACH DELETE n",
]

CASES = [
    ("keyword_definition", {"keyword": f"{NS}flying"}, "rule", f"{NS}702.9"),
    ("card_legality", {"normalized_name": f"{NS}alpha", "format": f"{NS}modern"},
     "legality", f"{NS}modern"),
    ("deck_legality", {"normalized_names": [f"{NS}alpha"], "format": f"{NS}modern"},
     "legality", f"{NS}Alpha"),
    ("card_keyword_rules", {"normalized_name": f"{NS}alpha"}, "rule", f"{NS}702.9"),
    ("card_rulings", {"normalized_name": f"{NS}alpha"}, "ruling", f"{NS}rl1"),
    ("card_interaction", {"left": f"{NS}alpha", "right": f"{NS}beta"}, "card", f"{NS}Alpha"),
    ("rule_subtree", {"rule_number": f"{NS}702.9"}, "rule", f"{NS}702.9a"),
    ("rule_neighbourhood", {"rule_number": f"{NS}702.9"}, "rule", f"{NS}509.1"),
]


@pytest.fixture
def graph():
    with driver_session() as session:
        for statement in CLEANUP:
            session.run(statement)
        session.run(FIXTURE)
        try:
            yield session
        finally:
            for statement in CLEANUP:
                session.run(statement)


@pytest.mark.integration
@pytest.mark.parametrize("name,params,kind,expected", CASES, ids=[c[0] for c in CASES])
def test_a_template_runs_and_its_rows_map_to_evidence(graph, name, params, kind, expected) -> None:
    template = BY_NAME[name]
    rows = [dict(record) for record in graph.run(template.cypher, limit=25, **params)]
    evidence = to_evidence(template, rows)

    assert rows, f"{name} returned no rows against the fixture"
    assert expected in {e.key for e in evidence if e.kind == kind}
    # A missed OPTIONAL MATCH collects [{key: None}]; none of it may reach a citation.
    assert all(e.key not in ("None", "") for e in evidence)
    assert all(e.template == name for e in evidence)


@pytest.mark.integration
def test_the_interaction_traversal_survives_the_keyword_hub(graph) -> None:
    """Its first version was valid Cypher that exhausted the server's memory.

    The two-sided join expanded through the Keyword hub regardless of how
    few keywords the two cards had, and `$limit` could not help because
    the blowup preceded aggregation.
    """
    template = BY_NAME["card_interaction"]
    rows = [
        dict(record)
        for record in graph.run(
            template.cypher, left=f"{NS}alpha", right=f"{NS}beta", limit=25
        )
    ]
    (row,) = rows
    assert {entry["keyword"] for entry in row["shared_keywords"]} == {f"{NS}Flying"}
