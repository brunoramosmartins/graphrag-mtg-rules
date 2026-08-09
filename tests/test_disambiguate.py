"""Homonym disambiguation: prompt shape and response handling, no network."""

from __future__ import annotations

from graphrag_mtg.extraction.disambiguate import build_prompt, parse_response
from graphrag_mtg.extraction.linker import PendingMention
from graphrag_mtg.extraction.schemas import CardMention, EvidenceSpan, LinkMethod

TEXT = "If Clone enters as a copy, creatures with fear are still unblockable."


def pending(surface: str, start: int, candidates: tuple[str, ...] = ("card-1",)) -> PendingMention:
    return PendingMention(
        mention=CardMention(
            ruling_id="r1",
            surface=surface,
            oracle_id=None,
            span=EvidenceSpan(start=start, end=start + len(surface), text=surface),
            method=LinkMethod.SURFACE,
            confidence=0.0,
        ),
        candidate_oracle_ids=candidates,
    )


class TestBuildPrompt:
    def test_numbers_each_occurrence_with_its_offset(self) -> None:
        items = [pending("Clone", TEXT.index("Clone")), pending("fear", TEXT.index("fear"))]
        prompt = build_prompt(items, TEXT)
        assert '1. "Clone" at character 3' in prompt
        assert '2. "fear" at character' in prompt
        assert TEXT in prompt


class TestParseResponse:
    def test_yes_resolves_to_the_single_candidate(self) -> None:
        items = [pending("Clone", 3)]
        report = parse_response(items, [{"n": 1, "is_card": True, "confidence": 0.9}])
        (mention,) = report.resolved
        assert mention.oracle_id == "card-1"
        assert mention.method == LinkMethod.LLM
        assert mention.span.text == "Clone"

    def test_no_is_counted_not_resolved(self) -> None:
        report = parse_response([pending("fear", 40)], [{"n": 1, "is_card": False}])
        assert report.resolved == []
        assert report.rejected_as_not_a_card == 1

    def test_ambiguous_candidate_set_is_never_guessed(self) -> None:
        items = [pending("Shock", 0, candidates=("a", "b"))]
        report = parse_response(items, [{"n": 1, "is_card": True, "confidence": 0.99}])
        assert report.resolved == []
        assert report.dropped["ambiguous_candidate_set"] == 1

    def test_missing_answer_is_counted_not_assumed(self) -> None:
        items = [pending("Clone", 3), pending("Opt", 20)]
        report = parse_response(items, [{"n": 1, "is_card": True, "confidence": 0.8}])
        assert len(report.resolved) == 1
        assert report.dropped["no_answer_for_occurrence"] == 1

    def test_confidence_is_clamped(self) -> None:
        report = parse_response([pending("Clone", 3)], [{"n": 1, "is_card": True, "confidence": 5}])
        assert report.resolved[0].confidence == 1.0

    def test_non_list_response(self) -> None:
        report = parse_response([pending("Clone", 3)], {"is_card": True})
        assert report.dropped["response_not_a_list"] == 1
