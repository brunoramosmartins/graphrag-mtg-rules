"""Implicit cross-reference extraction — prompt shape and response handling."""

from __future__ import annotations

from graphrag_mtg.extraction.crossref import build_prompt, parse_response

SOURCE = "A blocking creature must be able to block the attacker legally."
CANDIDATES = [("702.9", "Flying"), ("509.4", "Ordering blockers")]
CANDIDATE_NUMBERS = frozenset({"702.9", "509.4"})


class TestBuildPrompt:
    def test_lists_only_candidate_targets(self) -> None:
        prompt = build_prompt("509.1", SOURCE, CANDIDATES)
        assert "cite ONLY from this list" in prompt
        assert "702.9" in prompt and "509.4" in prompt
        assert SOURCE in prompt


class TestParseResponse:
    def _one(self, target="702.9", quote="able to block the attacker legally"):
        return [{"target_rule": target, "quote": quote, "rationale": "x", "confidence": 0.8}]

    def test_valid_candidate_gets_real_offsets(self) -> None:
        report = parse_response(
            "509.1", SOURCE, self._one(), candidate_numbers=CANDIDATE_NUMBERS
        )
        (ref,) = report.candidates
        assert ref.target_rule == "702.9"
        assert SOURCE[ref.span.start : ref.span.end] == "able to block the attacker legally"
        assert not report.dropped

    def test_target_outside_candidate_list_is_dropped(self) -> None:
        report = parse_response(
            "509.1", SOURCE, self._one(target="999.9"), candidate_numbers=CANDIDATE_NUMBERS
        )
        assert report.candidates == []
        assert report.dropped["target_not_a_candidate"] == 1

    def test_explicit_reference_is_not_reproposed(self) -> None:
        report = parse_response(
            "509.1",
            SOURCE,
            self._one(),
            explicit_refs={"702.9"},
            candidate_numbers=CANDIDATE_NUMBERS,
        )
        assert report.dropped["already_explicit"] == 1

    def test_self_reference_is_dropped(self) -> None:
        report = parse_response(
            "702.9", SOURCE, self._one(), candidate_numbers=CANDIDATE_NUMBERS
        )
        assert report.dropped["self_reference"] == 1

    def test_fabricated_quote_is_dropped(self) -> None:
        report = parse_response(
            "509.1",
            SOURCE,
            self._one(quote="words not in the rule"),
            candidate_numbers=CANDIDATE_NUMBERS,
        )
        assert report.dropped["quote_not_in_source"] == 1

    def test_duplicate_target_kept_once(self) -> None:
        raw = self._one() + self._one()
        report = parse_response("509.1", SOURCE, raw, candidate_numbers=CANDIDATE_NUMBERS)
        assert len(report.candidates) == 1
        assert report.dropped["duplicate_in_response"] == 1

    def test_empty_array_is_valid(self) -> None:
        report = parse_response("509.1", SOURCE, [], candidate_numbers=CANDIDATE_NUMBERS)
        assert report.candidates == [] and not report.dropped

    def test_non_list_response(self) -> None:
        report = parse_response("509.1", SOURCE, {"target_rule": "702.9"})
        assert report.dropped["response_not_a_list"] == 1
