"""Gate invariants: the seal, the span check, and every rejection reason."""

from __future__ import annotations

import pytest

from graphrag_mtg.extraction.gate import GatedTriple, gate_candidates
from graphrag_mtg.extraction.schemas import (
    CardMention,
    EvidenceSpan,
    LinkMethod,
    RuleCitation,
)

RULING_TEXT = "This works like Giant Growth under rule six-thirteen."
EXPLICIT_TEXT = "As per 613.4b, apply ability changes in timestamp order."

SOURCE_TEXTS = {"r1": RULING_TEXT, "r2": EXPLICIT_TEXT}
KNOWN_RULES = frozenset({"613", "613.4b", "702.19e"})
KNOWN_CARDS = frozenset({"gg-1"})


def mention(**overrides) -> CardMention:
    text = "Giant Growth"
    start = RULING_TEXT.index(text)
    fields = {
        "ruling_id": "r1",
        "surface": text,
        "oracle_id": "gg-1",
        "span": EvidenceSpan(start=start, end=start + len(text), text=text),
        "method": LinkMethod.EXACT,
        "confidence": 1.0,
    }
    fields.update(overrides)
    return CardMention(**fields)


def citation(**overrides) -> RuleCitation:
    text = "As per 613.4b"
    fields = {
        "ruling_id": "r2",
        "rule_number": "613.4b",
        "span": EvidenceSpan(start=0, end=len(text), text=text),
        "rationale": "explicit citation",
        "confidence": 0.9,
    }
    fields.update(overrides)
    return RuleCitation(**fields)


def run_gate(*candidates, **kwargs):
    defaults = {
        "source_texts": SOURCE_TEXTS,
        "known_rules": KNOWN_RULES,
        "known_cards": KNOWN_CARDS,
    }
    defaults.update(kwargs)
    return gate_candidates(candidates, **defaults)


class TestSeal:
    def test_gated_triple_cannot_be_constructed_directly(self) -> None:
        with pytest.raises(TypeError, match="gate_candidates"):
            GatedTriple(
                edge_type="MENTIONS",
                source_key="r1",
                target_key="gg-1",
                span_start=0,
                span_end=1,
                span_text="G",
                method="exact",
                confidence=1.0,
            )

    def test_gate_output_is_sealed(self) -> None:
        result = run_gate(mention())
        (triple,) = result.accepted
        assert isinstance(triple, GatedTriple)
        assert triple.edge_type == "MENTIONS"
        assert triple.target_key == "gg-1"


class TestChecks:
    def test_span_must_be_verbatim(self) -> None:
        bad = mention(span=EvidenceSpan(start=0, end=12, text="Giant Growth"))
        result = run_gate(bad)
        assert result.accepted == []
        assert result.rejected["span_not_verbatim"] == 1

    def test_source_must_exist(self) -> None:
        result = run_gate(mention(ruling_id="ghost"))
        assert result.rejected["source_not_in_graph"] == 1

    def test_unresolved_mention_rejected(self) -> None:
        result = run_gate(mention(oracle_id=None, method=LinkMethod.SURFACE, confidence=0.0))
        assert result.rejected["mention_unresolved"] == 1

    def test_card_must_exist(self) -> None:
        result = run_gate(mention(oracle_id="not-a-card"))
        assert result.rejected["card_not_in_graph"] == 1

    def test_hallucinated_rule_number_rejected(self) -> None:
        # Plausible but absent from the graph — the 601.2c-for-601.2b net.
        result = run_gate(citation(rule_number="613.9z"))
        assert result.rejected["rule_not_in_graph"] == 1

    def test_explicit_number_must_agree(self) -> None:
        # Span literally says 613.4b; citing 702.19e from it is rejected.
        # Under the permissive gate this is its own reason; under the shipped
        # one it never gets that far (see TestSchemaReduction).
        result = run_gate(citation(rule_number="702.19e"), require_explicit_citations=False)
        assert result.rejected["explicit_number_disagrees"] == 1

    def test_low_confidence_rejected(self) -> None:
        result = run_gate(citation(confidence=0.2))
        assert result.rejected["low_confidence"] == 1

    def test_accepted_citation_carries_rationale(self) -> None:
        (triple,) = run_gate(citation()).accepted
        assert triple.edge_type == "CITES_RULE"
        assert triple.rationale == "explicit citation"


class TestDedupe:
    def test_duplicates_keep_highest_confidence(self) -> None:
        result = run_gate(citation(confidence=0.8), citation(confidence=0.95))
        assert result.rejected["duplicate"] == 1
        (triple,) = result.accepted
        assert triple.confidence == 0.95

    def test_total_accounts_for_everything(self) -> None:
        result = run_gate(mention(), citation(), citation(confidence=0.1))
        assert result.total == 3


class TestSchemaReduction:
    """CITES_RULE is confined to what the ruling states (G3, 2026-08-09).

    The reduction is a gate check, not a prompt instruction, precisely
    because E-003 measured what the prompt instruction was worth: the
    inferred path scored citation F1 0.125 over 125 annotated rulings.
    """

    def inferred(self) -> RuleCitation:
        """A citation whose span names no rule — the LLM path's normal output."""
        text = "This works like Giant Growth"
        return RuleCitation(
            ruling_id="r1",
            rule_number="613",
            span=EvidenceSpan(start=0, end=len(text), text=text),
            rationale="the ruling turns on layers",
            method=LinkMethod.LLM,
            confidence=0.95,
        )

    def test_an_inferred_citation_is_rejected(self) -> None:
        result = run_gate(self.inferred())
        assert result.accepted == []
        assert result.rejected["citation_not_explicit"] == 1

    def test_confidence_does_not_buy_a_way_in(self) -> None:
        """A model certain of an unverifiable claim is the case being excluded."""
        result = run_gate(self.inferred().model_copy(update={"confidence": 1.0}))
        assert result.rejected["citation_not_explicit"] == 1

    def test_a_stated_number_still_passes(self) -> None:
        (triple,) = run_gate(citation()).accepted
        assert (triple.edge_type, triple.target_key) == ("CITES_RULE", "613.4b")

    def test_the_permissive_gate_reproduces_the_old_behaviour(self) -> None:
        """E-003 predates the reduction; its figure must stay reproducible."""
        result = run_gate(self.inferred(), require_explicit_citations=False)
        assert len(result.accepted) == 1

    def test_mentions_are_untouched_by_the_reduction(self) -> None:
        """G3 fired on citations. Linking is a separate, still-open question."""
        assert len(run_gate(mention()).accepted) == 1
