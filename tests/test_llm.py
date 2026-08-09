"""LLM client plumbing that needs no network: prices, estimates, parsing."""

from __future__ import annotations

import pytest

from graphrag_mtg.extraction.llm import (
    DEFAULT_OPENAI_MODEL,
    _parse_json,
    estimate_cost,
    price_for_model,
    resolve_model,
)


class TestPrices:
    def test_longest_prefix_wins(self) -> None:
        # gpt-4o-mini must not be priced as gpt-4o.
        assert price_for_model("gpt-4o-mini-2024") != price_for_model("gpt-4o-2024")

    def test_unknown_model_budgets_at_the_most_expensive_tier(self) -> None:
        assert price_for_model("some-future-model") == price_for_model("claude-opus-4-8")


class TestEstimate:
    def test_counts_calls_and_scales_with_text(self) -> None:
        short = estimate_cost(["hi"], model="gpt-4o-mini")
        longer = estimate_cost(["hi" * 500, "there" * 500], model="gpt-4o-mini")
        assert short.n_calls == 1
        assert longer.n_calls == 2
        assert longer.usd > short.usd > 0


class TestResolveModel:
    def test_claude_default_maps_to_openai_default(self) -> None:
        assert resolve_model("openai", "claude-opus-4-8") == DEFAULT_OPENAI_MODEL

    def test_explicit_models_pass_through(self) -> None:
        assert resolve_model("openai", "gpt-4o") == "gpt-4o"
        assert resolve_model("anthropic", "claude-opus-4-8") == "claude-opus-4-8"


class TestParseJson:
    def test_bare_json(self) -> None:
        assert _parse_json('[{"a": 1}]') == [{"a": 1}]

    def test_json_wrapped_in_prose(self) -> None:
        assert _parse_json('Sure! Here it is: [{"a": 1}]') == [{"a": 1}]

    def test_no_json_raises(self) -> None:
        with pytest.raises(ValueError, match="no JSON"):
            _parse_json("I cannot answer that.")
