#!/usr/bin/env python
"""Migrate manual citations from one Comprehensive Rules version to another.

The CR is living documentation: WotC ships a new version every set. Rule
numbers are *mostly* stable, but not reliably so — between the 2026-02-27 and
2026-08-07 releases, the `initiative` rules moved 725.x to 726.x to make room
for `monarch`, and 704.5w/310.10 each shifted by one. A citation that still
resolves is not the same as a citation that still means what the annotator
chose, and that is the failure this script exists to catch.

The migration is therefore **anchored on rule text, not on rule numbers**. The
annotator picked a rule by what it says; this relocates that choice to wherever
the same text now lives. Each cited number gets one verdict:

    unchanged   same number, same text (up to whitespace)  -> nothing to do
    edited      same number, text changed, no better match -> human reads the diff
    relocated   the old text now lives at another number   -> remap, content-anchored
    orphaned    the text is gone from the new CR           -> human re-decides

Only `relocated` is applied automatically, and only above a similarity floor;
`edited` and `orphaned` are reported for the annotator to judge, never guessed.

    # report only (default) — writes nothing
    python scripts/cr_migrate.py --new path/to/MagicCompRules-20260807.txt

    # show the word-level diff of every rule whose text changed
    python scripts/cr_migrate.py --new <path> --show-diffs

    # apply relocations and stamp the CR version on every row
    python scripts/cr_migrate.py --new <path> --apply

`--apply` rewrites the draft in place: it remaps relocated numbers inside
`cited_rules` and sets `cr_version` on every row, so the next migration knows
which CR the labels were authored against.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_mtg.etl.cr_parser import parse_cr

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
CR_TXT = Path("data/raw/comprehensive_rules.txt")

#: A cited number that is three digits alone refers to a whole chapter, which
#: has a heading but no body text of its own.
_CHAPTER_ONLY = re.compile(r"^\d{3}$")

#: Relocation is only proposed when the old text is essentially intact at its
#: new home, and clearly better matched there than at the number it used to
#: occupy. Both floors are deliberately strict: a wrong remap is worse than an
#: item on the human's review queue.
RELOCATION_FLOOR = 0.90
RELOCATION_MARGIN = 0.15

#: How far to look for a relocated rule, in chapters. CR reshuffles displace
#: rules by one or two chapters (725 -> 726), never across the document.
CHAPTER_WINDOW = 2


def normalize(text: str) -> str:
    """Collapse whitespace so formatting churn is not read as a text change.

    The 2026-08-07 CR replaced empty separator lines with lines holding a
    single non-breaking space, and uses U+00A0 inside two rule bodies. Without
    this, every such rule would be reported as edited.
    """
    return " ".join(text.replace(" ", " ").split())


def rule_bodies(path: Path) -> dict[str, str]:
    """Return ``{rule_number: normalized text}`` for one CR file."""
    document = parse_cr(path)
    return {rule.number: normalize(rule.text) for rule in document.rules}


def chapters_of(bodies: dict[str, str]) -> set[str]:
    """Return the set of chapter numbers (``"704"``) present in ``bodies``."""
    return {number.split(".", 1)[0] for number in bodies}


def _candidates(number: str, new: dict[str, str]) -> list[str]:
    """Rule numbers in ``new`` worth comparing against ``number``'s old text."""
    try:
        chapter = int(number.split(".", 1)[0])
    except ValueError:
        return list(new)
    window = range(chapter - CHAPTER_WINDOW, chapter + CHAPTER_WINDOW + 1)
    prefixes = tuple(f"{c}." for c in window)
    return [n for n in new if n.startswith(prefixes)]


@dataclass
class Verdict:
    """What became of one cited rule number in the new CR."""

    number: str
    status: str
    ruling_ids: list[str] = field(default_factory=list)
    new_number: str | None = None
    similarity: float | None = None
    old_text: str = ""
    new_text: str = ""

    @property
    def needs_human(self) -> bool:
        return self.status in {"edited", "orphaned"}


def judge(number: str, old: dict[str, str], new: dict[str, str]) -> Verdict:
    """Decide what happened to one cited rule number between two CR versions."""
    if _CHAPTER_ONLY.match(number):
        status = "unchanged" if number in chapters_of(new) else "orphaned"
        return Verdict(number=number, status=status)

    old_text = old.get(number, "")
    if not old_text:
        # Cited against a CR we no longer hold; nothing to anchor on.
        return Verdict(number=number, status="orphaned")

    same_ratio = 0.0
    if number in new:
        if new[number] == old_text:
            return Verdict(number=number, status="unchanged", old_text=old_text)
        same_ratio = difflib.SequenceMatcher(None, old_text, new[number]).ratio()

    best_number, best_ratio = None, 0.0
    for candidate in _candidates(number, new):
        if candidate == number:
            continue
        ratio = difflib.SequenceMatcher(None, old_text, new[candidate]).ratio()
        if ratio > best_ratio:
            best_number, best_ratio = candidate, ratio

    relocated = (
        best_number is not None
        and best_ratio >= RELOCATION_FLOOR
        and best_ratio >= same_ratio + RELOCATION_MARGIN
    )
    if relocated:
        return Verdict(
            number=number,
            status="relocated",
            new_number=best_number,
            similarity=best_ratio,
            old_text=old_text,
            new_text=new[best_number],
        )
    if number in new:
        return Verdict(
            number=number,
            status="edited",
            similarity=same_ratio,
            old_text=old_text,
            new_text=new[number],
        )
    return Verdict(number=number, status="orphaned", old_text=old_text)


def plan_migration(rows: list[dict], old: dict[str, str], new: dict[str, str]) -> list[Verdict]:
    """Judge every rule number cited anywhere in ``rows``, most severe first."""
    users: dict[str, list[str]] = {}
    for row in rows:
        for citation in row.get("cited_rules") or []:
            number = citation.get("rule_number") or citation.get("rule")
            if number:
                users.setdefault(number, []).append(row["ruling_id"])

    verdicts = []
    for number in sorted(users):
        verdict = judge(number, old, new)
        verdict.ruling_ids = users[number]
        verdicts.append(verdict)

    order = {"orphaned": 0, "edited": 1, "relocated": 2, "unchanged": 3}
    return sorted(verdicts, key=lambda v: (order[v.status], v.number))


def apply_plan(rows: list[dict], verdicts: list[Verdict], cr_version: str) -> list[str]:
    """Remap relocated citations in place and stamp ``cr_version`` on each row.

    Rows keep their annotator's decision: only the *number* moves, because the
    text the annotator chose moved. Returns a line per change, for the log.
    """
    remap = {v.number: v.new_number for v in verdicts if v.status == "relocated" and v.new_number}
    changes = []
    for row in rows:
        row["cr_version"] = cr_version
        for citation in row.get("cited_rules") or []:
            number = citation.get("rule_number") or citation.get("rule")
            if number in remap:
                citation["rule_number"] = remap[number]
                citation["migrated_from"] = number
                changes.append(f"{row['ruling_id']}: {number} -> {remap[number]}")
    return changes


def word_diff(old_text: str, new_text: str, context: int = 3) -> str:
    """Render a compact word-level diff, eliding long unchanged runs."""
    before, after = old_text.split(), new_text.split()
    matcher = difflib.SequenceMatcher(None, before, after)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            run = before[i1:i2]
            if len(run) <= context * 2:
                parts.append(" ".join(run))
            else:
                head, tail = " ".join(run[:context]), " ".join(run[-context:])
                parts.append(f"{head} […] {tail}")
        else:
            if tag in {"delete", "replace"}:
                parts.append("[-" + " ".join(before[i1:i2]) + "-]")
            if tag in {"insert", "replace"}:
                parts.append("[+" + " ".join(after[j1:j2]) + "+]")
    return " ".join(parts)


def report(verdicts: list[Verdict], *, show_diffs: bool) -> None:
    """Print the migration plan, severest first."""
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
    total = len(verdicts)
    summary = "  ".join(f"{status}={counts[status]}" for status in sorted(counts))
    print(f"{total} cited rule numbers: {summary}\n")

    for verdict in verdicts:
        if verdict.status == "unchanged":
            continue
        rulings = len(verdict.ruling_ids)
        head = f"[{verdict.status}] {verdict.number}"
        if verdict.new_number:
            head += f" -> {verdict.new_number}"
        if verdict.similarity is not None:
            head += f"  (similarity {verdict.similarity:.3f})"
        print(f"{head}  — {rulings} ruling(s)")
        if show_diffs and verdict.old_text and verdict.new_text:
            print(f"    {word_diff(verdict.old_text, verdict.new_text)}")
        elif verdict.status == "orphaned":
            print(f"    was: {verdict.old_text[:160]}")
        for ruling_id in verdict.ruling_ids:
            print(f"    ruling {ruling_id}")
        print()

    needs = [v for v in verdicts if v.needs_human]
    if needs:
        print(f"{len(needs)} rule number(s) need a human decision — --apply will not touch them.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new", type=Path, required=True, help="the newer CR .txt")
    parser.add_argument("--old", type=Path, default=CR_TXT, help="the CR the labels were authored against")
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--show-diffs", action="store_true", help="print word-level diffs")
    parser.add_argument("--apply", action="store_true", help="rewrite the draft in place")
    args = parser.parse_args()

    old_bodies = rule_bodies(args.old)
    new_document = parse_cr(args.new)
    new_bodies = {rule.number: normalize(rule.text) for rule in new_document.rules}
    cr_version = new_document.effective_date or args.new.name

    print(f"old CR: {args.old}  ({len(old_bodies)} rules)")
    print(f"new CR: {args.new}  ({len(new_bodies)} rules, effective {cr_version})\n")

    rows = [json.loads(line) for line in args.draft.open(encoding="utf-8") if line.strip()]
    verdicts = plan_migration(rows, old_bodies, new_bodies)
    report(verdicts, show_diffs=args.show_diffs)

    if not args.apply:
        print("\ndry run — nothing written. Re-run with --apply to migrate.")
        return 0

    changes = apply_plan(rows, verdicts, cr_version)
    with args.draft.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\napplied {len(changes)} citation remap(s); cr_version={cr_version!r} on {len(rows)} rows")
    for change in changes:
        print(f"  {change}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
