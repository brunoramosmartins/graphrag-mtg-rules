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
import time
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

#: Transport failures worth retrying: a rate limit, or a gateway between us
#: and the model. The `anthropic` SDK retries these itself; the httpx path
#: did not, and a 429 killed an E-002 pass 163 answers into a 500-question
#: run — the expensive kind of missing retry, because the spend is gone and
#: the file is a partial nobody may score.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Failures that never become a status code at all. A connection reset,
#: a read timeout, a DNS blip: the request dies in transport and there is
#: no response to inspect. Retrying only statuses looked complete and was
#: not — an E-001 embedding pass died at 16,640 of 115,547 documents on
#: `httpx.ReadError` (WinError 10054, the remote host closing the
#: connection), which the status-only loop passed straight through. The
#: lesson is the same one E-002's 429 taught, one layer lower down:
#: a long batched loop meets every transient failure the network has,
#: not only the ones the server was well enough to name.
RETRY_EXCEPTIONS = (httpx.TransportError,)

#: Attempts per call, the first one included.
MAX_ATTEMPTS = 5


def backoff(attempt: int) -> float:
    """Deterministic exponential backoff, capped at a minute.

    No jitter: a run that hits the same limits twice behaves the same way
    twice, which is what makes a re-run comparable.
    """
    return min(2.0**attempt, 60.0)


def retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying, from the server's advice or backoff.

    `Retry-After` is honoured when the provider sends one, because it knows
    when the window reopens and exponential backoff only guesses. Capped at
    a minute either way, and deterministic — no jitter, so a run that hits
    the same limits twice behaves the same way twice.
    """
    header = response.headers.get("Retry-After", "")
    if header.strip():
        try:
            return min(max(float(header), 0.0), 60.0)
        except ValueError:
            pass
    return backoff(attempt)

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

    def _post_chat(self, payload: dict[str, Any]) -> httpx.Response:
        """POST one completion, retrying the failures that are worth retrying.

        Raises:
            httpx.HTTPStatusError: on a non-retryable status, or after
                :data:`MAX_ATTEMPTS` attempts — a run that cannot get an
                answer must stop and say so, not silently record a gap.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http.post(OPENAI_CHAT_URL, json=payload)
            except RETRY_EXCEPTIONS as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                delay = backoff(attempt)
                print(f"  {type(exc).__name__} in transport; retrying in {delay:.0f}s")
                time.sleep(delay)
                continue
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                response.raise_for_status()
                return response
            delay = retry_delay(response, attempt)
            print(
                f"  {response.status_code} from the provider; "
                f"retrying in {delay:.0f}s ({attempt}/{MAX_ATTEMPTS - 1})"
            )
            time.sleep(delay)
        raise AssertionError("unreachable: the loop returns or raises")

    def complete_text(self, prompt: str, *, system: str = "") -> str:
        """Send one prompt and return the response text, unparsed.

        Phase 5 needs prose, not JSON: a grounded answer is written for a
        reader, and wrapping it in a JSON envelope would add a parse
        failure mode to a measurement about citations. Extraction keeps
        using :meth:`complete_json`, which now layers on top of this.
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
            response = self._post_chat(
                {
                    "model": self.model,
                    "max_completion_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "messages": messages,
                }
            )
            text = response.json()["choices"][0]["message"]["content"] or ""
        return text

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
        return _parse_json(self.complete_text(prompt, system=system))
