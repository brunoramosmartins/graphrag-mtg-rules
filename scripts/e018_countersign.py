#!/usr/bin/env python
"""Record the author's countersign of E-018's A/B/C/D split.

`docs/error-samples/e018.md` classifies nine answers by *why* each failed. That
classification was made by Claude, and standing rule 8 says the author reads.
The open checkbox at the foot of that file is what this closes.

**It records; it does not decide, and there is no model call here.** The group
is a causal judgement about an answer a person has read with the prompt as
sent. A letter that looks like a countersign and was not read is worth less
than no letter, because it would be trusted.

The nine are **derived, not listed**: ceiling `derivable: true`, the treatment
condition answered, and the judge scored it not `correct`. Deriving them means
that if the ceiling file moves again — as it did for `rg-3155`, from `true` to
`false`, which took the denominator from 17 to 16 — this population moves with
it instead of quietly disagreeing with it.

Read first, then mark:

    python scripts/e018_inspect.py --qid rg-1591 --condition treatment --full

Usage:
    python scripts/e018_countersign.py worksheet
    python scripts/e018_countersign.py mark
    python scripts/e018_countersign.py mark 1 A rg-51 D
    python scripts/e018_countersign.py mark rg-396 B --note "the count is the obstacle"
    python scripts/e018_countersign.py score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import load_jsonl
from e018_ceiling import VERDICTS as CEILING
from run_e018 import outputs

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Ids and single letters only. No CR text, no answer keys, no question text —
#: this file is committed, and `data/interim/` exists for everything that
#: cannot be. The reading itself happens against `e018_inspect.py`'s output.
SHEET = Path("data/golden/e018_countersign.json")

RULE = "=" * 78
THIN = "-" * 78

#: What each letter asserts, quoted from `docs/error-samples/e018.md` so the
#: sheet and the published file cannot drift into meaning different things.
GROUPS = {
    "A": "the injected rule was cited and misapplied — the inference is wrong",
    "B": "multi-step simulation; the CR rule is not the obstacle",
    "C": "reached the key's verdict and was scored not `correct`",
    "D": "reasoned from a different rule; the injected rule stayed inert",
}

#: The published classification, recorded so that a countersign which *differs*
#: is visible as a disagreement rather than as a fresh reading with no prior.
#: Not a default: a row marked with the same letter still had to be marked.
PROPOSED = {
    "rg-1591": "A",
    "rg-2249": "A",
    "rg-778": "A",
    "rg-198": "B",
    "rg-3": "B",
    "rg-396": "C",
    "rg-650": "C",
    "rg-2711": "C",
    "rg-51": "D",
}

#: A + D is the only figure allowed to leave the error-sample file, and it is
#: what the open checkbox gates. Named here so `score` cannot compute something
#: adjacent to it and call it the same thing.
GENERATION_GROUPS = ("A", "D")


def population() -> tuple[list[str], int]:
    """The nine to read, and the derivable denominator they sit in.

    Returns:
        The question ids in worksheet order, and the count of questions the
        ceiling marked derivable — the denominator every figure below uses.

    Raises:
        SystemExit: when the derivation disagrees with the published split,
            rather than silently countersigning a different set of questions
            than the file being countersigned describes.
    """
    if not CEILING.exists():
        raise SystemExit(f"No ceiling verdicts at {CEILING}.")
    verdicts = json.loads(CEILING.read_text(encoding="utf-8"))["verdicts"]
    derivable = [row["question_id"] for row in verdicts if row.get("derivable") is True]

    rows = load_jsonl(outputs("primary")[1], what="E-018 run")
    treatment = {row["question_id"]: row for row in rows if row["condition"] == "treatment"}

    ids = [
        qid
        for qid in derivable
        if treatment.get(qid, {}).get("generated")
        and treatment[qid].get("label") != "correct"
    ]
    if set(ids) != set(PROPOSED):
        missing = sorted(set(PROPOSED) - set(ids))
        extra = sorted(set(ids) - set(PROPOSED))
        raise SystemExit(
            "The derived population no longer matches the published split in "
            "docs/error-samples/e018.md.\n"
            f"  in the file, not derived: {missing or 'none'}\n"
            f"  derived, not in the file: {extra or 'none'}\n"
            "The ceiling or the run moved. Reconcile the file before marking."
        )
    return ids, len(derivable)


def seed(ids: list[str]) -> dict:
    """A fresh sheet: every row blank, every row carrying the prior."""
    return {
        "experiment": "E-018",
        "question": (
            "Read against the treatment prompt as sent: why did this answer "
            "fail? If the injected rule were removed, would it change?"
        ),
        "groups": GROUPS,
        "source": "docs/error-samples/e018.md",
        "rows": [
            {"question_id": qid, "proposed": PROPOSED[qid], "group": None, "note": ""}
            for qid in ids
        ],
    }


def load_sheet() -> dict:
    """The sheet, refusing to proceed before `worksheet` has written one."""
    if not SHEET.exists():
        raise SystemExit(
            f"No countersign sheet at {SHEET}.\n"
            "  python scripts/e018_countersign.py worksheet"
        )
    return json.loads(SHEET.read_text(encoding="utf-8"))


def worksheet(args: argparse.Namespace) -> int:
    """Print what to read, in what order, and seed the sheet once.

    Re-running is safe and never clears a mark: the rows are rebuilt from the
    derivation and any group already recorded is carried across.
    """
    ids, derivable = population()
    payload = seed(ids)
    if SHEET.exists():
        previous = {row["question_id"]: row for row in load_sheet()["rows"]}
        for row in payload["rows"]:
            old = previous.get(row["question_id"])
            if old and old.get("group"):
                row["group"], row["note"] = old["group"], old.get("note", "")
        print(f"{SHEET} already exists; marks already recorded are kept.\n")

    print(f"{RULE}\nE-018 COUNTERSIGN — {len(ids)} case(s), ceiling denominator {derivable}\n{RULE}")
    print(f"\n{payload['question']}\n")
    for letter, meaning in GROUPS.items():
        print(f"  {letter}  {meaning}")
    print(f"\n{THIN}")
    for index, row in enumerate(payload["rows"], start=1):
        mark_ = row["group"] or "-"
        print(
            f"  {index:>2}. {row['question_id']:<10} proposed {row['proposed']}   "
            f"recorded {mark_}\n"
            f"      python scripts/e018_inspect.py --qid {row['question_id']} "
            f"--condition treatment --full"
        )
    print(THIN)
    print(
        "\nThe four that move the published figure are the A and D cases: "
        f"{', '.join(qid for qid, g in PROPOSED.items() if g in GENERATION_GROUPS)}."
    )

    SHEET.parent.mkdir(parents=True, exist_ok=True)
    SHEET.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nSheet at {SHEET.as_posix()}.  "
        "Mark with:  python scripts/e018_countersign.py mark 1 A"
    )
    return 0


def resolve(target: str, rows: list[dict]) -> int:
    """A worksheet number or a question id, to a row index.

    Both are in front of the reader, so both are accepted. A bare integer is a
    worksheet number; anything else is an id.

    Raises:
        SystemExit: when the target names no row, rather than recording a
            group against whatever row happened to be first.
    """
    if target.isdigit():
        index = int(target) - 1
        if not 0 <= index < len(rows):
            raise SystemExit(
                f"{target} is not a worksheet number — the sheet has "
                f"{len(rows)} case(s), numbered 1 to {len(rows)}."
            )
        return index
    for index, row in enumerate(rows):
        if row["question_id"] == target:
            return index
    raise SystemExit(f"No case with id {target!r} in {SHEET}.")


def apply_mark(row: dict, value: str, note: str | None) -> str:
    """Record one group on one row. Returns what to print about it.

    A mark that overwrites an earlier one says so. A mark that departs from the
    published proposal says so too — that disagreement is the whole point of
    the exercise and it must not pass as a quiet edit.
    """
    was = row.get("group")
    row["group"] = value
    if note is not None:
        row["note"] = note

    line = f"  {row['question_id']}: {value}"
    if was and was != value:
        line += f"  (was {was})  ** CHANGED"
    elif was == value:
        line += "  (unchanged)"
    if value != row["proposed"]:
        line += f"  ** DEPARTS from the published {row['proposed']}"
    return line


def mark(args: argparse.Namespace) -> int:
    """Record groups from the command line. With no arguments, what is left."""
    payload = load_sheet()
    rows = payload["rows"]

    if not args.pairs:
        blank = [row["question_id"] for row in rows if not row.get("group")]
        print(f"{len(rows) - len(blank)} of {len(rows)} recorded.\n")
        for index, row in enumerate(rows, start=1):
            if not row.get("group"):
                print(f"  {index:>2}. {row['question_id']:<10} proposed {row['proposed']}")
        if not blank:
            print("  nothing left — run `score`.")
        return 0

    if len(args.pairs) % 2:
        raise SystemExit(
            "Arguments come in pairs: a worksheet number or question id, then "
            f"one of {' / '.join(GROUPS)}.\n"
            "  python scripts/e018_countersign.py mark 1 A rg-51 D"
        )
    steps = list(zip(args.pairs[::2], args.pairs[1::2], strict=True))
    if args.note is not None and len(steps) != 1:
        raise SystemExit("--note applies to one case; pass a single pair with it.")

    # Resolved and validated in full before anything is written: a batch that
    # failed on its third pair would otherwise leave two recorded and nothing
    # saying which two.
    for target, value in steps:
        if value.upper() not in GROUPS:
            raise SystemExit(f"{value!r} is not one of {' / '.join(GROUPS)} (for {target}).")
    planned = [(resolve(target, rows), value.upper()) for target, value in steps]
    for index, value in planned:
        print(apply_mark(rows[index], value, args.note))

    SHEET.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    blank = [row for row in rows if not row.get("group")]
    print(f"\n{len(rows) - len(blank)} of {len(rows)} recorded, {len(blank)} to go.")
    if not blank:
        print("Run `python scripts/e018_countersign.py score`.")
    return 0


def score(args: argparse.Namespace) -> int:
    """The countersigned split, and the checkbox text to paste.

    Refuses to report on a partial sheet. A figure computed over six of nine
    readings is not the countersign the published file is waiting on, and
    printing one would make it available to quote.
    """
    payload = load_sheet()
    rows = payload["rows"]
    _, derivable = population()

    blank = [row["question_id"] for row in rows if not row.get("group")]
    if blank:
        raise SystemExit(
            f"{len(blank)} case(s) unmarked: {', '.join(blank)}.\n"
            "No figure is reported from a partial sheet."
        )

    tally = {letter: [] for letter in GROUPS}
    for row in rows:
        tally[row["group"]].append(row["question_id"])
    departures = [row for row in rows if row["group"] != row["proposed"]]

    print(f"{RULE}\nE-018 COUNTERSIGNED SPLIT — {len(rows)} case(s)\n{RULE}\n")
    for letter, meaning in GROUPS.items():
        ids = tally[letter]
        print(f"  {letter}  {len(ids):>2}  {meaning}")
        if ids:
            print(f"        {', '.join(ids)}")

    generation = [qid for letter in GENERATION_GROUPS for qid in tally[letter]]
    print(f"\n{THIN}")
    print(
        f"Of the {derivable} questions the ceiling marked derivable, "
        f"{len(generation)} are classified as reasoning or application failures "
        "with sufficient evidence."
    )
    print(f"  {', '.join(sorted(generation)) or 'none'}")
    print(
        "\nThat is the only figure this file releases. It is not a failure "
        "rate: the denominator is an oracle-conditioned ceiling, not a system "
        "score."
    )

    print(f"\n{THIN}\nDEPARTURES FROM THE PUBLISHED SPLIT\n{THIN}")
    if not departures:
        print("  none — the published A/B/C/D split is countersigned as written.")
    for row in departures:
        note = f"  — {row['note']}" if row.get("note") else ""
        print(f"  {row['question_id']}: {row['proposed']} -> {row['group']}{note}")

    word = {3: "three", 4: "four", 5: "five", 6: "six"}.get(len(generation), str(len(generation)))
    print(f"\n{RULE}\nFOR docs/error-samples/e018.md\n{RULE}\n")
    print(
        f"- [x] **Author countersign of the A/B/C/D split, {args.date}.** The "
        f"{len(rows)} renderings were read by the author against the treatment "
        f"prompt as sent, in `scripts/e018_inspect.py`. "
        + (
            "The split stands as published.\n"
            if not departures
            else f"{len(departures)} case(s) moved: "
            + "; ".join(f"{r['question_id']} {r['proposed']} to {r['group']}" for r in departures)
            + ".\n"
        )
        + f"      **{word.capitalize()} of {derivable}** derivable questions are "
        "reasoning or application failures with the evidence in hand. Figures "
        "derived from this split may now leave this file. Recorded in "
        f"`{SHEET.as_posix()}`."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("worksheet", help="derive the cases, print them, seed the sheet")
    marker = sub.add_parser("mark", help="record groups; with no arguments, what is left")
    marker.add_argument("pairs", nargs="*", help="number-or-id then A / B / C / D")
    marker.add_argument("--note", default=None, help="a reason, for one pair")
    scorer = sub.add_parser("score", help="the countersigned split and the checkbox text")
    scorer.add_argument("--date", default="2026-09-14", help="the date read")
    args = parser.parse_args()
    return {"worksheet": worksheet, "mark": mark, "score": score}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
