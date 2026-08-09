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
class Template:
    """One named traversal, its parameters, and what it is for.

    Attributes:
        name: Stable identifier, used in the answer's provenance.
        cypher: The query. Read-only, parameterized, ``$limit``-bounded.
        params: Required parameter names, excluding ``limit``.
        strata: Golden-set strata this traversal is meant to answer.
        description: What the subgraph it returns means.
    """

    name: str
    cypher: str
    params: tuple[str, ...]
    strata: tuple[str, ...]
    description: str


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

CARD_LEGALITY = """
MATCH (c:Card {normalized_name: $normalized_name})-[e:HAS_LEGALITY]->(f:Format)
WHERE $format IS NULL OR f.name = $format
RETURN c.name AS card, f.name AS format, e.status AS status
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
       rl.ruling_id AS ruling_id,
       rl.text AS ruling_text,
       rl.published_at AS published_at,
       collect(DISTINCT {number: r.number, text: r.text}) AS cited_rules
ORDER BY rl.published_at DESC
LIMIT $limit
"""

CARD_INTERACTION = """
MATCH (a:Card {normalized_name: $left})
MATCH (b:Card {normalized_name: $right})
OPTIONAL MATCH (a)-[:HAS_RULING]->(shared:Ruling)-[:MENTIONS]->(b)
OPTIONAL MATCH (b)-[:HAS_RULING]->(mirrored:Ruling)-[:MENTIONS]->(a)
OPTIONAL MATCH (a)-[:HAS_KEYWORD]->(common:Keyword)<-[:HAS_KEYWORD]-(b)
OPTIONAL MATCH (common)-[:DEFINED_BY]->(shared_rule:Rule)
RETURN a.name AS left_card,
       b.name AS right_card,
       a.oracle_text AS left_text,
       b.oracle_text AS right_text,
       collect(DISTINCT {ruling_id: shared.ruling_id, text: shared.text}) AS left_rulings,
       collect(DISTINCT {ruling_id: mirrored.ruling_id, text: mirrored.text}) AS right_rulings,
       collect(DISTINCT {keyword: common.display_name, rule: shared_rule.number}) AS shared_keywords
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
        name="keyword_definition",
        cypher=KEYWORD_DEFINITION,
        params=("keyword",),
        strata=("definition_1hop",),
        description="A keyword, its glossary entry, its governing rule and that rule's subrules.",
    ),
    Template(
        name="card_legality",
        cypher=CARD_LEGALITY,
        params=("normalized_name", "format"),
        strata=("legality_1hop",),
        description="A card's legality status per format; $format may be null for all of them.",
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
    ),
    Template(
        name="rule_subtree",
        cypher=RULE_SUBTREE,
        params=("rule_number",),
        strata=("keyword_rule_2hop", "interaction_multihop"),
        description="A rule with its descendants — the chain a topic's subrules form.",
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
