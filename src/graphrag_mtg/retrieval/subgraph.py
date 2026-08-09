"""The retrieved subgraph: bounded, ordered, and citable item by item.

What the traversals return has to survive two pressures at once. It must
fit a context window, and every sentence Phase 5 writes from it must be
traceable back to a rule number, a ruling id, or a named path. Those pull
against each other — the cheapest way to fit a budget is to drop things
quietly, and a dropped fact that the answer still asserts is exactly the
failure this project exists to avoid.

So three rules hold here:

1. **Nothing is truncated silently.** Eviction is recorded in
   :attr:`Subgraph.dropped` and reported, so an answer built on a trimmed
   subgraph can say it was trimmed.
2. **Every item carries its provenance** — which template produced it and
   through which path — because a citation that cannot name its traversal
   is a citation of nothing.
3. **Empty is an outcome, not a bug.** The Phase 4 DoD demands a
   non-empty subgraph *or an explicit failure*, never quietly wrong
   context. :class:`Outcome` is that vocabulary, and ``NO_SEED`` is the
   case ADR-007 routes to text retrieval rather than treating as a miss.

Eviction drops the *farthest* evidence first. Distance is hops from
something the question actually named, which makes the budget spend
itself on what was asked about — and matches the reachability finding
that a wide ball stops discriminating (`scripts/reachability.py`: a k=6
ball holds 1515 of 3308 rules).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from graphrag_mtg.extraction.llm import estimate_tokens

#: Context ceiling for the serialized subgraph. Generous enough for a
#: multi-rule answer, small enough that a hub cannot fill the window.
DEFAULT_TOKEN_BUDGET = 6000

#: Cap on items of one kind from one template call. The interaction
#: traversal on a card sharing `flying` with thousands of others would
#: otherwise return the hub, not the answer.
DEFAULT_KIND_CAP = 25


class Outcome(StrEnum):
    """Why a retrieval produced what it produced.

    Every value other than :attr:`RESOLVED` is an *explicit* failure the
    caller must handle. None of them may be answered from as though the
    subgraph were complete.
    """

    RESOLVED = "resolved"
    NO_ENTITIES = "no_entities"  # linking resolved nothing at all
    AMBIGUOUS = "ambiguous"  # surfaces resolved, but need confirmation
    NO_SEED = "no_seed"  # entities exist, none reaches the rule graph
    NO_MATCH = "no_match"  # traversals ran and returned nothing


@dataclass(frozen=True)
class Evidence:
    """One citable fact, with the path that produced it.

    Attributes:
        kind: ``rule`` | ``ruling`` | ``card`` | ``keyword`` | ``legality``.
        key: The citation handle — rule number, ruling id, oracle_id.
        text: What the node says. The answer may quote this and nothing else.
        template: Name of the traversal that produced it.
        path: Readable traversal, e.g.
            ``(:Card {Serra Angel})-[:HAS_KEYWORD]->(:Keyword {flying})``.
        distance: Hops from an entity the question named. 0 means the
            question named this node itself.
    """

    kind: str
    key: str
    text: str
    template: str
    path: str
    distance: int = 0

    @property
    def tokens(self) -> int:
        """Rough size of this item once serialized."""
        return estimate_tokens(f"{self.kind} {self.key} {self.text} {self.path}")

    def cite(self) -> str:
        """The citation handle a generated answer must carry."""
        return f"{self.kind}:{self.key}"


@dataclass
class Subgraph:
    """Evidence for one question, bounded and accounted for."""

    question: str
    outcome: Outcome = Outcome.RESOLVED
    evidence: list[Evidence] = field(default_factory=list)
    templates_run: list[str] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    capped: Counter[str] = field(default_factory=Counter)
    note: str = ""

    @property
    def tokens(self) -> int:
        """Estimated size of the serialized subgraph."""
        return sum(item.tokens for item in self.evidence)

    @property
    def is_empty(self) -> bool:
        return not self.evidence

    def citations(self) -> list[str]:
        """Every citation handle present, deduped, in evidence order."""
        seen: dict[str, None] = {}
        for item in self.evidence:
            seen.setdefault(item.cite(), None)
        return list(seen)


def add_evidence(
    subgraph: Subgraph,
    items: Iterable[Evidence],
    *,
    kind_cap: int = DEFAULT_KIND_CAP,
) -> None:
    """Add items to a subgraph, capping how many of one kind get in.

    The cap is per ``(template, kind)``, which is where hubs live: one
    traversal returning ten thousand cards for `flying` is the failure
    mode, not ten traversals returning one each. Overflow is counted in
    :attr:`Subgraph.capped` rather than dropped in silence.
    """
    seen = {(e.template, e.kind, e.key) for e in subgraph.evidence}
    per_bucket = Counter((e.template, e.kind) for e in subgraph.evidence)
    for item in items:
        identity = (item.template, item.kind, item.key)
        if identity in seen:
            continue
        bucket = (item.template, item.kind)
        if per_bucket[bucket] >= kind_cap:
            subgraph.capped[item.kind] += 1
            continue
        subgraph.evidence.append(item)
        seen.add(identity)
        per_bucket[bucket] += 1


def enforce_budget(subgraph: Subgraph, budget: int = DEFAULT_TOKEN_BUDGET) -> None:
    """Trim to ``budget`` tokens, farthest evidence first, and record it.

    Ties at the same distance are broken by later arrival, so the first
    traversal to answer keeps its ground. Distance-0 evidence — nodes the
    question named — is evicted only if the budget cannot hold even that,
    which is a condition worth surfacing rather than papering over.
    """
    if subgraph.tokens <= budget:
        return
    order = sorted(
        range(len(subgraph.evidence)),
        key=lambda i: (-subgraph.evidence[i].distance, -i),
    )
    keep = set(range(len(subgraph.evidence)))
    running = subgraph.tokens
    for index in order:
        if running <= budget:
            break
        keep.discard(index)
        running -= subgraph.evidence[index].tokens
        subgraph.dropped[subgraph.evidence[index].kind] += 1
    subgraph.evidence = [e for i, e in enumerate(subgraph.evidence) if i in keep]
    if subgraph.dropped:
        subgraph.note = (
            f"trimmed to a {budget}-token budget; dropped {dict(subgraph.dropped)}"
        )


def serialize(subgraph: Subgraph) -> str:
    """Render the subgraph for a generation prompt.

    Grouped by kind, each line carrying its citation handle and the path
    it came from, so the answering prompt can be told to cite handles and
    nothing else. The trailing notice is deliberate: a model told the
    context was trimmed can hedge, and one told nothing cannot.
    """
    if subgraph.is_empty:
        return f"NO EVIDENCE ({subgraph.outcome}). {subgraph.note}".strip()

    lines: list[str] = []
    for kind in ("card", "keyword", "rule", "ruling", "legality"):
        items = [e for e in subgraph.evidence if e.kind == kind]
        if not items:
            continue
        lines.append(f"## {kind}")
        for item in items:
            lines.append(f"[{item.cite()}] {item.text}")
            lines.append(f"    via {item.template}: {item.path}")
    if subgraph.dropped or subgraph.capped:
        lines.append(
            "\nNOTICE: this context is incomplete — "
            f"dropped {dict(subgraph.dropped) or '{}'}, "
            f"capped {dict(subgraph.capped) or '{}'}. "
            "Say so if the answer depends on what is missing."
        )
    return "\n".join(lines)
