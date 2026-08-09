"""The extraction gate: nothing LLM-proposed enters the graph around it.

Contract (CLAUDE.md, non-negotiable): schema + evidence span + confidence
+ dedupe, plus linking to nodes that actually exist. The mechanism that
makes the contract testable is :class:`GatedTriple` — a sealed type that
only :func:`gate_candidates` can construct. `extraction/load.py` accepts
nothing else, so "zero ungated triples in the graph" is a type-level
property with a test, not a convention.

Checks, in order (a candidate is rejected at its first failure, and every
rejection is counted under a named reason — the counts drive prompt
iteration):

1. **schema** — the candidate re-validates against its Pydantic model
   (candidates round-trip through JSONL files between pipeline stages).
2. **source exists** — the ruling/rule the edge hangs on is in the graph.
3. **span is verbatim** — ``source_text[start:end] == span.text``. An
   evidence span that does not reproduce the source is evidence of
   nothing.
4. **target exists** — cited rule number / linked oracle_id is a real
   node. This is the net for "cites 601.2c when it means 601.2b" — a
   plausible-but-nonexistent number dies here.
5. **the citation is explicit** — the cited rule number must appear in
   the span itself. This is the E-003 schema reduction (2026-08-09)
   expressed as a gate check rather than as a prompt instruction, which
   is the whole point: a guarantee that lives in the prompt is a wish,
   and E-003 measured what that wish was worth (citation F1 0.125).
   ``require_explicit_citations=False`` restores the permissive check —
   agreement only when the span happens to contain a number — and exists
   so E-003's recorded figure stays reproducible.
6. **confidence** — below threshold is out. The threshold is part of
   E-003's configuration in `experiments/registry.md`; changing it after
   seeing results is what the registry exists to prevent.
7. **dedupe** — one edge per (type, source, target), keeping the highest
   confidence.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from graphrag_mtg.extraction.schemas import (
    CardMention,
    ExtractionCandidate,
    RuleCitation,
    RuleCrossRef,
)

DEFAULT_MIN_CONFIDENCE = 0.7

_RULE_NUMBER = re.compile(r"\d{3}(?:\.\d+[a-z]?)?")

# Module-private seal: possession proves the triple went through the gate.
_GATE_SEAL = object()


@dataclass(frozen=True)
class GatedTriple:
    """An edge that passed every gate check. Constructable only by the gate.

    Attributes:
        edge_type: ``MENTIONS`` | ``CITES_RULE`` | ``REFERENCES``.
        source_key: ``ruling_id`` (or source rule number for REFERENCES).
        target_key: ``oracle_id`` or rule number.
        span_start: Evidence span offsets into the source text.
        span_end: See ``span_start``.
        span_text: The verbatim evidence quote.
        method: Cascade stage that produced the edge.
        confidence: As reported by that stage.
        rationale: Audit note (citations/cross-refs only).
    """

    edge_type: str
    source_key: str
    target_key: str
    span_start: int
    span_end: int
    span_text: str
    method: str
    confidence: float
    rationale: str = ""

    def __post_init__(self) -> None:
        if getattr(self, "_seal", None) is not _GATE_SEAL:
            msg = "GatedTriple can only be created by gate_candidates()"
            raise TypeError(msg)

    @classmethod
    def _sealed(cls, **kwargs: object) -> GatedTriple:
        triple = object.__new__(cls)
        object.__setattr__(triple, "_seal", _GATE_SEAL)
        for name, value in kwargs.items():
            object.__setattr__(triple, name, value)
        return triple


@dataclass
class GateResult:
    """Accepted triples plus the full accounting of what was rejected."""

    accepted: list[GatedTriple] = field(default_factory=list)
    rejected: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        """Candidates seen (accepted + rejected)."""
        return len(self.accepted) + sum(self.rejected.values())


def gate_candidates(
    candidates: Iterable[ExtractionCandidate],
    *,
    source_texts: Mapping[str, str],
    known_rules: frozenset[str] | set[str],
    known_cards: frozenset[str] | set[str],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    require_explicit_citations: bool = True,
) -> GateResult:
    """Run every candidate through the gate.

    Args:
        candidates: Mixed CardMention / RuleCitation / RuleCrossRef stream.
        source_texts: Source text by key — ruling_id for mentions and
            citations, rule number for cross-refs. A key's absence means
            the source node is not in the graph.
        known_rules: Rule numbers currently in the graph.
        known_cards: oracle_ids currently in the graph.
        min_confidence: Gate threshold (pinned in E-003 before any run).
        require_explicit_citations: Ship default. A ``CITES_RULE``
            candidate passes only if its rule number appears in its own
            evidence span, which confines the edge to the deterministic
            slice. Set False to reproduce E-003, whose run predates the
            reduction — not to widen what a later run may load.

    Returns:
        A :class:`GateResult`; ``result.accepted`` is the only legal input
        to `extraction/load.py`.
    """
    result = GateResult()
    best: dict[tuple[str, str, str], GatedTriple] = {}

    for candidate in candidates:
        reason = _first_failure(
            candidate,
            source_texts=source_texts,
            known_rules=known_rules,
            known_cards=known_cards,
            min_confidence=min_confidence,
            require_explicit_citations=require_explicit_citations,
        )
        if reason is not None:
            result.rejected[reason] += 1
            continue
        triple = _to_triple(candidate)
        key = (triple.edge_type, triple.source_key, triple.target_key)
        kept = best.get(key)
        if kept is None:
            best[key] = triple
        else:
            result.rejected["duplicate"] += 1
            if triple.confidence > kept.confidence:
                best[key] = triple

    result.accepted = list(best.values())
    return result


def _first_failure(
    candidate: ExtractionCandidate,
    *,
    source_texts: Mapping[str, str],
    known_rules: frozenset[str] | set[str],
    known_cards: frozenset[str] | set[str],
    min_confidence: float,
    require_explicit_citations: bool = True,
) -> str | None:
    """Return the first failed check's reason, or None if all pass."""
    try:
        candidate = type(candidate).model_validate(candidate.model_dump())
    except ValidationError:
        return "schema_invalid"

    source_key = (
        candidate.source_rule if isinstance(candidate, RuleCrossRef) else candidate.ruling_id
    )
    source_text = source_texts.get(source_key)
    if source_text is None:
        return "source_not_in_graph"

    span = candidate.span
    if source_text[span.start : span.end] != span.text:
        return "span_not_verbatim"

    if isinstance(candidate, CardMention):
        if candidate.oracle_id is None:
            return "mention_unresolved"
        if candidate.oracle_id not in known_cards:
            return "card_not_in_graph"
    elif isinstance(candidate, RuleCitation):
        if candidate.rule_number not in known_rules:
            return "rule_not_in_graph"
        explicit = _RULE_NUMBER.findall(span.text)
        if require_explicit_citations and candidate.rule_number not in explicit:
            # The reduction. An inferred citation is not rejected for being
            # wrong — it is rejected for being unverifiable from its own
            # evidence, which is the property the gate was built to demand
            # and the one the LLM path could never supply.
            return "citation_not_explicit"
        if explicit and candidate.rule_number not in explicit:
            return "explicit_number_disagrees"
    elif isinstance(candidate, RuleCrossRef):
        if candidate.target_rule not in known_rules:
            return "rule_not_in_graph"

    if candidate.confidence < min_confidence:
        return "low_confidence"
    return None


def _to_triple(candidate: ExtractionCandidate) -> GatedTriple:
    if isinstance(candidate, CardMention):
        edge_type, source, target = "MENTIONS", candidate.ruling_id, candidate.oracle_id or ""
        rationale = ""
    elif isinstance(candidate, RuleCitation):
        edge_type, source, target = "CITES_RULE", candidate.ruling_id, candidate.rule_number
        rationale = candidate.rationale
    else:
        edge_type, source, target = "REFERENCES", candidate.source_rule, candidate.target_rule
        rationale = candidate.rationale
    return GatedTriple._sealed(
        edge_type=edge_type,
        source_key=source,
        target_key=target,
        span_start=candidate.span.start,
        span_end=candidate.span.end,
        span_text=candidate.span.text,
        method=str(candidate.method),
        confidence=candidate.confidence,
        rationale=rationale,
    )
