"""Extractor response handling — everything except the API call itself."""

from __future__ import annotations

from graphrag_mtg.extraction.extractor import build_prompt, parse_response

TEXT = "Trample damage is assigned only after lethal damage is assigned to all blockers."


class TestBuildPrompt:
    def test_open_mode_has_no_candidate_list(self) -> None:
        prompt = build_prompt(TEXT)
        assert "Candidate rules" not in prompt
        assert TEXT in prompt

    def test_grounded_mode_lists_candidates(self) -> None:
        prompt = build_prompt(TEXT, candidate_rules=[("702.19e", "trample assignment…")])
        assert "Candidate rules" in prompt
        assert "702.19e" in prompt


class TestParseResponse:
    def test_valid_item_gets_real_offsets(self) -> None:
        quote = "assigned only after lethal damage"
        raw = [
            {
                "rule_number": "702.19e",
                "quote": quote,
                "rationale": "trample rule",
                "confidence": 0.9,
            }
        ]
        report = parse_response("r1", TEXT, raw)
        (candidate,) = report.candidates
        assert TEXT[candidate.span.start : candidate.span.end] == quote
        assert candidate.rule_number == "702.19e"
        assert not report.dropped

    def test_fabricated_quote_is_dropped(self) -> None:
        raw = [
            {
                "rule_number": "702.19e",
                "quote": "words the ruling never says",
                "rationale": "x",
                "confidence": 0.9,
            }
        ]
        report = parse_response("r1", TEXT, raw)
        assert report.candidates == []
        assert report.dropped["quote_not_in_source"] == 1

    def test_bad_rule_number_shape_is_dropped(self) -> None:
        raw = [{"rule_number": "not-a-rule", "quote": "Trample", "confidence": 0.9}]
        report = parse_response("r1", TEXT, raw)
        assert report.dropped["schema_invalid"] == 1

    def test_non_list_response(self) -> None:
        report = parse_response("r1", TEXT, {"rule_number": "702.19e"})
        assert report.dropped["response_not_a_list"] == 1

    def test_empty_list_is_a_valid_answer(self) -> None:
        report = parse_response("r1", TEXT, [])
        assert report.candidates == [] and not report.dropped
