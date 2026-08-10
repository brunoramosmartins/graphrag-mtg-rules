"""Generated Cypher for the long tail — validated, and never trusted.

The second layer of ADR-005, and the phase's registered first cut if the
timebox runs out. Templates answer the golden set's families; this exists
for the question nobody wrote a traversal for.

**Defence in depth, and the order matters.** Three layers, each catching
what the one before it cannot:

1. the string checks here catch *mistakes* — a model that writes `SET`
   because the question said "set the power to 3";
2. ``EXPLAIN`` asks the server to plan the query without running it,
   which is the only check that knows whether the Cypher is actually
   valid against the real schema. The checks above reason about text and
   will happily pass a query that no database can parse;
3. the caller's **read transaction** is what confines an attacker. Neo4j
   refuses writes server-side there regardless of what the string says,
   and no amount of comment-smuggling or clause-splitting gets around
   it.

Layers 1 and 2 exist so a bad query fails loudly with a *reason*; layer 3
exists because the first two can be wrong. Pretending the string checks
were the security boundary would be the dangerous part.

Everything here fails closed. A query that cannot be parsed with
confidence is rejected, not executed and hoped about — and a rejection is
an honest "I cannot translate this question", which is a better answer
than a plausible query against the wrong nodes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from graphrag_mtg.retrieval.subgraph import Evidence
from graphrag_mtg.retrieval.templates import WRITE_CLAUSES

#: Clauses a read query may open with. Anything else is either a write or
#: a shape this module did not anticipate; both are rejected.
ALLOWED_OPENERS = ("MATCH", "OPTIONAL MATCH", "WITH", "UNWIND", "RETURN", "CALL")

#: Procedures a generated query may call. `apoc` and `db.*` include
#: procedures that write, load from URLs, or restart the database, so the
#: allowlist is empty until something specific earns a place on it.
ALLOWED_PROCEDURES: frozenset[str] = frozenset()

#: Hard ceiling injected when the model omits one. A generated traversal
#: without a bound is how a hub becomes an out-of-memory error.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_COMMENT = re.compile(r"//|/\*|\*/")
_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)
_CALL = re.compile(r"\bCALL\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")
_PARAMETER = re.compile(r"\$[A-Za-z_]\w*")


@dataclass(frozen=True)
class Verdict:
    """Whether a generated query may run, and why not if it may not.

    Attributes:
        ok: True only when every check passed.
        reason: Machine-readable rejection reason, empty when ``ok``.
        cypher: The query as it should run — possibly with a ``LIMIT``
            appended. Empty when rejected.
    """

    ok: bool
    reason: str = ""
    cypher: str = ""


def _without_strings(cypher: str) -> str:
    """Blank out string literals so their contents cannot trip the checks.

    A card named ``Delete the Past`` must not read as a ``DELETE`` clause.
    Blanking rather than removing keeps offsets stable for anything that
    later wants to report a position.
    """
    return _STRING_LITERAL.sub(lambda m: " " * len(m.group()), cypher)


def validate(cypher: str, *, max_limit: int = MAX_LIMIT) -> Verdict:
    """Check a generated query, failing closed on anything unrecognised.

    Args:
        cypher: The model's output, already stripped of prose.
        max_limit: Largest ``LIMIT`` allowed; a bigger one is clamped down
            rather than rejected, since an over-eager bound is a mistake
            and not an attack.

    Returns:
        A :class:`Verdict`. When ``ok``, ``cypher`` is what should be sent
        to the driver — which must still use a read transaction.
    """
    query = cypher.strip().rstrip(";").strip()
    if not query:
        return Verdict(False, "empty")

    body = _without_strings(query)

    if _COMMENT.search(body):
        # Comments have no legitimate use in generated output and are the
        # standard way to smuggle a second statement past a naive check.
        return Verdict(False, "comment")
    if ";" in body:
        return Verdict(False, "multiple_statements")

    upper = body.upper()
    for clause in WRITE_CLAUSES:
        if re.search(rf"\b{re.escape(clause)}\b", upper):
            return Verdict(False, f"write_clause:{clause.lower().replace(' ', '_')}")

    if not upper.lstrip().startswith(ALLOWED_OPENERS):
        return Verdict(False, "unexpected_opening_clause")

    for procedure in _CALL.findall(body):
        if procedure not in ALLOWED_PROCEDURES:
            return Verdict(False, f"procedure_not_allowed:{procedure}")

    if "RETURN" not in upper:
        return Verdict(False, "no_return")

    if _PARAMETER.search(body):
        # Nothing binds parameters in this layer: the query is generated
        # from the question and executed with an empty map, so `$name`
        # reaches the server unbound and raises. Refusing it here turns a
        # crash inside the pipeline into a named refusal — found while
        # adding EXPLAIN, because the prompt used to *ask* for parameters.
        return Verdict(False, "unbound_parameter")

    found = _LIMIT.search(body)
    if found is None:
        query = f"{query}\nLIMIT {DEFAULT_LIMIT}"
    elif int(found.group(1)) > max_limit:
        query = _LIMIT.sub(f"LIMIT {max_limit}", query, count=1)

    return Verdict(True, "", query)


#: Columns a generated query must return. Everything else in this project
#: is citable — a rule number, a ruling id, a named path — and the long-tail
#: layer does not get an exemption. Demanding the shape up front is what
#: lets a generated answer be quoted the same way a template's is.
CITABLE_COLUMNS = ("key", "text")


def returns_citable_columns(cypher: str) -> bool:
    """Whether a query returns the ``key`` and ``text`` columns citations need.

    Separate from :func:`validate` because safety and shape are different
    questions: a query can be perfectly read-only and still produce
    something nobody can cite.
    """
    _, _, tail = cypher.partition("RETURN")
    aliases = {alias.lower() for alias in re.findall(r"\bAS\s+([A-Za-z_]+)", tail)}
    return set(CITABLE_COLUMNS) <= aliases


#: Asks the server to plan a query without running it. Everything above
#: this line reasons about *text*; only the database knows whether the
#: Cypher parses and whether the labels and properties it names exist.
EXPLAIN = "EXPLAIN "


def _refusal(error: BaseException) -> str:
    """Compress a driver error into a short, machine-readable reason.

    Neo4j codes look like ``Neo.ClientError.Statement.SyntaxError``; the
    last segment is the part worth carrying into a subgraph note. Anything
    without a code falls back to its exception class.
    """
    code = getattr(error, "code", "") or type(error).__name__
    return str(code).rsplit(".", 1)[-1]


def check_plan(cypher: str, run) -> str:
    """Plan the query server-side, returning ``""`` when it is executable.

    This is the promise ADR-005 made and the string checks could not keep:
    a query can be read-only, citable, bounded and still be invalid Cypher
    or name a label that does not exist. Planning is cheap and touches no
    data.

    The ``except Exception`` is deliberate. This module never imports the
    Neo4j driver — ``run`` is injected — so it cannot name the driver's
    exception types, and the whole purpose here is to convert *any* server
    rejection into a named refusal rather than an exception escaping into
    the retrieval pipeline.

    Returns:
        An empty string when the server accepted the plan, otherwise
        ``explain:<Reason>``.
    """
    try:
        run(f"{EXPLAIN}{cypher}", {})
    except Exception as error:
        return f"explain:{_refusal(error)}"
    return ""


def schema_prompt(labels: dict[str, list[str]], relationships: list[str]) -> str:
    """Describe the graph to the model, and the rules its output must obey.

    Args:
        labels: ``label -> [property, ...]``.
        relationships: Relationship type names.
    """
    lines = ["Graph schema.", "", "Nodes:"]
    for label, properties in sorted(labels.items()):
        lines.append(f"  (:{label} {{{', '.join(sorted(properties))}}})")
    lines += ["", "Relationships:"] + [f"  -[:{name}]->" for name in sorted(relationships)]
    lines += [
        "",
        "Write ONE read-only Cypher query answering the question.",
        "Rules, all enforced before your query runs:",
        "  - read only: no CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, FOREACH",
        "  - one statement, no semicolons, no comments",
        "  - it must carry a LIMIT",
        "  - no procedure calls",
        "  - no parameters: write values as literals, because nothing binds",
        "    a `$name` in this path and the query would fail to run",
        "  - RETURN exactly two columns, aliased `key` and `text`: `key` is the",
        "    citation handle (a rule number, a ruling id, a card name) and `text`",
        "    is what will be quoted. An answer that cannot be cited is not shipped,",
        "    and this layer gets no exemption from that.",
        "",
        "If the schema cannot answer the question, reply exactly: CANNOT TRANSLATE",
    ]
    return "\n".join(lines)


CANNOT_TRANSLATE = "CANNOT TRANSLATE"


def extract_query(response: str) -> str:
    """Pull the query out of a model response, tolerating a code fence.

    Returns an empty string when the model declined, which the caller must
    treat as the honest outcome it is rather than retrying until something
    parses.
    """
    text = response.strip()
    if CANNOT_TRANSLATE in text.upper():
        return ""
    fenced = re.search(r"```(?:cypher)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    return (fenced.group(1) if fenced else text).strip()


@dataclass(frozen=True)
class Attempt:
    """One generation attempt: what came back, and whether it may run."""

    cypher: str = ""
    verdict: Verdict = Verdict(False, "not_attempted")
    declined: bool = False

    @property
    def usable(self) -> bool:
        return self.verdict.ok


class Text2Cypher:
    """The long-tail layer: generate, validate, plan, and only then execute.

    Wired into `retrieval/pipeline.py` as the last resort, after the plan
    has failed to find anything — not as a general-purpose path. Phase 3
    ended with `crossref.py` built, gated and never called by anything,
    which the phase note records as a failure; a component with no caller
    is a component nobody measured.

    The generator is injected as ``(question, system) -> str`` so this
    module never imports an LLM client and the caller keeps control of
    cost.
    """

    def __init__(
        self,
        generate: Callable[[str, str], str],
        labels: dict[str, list[str]],
        relationships: list[str],
    ) -> None:
        self._generate = generate
        self._system = schema_prompt(labels, relationships)

    def attempt(self, question: str) -> Attempt:
        """Generate one query and decide whether it is allowed to run."""
        raw = extract_query(self._generate(question, self._system))
        if not raw:
            return Attempt(declined=True, verdict=Verdict(False, "declined"))
        verdict = validate(raw)
        if not verdict.ok:
            return Attempt(cypher=raw, verdict=verdict)
        if not returns_citable_columns(verdict.cypher):
            return Attempt(cypher=raw, verdict=Verdict(False, "not_citable"))
        return Attempt(cypher=verdict.cypher, verdict=verdict)

    def evidence(self, question: str, run) -> tuple[list[Evidence], str]:
        """Run one validated query and return its rows as evidence.

        Returns:
            ``(evidence, reason)``. The reason is empty on success and
            names the refusal otherwise — "declined", a validation code,
            "not_citable", or an ``explain:``/``execution:`` code from the
            server — so a caller can report *why* the long tail did not
            answer instead of reporting nothing.
        """
        tried = self.attempt(question)
        if not tried.usable:
            return [], tried.verdict.reason
        rejected = check_plan(tried.cypher, run)
        if rejected:
            return [], rejected
        try:
            rows = list(run(tried.cypher, {}))
        except Exception as error:
            # Planned and still failed — a timeout, a memory ceiling, a
            # transient. Same rule as everywhere else in this stack: the
            # failure gets a name, it does not become an empty result that
            # reads like an answer.
            return [], f"execution:{_refusal(error)}"
        found = [
            Evidence(
                kind="row",
                key=str(row["key"]),
                text=str(row.get("text") or ""),
                template="text2cypher",
                path="generated query (validated read-only)",
                distance=2,
            )
            for row in rows
            if row.get("key") not in (None, "")
        ]
        return found, "" if found else "no_rows"
