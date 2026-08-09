#!/usr/bin/env python
"""Validate the annotation draft and publish verified rows to the golden file.

Reads ``data/interim/extraction_annotations_draft.jsonl``, checks every row
marked ``verified: true``, and writes the license-safe subset (no ruling
text) to ``data/golden/extraction_annotations.jsonl``, sorted by ruling_id
for stable diffs. Rows that fail any check block publication — fix them or
un-verify them.

Checks per verified row:

- every mention offset round-trips: ``text[start:end] == surface``;
- no mention still carries the ``UNDECIDED`` sentinel (each homonym got an
  explicit oracle_id-or-null decision);
- every cited rule number exists in the downloaded CR;
- every citation span round-trips against the text when a quote is given.

Usage:
    python scripts/check_extraction_annotations.py           # report only
    python scripts/check_extraction_annotations.py --publish # also write golden
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
GOLDEN_PATH = Path("data/golden/extraction_annotations.jsonl")
CR_TXT = Path("data/raw/comprehensive_rules.txt")

UNDECIDED = "UNDECIDED"

# Same pattern as scripts/check_cr_citations.py (kept in sync by eye — both
# read the CR as UTF-8 with BOM and match "613.4b " / "510.4. " rule lines).
_CR_RULE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s", re.MULTILINE)


def known_rules(path: Path = CR_TXT) -> set[str]:
    """Every rule number defined in the Comprehensive Rules text."""
    text = path.read_text(encoding="utf-8-sig")
    return {match.group(1) for match in _CR_RULE.finditer(text)}


def row_errors(row: dict, rules: set[str]) -> list[str]:
    """All validation failures for one verified row."""
    errors: list[str] = []
    text = row.get("text", "")
    for m in row.get("mentions", []):
        if m.get("target_oracle_id") == UNDECIDED:
            errors.append(f"mention {m['surface']!r} at {m['start']} still UNDECIDED")
        if text[m["start"] : m["end"]] != m["surface"]:
            errors.append(f"mention offsets broken for {m['surface']!r} at {m['start']}")
    for c in row.get("cited_rules", []):
        number = cited_number(c)
        if number is None:
            errors.append("a cited rule has no 'rule_number'")
            continue
        if number not in rules:
            errors.append(f"cited rule {number} not in the CR")
        # IP guard: a cited rule must not carry Comprehensive Rules text.
        # The gold needs only the number; a short verbatim quote must come
        # from the RULING, never the CR (see the annotation guide).
        if "text" in c:
            errors.append(f"cited rule {number} carries a 'text' field — drop it (CR text is not committed)")
        quote = c.get("quote")
        if quote and "start" in c and "end" in c and text[c["start"] : c["end"]] != quote:
            errors.append(f"citation offsets broken for rule {number}")
    return errors


def cited_number(c: dict) -> str | None:
    """Rule number from a cited-rule dict, accepting 'rule_number' or 'rule'."""
    return c.get("rule_number") or c.get("rule")


def _golden_citation(c: dict) -> dict:
    """Committed shape of a cited rule: the number, plus a *ruling* quote if given.

    Never carries the rule's CR text — the golden file is public and CR
    text is not committed (IP rule). The evaluation keys on the number
    alone; the optional quote is provenance from the ruling.
    """
    out: dict = {"rule_number": cited_number(c)}
    if c.get("quote") and "start" in c and "end" in c:
        out.update({"start": c["start"], "end": c["end"], "quote": c["quote"]})
    return out


def golden_row(row: dict) -> dict:
    """The committed shape: ids, offsets, decisions — no ruling or CR text."""
    return {
        "ruling_id": row["ruling_id"],
        "split": row["split"],
        "stratum": row["stratum"],
        "oracle_id": row.get("oracle_id"),
        "mentions": [
            {k: m[k] for k in ("surface", "start", "end", "target_oracle_id")}
            for m in row.get("mentions", [])
        ],
        "cited_rules": [_golden_citation(c) for c in row.get("cited_rules", [])],
        # Without this flag an empty `cited_rules` is ambiguous: it could mean
        # "the annotator read this ruling and no rule governs it" or "nobody has
        # looked yet". Scoring the second as gold would turn every citation the
        # extractor produces there into a false positive.
        "citations_reviewed": bool(row.get("citations_reviewed")),
        "notes": row.get("notes", ""),
        "annotator": row.get("annotator", ""),
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT)
    parser.add_argument("--publish", action="store_true", help="write the golden file")
    args = parser.parse_args()

    rules = known_rules(args.cr)
    verified: list[dict] = []
    pending = failed = 0
    with args.draft.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if not row.get("verified"):
                pending += 1
                continue
            errors = row_errors(row, rules)
            if errors:
                failed += 1
                print(f"{row['ruling_id']}:")
                for error in errors:
                    print(f"  - {error}")
                continue
            verified.append(row)

    n_mentions = sum(len(r["mentions"]) for r in verified)
    n_citations = sum(len(r["cited_rules"]) for r in verified)
    print(
        f"{len(verified)} verified ok ({n_mentions} mentions, {n_citations} citations), "
        f"{failed} verified-but-broken, {pending} not yet verified."
    )
    if failed:
        return 1
    if not args.publish:
        print("Report only — pass --publish to write the golden file.")
        return 0
    if not verified:
        print("Nothing verified yet — refusing to publish an empty golden file.")
        return 1

    verified.sort(key=lambda r: r["ruling_id"])
    with GOLDEN_PATH.open("w", encoding="utf-8") as out:
        for row in verified:
            out.write(json.dumps(golden_row(row), ensure_ascii=False) + "\n")
    print(f"Published {len(verified)} rows -> {GOLDEN_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
