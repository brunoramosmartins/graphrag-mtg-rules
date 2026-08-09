#!/usr/bin/env python
"""Mechanical audit of the manual annotations — no LLM, no network, no cost.

A gold set is the measuring instrument, so it cannot be validated by the system
it measures: letting the extractor vote on the labels would make the gold agree
with the model and the resulting F1 would mean nothing. What *can* be checked
without touching that independence is internal consistency, and that is all this
script does. It never proposes a citation and never edits the draft.

Two severities, because they need different responses:

    error   objectively wrong regardless of judgement — a rule number absent
            from the CR, the same rule cited twice on one ruling, a whole
            chapter cited where a rule was meant. Fix before publishing.
    review  worth a second look, frequently a false alarm — most usefully, a
            citation sharing no vocabulary at all with the ruling it explains.
            That catches a mistyped rule number, but it also fires on a correct
            citation found by reading rather than searching, so read the pair
            before changing anything.

Findings print to stdout only. Nothing is written, and no CR text ever reaches
a file: the CR is not redistributable and the golden set must stay free of it.

    python scripts/audit_gold.py                  # audit reviewed rows
    python scripts/audit_gold.py --show-text      # include the text of each pair
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from graphrag_mtg.etl.cr_parser import CRDocument, parse_cr
from graphrag_mtg.extraction.cite_search import _folded_terms

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
CR_TXT = Path("data/raw/comprehensive_rules.txt")

_CHAPTER_ONLY = re.compile(r"^\d{3}$")

ERROR = "error"
REVIEW = "review"


@dataclass(frozen=True)
class Finding:
    """One thing worth a human's attention, on one ruling."""

    ruling_id: str
    rule_number: str
    check: str
    severity: str
    detail: str


def cited_numbers(row: dict) -> list[str]:
    """Rule numbers cited by ``row``, in order, tolerating the older key."""
    return [
        number
        for citation in row.get("cited_rules") or []
        if (number := citation.get("rule_number") or citation.get("rule"))
    ]


def audit_row(row: dict, doc: CRDocument) -> list[Finding]:
    """Return every finding for one annotated ruling."""
    findings: list[Finding] = []
    ruling_id = row.get("ruling_id", "?")
    numbers = cited_numbers(row)
    by_number = doc.by_number

    for number, count in Counter(numbers).items():
        if count > 1:
            findings.append(
                Finding(ruling_id, number, "duplicate", ERROR, f"cited {count} times")
            )

    ruling_terms = set(_folded_terms(row.get("text", "")))
    for number in dict.fromkeys(numbers):
        if _CHAPTER_ONLY.match(number):
            findings.append(
                Finding(ruling_id, number, "chapter-level", ERROR, "a whole chapter, not a rule")
            )
            continue
        rule = by_number.get(number)
        if rule is None:
            findings.append(
                Finding(ruling_id, number, "unresolvable", ERROR, "not in this CR version")
            )
            continue
        if ruling_terms and not (ruling_terms & set(_folded_terms(rule.text))):
            findings.append(
                Finding(
                    ruling_id,
                    number,
                    "no-shared-vocabulary",
                    REVIEW,
                    "no distinctive term in common with the ruling",
                )
            )
    return findings


def audit(rows: list[dict], doc: CRDocument) -> list[Finding]:
    """Audit every citation-reviewed row, errors first."""
    findings: list[Finding] = []
    for row in rows:
        if row.get("citations_reviewed"):
            findings.extend(audit_row(row, doc))
    return sorted(findings, key=lambda f: (f.severity != ERROR, f.check, f.ruling_id))


def summarise(rows: list[dict]) -> dict[str, object]:
    """Distribution facts that no single row reveals — shape, not correctness.

    A lazy default shows up as one rule carrying an implausible share of the
    citations; a stratum annotated to a different standard shows up as an
    outlying rate of uncited rulings.
    """
    reviewed = [r for r in rows if r.get("citations_reviewed")]
    numbers = [n for row in reviewed for n in cited_numbers(row)]
    counts = Counter(numbers)
    per_ruling = Counter(len(cited_numbers(row)) for row in reviewed)
    by_stratum: dict[str, tuple[int, int]] = {}
    for stratum in sorted({r.get("stratum", "?") for r in reviewed}):
        group = [r for r in reviewed if r.get("stratum") == stratum]
        by_stratum[stratum] = (sum(1 for r in group if not cited_numbers(r)), len(group))
    return {
        "reviewed": len(reviewed),
        "unreviewed": len(rows) - len(reviewed),
        "citations": len(numbers),
        "distinct_rules": len(counts),
        "cited_once": sum(1 for v in counts.values() if v == 1),
        "most_cited": counts.most_common(5),
        "per_ruling": dict(sorted(per_ruling.items())),
        "uncited_by_stratum": by_stratum,
    }


def report(findings: list[Finding], stats: dict, rows: list[dict], doc: CRDocument, *, show_text: bool) -> None:
    """Print the audit, distribution first so findings land in context."""
    print(f"{stats['reviewed']} reviewed rows, {stats['unreviewed']} not yet reviewed")
    print(f"{stats['citations']} citations over {stats['distinct_rules']} distinct rules "
          f"({stats['cited_once']} cited once)")
    print(f"citations per ruling: {stats['per_ruling']}")
    print("most cited:", ", ".join(f"{n} x{c}" for n, c in stats["most_cited"]))
    print("uncited rulings by stratum:")
    for stratum, (uncited, total) in stats["uncited_by_stratum"].items():
        share = uncited / total if total else 0.0
        print(f"  {stratum:<10} {uncited:>3}/{total:<4} ({share:.0%})")

    errors = [f for f in findings if f.severity == ERROR]
    reviews = [f for f in findings if f.severity == REVIEW]
    print(f"\n{len(errors)} error(s), {len(reviews)} to review")

    by_id = {r.get("ruling_id"): r for r in rows}
    for finding in findings:
        print(f"\n[{finding.severity}] {finding.check}: {finding.ruling_id} -> {finding.rule_number}")
        print(f"    {finding.detail}")
        if show_text:
            row = by_id.get(finding.ruling_id, {})
            print(textwrap.fill(row.get("text", ""), 76, initial_indent="    ruling: ",
                                subsequent_indent="            "))
            rule = doc.by_number.get(finding.rule_number)
            if rule is not None:
                print(textwrap.fill(rule.text, 76, initial_indent=f"    {finding.rule_number}: ",
                                    subsequent_indent="            "))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT)
    parser.add_argument("--show-text", action="store_true", help="print each flagged pair in full")
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.draft.open(encoding="utf-8") if line.strip()]
    doc = parse_cr(args.cr)
    findings = audit(rows, doc)
    report(findings, summarise(rows), rows, doc, show_text=args.show_text)

    errors = sum(1 for f in findings if f.severity == ERROR)
    if errors:
        print(f"\n{errors} error(s) must be fixed before --publish.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
