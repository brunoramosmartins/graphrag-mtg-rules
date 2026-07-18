#!/usr/bin/env python
"""Generate ``legality_1hop`` golden questions from Scryfall oracle data.

Reads ``data/raw/scryfall_oracle_cards.json`` (fetch it first with
``python -m graphrag_mtg.etl.download --source scryfall``) and appends a
status-diverse batch of legality questions to ``data/golden/ids_v0.jsonl``.
The answer key is the card's ``legalities`` field, so these rows are our
own content and auto-verified. Existing rows are preserved.

Usage:
    python scripts/generate_legality_questions.py --count 20
    python scripts/generate_legality_questions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from graphrag_mtg.evaluation.generators import build_legality_question
from graphrag_mtg.evaluation.golden import GoldenQuestion, dump_golden, load_golden

ORACLE_PATH = Path("data/raw/scryfall_oracle_cards.json")
OUT_PATH = Path("data/golden/ids_v0.jsonl")
DEFAULT_FORMATS = ["standard", "modern", "legacy", "pioneer", "commander", "pauper", "vintage"]

# Non-playable layouts to skip (tokens, emblems, and other non-deck objects).
_SKIP_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series", "vanguard", "scheme", "planar"}

# Target mix so the batch is not all "legal"; banned/restricted are the
# interesting minority. Fractions of --count; capped by what actually exists.
_STATUS_MIX = {"legal": 0.40, "banned": 0.25, "not_legal": 0.20, "restricted": 0.15}


def _is_playable(card: dict) -> bool:
    if card.get("layout") in _SKIP_LAYOUTS or "Token" in card.get("type_line", ""):
        return False
    return bool(card.get("oracle_id") and card.get("legalities") and card.get("name"))


def _bucket_candidates(cards: list[dict], formats: list[str]) -> dict[str, list[tuple[dict, str]]]:
    """Group ``(card, format)`` pairs by their legality status."""
    buckets: dict[str, list[tuple[dict, str]]] = {s: [] for s in _STATUS_MIX}
    for card in cards:
        if not _is_playable(card):
            continue
        legalities = card["legalities"]
        for fmt in formats:
            status = legalities.get(fmt)
            if status in buckets:
                buckets[status].append((card, fmt))
    return buckets


def _sample(buckets: dict[str, list[tuple[dict, str]]], count: int, rng: random.Random) -> list[tuple[dict, str]]:
    """Draw a status-diverse sample, falling back to fill from any bucket."""
    selected: list[tuple[dict, str]] = []
    for status, frac in _STATUS_MIX.items():
        pool = buckets[status][:]
        rng.shuffle(pool)
        selected.extend(pool[: round(count * frac)])
    # Top up (or trim) to exactly `count` from the remaining pool.
    if len(selected) < count:
        chosen = {id(x) for x in selected}
        leftovers = [x for pool in buckets.values() for x in pool if id(x) not in chosen]
        rng.shuffle(leftovers)
        selected.extend(leftovers[: count - len(selected)])
    return selected[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20, help="legality questions to generate")
    parser.add_argument("--formats", nargs="+", default=DEFAULT_FORMATS)
    parser.add_argument("--seed", type=int, default=17, help="seed for reproducible sampling")
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--oracle", type=Path, default=ORACLE_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    if not args.oracle.exists():
        print(f"Missing {args.oracle}. Fetch it first:")
        print("  python -m graphrag_mtg.etl.download --source scryfall")
        return 1

    cards = json.loads(args.oracle.read_text(encoding="utf-8"))
    print(f"Loaded {len(cards):,} oracle cards")

    buckets = _bucket_candidates(cards, args.formats)
    print("candidates by status: " + ", ".join(f"{s}={len(v):,}" for s, v in buckets.items()))

    existing = load_golden(args.out) if args.out.exists() else []
    known_ids = {q.id for q in existing}

    rng = random.Random(args.seed)
    added: list[GoldenQuestion] = []
    for card, fmt in _sample(buckets, args.count, rng):
        q = build_legality_question(card, fmt)
        if q is None or q.id in known_ids:
            continue
        known_ids.add(q.id)
        added.append(q)

    print(f"Generated {len(added)} new legality question(s)")
    if args.dry_run:
        for q in added[:5]:
            print(f"  {q.id}: {q.question} -> {q.answer}")
        print("Dry run: wrote nothing.")
        return 0

    dump_golden(existing + added, args.out)
    print(f"Wrote {len(existing) + len(added)} row(s) to {args.out} (+{len(added)} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
