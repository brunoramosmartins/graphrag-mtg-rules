#!/usr/bin/env python
"""Find candidate CR rules for a ruling — a lookup aid for the citation pass.

Ranks Comprehensive Rules by lexical overlap with a ruling and prints the
top candidates with their text, so the annotator reads ~10 rules instead of
grepping 3000. It surfaces candidates; **you read the rule and decide** — a
faster grep, not an answer key (see the module docstring for why this keeps
the gold independent).

Usage:
    python scripts/cite_search.py --ruling 891b32e1…      # by draft ruling id
    python scripts/cite_search.py --text "a spell whose only target is illegal"
    python scripts/cite_search.py --text "..." --k 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.extraction.cite_search import CiteSearch

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")


def ruling_text(draft: Path, ruling_id: str) -> str | None:
    with draft.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["ruling_id"] == ruling_id:
                return row["text"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cr", type=Path, default=Path("data/raw/comprehensive_rules.txt"))
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--ruling", type=str, default=None, help="draft ruling id")
    parser.add_argument("--text", type=str, default=None, help="free-text query")
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()

    if args.ruling:
        text = ruling_text(args.draft, args.ruling)
        if text is None:
            print(f"ruling {args.ruling} not found in {args.draft}")
            return 1
    elif args.text:
        text = args.text
    else:
        print("Pass --ruling <id> or --text \"...\".")
        return 1

    print(f"Query: {text}\n")
    index = CiteSearch(parse_cr(args.cr))
    hits = index.search(text, k=args.k)
    if not hits:
        print("No lexical candidates — grep the CR by the interaction's key term.")
        return 0
    for hit in hits:
        print(f"  {hit.number:<10} (score {hit.score:5.1f})  {hit.snippet}")
    print("\nRead the rules above; cite the one that GOVERNS the ruling, or none.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
