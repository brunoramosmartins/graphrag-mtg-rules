"""The span and attribute vocabulary, in one place so it cannot drift.

Two things are worth stating outright, because both are properties the
instrumentation has to *keep*, not conveniences.

**A trace must say which arm produced it.** E-001 runs three arms through
overlapping code, and the phase before this one lost a whole run to a
mislabel: the harness passed a text retriever to what it recorded as the
graph-only arm, and every summary number still looked exactly as arm B
should look, because the routed branch fires on 2 of 20 questions. A
trace that named its stages identically across arms would reproduce that
failure in the viewer. So :data:`ARM` sits on the root span, and the two
stage sets are deliberately disjoint apart from the two stages that
genuinely *are* the same operation — see :data:`SHARED_STAGES`, which a
test pins.

**Question text is not a span attribute by default.** The golden set's
RulesGuru questions are carried as ids plus a gitignored fetch, precisely
so their text never lands in the public repo; a trace screenshot in the
README is the public repo. :func:`query_span` therefore records the
question's *length* always and its text only when the caller opts in —
which the README screenshot does, on a hand-authored question the repo
already contains in `golden/authored_v0.jsonl`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span

from graphrag_mtg.observability.tracing import annotate, register_span_kinds, stage

# ── Span names ───────────────────────────────────────────────────────────────

#: The root span: one question, one arm, end to end.
QUERY = "graphrag.query"

# Stages the graph arms (B and C) run.
LINKING = "linking"
ROUTING = "routing"
TRAVERSAL = "traversal"
TEXT_SEARCH = "text_search"
TEXT2CYPHER = "text2cypher"

# Stages the vector arm (A) runs. It has no router and nothing to walk;
# naming its fusion step `traversal` for symmetry would be exactly the
# mislabel this module exists to prevent.
LEXICAL = "retrieval.lexical"
DENSE = "retrieval.dense"
FUSION = "fusion"

# Run by every arm, and the same operation in each: a token ceiling
# enforced over whatever was found, then one generation call.
BUDGET = "budget"
GENERATION = "generation"

GRAPH_STAGES = frozenset({LINKING, ROUTING, TRAVERSAL, TEXT_SEARCH, TEXT2CYPHER, BUDGET, GENERATION})
VECTOR_STAGES = frozenset({LEXICAL, DENSE, FUSION, BUDGET, GENERATION})

#: What the two arms may share, exhaustively. Anything else appearing in
#: both sets means a stage was named for symmetry rather than for what it
#: does, and the trace stops distinguishing the arms.
SHARED_STAGES = frozenset({BUDGET, GENERATION})

# ── What kind of step each span is, in Phoenix's vocabulary ──────────────────

# Phoenix renders a span according to `openinference.span.kind`. Without it
# every span shows as `unknown` with no input, no output and no cost — which
# is what a trace of this pipeline looked like until 2026-09-10, and it is
# indistinguishable from instrumentation that was never added. The names
# above are ours and stay ours; this map is the translation the viewer reads.
#
# Two entries are deliberately CHAIN rather than the tempting alternative:
#
# - `fusion` is reciprocal-rank fusion over two ranked lists. RERANKER would
#   render more prettily and would tell the reader a reranking *model* ran.
#   None did.
# - `text2cypher` wraps validation and execution of a generated query. The
#   generation happens elsewhere; marking this span LLM would attribute a
#   model call to a step that makes none.
#: The kinds this project claims. A frozenset rather than three string
#: constants so the vocabulary's own tests can tell an attribute *key* from
#: a kind *value* by type — they are all uppercase module-level strings
#: otherwise, and one namespace test already tripped over that.
PHOENIX_KINDS = frozenset({"CHAIN", "LLM", "RETRIEVER"})

SPAN_KINDS = {
    QUERY: "CHAIN",
    LINKING: "CHAIN",
    ROUTING: "CHAIN",
    BUDGET: "CHAIN",
    TEXT2CYPHER: "CHAIN",
    FUSION: "CHAIN",
    TRAVERSAL: "RETRIEVER",
    TEXT_SEARCH: "RETRIEVER",
    LEXICAL: "RETRIEVER",
    DENSE: "RETRIEVER",
    GENERATION: "LLM",
}

register_span_kinds(SPAN_KINDS)

# ── Attribute names ──────────────────────────────────────────────────────────

#: OpenInference's name, not ours, and on purpose: Phoenix shows the model
#: on an LLM span only under this key. It is the one piece of the LLM
#: convention this project can fill honestly — `llm.token_count.*` would
#: have to come from the provider's usage report, and `LlmClient` does not
#: surface one, so the only numbers available are the chars/4 estimates the
#: budget span already carries under a name that says they are estimates.
#: Publishing an estimate under a key that means "what was billed" is the
#: provenance failure this project keeps finding, so the cost stays $0 and
#: says nothing rather than saying something false.
LLM_MODEL_NAME = "llm.model_name"

#: Keys that deliberately sit outside the `graphrag.` namespace, and the
#: whole list of them. Everything this project records is prefixed so that
#: "show me what this project wrote" is one Phoenix filter; a foreign key is
#: a key the *viewer* defines, which is only useful spelled its way. Keeping
#: the exceptions enumerated is what stops "the invariant has an exception"
#: from becoming "the invariant is a suggestion".
FOREIGN_ATTRIBUTES = frozenset({LLM_MODEL_NAME})

ARM = "graphrag.arm"
QUESTION = "graphrag.question"
QUESTION_CHARS = "graphrag.question.chars"
QUESTION_ID = "graphrag.question.id"
OUTCOME = "graphrag.outcome"
NOTE = "graphrag.note"

ENTITIES_RESOLVED = "graphrag.entities.resolved"
ENTITIES_AMBIGUOUS = "graphrag.entities.ambiguous"
ENTITIES_KINDS = "graphrag.entities.kinds"
CARDS_LINKED = "graphrag.entities.cards"
HAS_GRAPH_SEED = "graphrag.entities.has_graph_seed"

PLAN_TEMPLATES = "graphrag.plan.templates"
PLAN_TEXT_SEARCH = "graphrag.plan.text_search"
PLAN_EXPANSIONS = "graphrag.plan.expansions"

TEMPLATE = "graphrag.template"
ROWS = "graphrag.rows"
EVIDENCE_KEYS = "graphrag.evidence.keys"
PATHS = "graphrag.paths"
CITATION_KEYS = "graphrag.citations.keys"
EVIDENCE_ADDED = "graphrag.evidence.added"
EVIDENCE_TOTAL = "graphrag.evidence.total"
EVIDENCE_CAPPED = "graphrag.evidence.capped"
EVIDENCE_DROPPED = "graphrag.evidence.dropped"
RULE_FAMILIES = "graphrag.rules.families"
CITATIONS = "graphrag.citations"

TOKENS = "graphrag.tokens"
TOKEN_BUDGET = "graphrag.tokens.budget"
TOKENS_BEFORE = "graphrag.tokens.before"

RETRIEVER = "graphrag.retriever"
MODE = "graphrag.mode"
DEPTH = "graphrag.depth"
HITS = "graphrag.hits"
ROUNDS = "graphrag.rounds"
CONSIDERED = "graphrag.considered"
RRF_K = "graphrag.rrf_k"
BM25_K1 = "graphrag.bm25.k1"
BM25_B = "graphrag.bm25.b"
RERANKED = "graphrag.reranked"
EMBEDDED = "graphrag.embedded"

VALID = "graphrag.text2cypher.valid"
REFUSAL = "graphrag.text2cypher.refusal"

GENERATED = "graphrag.generated"
REFUSED = "graphrag.refused"
UNKNOWN_HANDLES = "graphrag.citations.unknown"
PROMPT_VERSION = "graphrag.prompt_version"
CONTEXT_INCOMPLETE = "graphrag.context_incomplete"

# ── Helpers ──────────────────────────────────────────────────────────────────

#: A CR rule number's chapter — "702.9b" is family 700, the keyword
#: abilities. Coarse on purpose: it is what makes two traces comparable at
#: a glance, where the full rule numbers are only comparable by reading.
_RULE_KEY = re.compile(r"^(\d)(\d\d)")


#: How many list entries a span carries before it says how many it left.
#: A traversal that adds thirty rulings would otherwise put thirty strings
#: on one attribute, which the viewer renders as a wall and nobody reads.
SPAN_LIST_CAP = 12


def first_n(values: Iterable[str], cap: int = SPAN_LIST_CAP) -> list[str]:
    """The first `cap` values, followed by a count of the ones left out.

    The marker is an entry rather than a separate attribute on purpose: a
    truncated list that does not say it was truncated is a list that reads
    as complete, and this project has already been bitten once by a number
    that described a subset while looking like the whole.
    """
    items = list(values)
    if len(items) <= cap:
        return items
    return [*items[:cap], f"...and {len(items) - cap} more"]


def rule_family(key: str) -> str | None:
    """The CR chapter a rule key belongs to, as ``"700"``; None if not a rule."""
    match = _RULE_KEY.match(key)
    return f"{match.group(1)}00" if match else None


def rule_families(citations: Iterable[str]) -> list[str]:
    """Sorted distinct CR chapters among ``kind:key`` citation handles."""
    families = set()
    for handle in citations:
        kind, _, key = handle.partition(":")
        if kind == "rule":
            family = rule_family(key)
            if family:
                families.add(family)
    return sorted(families)


@contextmanager
def query_span(
    question: str,
    *,
    arm: str,
    question_id: str | None = None,
    record_question: bool = False,
) -> Iterator[Span]:
    """The root span for one question.

    Args:
        question: The question, verbatim. Recorded as a length unless
            `record_question` says otherwise.
        arm: Which configuration is answering — ``"A"``, ``"B"``, ``"C"``,
            or the shipped system's own label. Free-form because the
            demo app is not one of E-001's arms and should not pretend to
            be, but never absent.
        question_id: The golden set's id for this question, when there is
            one. An id is not the question: the repo already versions
            RulesGuru ids publicly, and it is the text that the licence
            keeps out. Recorded because a screenshotted trace whose
            caption claims which question it shows should let the reader
            check that claim inside the image — the same reason a smoke
            artefact says it is synthetic from inside the data. Without
            it the only handle on a trace is `question.chars`, which
            identifies a question the way a page count identifies a book.
        record_question: Put the question text on the span. Off by
            default: a trace is a thing that gets screenshotted, and the
            golden set's licensed questions are kept out of this repo on
            purpose. Turn it on for a question the repo already carries.
    """
    with stage(QUERY, **{ARM: arm, QUESTION_CHARS: len(question)}) as span:
        if question_id:
            annotate(span, **{QUESTION_ID: question_id})
        if record_question:
            annotate(span, **{QUESTION: question})
        yield span
