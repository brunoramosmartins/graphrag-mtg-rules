"""Thin LLM client for extraction: JSON in, JSON out, cost printed first.

Cost discipline (project rule): every script that loops an LLM over the
corpus supports ``--limit N`` and prints an estimated cost *before*
spending. The estimate here is deliberately crude (chars/4 ≈ tokens) and
says so — its job is to prevent a surprise invoice, not to bill clients.

The ``anthropic`` package is an optional dependency
(``pip install -e .[extraction]``); importing this module without it is
safe, constructing a client is not.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from graphrag_mtg.config import get_settings

# USD per million tokens (input, output). Prices drift — verify against
# https://docs.claude.com/en/docs/about-claude/pricing before a full-corpus
# run, or override on the CLI. These are ceilings for budgeting, not truth.
DEFAULT_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
}

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
        return (
            f"{self.n_calls:,} calls, ~{self.input_tokens:,} input + "
            f"~{self.output_tokens:,} output tokens ≈ ${self.usd:,.2f} "
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


class LlmClient:
    """Anthropic Messages wrapper that only speaks JSON.

    Args:
        model: Model id; defaults to ``Settings.llm_model``.
        max_tokens: Response cap per call.
    """

    def __init__(self, model: str | None = None, max_tokens: int = 1024) -> None:
        import anthropic  # optional dependency; fail here, not at import time

        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self.model = model or settings.llm_model
        self.max_tokens = max_tokens

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
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system or None,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            block = _JSON_BLOCK.search(text)
            if block is None:
                msg = f"no JSON in model response: {text[:200]!r}"
                raise ValueError(msg) from None
            return json.loads(block.group())
