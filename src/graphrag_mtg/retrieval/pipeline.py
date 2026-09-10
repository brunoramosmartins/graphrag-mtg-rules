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

from graphrag_mtg.observability import spans
from graphrag_mtg.observability.tracing import annotate, stage
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
from graphrag_mtg.retrieval.text2cypher import Text2Cypher

Runner = Callable[[str, Mapping[str, Any]], Iterable[Mapping[str, Any]]]


def retrieve(
    question: str,
    *,
    linker: QueryLinker,
    run: Runner,
    rule_search: RuleSearch | None = None,
    text2cypher: Text2Cypher | None = None,
    oracle_text: Mapping[str, str] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    kind_cap: int = DEFAULT_KIND_CAP,
    always_text_search: bool = False,
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
        text2cypher: The long-tail layer, tried **only** after the planned
            route has produced nothing. Absent means such a question comes
            back as its named failure, which is the correct answer when no
            generator is configured.
        oracle_text: ``oracle_id -> oracle text``, expanding lexical
            retrieval. Measured on dev as worth 6 of 15 against 8 of 15.
        token_budget: Context ceiling.
        kind_cap: Per ``(template, kind)`` hub cap.
        always_text_search: Run text retrieval on every question rather
            than only where the plan routes there. Off by default, because
            off *is* the shipped system. It exists because the routed
            branch fires on **2 of the 20** Phase 4 development questions
            — 1 of 8 `interaction_multihop` — so E-001's arm C would
            otherwise differ from arm B on a tenth of the split, and
            "C vs B isolates the text contribution" would be close to a
            null comparison by construction. E-001 publishes both states,
            the same pattern its reranker and iterative-retrieval pins
            already use.

    Returns:
        A :class:`Subgraph`. Its ``outcome`` is ``RESOLVED`` only when
        evidence was actually found.
    """
    with stage(spans.LINKING) as span:
        entities = linker.link(question)
        annotate(
            span,
            **{
                spans.ENTITIES_RESOLVED: len(entities.resolved),
                spans.ENTITIES_AMBIGUOUS: len(entities.ambiguous),
                spans.ENTITIES_KINDS: [entity.kind for entity in entities.resolved],
                spans.CARDS_LINKED: [card.surface for card in entities.cards],
                # ADR-007's routing signal, and the one attribute that
                # explains an otherwise puzzling trace: a question naming
                # only keyword-less cards cannot be walked at any depth.
                spans.HAS_GRAPH_SEED: entities.has_graph_seed,
            },
        )

    with stage(spans.ROUTING) as span:
        chosen = plan(entities, oracle_text=dict(oracle_text or {}))
        annotate(
            span,
            **{
                spans.PLAN_TEMPLATES: [call.template for call in chosen.calls],
                spans.PLAN_TEXT_SEARCH: chosen.text_search,
                spans.PLAN_EXPANSIONS: len(chosen.expansions),
                spans.OUTCOME: chosen.outcome,
                spans.NOTE: chosen.reason,
            },
        )

    subgraph = Subgraph(question=question, outcome=chosen.outcome, note=chosen.reason)

    if chosen.outcome is not Outcome.RESOLVED:
        return _last_resort(subgraph, question, run, text2cypher, kind_cap)

    for call in chosen.calls:
        template = BY_NAME[call.template]
        with stage(spans.TRAVERSAL, **{spans.TEMPLATE: call.template}) as span:
            rows = list(run(template.cypher, call.params))
            subgraph.templates_run.append(call.template)
            before = len(subgraph.evidence)
            add_evidence(subgraph, to_evidence(template, rows), kind_cap=kind_cap)
            added = subgraph.evidence[before:]
            annotate(
                span,
                **{
                    spans.ROWS: len(rows),
                    spans.EVIDENCE_ADDED: len(added),
                    spans.EVIDENCE_CAPPED: sum(subgraph.capped.values()),
                    # What was found, not just how much. Handles and paths
                    # are identifiers — a rule number, a ruling id, a card
                    # name, and the walk that reached them — which is the
                    # half of this corpus the project publishes. The node
                    # *text* is the half it never commits, and it stays off
                    # the span for the same reason it stays out of the repo.
                    spans.EVIDENCE_KEYS: spans.first_n(
                        f"{item.kind}:{item.key}" for item in added
                    ),
                    # The traversal in readable form. This is the claim the
                    # README makes — an answer is a path — and until now it
                    # was the one thing a trace of a traversal did not show.
                    #
                    # Index-aligned with `evidence.keys` and therefore not
                    # filtered: a reader pairs `paths.2` with `keys.2`, and
                    # dropping an empty path would shift every entry after
                    # it onto the wrong key. Two lists that look aligned and
                    # are not is worse than one list with a gap in it.
                    spans.PATHS: spans.first_n(
                        item.path or "(no path recorded)" for item in added
                    ),
                },
            )

    if chosen.text_search or always_text_search:
        if rule_search is None:
            if not chosen.text_search:
                # Asked for text on every question and given no retriever.
                # The routed branch would have failed loudly; this one has
                # a graph result to fall back on, so it continues rather
                # than discarding it.
                _budget(subgraph, token_budget)
                return subgraph
            subgraph.outcome = Outcome.NO_SEED
            subgraph.note = f"{chosen.reason}; no text retrieval configured"
            return subgraph
        # Named by the retriever rather than hardcoded: arm C swaps in a
        # different searcher behind the same contract, and a run log
        # saying `rule_search` when `vector_search` ran is a record that
        # disagrees with what happened. The span carries the same name for
        # the same reason — a viewer is a log with pictures.
        name = getattr(rule_search, "template_name", "rule_search")
        with stage(spans.TEXT_SEARCH, **{spans.RETRIEVER: name}) as span:
            subgraph.templates_run.append(name)
            before = len(subgraph.evidence)
            add_evidence(
                subgraph,
                rule_search.evidence(question, chosen.expansions),
                kind_cap=kind_cap,
            )
            added = subgraph.evidence[before:]
            annotate(
                span,
                **{
                    spans.PLAN_EXPANSIONS: len(chosen.expansions),
                    spans.EVIDENCE_ADDED: len(added),
                    # Same handles as a traversal carries, and deliberately
                    # no `paths`: text retrieval reaches a rule by matching
                    # words, not by walking, and an attribute named `paths`
                    # on this span would describe a walk that never happened.
                    spans.EVIDENCE_KEYS: spans.first_n(
                        f"{item.kind}:{item.key}" for item in added
                    ),
                },
            )

    _budget(subgraph, token_budget)

    if subgraph.is_empty:
        # Traversals ran and matched nothing. Distinct from NO_ENTITIES:
        # the question named real nodes, and the graph has nothing to say
        # about them — which a caller may want to report differently.
        subgraph.outcome = Outcome.NO_MATCH
        subgraph.note = f"{chosen.reason}; every traversal returned nothing"
        return _last_resort(subgraph, question, run, text2cypher, kind_cap)

    subgraph.note = "; ".join([chosen.reason, *chosen.notes])
    return subgraph


def _budget(subgraph: Subgraph, token_budget: int) -> None:
    """Enforce the token ceiling, and record what it cost.

    A span rather than a bare call because the trim is the one step whose
    effect is invisible in the answer: evidence that was retrieved and
    then evicted leaves no trace in the prose, and "the model never saw
    the rule" and "the model saw it and ignored it" are different bugs.
    """
    with stage(spans.BUDGET, **{spans.TOKEN_BUDGET: token_budget}) as span:
        before = subgraph.tokens
        enforce_budget(subgraph, token_budget)
        annotate(
            span,
            **{
                spans.TOKENS_BEFORE: before,
                spans.TOKENS: subgraph.tokens,
                spans.EVIDENCE_TOTAL: len(subgraph.evidence),
                spans.EVIDENCE_DROPPED: sum(subgraph.dropped.values()),
                spans.EVIDENCE_CAPPED: sum(subgraph.capped.values()),
                spans.RULE_FAMILIES: spans.rule_families(subgraph.citations()),
                spans.CITATIONS: len(subgraph.citations()),
            },
        )


def _last_resort(
    subgraph: Subgraph,
    question: str,
    run: Runner,
    text2cypher: Text2Cypher | None,
    kind_cap: int,
) -> Subgraph:
    """Try the generated-Cypher layer, and say what happened either way.

    Reached only when the planned route produced nothing, so the long tail
    stays a fallback rather than a competing path — and the failure that
    sent us here is preserved in the note, because "the templates found
    nothing and generation also declined" is a more useful report than
    either half alone.
    """
    if text2cypher is None:
        return subgraph
    with stage(spans.TEXT2CYPHER, **{spans.OUTCOME: subgraph.outcome}) as span:
        found, why = text2cypher.evidence(question, run)
        subgraph.templates_run.append("text2cypher")
        annotate(
            span,
            **{
                spans.VALID: bool(found),
                spans.EVIDENCE_ADDED: len(found),
                # `why` carries the validator's refusal — the reason a
                # generated query was rejected is the whole point of
                # tracing this layer, and it is otherwise only in a note.
                spans.REFUSAL: None if found else why,
            },
        )
        if not found:
            subgraph.note = f"{subgraph.note}; text2cypher: {why}"
            return subgraph
        add_evidence(subgraph, found, kind_cap=kind_cap)
        subgraph.outcome = Outcome.RESOLVED
        subgraph.note = f"{subgraph.note}; answered by generated Cypher (validated read-only)"
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
