"""Pydantic schemas for every LLM-proposed edge (ontology v1).

Three edge families come out of Phase 3, all defined in docs/ontology.md:

- ``(:Ruling)-[:MENTIONS]->(:Card)`` — entity linking (exact→fuzzy→LLM);
- ``(:Ruling)-[:CITES_RULE]->(:Rule)`` — LLM extraction (the roadmap's
  working name APPLIES_RULE; the ontology's canonical name wins);
- ``(:Rule)-[:REFERENCES]->(:Rule)`` — *implicit* cross-references only
  (explicit "see rule X" links are already deterministic).

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

    EXACT = "exact"  # normalized full-name match, multi-word (unambiguous)
    LOOSE = "loose"  # punctuation-insensitive match (Lim-Dul's ~ Lim Duls)
    SURFACE = "surface"  # single-word name seen capitalized — needs LLM
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

    Only 25 of 77,999 rulings (3 cards) state a rule number, so this
    is *inference*, not quote-matching: the LLM maps the ruling's language
    onto the rule that governs it. The span quotes the ruling passage that
    invokes the rule's concept; ``rationale`` says why that passage means
    that rule. When the passage *does* contain an explicit rule number, the
    gate additionally requires it to agree with ``rule_number`` — the cheap
    check that catches "601.2c when the text says 601.2b".

    Attributes:
        ruling_id: Source ruling.
        rule_number: Cited CR rule (e.g. ``"613.4b"``), which must exist in
            the graph.
        span: Ruling passage the citation rests on.
        rationale: One sentence tying span to rule; audit material, never
            shown as an answer.
        method: Always :attr:`LinkMethod.LLM` for citations today.
        confidence: Model-reported, thresholded by the gate.
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
