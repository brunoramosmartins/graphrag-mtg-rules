"""End to end: a question in, a bounded and citable subgraph out.

Wires what the other modules decided. The order is the point — everything
cheap and inspectable happens before anything expensive:

    question
      -> QueryLinker.link      what nodes does this name?
      -> router.plan           which layers, and why (pure, no I/O)
      -> traversals            only the calls the plan chose
      -> rule_search           only when the plan says the graph cannot seed
      -> Subgraph              capped, budgeted, and accounted for

The plan is inspected before the database is touched, so a question that
resolves nothing costs one dictionary lookup rather than eight queries
returning nothing.

**Failures stay named.** A question the stack cannot serve comes back as
an :class:`~graphrag_mtg.retrieval.subgraph.Outcome`, never as an empty
subgraph that reads like an answer with no evidence. The Phase 4 DoD
demands a non-empty subgraph *or an explicit failure*, and this is where
that promise is kept.

The Neo4j session is injected as a ``run`` callable — ``(cypher, params)
-> rows`` — so the assembly logic is testable without a database, and so
the caller controls the transaction. That caller must use a **read**
transaction: the validation in `text2cypher` catches mistakes, but only
the server refuses writes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from graphrag_mtg.retrieval.linking import QueryEntities, QueryLinker
from graphrag_mtg.retrieval.router import Plan, plan
from graphrag_mtg.retrieval.rows import to_evidence
from graphrag_mtg.retrieval.rule_search import RuleSearch
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    Outcome,
    Subgraph,
    add_evidence,
    enforce_budget,
)
from graphrag_mtg.retrieval.templates import BY_NAME

Runner = Callable[[str, Mapping[str, Any]], Iterable[Mapping[str, Any]]]


def retrieve(
    question: str,
    *,
    linker: QueryLinker,
    run: Runner,
    rule_search: RuleSearch | None = None,
    oracle_text: Mapping[str, str] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    kind_cap: int = DEFAULT_KIND_CAP,
) -> Subgraph:
    """Retrieve evidence for one question.

    Args:
        question: The user's question, verbatim.
        linker: Resolves mentions to nodes.
        run: Executes one query — ``(cypher, params) -> rows``. Must run in
            a read transaction.
        rule_search: Lexical CR retrieval, used only when the plan routes
            there. Absent means a seedless question returns
            :attr:`Outcome.NO_SEED` rather than silently reaching for
            nothing.
        oracle_text: ``oracle_id -> oracle text``, expanding lexical
            retrieval. Measured on dev as worth 6 of 15 against 8 of 15.
        token_budget: Context ceiling.
        kind_cap: Per ``(template, kind)`` hub cap.

    Returns:
        A :class:`Subgraph`. Its ``outcome`` is ``RESOLVED`` only when
        evidence was actually found.
    """
    entities = linker.link(question)
    chosen = plan(entities, oracle_text=dict(oracle_text or {}))
    subgraph = Subgraph(question=question, outcome=chosen.outcome, note=chosen.reason)

    if chosen.outcome is not Outcome.RESOLVED:
        return subgraph

    for call in chosen.calls:
        template = BY_NAME[call.template]
        rows = list(run(template.cypher, call.params))
        subgraph.templates_run.append(call.template)
        add_evidence(subgraph, to_evidence(template, rows), kind_cap=kind_cap)

    if chosen.text_search:
        if rule_search is None:
            subgraph.outcome = Outcome.NO_SEED
            subgraph.note = f"{chosen.reason}; no text retrieval configured"
            return subgraph
        subgraph.templates_run.append("rule_search")
        add_evidence(
            subgraph,
            rule_search.evidence(question, chosen.expansions),
            kind_cap=kind_cap,
        )

    enforce_budget(subgraph, token_budget)

    if subgraph.is_empty:
        # Traversals ran and matched nothing. Distinct from NO_ENTITIES:
        # the question named real nodes, and the graph has nothing to say
        # about them — which a caller may want to report differently.
        subgraph.outcome = Outcome.NO_MATCH
        subgraph.note = f"{chosen.reason}; every traversal returned nothing"
    else:
        subgraph.note = "; ".join([chosen.reason, *chosen.notes])
    return subgraph


def neo4j_runner(session) -> Runner:
    """Adapt a Neo4j session to :data:`Runner`, read-only.

    ``execute_read`` is not decoration. The template invariants and the
    text2cypher validator both check strings, and strings can be wrong in
    ways review does not catch; a read transaction is the only part of
    this stack that the server itself enforces.
    """

    def run(cypher: str, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return session.execute_read(
            lambda tx: [dict(record) for record in tx.run(cypher, **params)]
        )

    return run


def explain(subgraph: Subgraph, entities: QueryEntities, chosen: Plan) -> str:
    """A short account of one retrieval, for run reports and debugging."""
    lines = [
        f"question: {subgraph.question}",
        f"outcome:  {subgraph.outcome} — {subgraph.note}",
        f"entities: {', '.join(f'{e.kind}:{e.key}' for e in entities.resolved) or 'none'}",
        f"ran:      {', '.join(subgraph.templates_run) or 'nothing'}",
        f"evidence: {len(subgraph.evidence)} items, ~{subgraph.tokens} tokens",
    ]
    if subgraph.dropped or subgraph.capped:
        lines.append(f"trimmed:  dropped {dict(subgraph.dropped)}, capped {dict(subgraph.capped)}")
    if chosen.notes:
        lines += [f"note:     {note}" for note in chosen.notes]
    return "\n".join(lines)
