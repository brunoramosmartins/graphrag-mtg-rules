#!/usr/bin/env python
"""Record a citation decision without hand-editing JSON.

You pick the rule(s) with `cite_search.py`; this writes them into the draft
in the canonical shape and marks the ruling citation-reviewed — no commas,
no key typos, and every rule number is checked against the CR before it is
saved, so a mistyped number fails here instead of at publish time.

    # cite one or more governing rules for a ruling
    python scripts/cite.py 3d4f42d9… 113.7a 603.10a

    # the ruling turns on no rule — reviewed, no citation
    python scripts/cite.py 3d4f42d9… --none

    # append to what is already cited instead of replacing
    python scripts/cite.py 3d4f42d9… 704.5 --add

By default the given rules *replace* the ruling's citations (the last call
wins); pass --add to append. `--annotator` sets the annotator field.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
CR_TXT = Path("data/raw/comprehensive_rules.txt")

_CR_RULE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s", re.MULTILINE)
_CR_CHAPTER = re.compile(r"^(\d{3})\.\s", re.MULTILINE)


def known_rules(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8-sig")
    return set(_CR_RULE.findall(text)) | set(_CR_CHAPTER.findall(text))


def apply_citation(
    rows: list[dict],
    ruling_id: str,
    rule_numbers: list[str],
    known: set[str],
    *,
    mark_none: bool = False,
    append: bool = False,
    annotator: str | None = None,
) -> str:
    """Record a citation decision on one draft row, in place.

    Returns a human-readable summary. Raises ``ValueError`` on an unknown
    ruling id or a rule number absent from the CR — the errors worth
    catching before they reach the gold.
    """
    row = next((r for r in rows if r["ruling_id"] == ruling_id), None)
    if row is None:
        msg = f"ruling {ruling_id!r} not in the draft"
        raise ValueError(msg)
    if not rule_numbers and not mark_none:
        msg = "give at least one rule number, or --none to review with no citation"
        raise ValueError(msg)

    unknown = [n for n in rule_numbers if n not in known]
    if unknown:
        msg = f"rule number(s) not in the CR: {unknown} — check with cite_search.py"
        raise ValueError(msg)

    existing = row.get("cited_rules", []) if append else []
    seen = {c.get("rule_number") or c.get("rule") for c in existing}
    for number in rule_numbers:
        if number not in seen:
            existing.append({"rule_number": number})
            seen.add(number)
    row["cited_rules"] = existing
    row["citations_reviewed"] = True
    if annotator:
        row["annotator"] = annotator

    cited = [c["rule_number"] for c in row["cited_rules"]]
    return f"{ruling_id}: cited_rules={cited or '[]'}, citations_reviewed=true"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruling_id", help="draft ruling id")
    parser.add_argument("rules", nargs="*", help="CR rule numbers, e.g. 113.7a 603.10a")
    parser.add_argument("--none", action="store_true", help="reviewed, turns on no rule")
    parser.add_argument("--add", action="store_true", help="append instead of replace")
    parser.add_argument("--annotator", type=str, default=None)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.draft.open(encoding="utf-8")]
    try:
        summary = apply_citation(
            rows,
            args.ruling_id,
            args.rules,
            known_rules(args.cr),
            mark_none=args.none,
            append=args.add,
            annotator=args.annotator,
        )
    except ValueError as err:
        print(f"error: {err}")
        return 1

    with args.draft.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
