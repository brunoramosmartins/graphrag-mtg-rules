#!/usr/bin/env python
"""Freeze E-018's populations, and measure the ceiling before the run.

E-013 paid for this lesson and E-016 answered it: *a ceiling is a claim about
the experiment, and it has to be computed over the experiment's own inputs.*
E-018 registered a detectable effect and no ceiling, and the ceiling matters
more here than in either of them — the 2026-09-13 audit recorded that roughly
60% of arm B's correct answers cite no CR rule at all. If most of the 21
questions have keys that are answered from rulings rather than from the CR,
then injecting `gold_cr_rules` is inert for a reason about the corpus, the
aggregate reads null, and branch 3 cancels a phase for the wrong reason.

**The judgement is the author's and this script does not make it.** For each
question the reader decides one thing:

    Is this key's verdict derivable from this question's gold CR rules alone?

`worksheet` renders what is needed to decide; `score` reads the decisions back.
Nothing here fills a verdict in, and `score` refuses a sheet with a blank.

**Three commands, in order:**

    freeze      the two id files the 2026-09-13 amendment requires, computed
                from E-001's recorded arm-B retrieval and never recomputed at
                run time. Refuses to overwrite a frozen file that disagrees.
    worksheet   the readable sheet, into `data/interim/` because it carries CR
                rule text and answer keys, which the Fan Content Policy forbids
                committing. The verdict file it seeds carries ids and booleans
                only, and that one is versioned.
    score       the ceiling with a Wilson interval, against the registered gate.

The registered gate: **if the ceiling is below 0.333 x 21 (7 questions), E-018
is redesigned rather than run**, because branch 1 would be unreachable by
construction.

Usage:
    python scripts/e018_ceiling.py freeze
    python scripts/e018_ceiling.py worksheet
    python scripts/e018_ceiling.py score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.evaluation.metrics import wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import artefacts, gold_rules, load_jsonl, outcome_of, retrieved_rules
from run_eval import GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THIN = "-" * 78

#: Arm B only. E-018 is a within-arm intervention and draws no arm comparison.
ARM = "B"
SPLIT = "eval"

#: Ids only, so these are safe to version: no rule text, no key text.
ABSENT_IDS = Path("data/golden/e018_absent_ids.json")
NO_SEED_IDS = Path("data/golden/e018_no_seed_ids.json")

#: Ids and booleans only — the author's judgement, versioned.
VERDICTS = Path("data/golden/e018_ceiling.json")

#: Carries CR rule text and answer keys. `data/interim/` is gitignored and
#: that is the reason this file lives there rather than under `docs/`.
WORKSHEET = Path("data/interim/e018_ceiling_worksheet.md")

#: Registered in the 2026-09-13 amendment: the smallest net lift that can
#: clear the strict Holm step at n = 21 is 0.333, so a ceiling below this many
#: questions makes branch 1 unreachable whatever the intervention does.
GATE = 7

QUESTION = "Is this key's verdict derivable from this question's gold CR rules alone?"


def populations(golden: Path) -> tuple[list[str], list[str], list[str]]:
    """The three id sets E-018 needs, from E-001's record and nothing else.

    Args:
        golden: The golden-set directory carrying `gold_cr_rules`.

    Returns:
        Absent (the primary population), no-seed (excluded from it), and
        present (the secondary subset), each sorted for a stable file.
    """
    retrieval_path, answers_path, _ = artefacts(ARM, SPLIT)
    records = {row["question_id"]: row for row in load_jsonl(retrieval_path, what="retrieval")}
    answers = {row["question_id"]: row for row in load_jsonl(answers_path, what="answers")}
    wanted = gold_rules(golden)

    carrying = sorted(qid for qid in records if qid in wanted)
    present, absent, no_seed = [], [], []
    for qid in carrying:
        if outcome_of(answers[qid], None) == "refused_by_pipeline":
            no_seed.append(qid)
        elif retrieved_rules(records[qid]) & set(wanted[qid]):
            present.append(qid)
        else:
            absent.append(qid)
    return absent, no_seed, present


def freeze_file(path: Path, ids: list[str], *, what: str) -> None:
    """Write an id file once, and refuse to change it afterwards.

    A frozen population that can be silently recomputed is not frozen. If the
    graph, the golden set or the harness moves, this raises rather than
    quietly redefining what the entry measures.

    Raises:
        SystemExit: if the file exists and its contents differ.
    """
    payload = {"experiment": "E-018", "arm": ARM, "split": SPLIT, "what": what, "ids": ids}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("ids") != ids:
            gone = sorted(set(existing.get("ids", [])) - set(ids))
            new = sorted(set(ids) - set(existing.get("ids", [])))
            raise SystemExit(
                f"{path} is frozen and disagrees with what E-001's record now produces.\n"
                f"  no longer present: {gone or 'none'}\n"
                f"  newly present:     {new or 'none'}\n"
                f"The population E-018 registered is the one in the file. Something "
                f"moved underneath it — find out what before touching this."
            )
        print(f"  {path}  unchanged ({len(ids)} id(s))")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"  {path}  written ({len(ids)} id(s))")


def freeze(args: argparse.Namespace) -> int:
    """Write the two id files, from E-001's record and before any spend."""
    absent, no_seed, present = populations(args.golden)
    print(f"arm {ARM}   split {SPLIT}   from E-001's recorded retrieval\n")
    print(f"  {len(absent) + len(no_seed) + len(present)} question(s) carry gold_cr_rules")
    print(f"  {len(present)} had a gold rule retrieved      — secondary, fires no branch")
    print(f"  {len(no_seed)} never called the model          — exploratory stratum")
    print(f"  {len(absent)} are the primary population\n")
    freeze_file(ABSENT_IDS, absent, what="primary population: gold rule absent, model called")
    freeze_file(NO_SEED_IDS, no_seed, what="excluded from the primary: the model was never called")
    return 0


#: A rule whose own text is shorter than this is a heading — `702.2` is the
#: single word "Deathtouch" and everything that governs lives in `702.2a`
#: onward. Judging derivability from the heading alone would understate what
#: the gold annotation actually points at, so the subtree is rendered too.
HEADING_CHARS = 40


def rule_block(number: str, cr: object) -> list[str]:
    """One gold rule rendered for reading: its text, and its subrules.

    The subtree matters twice. A reader asked whether a key is derivable from
    `613.7` cannot answer it from `613.7` alone — thirteen subrules carry the
    substance. And E-018 injects *rules*, so whether it injects the parent or
    the subtree is a design question the entry never asked; rendering the
    subtree here is what makes that question visible before the run.

    A number whose own text is a bare heading is flagged, because two very
    different things produce one: a legitimate keyword parent, and an
    annotation written against an older CR where that number meant something
    else. Only a reader can tell them apart.
    """
    by_number = cr.by_number  # type: ignore[attr-defined]
    rule = by_number.get(number)
    if rule is None:
        return [f"- **{number}** — ** NOT IN THIS CR. Renumbered or removed."]

    lines = [f"- **{number}** — {rule.text}"]
    if len(rule.text) < HEADING_CHARS:
        lines.append(
            f"  - ⚠ **{number} carries no text of its own here.** Either it is a keyword "
            f"heading whose substance is below, or the key cites it for something this "
            f"CR numbers differently. If it is the second, mark `stale` rather than "
            f"answering the question."
        )
    children = [item for item in cr.subtree(number) if item.number != number]  # type: ignore[attr-defined]
    for child in children:
        lines.append(f"  - {child.number} — {child.text}")
    return lines


def worksheet(args: argparse.Namespace) -> int:
    """Render the sheet to read, and seed the verdict file if it is absent."""
    if not ABSENT_IDS.exists():
        raise SystemExit(f"No frozen population at {ABSENT_IDS}. Run `freeze` first.")
    ids = json.loads(ABSENT_IDS.read_text(encoding="utf-8"))["ids"]
    wanted = gold_rules(args.golden)
    cr = parse_cr()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from audit_correctness import question_and_key

    lines = [
        "# E-018 ceiling worksheet",
        "",
        f"**{QUESTION}**",
        "",
        "Not *would the model get it right* — whether the rules below **contain the",
        "verdict**. A key answered from a ruling, from card text, or from a rule the",
        "annotation did not list is `false`, and that is a finding about the corpus,",
        "not a failure of the question.",
        "",
        f"This count is the maximum number of flips E-018 can produce. Below **{GATE}**",
        "of 21, branch 1 is unreachable by construction and the entry is redesigned",
        "rather than run.",
        "",
        f"Record each verdict in `{VERDICTS}`. Nothing in this file is filled in for",
        "you, and `score` refuses a sheet with a blank.",
        "",
        f"CR effective {cr.effective_date}.",
        "",
        "---",
        "",
    ]
    for index, qid in enumerate(ids, start=1):
        question, key = question_and_key(qid, args.caches, args.golden)
        lines += [f"## {index}. `{qid}`", "", "**Question.** " + question, "", "**Key.**", ""]
        lines += [f"> {para}" for para in key.strip().splitlines() if para.strip()]
        lines += ["", "**Gold CR rules**, each with its subrules.", ""]
        for number in wanted[qid]:
            lines += rule_block(number, cr)
        lines += ["", f"**{QUESTION}**  `true` / `false`", "", "---", ""]

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(ids)} question(s) -> {WORKSHEET}")

    if VERDICTS.exists():
        print(f"{VERDICTS} already exists and was not touched.")
    else:
        payload = {
            "experiment": "E-018",
            "question": QUESTION,
            "gate": GATE,
            "verdicts": [
                # `stale` is not a third answer to the question. It records
                # that the annotation points at a number this CR uses for
                # something else, which is a defect in the key file rather
                # than a fact about the corpus — and which would make E-018
                # inject the wrong rule text and read the result as a null.
                {"question_id": qid, "derivable": None, "stale": False, "note": ""}
                for qid in ids
            ],
        }
        VERDICTS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Seeded {VERDICTS} with {len(ids)} blank verdict(s).")
    print(f"\nNext: read {WORKSHEET}, set every `derivable`, then:")
    print("  python scripts/e018_ceiling.py score")
    return 0


def partition(verdicts: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Split a verdict sheet into derivable, stale and still-blank ids.

    A blank is not a `false`. Treating it as one would let a half-read sheet
    produce a ceiling, and a ceiling over whichever questions happened to be
    read first is not a ceiling.
    """
    derivable = [row["question_id"] for row in verdicts if row.get("derivable") is True]
    stale = [row["question_id"] for row in verdicts if row.get("stale")]
    blank = [row["question_id"] for row in verdicts if row.get("derivable") is None]
    return derivable, stale, blank


def score(args: argparse.Namespace) -> int:
    """The ceiling, with an interval, against the gate registered before it."""
    if not VERDICTS.exists():
        raise SystemExit(f"No verdicts at {VERDICTS}. Run `worksheet` first.")
    payload = json.loads(VERDICTS.read_text(encoding="utf-8"))
    verdicts = payload["verdicts"]
    derivable, stale, blank = partition(verdicts)
    if blank:
        raise SystemExit(
            f"{len(blank)} of {len(verdicts)} verdict(s) are still blank: "
            f"{', '.join(blank[:5])}{'...' if len(blank) > 5 else ''}\n"
            f"A ceiling computed over a partial sheet is a ceiling over whichever "
            f"questions happened to be read first."
        )
    n = len(verdicts)
    interval = wilson_interval(len(derivable), n)

    print(f"{QUESTION}\n")
    print(f"  derivable:  {len(derivable)} of {n}")
    print(f"  proportion: {len(derivable) / n:.3f}  [{interval.low:.3f}, {interval.high:.3f}]")
    print(f"  gate:       {GATE} of {n} ({GATE / n:.3f}), registered before the reading\n")
    if stale:
        print(THIN)
        print(f"** {len(stale)} question(s) carry a gold rule number this CR uses for")
        print(f"   something else: {', '.join(stale)}")
        print("   E-018 would inject the wrong rule text on these and score the result")
        print("   as a null. Fix the key file before the run, or exclude them and say")
        print("   so — they cannot be left as they are.\n")
    print(THIN)
    if len(derivable) < GATE:
        print("BELOW THE GATE. Branch 1 is unreachable by construction: the injection")
        print("cannot produce enough flips to clear the strict Holm step even if it")
        print("works perfectly on every question where it can work at all.")
        print("E-018 is redesigned rather than run. Record this in the registry as the")
        print("ceiling it is, not as a result.")
        return 1
    print("At or above the gate. E-018 can run as amended. This ceiling is the maximum")
    print("number of flips the design can produce — any result above it is a defect in")
    print("the measurement, not a finding.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument(
        "--caches",
        type=Path,
        nargs="+",
        default=None,
        help="where question text and keys live; defaults to run_eval's pair",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze", help="write the two id files, once")
    sub.add_parser("worksheet", help="render the sheet and seed the verdict file")
    sub.add_parser("score", help="the ceiling against the registered gate")
    args = parser.parse_args()

    if args.caches is None:
        from audit_correctness import CACHE_DIR as E007_CACHE_DIR
        from run_eval import CACHE_DIR

        args.caches = [CACHE_DIR, E007_CACHE_DIR]

    return {"freeze": freeze, "worksheet": worksheet, "score": score}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
