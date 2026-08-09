"""Pydantic schemas for every LLM-proposed edge (ontology v1).

Three edge families come out of Phase 3, all defined in docs/ontology.md:

- ``(:Ruling)-[:MENTIONS]->(:Card)`` — entity linking (exact→fuzzy→LLM);
- ``(:Ruling)-[:CITES_RULE]->(:Rule)`` — **deterministic only** since the
  E-003 schema reduction (2026-08-09): the ruling must state the rule
  number itself. LLM-inferred citations are measured at F1 0.125 and the
  gate now refuses them (the roadmap's working name was APPLIES_RULE; the
  ontology's canonical name wins);
- ``(:Rule)-[:REFERENCES]->(:Rule)`` — *implicit* cross-references only
  (explicit "see rule X" links are already deterministic). Never wired
  into the pipeline, so no unmeasured LLM edge has ever reached the graph.

Every candidate carries a mandatory :class:`EvidenceSpan`. The span is a
claim about the source text ("characters ``start:end`` read exactly
``text``"), which makes it *checkable*: `extraction/gate.py` re-reads the
source and rejects any candidate whose claim is false. A triple without a
verifiable span never reaches the graph — that is the project's line in
the sand against extraction hallucination.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class LinkMethod(StrEnum):
    """Which stage of the linking/extraction cascade produced a candidate."""

    EXACT = "exact"  # normalized multi-word match with a capitalized word
    LOOSE = "loose"  # punctuation-insensitive match (Lim-Dul's ~ Lim Duls)
    SURFACE = "surface"  # single-word name seen capitalized — needs LLM
    EXPLICIT = "explicit"  # the source text states the rule number itself
    LLM = "llm"  # LLM-disambiguated or LLM-extracted


class EvidenceSpan(BaseModel):
    """A verbatim, offset-addressed quote from the source document.

    Attributes:
        start: Character offset of the first character in the source text.
        end: Character offset one past the last character.
        text: The exact substring ``source[start:end]``. The gate verifies
            this equality; a span that does not reproduce the source is
            evidence of nothing.
    """

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _end_after_start(self) -> EvidenceSpan:
        if self.end <= self.start:
            msg = f"empty span: start={self.start}, end={self.end}"
            raise ValueError(msg)
        if self.end - self.start != len(self.text):
            msg = f"span length {self.end - self.start} != text length {len(self.text)}"
            raise ValueError(msg)
        return self


class CardMention(BaseModel):
    """Candidate ``(:Ruling)-[:MENTIONS]->(:Card)`` edge.

    Attributes:
        ruling_id: Source ruling (the graph's Ruling key).
        surface: The name form as it appears in the ruling text.
        oracle_id: Target card, when resolved; ``None`` while the candidate
            still awaits LLM disambiguation.
        span: Where in the ruling the surface occurs.
        method: Cascade stage that produced (or resolved) the candidate.
        confidence: In ``[0, 1]``. Deterministic stages assert 1.0; the LLM
            stage reports its own, and the gate thresholds it.
    """

    ruling_id: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    oracle_id: str | None = None
    span: EvidenceSpan
    method: LinkMethod
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def resolved(self) -> bool:
        """Whether the mention already points at a concrete card."""
        return self.oracle_id is not None


class RuleCitation(BaseModel):
    """Candidate ``(:Ruling)-[:CITES_RULE]->(:Rule)`` edge.

    Only 25 of 77,999 rulings (3 cards) state a rule number. The original
    design treated the rest as *inference* — the LLM mapping a ruling's
    language onto the rule that governs it — and E-003 measured that at
    citation F1 0.125 [0.073, 0.180], with a sampled decomposition
    (E-003b) attributing the gap to model error rather than to the metric
    or the gold. Gate G3's registered rule fired, and since 2026-08-09 the
    gate requires ``rule_number`` to appear inside ``span.text``. The model
    is left free to propose; nothing it infers reaches the graph.

    That leaves the tiny explicit slice, produced deterministically by
    `extraction/explicit_citations.py`. The narrow schema is the honest
    one: this edge now means "the ruling names this rule", not "this rule
    governs this ruling".

    Attributes:
        ruling_id: Source ruling.
        rule_number: Cited CR rule (e.g. ``"613.4b"``), which must exist in
            the graph *and*, under the shipped gate, appear in the span.
        span: Ruling passage the citation rests on.
        rationale: One sentence tying span to rule; audit material, never
            shown as an answer.
        method: :attr:`LinkMethod.EXPLICIT` for the deterministic path;
            :attr:`LinkMethod.LLM` survives for reproducing E-003.
        confidence: Model-reported, thresholded by the gate; the
            deterministic path asserts 1.0.
    """

    ruling_id: str = Field(min_length=1)
    rule_number: str = Field(pattern=r"^\d{1,3}(\.\d+[a-z]?)?$")
    span: EvidenceSpan
    rationale: str = Field(min_length=1)
    method: LinkMethod = LinkMethod.LLM
    confidence: float = Field(ge=0.0, le=1.0)


class RuleCrossRef(BaseModel):
    """Candidate implicit ``(:Rule)-[:REFERENCES]->(:Rule)`` edge.

    Only for references the deterministic parser cannot see (no "see rule
    X" phrase). The span lives in the *source rule's* text.
    """

    source_rule: str = Field(pattern=r"^\d{1,3}(\.\d+[a-z]?)?$")
    target_rule: str = Field(pattern=r"^\d{1,3}(\.\d+[a-z]?)?$")
    span: EvidenceSpan
    rationale: str = Field(min_length=1)
    method: LinkMethod = LinkMethod.LLM
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _no_self_reference(self) -> RuleCrossRef:
        if self.source_rule == self.target_rule:
            msg = f"rule {self.source_rule} cannot implicitly reference itself"
            raise ValueError(msg)
        return self


ExtractionCandidate = CardMention | RuleCitation | RuleCrossRef
