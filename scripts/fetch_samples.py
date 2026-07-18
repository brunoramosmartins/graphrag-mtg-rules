#!/usr/bin/env python
"""Phase 0 licensing-gate helper: fetch a small sample from each source.

Confirms that the Gate-G1 URLs still resolve and the formats still match
(DoD: "manual download of a sample from each source worked"). Downloads a
handful of records only; it does NOT download bulk data. Nothing fetched
here is committed — outputs go to data/interim/samples/ (gitignored).

Usage:
    python scripts/fetch_samples.py            # all sources
    python scripts/fetch_samples.py --source scryfall
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

OUT_DIR = Path("data/interim/samples")
USER_AGENT = "graphrag-mtg-rules/0.1 (non-commercial fan project; +github.com/brunoramosmartins)"
TIMEOUT = 30.0

# Scryfall bulk INDEX (metadata only — not the multi-hundred-MB bulk file).
SCRYFALL_BULK_INDEX = "https://api.scryfall.com/bulk-data"
# A single well-known card, to confirm the card + rulings shape.
SCRYFALL_CARD = "https://api.scryfall.com/cards/named?exact=Lightning%20Bolt"


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def fetch_scryfall(out: Path) -> None:
    """Confirm the Scryfall bulk index and a single card + its rulings."""
    with _client() as client:
        index = client.get(SCRYFALL_BULK_INDEX).raise_for_status().json()
        (out / "scryfall_bulk_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
        types = [item.get("type") for item in index.get("data", [])]
        print(f"[scryfall] bulk index OK; available types: {types}")

        card = client.get(SCRYFALL_CARD).raise_for_status().json()
        (out / "scryfall_card_lightning_bolt.json").write_text(
            json.dumps(card, indent=2), encoding="utf-8"
        )
        rulings_uri = card.get("rulings_uri")
        print(f"[scryfall] card OK: {card.get('name')} ({card.get('oracle_id')})")
        if rulings_uri:
            rulings = client.get(rulings_uri).raise_for_status().json()
            (out / "scryfall_rulings_sample.json").write_text(
                json.dumps(rulings, indent=2), encoding="utf-8"
            )
            print(f"[scryfall] rulings OK: {len(rulings.get('data', []))} rulings fetched")


def fetch_comprehensive_rules(out: Path) -> None:
    """Confirm the CR landing page is reachable (the TXT link changes each release).

    We do NOT download or store the CR text (WotC copyright / Fan Content
    Policy). This only checks that the official rules page resolves, so the
    Phase 2 download script has a live starting point to confirm manually.
    """
    url = "https://magic.wizards.com/en/rules"
    with _client() as client:
        resp = client.get(url, headers={"Accept": "text/html"})
        (out / "cr_landing_status.txt").write_text(
            f"{url}\nHTTP {resp.status_code}\n", encoding="utf-8"
        )
        print(f"[comprehensive-rules] landing page {url} -> HTTP {resp.status_code} (text not stored)")


def fetch_rulesguru(out: Path) -> None:
    """Fetch ~10 RulesGuru questions to confirm the API shape (Gate G2 input).

    License + versioning are settled in docs/data-sources.md: eval-only,
    non-commercial, no model training; version question IDs + this fetch,
    never the question text. The API is a work in progress, so if the shape
    changes, reconfirm against docs/data-sources.md before Phase 1 curation.
    """
    url = "https://rulesguru.org/api/questions"  # no trailing slash — Express route is exact
    # The API is a GET with a percent-encoded JSON `settings` query param
    # (NOT a POST body). Schema per https://rulesguru.org/api/documentation/.
    # Rate-limited to one request / 2s, so `count` batches in a single call.
    # Keep the smoke filters permissive: an empty `legality` (or any filter
    # that matches nothing) makes the API answer 404 "not enough questions".
    # Omitting legality lets the server draw from the full pool.
    settings = {
        "count": 10,
        "level": ["0", "1", "2"],
        "complexity": ["Simple", "Intermediate", "Complicated"],
        "tags": [],
        "tagsConjunc": "OR",
        "rules": [],
        "rulesConjunc": "OR",
        "cards": [],
        "cardsConjunc": "OR",
    }
    try:
        with _client() as client:
            resp = client.get(url, params={"json": json.dumps(settings, separators=(",", ":"))})
            resp.raise_for_status()
            data = resp.json()
        (out / "rulesguru_sample.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[rulesguru] API OK; sample saved ({url})")
    except Exception as exc:  # endpoint may differ; report, don't crash the run
        (out / "rulesguru_error.txt").write_text(
            f"{url}\nfetch failed: {exc}\n"
            "The API is a work in progress; reconfirm the endpoint/shape "
            "against docs/data-sources.md before Phase 1 curation.\n",
            encoding="utf-8",
        )
        print(f"[rulesguru] could not fetch automatically ({exc}); see rulesguru_error.txt")


SOURCES = {
    "scryfall": fetch_scryfall,
    "comprehensive-rules": fetch_comprehensive_rules,
    "rulesguru": fetch_rulesguru,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), help="fetch only one source")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [args.source] if args.source else list(SOURCES)
    for name in targets:
        print(f"== {name} ==")
        SOURCES[name](OUT_DIR)
    print(f"\nSamples written to {OUT_DIR} (gitignored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
