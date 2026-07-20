"""Schema invariants: a span is a checkable claim or it is invalid."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from graphrag_mtg.extraction.schemas import (
    CardMention,
    EvidenceSpan,
    LinkMethod,
    RuleCitation,
    RuleCrossRef,
)


def span(text: str = "Giant Growth", start: int = 10) -> EvidenceSpan:
    return EvidenceSpan(start=start, end=start + len(text), text=text)


class TestEvidenceSpan:
    def test_length_must_match_offsets(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceSpan(start=0, end=5, text="too long for five")

    def test_empty_span_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceSpan(start=3, end=3, text="")

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceSpan(start=10, end=4, text="abcdef")


class TestCardMention:
    def test_resolved_property(self) -> None:
        base = {
            "ruling_id": "r1",
            "surface": "Giant Growth",
            "span": span(),
            "method": LinkMethod.EXACT,
            "confidence": 1.0,
        }
        assert not CardMention(**base, oracle_id=None).resolved
        assert CardMention(**base, oracle_id="abc").resolved


class TestRuleCitation:
    def test_rule_number_shape_enforced(self) -> None:
        base = {
            "ruling_id": "r1",
            "span": span(),
            "rationale": "because",
            "confidence": 0.9,
        }
        RuleCitation(**base, rule_number="613.4b")
        RuleCitation(**base, rule_number="613")
        with pytest.raises(ValidationError):
            RuleCitation(**base, rule_number="613.4b.2")
        with pytest.raises(ValidationError):
            RuleCitation(**base, rule_number="rule 613")


class TestRuleCrossRef:
    def test_self_reference_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleCrossRef(
                source_rule="613.4",
                target_rule="613.4",
                span=span(),
                rationale="loop",
                confidence=0.9,
            )
