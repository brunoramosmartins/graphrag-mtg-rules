"""Thin, rate-limited client for the RulesGuru question API.

License: the questions are used **eval-only, non-commercial, no model
training**, and their text is never committed — only IDs plus this fetch
(see docs/data-sources.md). The API is a GET to ``/api/questions`` (no
trailing slash) with a percent-encoded ``json`` settings param; it is
rate-limited to one request per 2 seconds, enforced here.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

API_URL = "https://rulesguru.org/api/questions"
RATE_LIMIT_SECONDS = 2.5  # API allows one / 2s; add margin, measured request-end to next-start
USER_AGENT = "graphrag-mtg-rules/0.1 (non-commercial fan project; +github.com/brunoramosmartins)"
TIMEOUT = 30.0

_last_call_monotonic = 0.0


def client() -> httpx.Client:
    """Return an httpx client with the project User-Agent and redirects on."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def _respect_rate_limit() -> None:
    """Sleep so the gap since the previous call *completed* is >= the limit."""
    if _last_call_monotonic:
        elapsed = time.monotonic() - _last_call_monotonic
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)


def fetch(settings: dict[str, Any], *, http: httpx.Client | None = None) -> list[dict]:
    """Fetch questions for the given API ``settings`` (see docs/golden-set.md).

    Returns the list of question objects. Raises ``httpx.HTTPStatusError``
    on failure — note the API answers 404 ("not enough questions") when a
    filter matches nothing, so avoid over-constraining filters.
    """
    global _last_call_monotonic
    own = http is None
    http = http or client()
    try:
        _respect_rate_limit()
        resp = http.get(API_URL, params={"json": json.dumps(settings, separators=(",", ":"))})
        resp.raise_for_status()
        return resp.json()
    finally:
        _last_call_monotonic = time.monotonic()  # record completion, incl. after errors
        if own:
            http.close()


def fetch_by_id(question_id: int, *, http: httpx.Client | None = None) -> dict | None:
    """Fetch a single question by its RulesGuru id, or None if absent."""
    results = fetch({"id": question_id, "count": 1}, http=http)
    return results[0] if results else None
