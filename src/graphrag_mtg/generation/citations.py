"""The citation format, and the one design decision that makes it safe.

The roadmap's target rendering is::

    [path: (Card "Opalescence")-[:HAS_RULING]->(r_123); (Rule 613.4)-[:SUBRULE_OF]->(613)]
    [CR 613.4] [ruling 2009-10-01]

**The model does not write that.** It writes the bare handles the
subgraph already carries — ``[rule:613.4]``, ``[ruling:2009-10-01]`` — and
this module expands them into the rendering above using the evidence that
was actually retrieved. The distinction is the whole point: a model asked
to write a graph path will write a plausible one, and a plausible path is
indistinguishable from a real one to every reader. Rendering from the
subgraph makes a fabricated *path* impossible, and leaves exactly one
failure the model can still commit — citing a handle that is not in the
context — which :func:`expand` detects mechanically and marks in the
answer rather than hiding.

That mechanical detection is also what gives E-007 its `evidence_absent`
code for free: it is the only support failure that needs no judgement.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph

#: A handle as the model must write it: ``[rule:613.4]``, and several in
#: one marker separated by ``;`` — ``[rule:613.4; ruling:2009-10-01]``.
#: Deliberately the same string :meth:`Evidence.cite` produces, so the
#: prompt can say "cite what you see" and mean it literally.
MARKER = re.compile(r"\[([a-z_]+:[^\]]+)\]")

#: How a handle that is not in the subgraph is rendered. Loud on purpose:
#: it is a claim the evidence does not back, and the reader is the last
#: line of defence when the audit has not run yet.
UNVERIFIED = "UNVERIFIED"

_KIND_LABEL = {
    "rule": "CR",
    "ruling": "ruling",
    "card": "card",
    "keyword": "keyword",
    "legality": "legality",
}


def handles(marker_body: str) -> list[str]:
    """Split one marker's body into individual handles."""
    return [part.strip() for part in marker_body.split(";") if part.strip()]


def cited_handles(answer: str) -> list[str]:
    """Every handle an answer cites, in order, deduped."""
    seen: dict[str, None] = {}
    for match in MARKER.finditer(answer):
        for handle in handles(match.group(1)):
            seen.setdefault(handle, None)
    return list(seen)


def normalize_spacing(text: str) -> str:
    """Collapse the whitespace a removed marker leaves behind.

    Sentence punctuation is deliberately untouched: the E-007 segmenter
    depends on it, and a cleanup that ate a full stop would silently merge
    two claims into one row.
    """
    collapsed = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r" +([.,;:!?])", r"\1", collapsed).strip()


def strip_citations(answer: str) -> str:
    """Remove every citation marker, leaving the prose alone.

    E-007 segments the *citation-stripped* text, so that where a sentence
    ends cannot be influenced by where a citation sits.
    """
    return normalize_spacing(MARKER.sub("", answer))


@dataclass(frozen=True)
class Citation:
    """One rendered citation: its evidence, its paths, its handles.

    Attributes:
        items: The evidence backing this marker, in citation order.
        unknown: Handles the marker cited that the subgraph does not hold.
    """

    items: tuple[Evidence, ...]
    unknown: tuple[str, ...] = ()

    def render(self) -> str:
        """The reader-facing form, paths first, then the source handles."""
        parts: list[str] = []
        paths = [item.path for item in self.items if item.path]
        if paths:
            parts.append(f"[path: {'; '.join(paths)}]")
        for item in self.items:
            label = _KIND_LABEL.get(item.kind, item.kind)
            parts.append(f"[{label} {item.key}]")
        parts += [f"[{UNVERIFIED} {handle}]" for handle in self.unknown]
        return " ".join(parts)


def index(subgraph: Subgraph) -> dict[str, Evidence]:
    """Map every handle a citation may use to its evidence.

    Generous on input, strict on output. The context shows rulings under a
    short ordinal — `ruling:3` — because a model cannot reliably copy 32
    random hex characters, and a mistyped id is a *typing* failure being
    scored as a *grounding* failure. But a correctly copied real id still
    resolves, since there is no reason to punish the model for getting the
    hard thing right.
    """
    table = dict(subgraph.handles())
    for item in subgraph.evidence:
        table.setdefault(item.cite(), item)
    return table


def resolve(marker_body: str, table: Mapping[str, Evidence]) -> Citation:
    """Turn one marker body into a :class:`Citation` against the evidence."""
    found: list[Evidence] = []
    unknown: list[str] = []
    for handle in handles(marker_body):
        item = table.get(handle)
        if item is None:
            unknown.append(handle)
        else:
            found.append(item)
    return Citation(tuple(found), tuple(unknown))


def expand(answer: str, subgraph: Subgraph) -> tuple[str, list[str]]:
    """Render every handle marker into the full citation format.

    Args:
        answer: The model's text, citing bare handles.
        subgraph: The evidence the answer was generated from.

    Returns:
        ``(rendered, unknown)`` — the answer with markers expanded, and
        every handle cited that the subgraph does not contain. A non-empty
        ``unknown`` is a fabricated citation and the caller decides what to
        do about it; this function neither drops it nor hides it, because a
        silently removed bad citation looks exactly like a good one.
    """
    table = index(subgraph)
    unknown: list[str] = []

    def replace(match: re.Match[str]) -> str:
        citation = resolve(match.group(1), table)
        unknown.extend(h for h in citation.unknown if h not in unknown)
        return citation.render()

    return MARKER.sub(replace, answer), unknown


def uncited_sentences(answer: str) -> list[str]:
    """Sentences carrying no citation marker, for a fast pre-audit look.

    A convenience for iteration, **not** the E-007 measurement: the real
    one segments the citation-stripped text under
    `docs/claim-annotation-guide.md`, labels each sentence factual or not,
    and is frozen before any of this is read. Anything computed here is a
    hint for the author mid-loop, and the docstring says so because a
    number that looks like the metric will be mistaken for it.
    """
    return [
        sentence.strip()
        for sentence in _SENTENCE.split(answer)
        if sentence.strip() and not MARKER.search(sentence)
    ]


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def evidence_lines(items: Iterable[Evidence]) -> Sequence[str]:
    """Handle-and-text lines for a prompt, one per evidence item."""
    return [f"[{item.cite()}] {item.text}" for item in items]
