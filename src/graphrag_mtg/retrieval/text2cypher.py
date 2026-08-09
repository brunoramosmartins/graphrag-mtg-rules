"""Generated Cypher for the long tail — validated, and never trusted.

The second layer of ADR-005, and the phase's registered first cut if the
timebox runs out. Templates answer the golden set's families; this exists
for the question nobody wrote a traversal for.

**Defence in depth, and the order matters.** The checks in this module
catch *mistakes* — a model that writes `SET` because the question said
"set the power to 3". They do not catch an attacker, and pretending
otherwise would be the dangerous part. What actually confines the damage
is running the query in a **read transaction**: Neo4j refuses writes
server-side there regardless of what the string says, and no amount of
comment-smuggling or clause-splitting gets around it. This module
validates first so a bad query fails loudly with a reason, and the caller
executes with ``session.execute_read`` so a validation miss is still not
a write.

Everything here fails closed. A query that cannot be parsed with
confidence is rejected, not executed and hoped about — and a rejection is
an honest "I cannot translate this question", which is a better answer
than a plausible query against the wrong nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

    found = _LIMIT.search(body)
    if found is None:
        query = f"{query}\nLIMIT {DEFAULT_LIMIT}"
    elif int(found.group(1)) > max_limit:
        query = _LIMIT.sub(f"LIMIT {max_limit}", query, count=1)

    return Verdict(True, "", query)


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
        "  - it must RETURN something, and carry a LIMIT",
        "  - no procedure calls",
        "  - use parameters for values you were given, not string concatenation",
        "",
        'If the schema cannot answer the question, reply exactly: CANNOT TRANSLATE',
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
