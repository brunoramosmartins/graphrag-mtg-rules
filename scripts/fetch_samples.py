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

    RulesGuru's question endpoint may change; if this fails, record the
    manual steps in notes/ and confirm the content license (see
    docs/data-sources.md, the one open G1 item).
    """
    url = "https://rulesguru.org/api/questions/"
    payload = {
        "count": 10,
        "questionTags": [],
        "answerTags": [],
        "complexityLevels": ["Simple", "Intermediate", "Complicated"],
        "expansions": [],
        "playableCardsOnly": False,
        "rulesToInclude": [],
    }
    try:
        with _client() as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        (out / "rulesguru_sample.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[rulesguru] API OK; sample saved ({url})")
    except Exception as exc:  # endpoint may differ; report, don't crash the run
        (out / "rulesguru_error.txt").write_text(
            f"{url}\nfetch failed: {exc}\n"
            "Confirm the current API endpoint and the QUESTION-CONTENT LICENSE "
            "before Phase 1 (open G1 item; see docs/data-sources.md).\n",
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
