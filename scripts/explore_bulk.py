#!/usr/bin/env python
"""Exploratory statistics over the downloaded corpus (Phase 1, issue #11).

Answers the questions the ontology depends on, from the real data rather
than assumption: how many cards and faces, which layouts actually occur,
how common keywords are, how rulings are distributed, and whether the CR
really is a clean numbered tree.

Run ``python -m graphrag_mtg.etl.download`` first. Nothing is written; this
only reads ``data/raw/`` and prints.

Usage:
    python scripts/explore_bulk.py
    python scripts/explore_bulk.py --section cards
    python scripts/explore_bulk.py --top 15
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

RAW = Path("data/raw")
ORACLE = RAW / "scryfall_oracle_cards.json"
RULINGS = RAW / "scryfall_rulings.json"
CR_TXT = RAW / "comprehensive_rules.txt"

SECTIONS = ("cards", "keywords", "legalities", "rulings", "cr")

# A CR line starts with a rule number: "613.7c" / "613.7" / "613." — the
# lettered form is the leaf the golden set cites most.
_CR_RULE = re.compile(r"^(\d{3})\.(\d+)([a-z])?\.?\s")


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _table(counter: Counter, top: int, total: int | None = None) -> None:
    width = max((len(str(k)) for k, _ in counter.most_common(top)), default=8)
    for key, count in counter.most_common(top):
        share = f"  {count / total:6.1%}" if total else ""
        print(f"  {key!s:<{width}}  {count:>7,}{share}")


def load_cards() -> list[dict]:
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def section_cards(cards: list[dict], top: int) -> None:
    _rule("Cards & layouts")
    total = len(cards)
    print(f"  oracle cards: {total:,}")

    layouts = Counter(c.get("layout", "?") for c in cards)
    multiface = sum(1 for c in cards if c.get("card_faces"))
    faces = sum(len(c.get("card_faces") or []) for c in cards)
    print(f"  multi-face cards: {multiface:,} ({multiface / total:.1%})  ->  {faces:,} faces")
    print(f"  distinct layouts: {len(layouts)}")
    _table(layouts, top, total)


def section_keywords(cards: list[dict], top: int) -> None:
    _rule("Keywords")
    counter = Counter(kw for c in cards for kw in c.get("keywords", []))
    with_kw = sum(1 for c in cards if c.get("keywords"))
    print(f"  distinct keywords: {len(counter):,}")
    print(f"  cards with >=1 keyword: {with_kw:,} ({with_kw / len(cards):.1%})")
    _table(counter, top)


def section_legalities(cards: list[dict], top: int) -> None:
    _rule("Legalities (Card -[:HAS_LEGALITY]-> Format)")
    formats = Counter()
    statuses = Counter()
    for card in cards:
        for fmt, status in (card.get("legalities") or {}).items():
            formats[fmt] += 1
            statuses[status] += 1
    print(f"  distinct formats: {len(formats)}")
    print(f"  legality edges if all loaded: {sum(formats.values()):,}")
    print("  by status:")
    _table(statuses, len(statuses), sum(statuses.values()))


def section_rulings(cards: list[dict], top: int) -> None:
    _rule("Rulings (Card -[:HAS_RULING]-> Ruling)")
    if not RULINGS.exists():
        print(f"  missing {RULINGS}; run: python -m graphrag_mtg.etl.download --source scryfall")
        return
    rulings = json.loads(RULINGS.read_text(encoding="utf-8"))
    per_card = Counter(r.get("oracle_id") for r in rulings if r.get("oracle_id"))
    names = {c.get("oracle_id"): c.get("name") for c in cards}
    covered = len(per_card)
    print(f"  rulings: {len(rulings):,}")
    print(f"  cards with >=1 ruling: {covered:,} ({covered / len(cards):.1%})")
    if per_card:
        print(f"  mean rulings per covered card: {len(rulings) / covered:.1f}")
        print("  most-ruled cards (the interaction-heavy ones):")
        for oracle_id, count in per_card.most_common(top):
            print(f"    {names.get(oracle_id, oracle_id):<34} {count:>4}")


def section_cr(top: int) -> None:
    _rule("Comprehensive Rules structure")
    if not CR_TXT.exists():
        print(f"  missing {CR_TXT}; set CR_TXT_URL and run the downloader.")
        return
    text = CR_TXT.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    numbered = [m for m in (_CR_RULE.match(ln) for ln in lines) if m]
    lettered = [m for m in numbered if m.group(3)]
    chapters = Counter(m.group(1)[0] for m in numbered)

    print(f"  lines: {len(lines):,}")
    print(f"  numbered rule lines: {len(numbered):,}  (lettered leaves: {len(lettered):,})")
    print("  by top-level chapter (1xx..9xx):")
    _table(chapters, 9, len(numbered))

    # The layer system is the spine of the interaction stratum - show it.
    print("\n  sample subtree - 613 (layer system), first lines:")
    for line in lines:
        match = _CR_RULE.match(line)
        if match and match.group(1) == "613":
            print(f"    {line.strip()[:96]}")
            if match.group(2) == "7" and match.group(3) == "c":
                break


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=SECTIONS, help="run a single section")
    parser.add_argument("--top", type=int, default=10, help="rows per ranked table")
    args = parser.parse_args()

    wanted = [args.section] if args.section else list(SECTIONS)
    needs_cards = any(s in wanted for s in ("cards", "keywords", "legalities", "rulings"))

    cards: list[dict] = []
    if needs_cards:
        if not ORACLE.exists():
            print(f"Missing {ORACLE}. Fetch it first:")
            print("  python -m graphrag_mtg.etl.download --source scryfall")
            return 1
        cards = load_cards()

    for name in wanted:
        if name == "cards":
            section_cards(cards, args.top)
        elif name == "keywords":
            section_keywords(cards, args.top)
        elif name == "legalities":
            section_legalities(cards, args.top)
        elif name == "rulings":
            section_rulings(cards, args.top)
        elif name == "cr":
            section_cr(args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
