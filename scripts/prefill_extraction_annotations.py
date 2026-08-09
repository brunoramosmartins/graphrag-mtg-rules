#!/usr/bin/env python
"""Pre-fill the extraction annotation draft with deterministic seeds.

Turns ``data/interim/extraction_annotation_todo.jsonl`` (the frozen sample
with text) into ``data/interim/extraction_annotations_draft.jsonl``, one
editable row per ruling:

- **mentions** are seeded from the deterministic linker: exact/loose
  matches arrive with ``target_oracle_id`` filled and ``seed`` naming the
  stage; single-word homonym candidates arrive with the sentinel
  ``"target_oracle_id": "UNDECIDED"`` — every one demands an explicit
  human decision (a real oracle_id, or ``null`` for "ordinary English").
- **cited_rules** is always empty. Deliberately: rule citations are what
  the LLM extractor will be scored on, so seeding them from any model
  would grade the system against itself. They are typed by hand.

Seeds speed up precision checking only — recall still requires reading
the full text (the linker's misses are exactly what the annotation must
catch), which is why ``text`` rides along in the draft.

The annotator's own labels live in this file once editing starts, so the
script refuses to overwrite an existing draft without ``--force``.

Usage:
    python scripts/prefill_extraction_annotations.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphrag_mtg.extraction.linker import Lexicon, scan_ruling

TODO_PATH = Path("data/interim/extraction_annotation_todo.jsonl")
DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")

UNDECIDED = "UNDECIDED"


def draft_row(row: dict, lexicon: Lexicon, name_by_id: dict[str, str]) -> dict:
    """Build one editable annotation row from a todo row.

    Card *names* ride along next to every oracle_id (``target_name``,
    ``candidates[].name``) purely for the annotator's eyes — the publish
    script keeps only ids and offsets.
    """
    resolved, pending = scan_ruling(
        row["ruling_id"], row["text"], lexicon, host_oracle_id=row.get("oracle_id")
    )
    mentions = [
        {
            "surface": m.surface,
            "start": m.span.start,
            "end": m.span.end,
            "target_oracle_id": m.oracle_id,
            "target_name": name_by_id.get(m.oracle_id or "", "?"),
            "seed": str(m.method),
        }
        for m in resolved
    ]
    mentions += [
        {
            "surface": p.mention.surface,
            "start": p.mention.span.start,
            "end": p.mention.span.end,
            "target_oracle_id": UNDECIDED,
            "seed": "surface",
            "candidates": [
                {"oracle_id": oid, "name": name_by_id.get(oid, "?")}
                for oid in p.candidate_oracle_ids
            ],
        }
        for p in pending
    ]
    mentions.sort(key=lambda m: m["start"])
    return {
        "ruling_id": row["ruling_id"],
        "split": row["split"],
        "stratum": row["stratum"],
        "oracle_id": row.get("oracle_id"),
        "text": row["text"],
        "mentions": mentions,
        "cited_rules": [],
        "notes": "",
        "annotator": "",
        "verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--todo", type=Path, default=TODO_PATH)
    parser.add_argument(
        "--cards", type=Path, default=Path("data/raw/scryfall_oracle_cards.json")
    )
    parser.add_argument("--out", type=Path, default=DRAFT_PATH)
    parser.add_argument("--force", action="store_true", help="overwrite an existing draft")
    args = parser.parse_args()

    if args.out.exists() and not args.force:
        print(f"{args.out} already exists — it may hold annotation work. Use --force to redo.")
        return 1

    with args.cards.open(encoding="utf-8") as fh:
        cards = json.load(fh)
    lexicon = Lexicon.build((c["name"], c["oracle_id"]) for c in cards)
    name_by_id = {c["oracle_id"]: c["name"] for c in cards}

    n_rows = n_seeded = n_undecided = 0
    with args.todo.open(encoding="utf-8") as todo, args.out.open("w", encoding="utf-8") as out:
        for line in todo:
            row = draft_row(json.loads(line), lexicon, name_by_id)
            n_rows += 1
            n_seeded += sum(1 for m in row["mentions"] if m["target_oracle_id"] != UNDECIDED)
            n_undecided += sum(1 for m in row["mentions"] if m["target_oracle_id"] == UNDECIDED)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"{n_rows} draft rows -> {args.out}: {n_seeded} seeded mentions to verify, "
        f"{n_undecided} UNDECIDED homonyms to decide, cited_rules all yours to write."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
