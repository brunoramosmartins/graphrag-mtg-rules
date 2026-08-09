"""Thin LLM client for extraction: JSON in, JSON out, cost printed first.

Two providers behind one interface, chosen by ``LLM_PROVIDER``:

- ``anthropic`` (default, ADR-003) — the ``anthropic`` package
  (``pip install -e .[extraction]``).
- ``openai`` — plain ``httpx`` against the Chat Completions API; no extra
  dependency. A pragmatic alternative when Anthropic credits are not at
  hand — the extraction prompts and the gate are provider-agnostic, and
  every candidate records which model produced it downstream anyway
  (``extractor_version`` + the run log).

Cost discipline (project rule): every script that loops an LLM over the
corpus supports ``--limit N`` and prints an estimated cost *before*
spending. The estimate here is deliberately crude (chars/4 ≈ tokens) and
says so — its job is to prevent a surprise invoice, not to bill clients.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from graphrag_mtg.config import get_settings

# USD per million tokens (input, output). Prices drift — verify against the
# provider's pricing page before a full-corpus run. Longer prefixes first so
# "gpt-4o-mini" never matches the "gpt-4o" row. Budget ceilings, not truth.
DEFAULT_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.0, 8.0),
}

# Sensible model when the provider is switched but LLM_MODEL still holds the
# other provider's default.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def estimate_tokens(text: str) -> int:
    """Crude token estimate (~4 chars/token for English prose)."""
    return max(1, len(text) // 4)


def price_for_model(model: str) -> tuple[float, float]:
    """Return (input, output) USD/MTok for the closest known model family."""
    for prefix, prices in DEFAULT_PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return prices
    # Unknown family: budget at the most expensive known tier.
    return DEFAULT_PRICES_PER_MTOK["claude-opus"]


@dataclass(frozen=True)
class CostEstimate:
    """Pre-run budget for a batch of prompts."""

    n_calls: int
    input_tokens: int
    output_tokens: int
    usd: float

    def __str__(self) -> str:
        # ASCII only: this string hits consoles that cannot encode "≈" (cp1252).
        return (
            f"{self.n_calls:,} calls, ~{self.input_tokens:,} input + "
            f"~{self.output_tokens:,} output tokens = ~${self.usd:,.2f} "
            "(chars/4 heuristic; verify current pricing before a full run)"
        )


def estimate_cost(
    prompts: Iterable[str],
    *,
    model: str,
    output_tokens_per_call: int = 300,
    system: str = "",
) -> CostEstimate:
    """Estimate the cost of one call per prompt, before making any."""
    price_in, price_out = price_for_model(model)
    system_tokens = estimate_tokens(system) if system else 0
    n_calls = 0
    input_tokens = 0
    for prompt in prompts:
        n_calls += 1
        input_tokens += estimate_tokens(prompt) + system_tokens
    output_tokens = n_calls * output_tokens_per_call
    usd = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return CostEstimate(n_calls, input_tokens, output_tokens, usd)


def _parse_json(text: str) -> Any:
    """Parse a model response as JSON, tolerating prose around the block.

    Raises:
        ValueError: if the response contains no valid JSON.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        block = _JSON_BLOCK.search(text)
        if block is None:
            msg = f"no JSON in model response: {text[:200]!r}"
            raise ValueError(msg) from None
        return json.loads(block.group())


def resolve_model(provider: str, model: str) -> str:
    """Pick the model for a provider, fixing a cross-provider default.

    ``LLM_MODEL`` defaults to a Claude id; if the provider was switched to
    OpenAI without changing it, fall back to :data:`DEFAULT_OPENAI_MODEL`
    instead of sending a Claude id to the wrong API.
    """
    if provider == "openai" and model.startswith("claude"):
        return DEFAULT_OPENAI_MODEL
    return model


class LlmClient:
    """Provider-agnostic completion client that only speaks JSON.

    Args:
        model: Model id; defaults to ``Settings.llm_model`` (mapped through
            :func:`resolve_model` for the active provider).
        max_tokens: Response cap per call.

    Raises:
        RuntimeError: if the active provider has no API key configured, or
            ``LLM_PROVIDER`` names an unknown provider.
    """

    def __init__(
        self, model: str | None = None, max_tokens: int = 1024, temperature: float = 0.0
    ) -> None:
        settings = get_settings()
        self.provider = settings.llm_provider.lower()
        self.max_tokens = max_tokens
        # Pinned to 0 by default. Left unset, both providers sample at their
        # own default and two runs of the *same* configuration disagree: on the
        # E-003 dev subset the identical prompt scored 0.167 and then 0.114,
        # a spread as large as the differences between prompt iterations. An
        # experiment cannot attribute a change it cannot reproduce.
        self.temperature = temperature
        self.model = resolve_model(self.provider, model or settings.llm_model)

        if self.provider == "anthropic":
            if not settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
                msg = (
                    "No Anthropic API key configured. Set ANTHROPIC_API_KEY in .env "
                    "(see .env.example) — never on the command line."
                )
                raise RuntimeError(msg)
            import anthropic  # optional dependency; fail here, not at import time

            self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        elif self.provider == "openai":
            key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                msg = (
                    "No OpenAI API key configured. Set OPENAI_API_KEY in .env "
                    "(see .env.example) — never on the command line."
                )
                raise RuntimeError(msg)
            self._http = httpx.Client(
                headers={"Authorization": f"Bearer {key}"}, timeout=httpx.Timeout(120.0)
            )
        else:
            msg = f"unknown LLM_PROVIDER {self.provider!r} (expected 'anthropic' or 'openai')"
            raise RuntimeError(msg)

    def complete_json(self, prompt: str, *, system: str = "") -> Any:
        """Send one prompt and parse the response as JSON.

        The extraction prompts all demand a bare JSON object/array; models
        occasionally wrap it in prose, so the first JSON-looking block is
        parsed. A response with no parseable JSON raises ``ValueError`` —
        callers count it as a failed extraction rather than retrying
        forever (prompt iteration happens against the fixed dev sample).

        Raises:
            ValueError: if the response contains no valid JSON.
        """
        if self.provider == "anthropic":
            message = self._anthropic.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system or None,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(block.text for block in message.content if block.type == "text")
        else:
            messages = [{"role": "system", "content": system}] if system else []
            messages.append({"role": "user", "content": prompt})
            response = self._http.post(
                OPENAI_CHAT_URL,
                json={
                    "model": self.model,
                    "max_completion_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "messages": messages,
                },
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"] or ""
        return _parse_json(text)
