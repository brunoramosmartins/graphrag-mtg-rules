"""Which retrieval layer answers this question, and why.

The decision ADR-007 describes, written as a pure function so it can be
argued with. :func:`plan` takes what the question resolved to and returns
the traversals to run, whether text retrieval is needed, and a stated
reason — no graph, no LLM, no I/O. Everything expensive happens to a plan
that has already been inspected.

The routing rule is the one the reachability measurement produced:

- **No entities at all** — nothing to traverse from. Explicit failure.
- **Only ambiguous surfaces** — the question may be about cards, but
  asserting which would be guessing. Explicit failure, with candidates,
  so the caller can ask.
- **Entities that seed the rule graph** (a rule, a keyword, or a card
  carrying keywords) — traversals answer, and text retrieval is not
  needed. This is `definition_1hop`, `keyword_rule_2hop`,
  `legality_1hop`, where reachability is 100% at two hops.
- **Entities that do not seed it** — cards without keyword abilities.
  Traversals still supply the cards and their rulings, and CR rules come
  from text retrieval expanded with those cards' oracle text. This is the
  `interaction_multihop` route, and the development split says it reaches
  a gold rule in 2 of 8 questions, so the plan says so rather than
  implying coverage it does not have.

That last bullet is why :attr:`Plan.reason` exists and is carried into
the subgraph: a route chosen because the graph could not seed the
question is a materially weaker answer than one the graph answered, and
the difference must survive into what Phase 5 is told.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.retrieval.linking import QueryEntities
from graphrag_mtg.retrieval.subgraph import Outcome
from graphrag_mtg.retrieval.templates import BY_NAME

#: Rows any single traversal may return. Beyond the per-kind cap in
#: `subgraph.add_evidence`; this one bounds the database, that one bounds
#: the context.
DEFAULT_ROW_LIMIT = 50


@dataclass(frozen=True)
class Call:
    """One traversal to run, with its parameters already bound."""

    template: str
    params: dict[str, object]

    def cypher(self) -> str:
        """The query text this call will execute."""
        return BY_NAME[self.template].cypher


@dataclass(frozen=True)
class Plan:
    """What to run for one question, and the honest reason for it.

    Attributes:
        calls: Traversals, in the order they should run.
        text_search: Whether CR rules must come from lexical retrieval.
        expansions: Oracle text to widen that retrieval with — a question
            is written in card names and the CR never mentions one.
        outcome: :attr:`Outcome.RESOLVED` when there is something to run;
            otherwise the explicit failure the caller must surface.
        reason: One line, carried into the subgraph and into the answer's
            provenance.
    """

    calls: tuple[Call, ...] = ()
    text_search: bool = False
    expansions: tuple[str, ...] = ()
    outcome: Outcome = Outcome.RESOLVED
    reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def runnable(self) -> bool:
        """Whether anything will actually be executed."""
        return bool(self.calls or self.text_search)


def plan(
    entities: QueryEntities,
    *,
    oracle_text: dict[str, str] | None = None,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> Plan:
    """Choose the retrieval route for one question's resolved entities.

    Args:
        entities: Output of :meth:`QueryLinker.link`.
        oracle_text: ``oracle_id -> oracle text``, used to expand lexical
            retrieval. Absent means text search runs on the question
            alone, which the development split measured as materially
            worse (6 of 15 against 8 of 15).
        row_limit: ``$limit`` bound on every traversal.

    Returns:
        A :class:`Plan`. Nothing has run yet, and nothing will if
        :attr:`Plan.outcome` is not ``RESOLVED``.
    """
    oracle_text = oracle_text or {}

    if not entities.resolved:
        if entities.ambiguous:
            surfaces = ", ".join(sorted({a.surface for a in entities.ambiguous}))
            return Plan(
                outcome=Outcome.AMBIGUOUS,
                reason=f"could not confirm what these name: {surfaces}",
            )
        return Plan(
            outcome=Outcome.NO_ENTITIES,
            reason="no card, keyword or rule in the question resolved to a node",
        )

    calls: list[Call] = []
    for rule in entities.rules:
        calls.append(Call("rule_subtree", {"rule_number": rule.key, "limit": row_limit}))
        calls.append(Call("rule_neighbourhood", {"rule_number": rule.key, "limit": row_limit}))
    for keyword in entities.keywords:
        # Keyword.name in the graph is normalized; display_name is not. Passing
        # the display form matched nothing at all and every definition_1hop
        # question came back NO_MATCH — caught by E-006, not by review.
        calls.append(
            Call("keyword_definition", {"keyword": normalize_name(keyword.key), "limit": row_limit})
        )
    for card in entities.cards:
        name = normalize_name(card.surface)
        calls.append(Call("card_keyword_rules", {"normalized_name": name, "limit": row_limit}))
        calls.append(Call("card_rulings", {"normalized_name": name, "limit": row_limit}))
        # Legality only when the question names a format. Running it always
        # would add 23 rows of noise per card to every question that never
        # asked about a format.
        for fmt in entities.formats:
            calls.append(
                Call("card_legality", {"normalized_name": name, "format": fmt.key,
                                       "limit": row_limit})
            )

    pair = [normalize_name(c.surface) for c in entities.cards[:2]]
    if len(pair) == 2:
        calls.append(Call("card_interaction", {"left": pair[0], "right": pair[1], "limit": row_limit}))

    # A named format makes this a legality question, which one typed edge
    # answers completely. Such a question does not need the CR rule graph,
    # so failing to seed it is not a gap to paper over with text retrieval —
    # doing that would bolt eight lexical rule hits onto "is this card legal
    # in Modern?" and call them evidence.
    legality_only = bool(entities.formats)
    seeded = entities.has_graph_seed or legality_only
    expansions = tuple(
        text
        for card in entities.cards
        if (text := oracle_text.get(card.key, "").strip())
    )
    notes: list[str] = []
    if not seeded:
        notes.append(
            "no entity reaches the CR rule graph: every named card is without keyword "
            "abilities, so rules come from text retrieval and are weaker evidence"
        )
    if not seeded and not expansions:
        notes.append("no oracle text available to widen retrieval with")

    if legality_only:
        reason = "a format was named; the legality edge answers this without CR rules"
    elif seeded:
        reason = "entities seed the rule graph; traversals answer"
    else:
        reason = "no graph seed; traversals supply cards and rulings, text retrieval supplies rules"
    return Plan(
        calls=tuple(calls),
        text_search=not seeded,
        expansions=expansions,
        outcome=Outcome.RESOLVED,
        reason=reason,
        notes=tuple(notes),
    )


def describe(entities: QueryEntities, chosen: Plan) -> str:
    """A one-paragraph account of the route, for logs and for the run report."""
    named = ", ".join(f"{e.kind}:{e.key}" for e in entities.resolved)
    lines = [f"question: {entities.question}", f"entities: {named or 'none'}"]
    if chosen.outcome is not Outcome.RESOLVED:
        lines.append(f"outcome: {chosen.outcome} — {chosen.reason}")
        return "\n".join(lines)
    lines.append(f"route: {chosen.reason}")
    lines.append(f"traversals: {', '.join(c.template for c in chosen.calls) or 'none'}")
    lines.append(f"text retrieval: {'yes' if chosen.text_search else 'no'}")
    lines += [f"note: {note}" for note in chosen.notes]
    return "\n".join(lines)

