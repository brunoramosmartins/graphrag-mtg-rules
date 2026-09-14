#!/usr/bin/env python
"""E-025: is the governing chapter determined, or is it the annotator's choice?

E-024's control arm held the **answer key** and still named the annotator's
chapter on only 16 of 22. `docs/annotation-guide.md` asks for *"the most
specific rule that carries the answer"*, and "most specific" and "carries" are
both judgements. If a careful reader holding the answer would not reproduce
their own annotation, then `gold_cr_rules` is a choice among defensible options
rather than a fact about the question — and the 2/22 gold-rule reach that
Phase 9's objective rested on has been scored against one reader's pick.

**The blind is the whole instrument.** `worksheet` renders the question, the
key and the CR chapter index, and **never the existing annotation**. `mark`
records a chapter without echoing what the original said. `score` is the only
command that reads both, and it refuses to run on an unfinished sheet.

**The asymmetry, registered before any reading.** The author wrote the original
annotations and will remember some. That contaminates toward agreement, so a
**low** figure is strong evidence the target is soft and a **high** figure is
weak evidence that it is not. A second independent annotator would fix it and
this project does not have one.

Boundaries, numeric and fixed in the entry before this file existed, placed off
the 1/22 grid because E-018 landed exactly on two attainable thresholds and
E-024 had none at all:

    >= 0.85   the target is determinate
    <= 0.70   the target is a choice
    between   inconclusive, and it is the default

Usage:
    python scripts/run_e025.py worksheet
    python scripts/run_e025.py mark 1 613 2 704
    python scripts/run_e025.py mark
    python scripts/run_e025.py score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.evaluation.metrics import wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_correctness import CACHE_DIR as E007_CACHE_DIR
from audit_correctness import question_and_key
from e001_inspect import artefacts, gold_rules, load_jsonl
from run_e024 import STRATUM, chapter_of
from run_eval import CACHE_DIR, GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THIN = "-" * 78

ARM = "B"
SPLIT = "eval"

#: Question and key text, so gitignored. Same reason the E-018 ceiling
#: worksheet lives there.
WORKSHEET = Path("data/interim/e025_worksheet.md")

#: Ids and three digits. No key text, no CR text — versioned.
VERDICTS = Path("data/golden/e025_rechapter.json")

#: Registered in the entry, before this file existed.
DETERMINATE = 0.85
CHOICE = 0.70

QUESTION = "Which CR chapter carries this answer?"


def population(args: argparse.Namespace) -> list[str]:
    """The 22 question ids, in the order E-024 used."""
    retrieval_path, _, _ = artefacts(ARM, SPLIT)
    wanted = gold_rules(args.golden)
    return [
        row["question_id"]
        for row in load_jsonl(retrieval_path, what="retrieval")
        if row["stratum"] == STRATUM and row["question_id"] in wanted
    ]


def chapter_index(cr: object) -> list[tuple[str, str]]:
    """Every three-digit chapter and its title, for the reader to pick from.

    Rendered so the judgement is *which chapter carries this* and not *can the
    reader recall chapter numbers*. The second is noise and has nothing to do
    with what this entry measures.
    """
    return [
        (rule.number, rule.text)
        for rule in cr.rules  # type: ignore[attr-defined]
        if rule.level == 1 and rule.number.isdigit() and len(rule.number) == 3
    ]


def worksheet(args: argparse.Namespace) -> int:
    """Render the sheet. It never shows the existing annotation."""
    ids = population(args)
    cr = parse_cr()
    index = chapter_index(cr)

    lines = [
        "# E-025 re-annotation worksheet",
        "",
        f"**{QUESTION}**",
        "",
        "For each question below: read the question and the key, and name the",
        "**three-digit CR chapter** whose rules carry that answer. One chapter.",
        "",
        "This is the same judgement `docs/annotation-guide.md` step 4 asks for —",
        "*the most specific rule that carries the answer* — taken at chapter",
        "granularity and **without seeing what you chose the first time**.",
        "",
        "**Do not look up the original `gold_cr_rules`.** The whole measurement is",
        "whether the annotation reproduces blind. If you happen to remember one,",
        "record what you would choose now and note `remembered` — that case is",
        "reported separately rather than silently counted as agreement.",
        "",
        "Record with:",
        "",
        "```",
        "python scripts/run_e025.py mark 1 613 2 704 3 616",
        "python scripts/run_e025.py mark 5 700 --note remembered",
        "python scripts/run_e025.py mark          # what is left",
        "```",
        "",
        f"CR effective {cr.effective_date}. The chapter index is at the end.",
        "",
        "---",
        "",
    ]
    for index_number, qid in enumerate(ids, start=1):
        question, key = question_and_key(qid, args.caches, args.golden)
        lines += [f"## {index_number}. `{qid}`", "", "**Question.** " + question, "", "**Key.**", ""]
        lines += [f"> {line}" for line in key.strip().splitlines() if line.strip()]
        lines += ["", f"**{QUESTION}**  `___`", "", "---", ""]

    lines += ["", "## CR chapter index", "", "| chapter | title |", "|---|---|"]
    lines += [f"| `{number}` | {title} |" for number, title in index]

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(ids)} question(s) and {len(index)} chapters -> {WORKSHEET}")

    if VERDICTS.exists():
        print(f"{VERDICTS} already exists and was not touched.")
    else:
        payload = {
            "experiment": "E-025",
            "question": QUESTION,
            "determinate_at": DETERMINATE,
            "choice_at": CHOICE,
            "verdicts": [{"question_id": qid, "chapter": None, "note": ""} for qid in ids],
        }
        VERDICTS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Seeded {VERDICTS} with {len(ids)} blank verdict(s).")
    print(f"\nNext: read {WORKSHEET}, then `python scripts/run_e025.py mark ...`")
    return 0


#: A three-digit chapter, optionally with a subrule — `613`, `613.4b`.
_RULE_NUMBER = re.compile(r"\b\d{3}(?:\.\d+[a-z]?)?\b")


def key_names_the_rule(qid: str, gold: list[str], args: argparse.Namespace) -> bool:
    """Whether this question's key cites its own gold rule, or that chapter.

    Found by rendering the worksheet and checking the blind: **6 of the 22 keys
    name the rule**, and all six are the author's own `hand-*` keys. For those,
    re-annotating is transcription rather than judgement — agreement is
    guaranteed and measures nothing — so they leave the primary and become a
    **positive control**: if the reading cannot reproduce an annotation the key
    hands it, the primary figure should not be read at all.

    The 16 RulesGuru keys are silent on the rule, and they are the population
    this entry can actually measure.
    """
    _, key = question_and_key(qid, args.caches, args.golden)
    named = set(_RULE_NUMBER.findall(key))
    chapters = {number.split(".")[0] for number in named}
    return bool(named & set(gold) or chapters & {chapter_of(rule) for rule in gold})


def load_verdicts() -> tuple[dict, list[dict]]:
    if not VERDICTS.exists():
        raise SystemExit(f"No verdicts at {VERDICTS}. Run `worksheet` first.")
    payload = json.loads(VERDICTS.read_text(encoding="utf-8"))
    return payload, payload["verdicts"]


def mark(args: argparse.Namespace) -> int:
    """Record chapters. It records; it does not suggest and it does not echo."""
    payload, verdicts = load_verdicts()
    if not args.pairs:
        blank = [row["question_id"] for row in verdicts if row["chapter"] is None]
        print(f"{len(verdicts) - len(blank)} of {len(verdicts)} recorded.\n")
        for index, row in enumerate(verdicts, start=1):
            if row["chapter"] is None:
                print(f"  {index:>3}. {row['question_id']}")
        if not blank:
            print("  nothing left — run `score`.")
        return 0
    if len(args.pairs) % 2:
        raise SystemExit(
            "Arguments come in pairs: a worksheet number or question id, then a "
            "three-digit chapter.\n  python scripts/run_e025.py mark 1 613 2 704"
        )
    steps = list(zip(args.pairs[::2], args.pairs[1::2], strict=True))
    if args.note is not None and len(steps) != 1:
        raise SystemExit("--note applies to one verdict; pass a single pair with it.")

    planned = []
    for target, chapter in steps:
        if not (chapter.isdigit() and len(chapter) == 3):
            raise SystemExit(f"{chapter!r} is not a three-digit chapter (for {target}).")
        if target.isdigit() and 1 <= int(target) <= len(verdicts):
            planned.append((int(target) - 1, chapter))
            continue
        matches = [i for i, row in enumerate(verdicts) if row["question_id"] == target]
        if not matches:
            raise SystemExit(f"No question {target!r} in {VERDICTS}.")
        planned.append((matches[0], chapter))

    for index, chapter in planned:
        row = verdicts[index]
        was = row["chapter"]
        row["chapter"] = chapter
        if args.note is not None:
            row["note"] = args.note
        changed = "  ** CHANGED" if was and was != chapter else ""
        print(f"  {row['question_id']}: {was + ' -> ' if was else ''}{chapter}{changed}")

    VERDICTS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    left = sum(1 for row in verdicts if row["chapter"] is None)
    print(f"\n{len(verdicts) - left} of {len(verdicts)} recorded, {left} to go.")
    return 0


def score(args: argparse.Namespace) -> int:
    """Agreement against the original annotation, and the registered branches.

    The only command that reads both sides. It refuses an unfinished sheet,
    because agreement over whichever questions happened to be read first is
    agreement over a reading order.
    """
    _, verdicts = load_verdicts()
    blank = [row["question_id"] for row in verdicts if row["chapter"] is None]
    if blank:
        raise SystemExit(
            f"{len(blank)} of {len(verdicts)} still blank: {', '.join(blank[:5])}"
            f"{'...' if len(blank) > 5 else ''}"
        )
    wanted = gold_rules(args.golden)
    primary, control, disagree, remembered = [], [], [], []
    for row in verdicts:
        qid = row["question_id"]
        original = sorted({chapter_of(rule) for rule in wanted[qid]})
        hit = row["chapter"] in original
        (control if key_names_the_rule(qid, wanted[qid], args) else primary).append(hit)
        if not hit:
            disagree.append((qid, row["chapter"], original))
        if "remember" in (row.get("note") or "").lower():
            remembered.append(qid)

    n = len(primary)
    hits = sum(primary)
    rate = hits / n
    interval = wilson_interval(hits, n)
    print(f"{QUESTION}\n")
    print(f"  PRIMARY — the {n} questions whose key does not name the rule")
    print(f"  agreement with the original annotation: {hits}/{n}")
    print(f"  {rate:.3f}  [{interval.low:.3f}, {interval.high:.3f}]")
    print(f"  registered: determinate at >= {DETERMINATE}, a choice at <= {CHOICE}")
    print()
    print(f"  POSITIVE CONTROL — the {len(control)} whose key names the rule or its")
    print(f"  chapter: {sum(control)}/{len(control)}. Re-annotating these is transcription,")
    print("  not judgement, so anything below near-perfect means the reading is")
    print("  unreliable and the primary above should not be read.")
    if remembered:
        print(f"\n  flagged as remembered: {len(remembered)} — {', '.join(remembered)}")
        print("  (reported, not removed; they are the contaminated direction)")

    print(f"\n{THIN}\nWHERE IT DISAGREES")
    for qid, chosen, original in disagree:
        print(f"  {qid:<30} now {chosen}   originally {', '.join(original)}")

    print(f"\n{THIN}")
    if rate >= DETERMINATE:
        print("DETERMINATE. `gold_cr_rules` stands as a measurement target, the")
        print("retrieval figures keep their current force, and a router has something")
        print("well defined to aim at. Note the registered asymmetry: you annotated")
        print("these yourself, which contaminates toward agreement, so this is the")
        print("WEAK direction of the result.")
    elif rate <= CHOICE:
        print("A CHOICE. Every figure scored against `gold_cr_rules` gains a published")
        print("caveat naming this entry; E-024's question is withdrawn as ill-posed;")
        print("and the scope statement's interaction_multihop half is restated in")
        print("terms of what retrieval brought rather than what it missed. This is the")
        print("STRONG direction — contamination worked against it.")
    else:
        print("INCONCLUSIVE, and it is the default. Nothing is adopted and nothing is")
        print(f"withdrawn: {n} questions cannot separate a determinate target from a")
        print("choice at the boundaries this entry registered before reading.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    common.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("worksheet", parents=[common], help="render the sheet, blind")
    marker = sub.add_parser("mark", parents=[common], help="record chapters")
    marker.add_argument("pairs", nargs="*", metavar="TARGET CHAPTER")
    marker.add_argument("--note", default=None, help="a note, with a single pair")
    sub.add_parser("score", parents=[common], help="agreement against the original")
    args = parser.parse_args()
    return {"worksheet": worksheet, "mark": mark, "score": score}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
