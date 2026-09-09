"""LLM client plumbing that needs no network: prices, estimates, parsing."""

from __future__ import annotations

import httpx
import pytest

from graphrag_mtg.extraction.llm import (
    DEFAULT_OPENAI_MODEL,
    RETRY_EXCEPTIONS,
    RETRY_STATUSES,
    _parse_json,
    backoff,
    estimate_cost,
    price_for_model,
    resolve_model,
    retry_delay,
)


class TestRetryExceptions:
    def test_a_connection_reset_is_retryable(self) -> None:
        # An E-001 embedding pass died at 16,640 of 115,547 documents on
        # httpx.ReadError — WinError 10054, the remote host closing the
        # connection. It never becomes a status code, so a loop inspecting
        # response.status_code passed it straight through.
        assert issubclass(httpx.ReadError, RETRY_EXCEPTIONS)

    def test_a_timeout_and_a_connect_failure_are_retryable(self) -> None:
        assert issubclass(httpx.ReadTimeout, RETRY_EXCEPTIONS)
        assert issubclass(httpx.ConnectError, RETRY_EXCEPTIONS)

    def test_a_bad_status_is_not_a_transport_failure(self) -> None:
        # The two paths stay separate: a 4xx that is not a rate limit must
        # fail immediately, not be retried five times.
        assert not issubclass(httpx.HTTPStatusError, RETRY_EXCEPTIONS)

    def test_backoff_is_exponential_and_capped(self) -> None:
        assert [backoff(i) for i in range(1, 5)] == [2.0, 4.0, 8.0, 16.0]
        assert backoff(99) == 60.0

    def test_backoff_has_no_jitter(self) -> None:
        # A run that hits the same limits twice must behave the same way
        # twice, or a re-run is not comparable.
        assert backoff(3) == backoff(3)


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


class TestRetryDelay:
    """A 429 killed an E-002 pass 163 answers into 500. The spend is gone."""

    def response(self, status: int = 429, **headers: str) -> httpx.Response:
        return httpx.Response(status, headers=headers)

    def test_a_rate_limit_is_retryable(self) -> None:
        assert 429 in RETRY_STATUSES
        assert 400 not in RETRY_STATUSES
        assert 401 not in RETRY_STATUSES

    def test_the_providers_own_advice_wins(self) -> None:
        """It knows when the window reopens; backoff only guesses."""
        assert retry_delay(self.response(**{"Retry-After": "7"}), 1) == 7.0

    def test_backoff_grows_without_advice(self) -> None:
        assert retry_delay(self.response(), 1) < retry_delay(self.response(), 3)

    def test_a_minute_is_the_ceiling(self) -> None:
        assert retry_delay(self.response(), 20) == 60.0
        assert retry_delay(self.response(**{"Retry-After": "3600"}), 1) == 60.0

    def test_an_unparseable_header_falls_back_to_backoff(self) -> None:
        assert retry_delay(self.response(**{"Retry-After": "soon"}), 2) == 4.0

    def test_a_negative_header_does_not_produce_a_negative_wait(self) -> None:
        assert retry_delay(self.response(**{"Retry-After": "-5"}), 1) == 0.0
