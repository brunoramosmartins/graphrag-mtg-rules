#!/usr/bin/env python
"""Render the annotation draft as a readable worksheet — no graph queries.

Turns `data/interim/extraction_annotations_draft.jsonl` into a plain-text
worksheet so a human never has to read raw JSON or query Neo4j to decide
a mention. For every unverified ruling it prints:

- the ruling text with each candidate mention marked inline (>>surface<<);
- the host card (skipped as a mention by definition);
- for every UNDECIDED homonym, each candidate card's type line and oracle
  text, pulled from the local oracle-cards file — the exact context the
  "is this word a card name?" decision needs;
- blanks showing what to fill in the JSON.

You still edit the JSONL (that is the source of truth the checker reads).
This is the reading companion that makes each edit obvious.

Usage:
    python scripts/annotation_worksheet.py --split dev            # dev warm-up
    python scripts/annotation_worksheet.py --split annotation --unverified-only
    python scripts/annotation_worksheet.py --ruling 891b32e1…     # one ruling
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

# Card text carries em-dashes and other non-cp1252 characters; force UTF-8 so
# the worksheet is readable in a default Windows console, not mojibake.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
CARDS_PATH = Path("data/raw/scryfall_oracle_cards.json")

UNDECIDED = "UNDECIDED"
RULE = "-" * 78


def load_card_index(path: Path) -> dict[str, dict]:
    """oracle_id -> {name, type_line, oracle_text} for worksheet context."""
    with path.open(encoding="utf-8") as fh:
        cards = json.load(fh)
    return {
        c["oracle_id"]: {
            "name": c["name"],
            "type_line": c.get("type_line", ""),
            "oracle_text": c.get("oracle_text", ""),
        }
        for c in cards
    }


def mark_mentions(text: str, mentions: list[dict]) -> str:
    """Wrap each mention's span in >>...<< without disturbing offsets."""
    for m in sorted(mentions, key=lambda m: m["start"], reverse=True):
        text = text[: m["start"]] + f">>{m['surface']}<<" + text[m["end"] :]
    return textwrap.fill(text, width=78)


def render_ruling(row: dict, cards: dict[str, dict]) -> str:
    """One ruling's worksheet block."""
    lines = [
        RULE,
        f"ruling {row['ruling_id']}   split={row['split']}   stratum={row['stratum']}",
    ]
    host = cards.get(row.get("oracle_id") or "")
    if host:
        lines.append(f"host card (never a mention): {host['name']} — {host['type_line']}")
    lines += ["", mark_mentions(row["text"], row["mentions"]), ""]

    seeded = [m for m in row["mentions"] if m["target_oracle_id"] not in (None, UNDECIDED)]
    undecided = [m for m in row["mentions"] if m["target_oracle_id"] == UNDECIDED]

    if seeded:
        lines.append("SEEDED mentions (confirm the card is right, or fix):")
        for m in seeded:
            name = cards.get(m["target_oracle_id"], {}).get("name", "?")
            lines.append(f"  [{m['seed']}] '{m['surface']}' @ {m['start']} -> {name}")

    if undecided:
        lines.append("")
        lines.append("DECIDE each homonym: set target_oracle_id to an id below, or null:")
        for m in undecided:
            lines.append(f"  '{m['surface']}' @ {m['start']}  ({len(m['candidates'])} card(s)):")
            for cand in m["candidates"]:
                info = cards.get(cand["oracle_id"], {})
                oracle = textwrap.shorten(info.get("oracle_text", ""), width=90) or "(no text)"
                lines.append(f"      {cand['oracle_id']}")
                lines.append(f"        {info.get('type_line', '?')} — {oracle}")

    lines += [
        "",
        "CITED RULES: read the ruling, look each number up in the CR, quote the clause.",
        "  (empty is correct when the ruling just restates card text)",
        f"Then set annotator + verified:true.  [currently verified={row['verified']}]",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--cards", type=Path, default=CARDS_PATH)
    parser.add_argument("--split", choices=("dev", "annotation"), default=None)
    parser.add_argument("--ruling", type=str, default=None, help="one ruling id")
    parser.add_argument("--unverified-only", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="write to a file instead of stdout")
    args = parser.parse_args()

    cards = load_card_index(args.cards)
    blocks = []
    homonyms = seeded = 0
    with args.draft.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if args.split and row["split"] != args.split:
                continue
            if args.ruling and row["ruling_id"] != args.ruling:
                continue
            if args.unverified_only and row["verified"]:
                continue
            blocks.append(render_ruling(row, cards))
            homonyms += sum(1 for m in row["mentions"] if m["target_oracle_id"] == UNDECIDED)
            seeded += sum(
                1 for m in row["mentions"] if m["target_oracle_id"] not in (None, UNDECIDED)
            )

    footer = (
        f"\n{RULE}\n{len(blocks)} rulings shown — "
        f"{seeded} seeded mentions to confirm, {homonyms} homonyms to decide."
    )
    output = "\n".join(blocks) + footer
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"Worksheet written to {args.out} ({len(blocks)} rulings).")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
