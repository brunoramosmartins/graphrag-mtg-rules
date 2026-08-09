#!/usr/bin/env python
"""Normalize cited_rules in the annotation draft to the canonical shape.

Rewrites each cited rule to ``{"rule_number": <n>}`` (keeping an optional
ruling ``quote`` + offsets if present): accepts the legacy ``rule`` key and
**drops any ``text`` field**, which must never reach the public golden file
(Comprehensive Rules text is not committed — IP rule). Idempotent; only
touches ``cited_rules``, never mentions or verification flags.

Usage:
    python scripts/normalize_citations.py            # report only
    python scripts/normalize_citations.py --write     # rewrite the draft
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")


def normalize_citation(c: dict) -> dict:
    """Canonical cited-rule dict: number (+ optional ruling quote), no CR text."""
    out: dict = {"rule_number": c.get("rule_number") or c.get("rule")}
    if c.get("quote") and "start" in c and "end" in c:
        out.update({"start": c["start"], "end": c["end"], "quote": c["quote"]})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--write", action="store_true", help="rewrite the draft in place")
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.draft.open(encoding="utf-8")]
    changed = dropped_text = 0
    for row in rows:
        new = []
        for c in row.get("cited_rules", []):
            if "text" in c:
                dropped_text += 1
            canonical = normalize_citation(c)
            if canonical != c:
                changed += 1
            new.append(canonical)
        row["cited_rules"] = new

    print(f"{changed} cited-rule entries need rewriting ({dropped_text} CR-text fields dropped).")
    if not args.write:
        print("Report only — pass --write to rewrite the draft.")
        return 0

    with args.draft.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Rewrote {args.draft}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
