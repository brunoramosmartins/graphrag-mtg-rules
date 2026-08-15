"""Template traversals: the reliable, testable retrieval layer (ADR-005).

Every query the system trusts lives here as a named constant with declared
parameters, never as an f-string assembled at a call site. Two reasons,
both load-bearing:

- **Injection.** Values arrive as Cypher parameters (``$name``). A card
  called ``Boseiju, Who Endures`` and a card called ``') DETACH DELETE n //``
  travel the same path and neither becomes syntax.
- **Auditability.** A citation in this project names the path that
  produced it. A path assembled by string concatenation cannot be quoted
  back to a reader with confidence that it is what ran.

Coverage follows the reachability measurement, not optimism
(`scripts/reachability.py`, ADR-007). The graph reaches 100% of the gold
rules for `definition_1hop` and `keyword_rule_2hop` at two hops, inside
balls of ~200 rules, and `legality_1hop` is a single typed edge — those
three strata are template territory and these queries are the whole
answer. `interaction_multihop` is not: half its questions have no
keyword to seed from, so the templates here supply entities, rulings and
whatever structure exists, and ADR-007's text retrieval supplies the
rules. A template that returns nothing for such a question is doing its
job; the failure the DoD forbids is returning something *wrong* quietly.

Every template is read-only and carries a mandatory ``$limit``. That is
enforced by a test over :data:`TEMPLATES` rather than by review, so a
template added later cannot quietly omit either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Clauses that write. Checked against every template by the test suite;
# text2cypher (Phase 4, later) validates generated Cypher against the same
# list, so the two layers cannot disagree about what "read-only" means.
WRITE_CLAUSES = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "LOAD CSV",
    "CALL apoc.periodic",
    "FOREACH",
)

# Ceiling on variable-length expansion. The CR tree is at most three levels
# deep (chapter -> rule -> subrule), so 3 reaches every descendant while
# refusing to become an unbounded walk.
MAX_TREE_DEPTH = 3

#: Placeholder the queries below carry, substituted by :func:`_bounded`.
#: Not an f-string and not ``%``: Cypher map literals are full of braces
#: (``{number: sub.number}``), and either mechanism would need every one of
#: them doubled — which is how a query becomes unreadable and then wrong.
DEPTH_MARKER = "*MAXDEPTH"


def _bounded(cypher: str) -> str:
    """Substitute the tree-depth ceiling into a query."""
    return cypher.replace(DEPTH_MARKER, f"*1..{MAX_TREE_DEPTH}")


@dataclass(frozen=True)
class Emit:
    """How one returned column becomes citable evidence.

    Declared beside the query on purpose. A ``RETURN`` clause edited
    without its mapping is a silent break — the traversal still runs, the
    rows still arrive, and the evidence quietly stops appearing. Keeping
    both in one file lets a test assert that every column named here is
    one the query actually returns.

    Attributes:
        kind: Evidence kind (``rule``, ``ruling``, ``card``, ...).
        key: Column holding the citation handle. Inside ``collection``,
            the key of each map.
        text: Column holding the text. Same rule inside a collection.
        path: Citation path, formatted with the row (and the collected
            item). This is the project's differentiator, so it is data
            rather than something assembled at the call site.
        collection: When set, the column holds a list of maps and one
            piece of evidence is produced per entry.
        distance: Hops from what the question named. Drives eviction.
    """

    kind: str
    key: str
    text: str
    path: str
    collection: str = ""
    distance: int = 0


@dataclass(frozen=True)
class Template:
    """One named traversal, its parameters, and what it is for.

    Attributes:
        name: Stable identifier, used in the answer's provenance.
        cypher: The query. Read-only, parameterized, ``$limit``-bounded.
        params: Required parameter names, excluding ``limit``.
        strata: Golden-set strata this traversal is meant to answer.
        description: What the subgraph it returns means.
        emits: How its rows become evidence.
    """

    name: str
    cypher: str
    params: tuple[str, ...]
    strata: tuple[str, ...]
    description: str
    emits: tuple[Emit, ...] = ()

    def columns(self) -> set[str]:
        """Column names this query returns, read from its ``AS`` aliases.

        Sliced from ``RETURN`` onward, so an ``UNWIND ... AS wanted``
        earlier in the query is not mistaken for a returned column.
        """
        _, _, tail = self.cypher.partition("RETURN")
        return set(re.findall(r"\bAS\s+([a-z_]+)", tail, re.IGNORECASE))


KEYWORD_DEFINITION = _bounded("""
MATCH (k:Keyword {name: $keyword})-[:DEFINED_BY]->(r:Rule)
OPTIONAL MATCH (r)-[:HAS_SUBRULE*MAXDEPTH]->(sub:Rule)
RETURN k.display_name AS keyword,
       k.glossary_text AS glossary,
       r.number AS rule_number,
       r.text AS rule_text,
       collect(DISTINCT {number: sub.number, text: sub.text}) AS subrules
LIMIT $limit
""")

#: The card the question named, unconditionally.
#:
#: Every other card traversal reaches the node through a relationship, so a
#: card with no rulings and no keywords produced no rows and vanished —
#: taking its oracle text, the single most important evidence for a rules
#: question about it, with it. Measured on E-007's pool: 264 card traversals
#: planned, 164 cards reaching a subgraph. A question naming a card gets the
#: card, and whether anything hangs off it is a separate question.
CARD_CORE = """
MATCH (c:Card {normalized_name: $normalized_name})
RETURN c.name AS card,
       c.oracle_text AS card_text,
       c.type_line AS type_line
LIMIT $limit
"""

CARD_LEGALITY = """
MATCH (c:Card {normalized_name: $normalized_name})-[e:HAS_LEGALITY]->(f:Format)
WHERE $format IS NULL OR f.name = $format
RETURN c.name AS card, c.oracle_text AS card_text, f.name AS format, e.status AS status
ORDER BY f.name
LIMIT $limit
"""

DECK_LEGALITY = """
UNWIND $normalized_names AS wanted
MATCH (c:Card {normalized_name: wanted})-[e:HAS_LEGALITY]->(f:Format {name: $format})
WHERE e.status <> 'legal'
RETURN c.name AS card, f.name AS format, e.status AS status
ORDER BY c.name
LIMIT $limit
"""

CARD_KEYWORD_RULES = _bounded("""
MATCH (c:Card {normalized_name: $normalized_name})-[:HAS_KEYWORD]->(k:Keyword)
MATCH (k)-[:DEFINED_BY]->(r:Rule)
OPTIONAL MATCH (r)-[:HAS_SUBRULE*MAXDEPTH]->(sub:Rule)
RETURN c.name AS card,
       k.display_name AS keyword,
       k.glossary_text AS keyword_glossary,
       r.number AS rule_number,
       r.text AS rule_text,
       collect(DISTINCT {number: sub.number, text: sub.text}) AS subrules
ORDER BY k.display_name
LIMIT $limit
""")

CARD_RULINGS = """
MATCH (c:Card {normalized_name: $normalized_name})-[:HAS_RULING]->(rl:Ruling)
OPTIONAL MATCH (rl)-[:CITES_RULE]->(r:Rule)
RETURN c.name AS card,
       c.oracle_text AS card_text,
       rl.ruling_id AS ruling_id,
       rl.text AS ruling_text,
       rl.published_at AS published_at,
       collect(DISTINCT {number: r.number, text: r.text}) AS cited_rules
ORDER BY rl.published_at DESC
LIMIT $limit
"""

# Staged with WITH on purpose, and the staging is not style. The obvious
# form of the keyword join —
#     OPTIONAL MATCH (a)-[:HAS_KEYWORD]->(k:Keyword)<-[:HAS_KEYWORD]-(b)
# — exhausts the server's memory pool on the loaded graph, even when both
# cards have *no* keywords at all: the planner expands through the Keyword
# hub, where `flying` alone carries thousands of edges. `$limit` cannot
# save it, because the blowup happens before aggregation. Collecting after
# each OPTIONAL MATCH keeps every intermediate result bounded, and
# intersecting the two keyword sets replaces the two-sided pattern
# entirely. This is the roadmap's registered "interaction subgraphs
# explode" risk, found by running the query rather than by reading it.
CARD_INTERACTION = """
MATCH (a:Card {normalized_name: $left})
MATCH (b:Card {normalized_name: $right})
OPTIONAL MATCH (a)-[:HAS_RULING]->(shared:Ruling)-[:MENTIONS]->(b)
WITH a, b, collect(DISTINCT {ruling_id: shared.ruling_id, text: shared.text}) AS shared_left
OPTIONAL MATCH (b)-[:HAS_RULING]->(mirrored:Ruling)-[:MENTIONS]->(a)
WITH a, b, shared_left,
     collect(DISTINCT {ruling_id: mirrored.ruling_id, text: mirrored.text}) AS shared_right
OPTIONAL MATCH (a)-[:HAS_KEYWORD]->(mine:Keyword)
WITH a, b, shared_left, shared_right, collect(DISTINCT mine) AS a_keywords
OPTIONAL MATCH (b)-[:HAS_KEYWORD]->(common:Keyword) WHERE common IN a_keywords
OPTIONAL MATCH (common)-[:DEFINED_BY]->(shared_rule:Rule)
WITH a, b, shared_left, shared_right,
     collect(DISTINCT {keyword: common.display_name, rule: shared_rule.number}) AS shared_kw
RETURN a.name AS left_card,
       b.name AS right_card,
       a.oracle_text AS left_text,
       b.oracle_text AS right_text,
       shared_left AS left_rulings,
       shared_right AS right_rulings,
       shared_kw AS shared_keywords
LIMIT $limit
"""

RULE_SUBTREE = _bounded("""
MATCH (r:Rule {number: $rule_number})
OPTIONAL MATCH (r)-[:HAS_SUBRULE*MAXDEPTH]->(sub:Rule)
RETURN r.number AS rule_number,
       r.text AS rule_text,
       r.section AS section,
       collect(DISTINCT {number: sub.number, text: sub.text, examples: sub.examples}) AS subrules
LIMIT $limit
""")

RULE_NEIGHBOURHOOD = """
MATCH (r:Rule {number: $rule_number})
OPTIONAL MATCH (r)-[:REFERENCES]->(out:Rule)
OPTIONAL MATCH (r)<-[:REFERENCES]-(inbound:Rule)
RETURN r.number AS rule_number,
       r.text AS rule_text,
       collect(DISTINCT {number: out.number, text: out.text}) AS references_out,
       collect(DISTINCT {number: inbound.number, text: inbound.text}) AS references_in
LIMIT $limit
"""

TEMPLATES: tuple[Template, ...] = (
    Template(
        name="card_core",
        cypher=CARD_CORE,
        params=("normalized_name",),
        strata=("legality_1hop", "keyword_rule_2hop", "interaction_multihop"),
        description=(
            "The named card itself, with its oracle text. Runs for every card a "
            "question resolves, so a card with no rulings and no keywords is still "
            "evidence rather than silence."
        ),
        emits=(Emit("card", "card", "card_text", "(:Card {{{card}}})"),),
    ),
    Template(
        name="keyword_definition",
        cypher=KEYWORD_DEFINITION,
        params=("keyword",),
        strata=("definition_1hop",),
        description="A keyword, its glossary entry, its governing rule and that rule's subrules.",
        emits=(
            Emit("keyword", "keyword", "glossary", "(:Keyword {{{keyword}}})"),
            Emit("rule", "rule_number", "rule_text",
                 "(:Keyword {{{keyword}}})-[:DEFINED_BY]->(:Rule {{{rule_number}}})", distance=1),
            Emit("rule", "number", "text",
                 "(:Rule {{{rule_number}}})-[:HAS_SUBRULE*]->(:Rule)",
                 collection="subrules", distance=2),
        ),
    ),
    Template(
        name="card_legality",
        cypher=CARD_LEGALITY,
        params=("normalized_name", "format"),
        strata=("legality_1hop",),
        description="A card's legality status per format; $format may be null for all of them.",
        emits=(
            # The card node itself comes from `card_core`, which always runs.
            Emit("legality", "format", "status",
                 "(:Card {{{card}}})-[:HAS_LEGALITY {{{status}}}]->(:Format {{{format}}})"),
        ),
    ),
    Template(
        name="deck_legality",
        cypher=DECK_LEGALITY,
        params=("normalized_names", "format"),
        strata=("negative_temporal",),
        description=(
            "The cards in a list that are NOT legal in a format. Returns the violations, "
            "so an empty result is the legal answer and every row is a citable reason."
        ),
        emits=(
            Emit("legality", "card", "status",
                 "(:Card {{{card}}})-[:HAS_LEGALITY {{{status}}}]->(:Format {{{format}}})"),
        ),
    ),
    Template(
        name="card_keyword_rules",
        cypher=CARD_KEYWORD_RULES,
        params=("normalized_name",),
        strata=("keyword_rule_2hop", "interaction_multihop"),
        description=(
            "Card -> its keywords -> the rules defining them -> subrules. The seed path "
            "measured by scripts/reachability.py; empty for a card with no keywords."
        ),
        emits=(
            Emit("keyword", "keyword", "keyword_glossary",
                 "(:Card {{{card}}})-[:HAS_KEYWORD]->(:Keyword {{{keyword}}})", distance=1),
            Emit("rule", "rule_number", "rule_text",
                 "(:Keyword {{{keyword}}})-[:DEFINED_BY]->(:Rule {{{rule_number}}})", distance=2),
            Emit("rule", "number", "text",
                 "(:Rule {{{rule_number}}})-[:HAS_SUBRULE*]->(:Rule)",
                 collection="subrules", distance=3),
        ),
    ),
    Template(
        name="card_rulings",
        cypher=CARD_RULINGS,
        params=("normalized_name",),
        strata=("interaction_multihop",),
        description=(
            "A card's official rulings, newest first, with any explicitly cited rule. "
            "Since ADR-006 the citation is present only when the ruling states a number."
        ),
        emits=(
            # The card node itself comes from `card_core`, which always runs.
            Emit("ruling", "ruling_id", "ruling_text",
                 "(:Card {{{card}}})-[:HAS_RULING]->(:Ruling)", distance=1),
            Emit("rule", "number", "text",
                 "(:Ruling)-[:CITES_RULE]->(:Rule)", collection="cited_rules", distance=2),
        ),
    ),
    Template(
        name="card_interaction",
        cypher=CARD_INTERACTION,
        params=("left", "right"),
        strata=("interaction_multihop",),
        description=(
            "Two cards, their oracle text, rulings of one that mention the other in "
            "either direction, and keywords they share with the rules defining them."
        ),
        emits=(
            # Both card nodes come from `card_core`, which always runs.
            Emit("ruling", "ruling_id", "text",
                 "(:Card {{{left_card}}})-[:HAS_RULING]->(:Ruling)-[:MENTIONS]->(:Card {{{right_card}}})",
                 collection="left_rulings", distance=1),
            Emit("ruling", "ruling_id", "text",
                 "(:Card {{{right_card}}})-[:HAS_RULING]->(:Ruling)-[:MENTIONS]->(:Card {{{left_card}}})",
                 collection="right_rulings", distance=1),
            Emit("rule", "rule", "keyword",
                 "(:Card {{{left_card}}})-[:HAS_KEYWORD]->(:Keyword)<-[:HAS_KEYWORD]-(:Card {{{right_card}}})",
                 collection="shared_keywords", distance=2),
        ),
    ),
    Template(
        name="rule_subtree",
        cypher=RULE_SUBTREE,
        params=("rule_number",),
        strata=("keyword_rule_2hop", "interaction_multihop"),
        description="A rule with its descendants — the chain a topic's subrules form.",
        emits=(
            Emit("rule", "rule_number", "rule_text", "(:Rule {{{rule_number}}})"),
            Emit("rule", "number", "text",
                 "(:Rule {{{rule_number}}})-[:HAS_SUBRULE*]->(:Rule)",
                 collection="subrules", distance=1),
        ),
    ),
    Template(
        name="rule_neighbourhood",
        cypher=RULE_NEIGHBOURHOOD,
        params=("rule_number",),
        strata=("interaction_multihop", "negative_temporal"),
        description=(
            "A rule plus its cross-references in both directions. One hop only: "
            "reachability showed a k=6 ball holding 1515 of 3308 rules."
        ),
        emits=(
            Emit("rule", "rule_number", "rule_text", "(:Rule {{{rule_number}}})"),
            Emit("rule", "number", "text",
                 "(:Rule {{{rule_number}}})-[:REFERENCES]->(:Rule)",
                 collection="references_out", distance=1),
            Emit("rule", "number", "text",
                 "(:Rule)-[:REFERENCES]->(:Rule {{{rule_number}}})",
                 collection="references_in", distance=1),
        ),
    ),
)

BY_NAME: dict[str, Template] = {t.name: t for t in TEMPLATES}


def templates_for(stratum: str) -> tuple[Template, ...]:
    """Every template declared to serve a golden-set stratum.

    Returns an empty tuple for an unknown stratum rather than raising: a
    question the templates do not cover is routed to the other layer, and
    that is a documented outcome, not an error.
    """
    return tuple(t for t in TEMPLATES if stratum in t.strata)
