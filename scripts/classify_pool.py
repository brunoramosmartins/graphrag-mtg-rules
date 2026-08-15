#!/usr/bin/env python
"""Assign the real stratum to each question in E-007's audit pool.

The three `STRATUM_PLAN` entries are **source filters, not strata**. The
golden set proves it: `data/golden/ids_v0.jsonl` holds no `rulings_2hop`
question at all, because the complexity-seeded label was reclassified by
hand during Phase 1 annotation. RulesGuru `complexity` measures how hard a
question is to *answer*, not how many hops it needs.

This has to happen **before** the 10/30 split, not after. The split draws
proportionally by stratum, so splitting on seeded labels would be
nominally stratified and substantively hollow — and if the true
`interaction_multihop` questions landed mostly in the development side,
the audit would lose the one stratum that exercises refusals, which is the
failure this pool was redrawn to fix.

Only one field is being decided here. E-007 does not need `gold_path`,
`gold_cr_rules` or `vector_should`: it measures citation coverage and
support, not retrieval recall, and sufficiency is labelled later against
the RulesGuru answer key. One field over 42 questions, not the Phase 1
annotation.

The worksheet carries the question text and therefore lives under
`data/interim/` (gitignored). Only `id -> stratum` is written back to the
committed pool — the licence posture the golden set already uses.

Usage:
    python scripts/classify_pool.py worksheet          # once, builds the file
    python scripts/classify_pool.py show --next        # read the next undecided
    python scripts/classify_pool.py set rg-4825 interaction_multihop
    python scripts/classify_pool.py status             # how many are left
    python scripts/classify_pool.py apply              # write back to the pool

`show` prints; `set` writes. Same split as `annotation_worksheet.py` and
`cite.py`, and for the same reason — hand-editing JSONL is where typos and
key errors come from, and a mistyped stratum should fail at the keystroke
rather than at the split.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

from graphrag_mtg.evaluation.golden import Stratum, dump_golden, load_golden

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POOL_PATH = Path("data/golden/e007_audit_pool.jsonl")
CACHE_DIR = Path("data/interim/e007_cache")
WORKSHEET_PATH = Path("data/interim/e007_strata_worksheet.jsonl")

#: What a question may be classified as. `rulings_2hop` stays available
#: even though the golden set ended with none — refusing to offer it would
#: decide the answer in advance.
CHOICES = tuple(s.value for s in Stratum)


RULE = "-" * 78

#: The decision table from `docs/annotation-guide.md` step 1, printed with
#: every question so the guide does not have to be open in another window.
#: Kept here verbatim rather than paraphrased — a crib that drifts from the
#: procedure is worse than no crib.
CRIB = """\
  legality_1hop        is this card legal in this format?
  definition_1hop      what does one keyword do, and nothing else?
  keyword_rule_2hop    one keyword's rule PLUS a sub-rule or cross-reference
  rulings_2hop         answered by a card's official ruling citing a rule
  interaction_multihop composes TWO OR MORE effects/permanents; no single
                       rule states the result
  negative_temporal    turns on something NOT happening, or on timing/order

  TIE-BREAKER: if two or more permanents/effects must be reasoned about
  *together*, it is interaction_multihop — even when RulesGuru says Simple.
  Interaction is about composition, not difficulty."""


def load_worksheet(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"No worksheet at {path}. Run `classify_pool.py worksheet` first.")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def save_worksheet(rows: list[dict], path: Path) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )


def wrap(text: str) -> str:
    return textwrap.fill(text, width=76, initial_indent="  ", subsequent_indent="  ")


def render(entry: dict, position: str = "", *, with_answer: bool = False) -> str:
    """One question, formatted for a decision rather than for reading JSON.

    The answer is off by default because the guide classifies on the
    question's *shape* — but it is one flag away, since a judge-curated
    answer settles an ambiguous case and there is nothing to protect it
    from. E-007's contamination boundary is elsewhere: sufficiency labels
    are frozen before any *generated* answer is read.
    """
    decided = entry.get("stratum") or "—"
    lines = [
        RULE,
        f"{entry['id']}  {position}".rstrip(),
        f"  seeded: {entry['seeded']}   (complexity {entry.get('complexity') or '?'}"
        f", level {entry.get('level') if entry.get('level') != '' else '?'})",
        f"  tags:   {', '.join(entry.get('tags') or []) or '—'}",
        "",
        "  QUESTION",
        wrap(entry.get("question", "")),
    ]
    if with_answer:
        lines += ["", "  ANSWER (RulesGuru, judge-curated — not yours to verify)"]
        lines.append(wrap(entry.get("answer", "") or "—"))
        if entry.get("cited_rules"):
            lines.append(f"  cites: {', '.join(str(r) for r in entry['cited_rules'])}")
        if entry.get("url"):
            lines.append(f"  {entry['url']}")
    lines += [
        "",
        CRIB,
        "",
        f"  decided: {decided}",
        f"  -> python scripts/classify_pool.py set {entry['id']} <stratum>",
    ]
    return "\n".join(lines)


def cmd_show(args: argparse.Namespace) -> int:
    """Print questions to decide on. Reads only; `set` is what writes."""
    rows = load_worksheet(args.worksheet)
    if args.id:
        chosen = [row for row in rows if row["id"] == args.id]
        if not chosen:
            raise SystemExit(f"{args.id} is not in {args.worksheet}.")
    elif args.all:
        chosen = rows
    else:
        undecided = [row for row in rows if not (row.get("stratum") or "").strip()]
        if not undecided:
            print("Every question is classified. Next: `classify_pool.py apply`.")
            return 0
        chosen = undecided[: args.count]

    done = sum(1 for row in rows if (row.get("stratum") or "").strip())
    for i, entry in enumerate(chosen, start=1):
        print(
            render(
                entry,
                f"[{i} of {len(chosen)} shown; {done}/{len(rows)} done]",
                with_answer=args.with_answer,
            )
        )
    print(RULE)
    if not args.with_answer:
        print("(pass --with-answer when the question's shape alone does not settle it)")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Record one classification, validated, without hand-editing JSON."""
    if args.stratum not in CHOICES:
        raise SystemExit(f"{args.stratum!r} is not a stratum. Choose one of: {', '.join(CHOICES)}")
    rows = load_worksheet(args.worksheet)
    for row in rows:
        if row["id"] == args.id:
            previous = row.get("stratum") or ""
            row["stratum"] = args.stratum
            save_worksheet(rows, args.worksheet)
            note = f" (was {previous})" if previous and previous != args.stratum else ""
            done = sum(1 for r in rows if (r.get("stratum") or "").strip())
            print(f"{args.id}: {args.stratum}{note}   [{done}/{len(rows)} done]")
            return 0
    raise SystemExit(f"{args.id} is not in {args.worksheet}.")


def cmd_status(args: argparse.Namespace) -> int:
    """How much is left, and what the mix looks like so far."""
    rows = load_worksheet(args.worksheet)
    counts: dict[str, int] = {}
    undecided: list[str] = []
    for row in rows:
        value = (row.get("stratum") or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
        else:
            undecided.append(row["id"])
    print(f"{len(rows) - len(undecided)}/{len(rows)} classified.")
    print(f"  so far: {dict(sorted(counts.items()))}")
    changed = sum(
        1
        for row in rows
        if (row.get("stratum") or "").strip() and row["stratum"] != row["seeded"]
    )
    print(f"  differs from the seeded label on {changed} of the decided ones")
    if undecided:
        print(f"  left: {', '.join(undecided[:12])}{' ...' if len(undecided) > 12 else ''}")
    return 0


def cached(question_id: str, cache: Path) -> dict:
    path = cache / f"{question_id}.json"
    if not path.exists():
        raise SystemExit(f"No cached text for {question_id} at {path}. Re-run the draw.")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_worksheet(args: argparse.Namespace) -> int:
    """Write one row per question, with the text needed to classify it."""
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to overwrite your labels.")
    rows = load_golden(args.pool)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = cached(row.id, args.cache_dir)
            handle.write(
                json.dumps(
                    {
                        "id": row.id,
                        "stratum": "",  # <- you fill this in
                        "seeded": row.stratum.value,
                        "tags": payload.get("tags", []),
                        "complexity": payload.get("complexity", ""),
                        "level": payload.get("level", ""),
                        "question": payload.get("questionSimple") or payload.get("question", ""),
                        # The judge-curated answer, and RulesGuru's own rule
                        # citations. Not needed to classify — the guide reads
                        # the question's shape — but decisive when a question
                        # is ambiguous, and required later for sufficiency.
                        "answer": payload.get("answerSimple", ""),
                        "cited_rules": payload.get("citedRules", []),
                        "url": payload.get("url", ""),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"Wrote {len(rows)} row(s) to {args.out} (gitignored — it carries question text).")
    print(f"Fill `stratum` on every row with one of: {', '.join(CHOICES)}")
    print("Classify from the question's shape, not from `seeded` — that came from")
    print("RulesGuru complexity, which measures difficulty rather than hops.")
    print("See docs/annotation-guide.md, step 1.")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Write the decided strata back to the pool, and report the achieved mix."""
    if not args.worksheet.exists():
        raise SystemExit(f"No worksheet at {args.worksheet}. Run `worksheet` first.")
    decided: dict[str, str] = {}
    missing: list[str] = []
    for line in args.worksheet.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        value = (entry.get("stratum") or "").strip()
        if value not in CHOICES:
            missing.append(entry["id"])
        else:
            decided[entry["id"]] = value

    if missing:
        print(f"{len(missing)} question(s) unclassified or invalid:")
        for question_id in missing[:10]:
            print(f"  {question_id}")
        raise SystemExit("Every question needs a stratum before the split can be drawn.")

    rows = load_golden(args.pool)
    changed = sum(1 for row in rows if row.stratum.value != decided.get(row.id, row.stratum.value))
    updated = [
        row.model_copy(update={"stratum": Stratum(decided[row.id])}) if row.id in decided else row
        for row in rows
    ]
    if args.dry_run:
        print(f"Dry run: would reclassify {changed} of {len(rows)} row(s); wrote nothing.")
    else:
        dump_golden(updated, args.pool)
        print(f"Reclassified {changed} of {len(rows)} row(s) in {args.pool}.")

    counts: dict[str, int] = {}
    for row in updated:
        counts[row.stratum.value] = counts.get(row.stratum.value, 0) + 1
    print(f"Achieved mix: {dict(sorted(counts.items()))}")
    print("Report this as achieved, never as planned — the seeded labels were a filter.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, default=POOL_PATH)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    sheet = sub.add_parser("worksheet", help="write the classification worksheet")
    sheet.add_argument("--out", type=Path, default=WORKSHEET_PATH)
    sheet.add_argument("--force", action="store_true")
    sheet.set_defaults(func=cmd_worksheet)

    shower = sub.add_parser("show", help="print questions to decide on")
    shower.add_argument("--id", help="one question by id")
    shower.add_argument("--all", action="store_true", help="every question, decided or not")
    shower.add_argument("--next", action="store_true", help="the next undecided (default)")
    shower.add_argument("--count", type=int, default=1, help="how many undecided to print")
    shower.add_argument(
        "--with-answer",
        action="store_true",
        help="also print RulesGuru's judge-curated answer and its rule citations",
    )
    shower.set_defaults(func=cmd_show)

    setter = sub.add_parser("set", help="record one classification")
    setter.add_argument("id")
    setter.add_argument("stratum", choices=CHOICES)
    setter.set_defaults(func=cmd_set)

    status = sub.add_parser("status", help="how many are left, and the mix so far")
    status.set_defaults(func=cmd_status)

    apply_cmd = sub.add_parser("apply", help="write decided strata back to the pool")
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
