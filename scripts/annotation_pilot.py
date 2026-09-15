#!/usr/bin/env python
"""Time five `interaction_multihop` annotations before promising forty-nine.

E-019 registers n = 49 per stratum. Nobody has ever timed one of these
annotations, so 49 is a number the entry asserts and nothing supports. This
measures it on five and turns the measurement into one of three pre-fixed
verdicts.

**The decision rule is in this file before the stopwatch starts**, which is the
whole point. E-024 chose a boundary after seeing its control arm and returned
nothing; a pilot that measures the time and *then* decides what was acceptable
is the same instrument defect wearing a stopwatch.

**Design B has almost no room to shrink**, and that is what makes this pilot
close to binary rather than a dial. Permutation power against n per stratum:

    n = 49 -> 0.78     n = 40 -> 0.63     n = 30 -> 0.49     n = 24 -> 0.43

Below about 40 the entry is E-025 again: designed to return `inconclusive` at
every n it can reach. So the honest outcomes are *proceed at 49*, *proceed at
40 with the power restated*, or *Design B is not curatable and E-019 needs a
different design* — not "do as many as we can and see".

**The five are not thrown away.** They are the first five of the 49, annotated
under the same guide. A learning curve makes the first five *slower* than
steady state, which biases this pilot toward pessimism — the safe direction.

**There are two human costs here, not one, and the second scales with the pool
rather than with n.** `classify_pool.py` is a per-question human workflow —
`sheet`, then `show`/`set` for each candidate, then `apply` — and it runs over
*every* candidate to find the ones that are `interaction_multihop`. In the
golden set that stratum was **30 of 77 rows, a yield of 0.39**, so reaching 49
annotated questions means classifying roughly **126** candidates first. A
projection that prices only the annotation is low by the whole classification
pass, which is why this times both.

Prerequisite: a fresh candidate pool that excludes everything already spent.

    python scripts/build_golden_pool.py --per-stratum 30 \\
        --out data/golden/phase10_pool_v0.jsonl \\
        --exclude data/golden/ids_v0.jsonl data/golden/e007_audit_pool.jsonl \\
        --cache-dir data/interim/phase10_cache
    python scripts/classify_pool.py --pool data/golden/phase10_pool_v0.jsonl sheet

Usage:
    python scripts/annotation_pilot.py classify start
    python scripts/annotation_pilot.py classify stop --count 30
    python scripts/annotation_pilot.py draw
    python scripts/annotation_pilot.py start 1
    python scripts/annotation_pilot.py stop 1
    python scripts/annotation_pilot.py report
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

#: Ids and seconds only. Committable: no question text, no keys, no CR text.
TIMING = Path("data/golden/e019_pilot_timing.json")

#: Question and key text live here, gitignored, like every other worksheet.
WORKSHEET = Path("data/interim/e019_pilot_worksheet.md")

#: The candidate pool this draws from, produced by the two commands in the
#: docstring above. Not created here: drawing and fetching are different jobs
#: and a pilot that can fetch is a pilot that can quietly re-draw.
POOL = Path("data/golden/phase10_pool_v0.jsonl")

STRATUM = "interaction_multihop"
PILOT_N = 5

#: Recorded so the draw is reproducible and so nobody can re-draw until the
#: sample looks easy. Changing this after a draw exists is caught by `draw`.
DRAW_SEED = 20260914

#: E-019's registered target, and the two fallbacks that still carry power.
#: Straight from the entry's permutation column.
POWER_AT = {49: 0.78, 40: 0.63, 30: 0.49, 24: 0.43}
TARGET_N = 49
FLOOR_N = 40

#: How many candidates classify as `interaction_multihop`, measured on the
#: golden set: 30 of its 77 rows. Used to price the classification pass, which
#: runs over every candidate rather than over the n that survive it.
#:
#: It is an estimate from one pool and RulesGuru's mix may differ; `report`
#: prints the implied candidate count so the assumption is visible rather than
#: buried in a multiplication.
CLASSIFY_YIELD = 30 / 77

#: ** THE ONE NUMBER THAT IS THE AUTHOR'S AND NOT THE INSTRUMENT'S. **
#:
#: Hours the author is willing to spend annotating `interaction_multihop` for
#: this phase. Everything else here is arithmetic; this is a preference, and
#: putting it in code rather than in a conversation is what stops it being
#: revised upward at the moment the projection comes back inconvenient.
#:
#: 20 hours over 49 questions is about 24 minutes each. It is a placeholder
#: until the author confirms or replaces it, and `report` refuses to run while
#: it is still marked unconfirmed.
BUDGET_HOURS = 20.0
BUDGET_CONFIRMED = False


def load_pool() -> list[dict]:
    """The classified candidate pool, refusing to guess where it is.

    Raises:
        SystemExit: when the pool does not exist, naming the two commands that
            build it rather than failing on a missing path.
    """
    if not POOL.exists():
        raise SystemExit(
            f"No candidate pool at {POOL}.\n"
            "  python scripts/build_golden_pool.py --per-stratum 30 \\\n"
            f"      --out {POOL} \\\n"
            "      --exclude data/golden/ids_v0.jsonl "
            "data/golden/e007_audit_pool.jsonl \\\n"
            "      --cache-dir data/interim/phase10_cache\n"
            f"  python scripts/classify_pool.py --pool {POOL}"
        )
    return [json.loads(line) for line in POOL.read_text(encoding="utf-8").splitlines() if line.strip()]


def draw(args: argparse.Namespace) -> int:
    """Draw five at a recorded seed, once, and refuse to re-draw.

    A pilot that can be re-drawn is a pilot that reports the timing of the
    easiest five somebody kept drawing until they got.
    """
    carried = {"started": None, "seconds": None, "count": None}
    if TIMING.exists():
        existing = json.loads(TIMING.read_text(encoding="utf-8"))
        if existing.get("rows"):
            raise SystemExit(
                f"A pilot already exists at {TIMING.as_posix()}, drawn at seed "
                f"{existing.get('seed')} on {existing.get('drawn')}.\n"
                "Re-drawing would let the sample be chosen after seeing it. "
                "Delete the file deliberately if the pool itself changed."
            )
        # A classification pass timed before the draw is kept: it happens first
        # by necessity, since the draw selects from what it produced.
        carried = existing.get("classification", carried)

    import random

    candidates = sorted(
        row["id"] for row in load_pool() if row.get("stratum") == STRATUM
    )
    if len(candidates) < PILOT_N:
        raise SystemExit(
            f"Only {len(candidates)} {STRATUM} candidate(s) in {POOL.as_posix()}; "
            f"need at least {PILOT_N}. Widen --per-stratum and re-run the pool build."
        )
    chosen = random.Random(DRAW_SEED).sample(candidates, PILOT_N)

    payload = {
        "experiment": "E-019",
        "what": "curation cost pilot: how long does one interaction_multihop annotation take",
        "stratum": STRATUM,
        "seed": DRAW_SEED,
        "drawn": datetime.now(UTC).date().isoformat(),
        "pool": POOL.as_posix(),
        "candidates_available": len(candidates),
        "budget_hours": BUDGET_HOURS,
        "target_n": TARGET_N,
        "floor_n": FLOOR_N,
        "classification": carried,
        "rows": [
            {"question_id": qid, "started": None, "seconds": None, "note": ""}
            for qid in chosen
        ],
    }
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"{RULE}\nE-019 CURATION PILOT — {PILOT_N} of {len(candidates)} available\n{RULE}\n")
    for index, qid in enumerate(chosen, start=1):
        print(f"  {index}. {qid}")
    print(
        f"\nSeed {DRAW_SEED}, recorded. Timing file: {TIMING.as_posix()}\n"
        f"Question and key text: {WORKSHEET.as_posix()} (gitignored)\n\n"
        "Annotate each one by docs/annotation-guide.md, in full, as if it were\n"
        "going into the split — because it is. Time only the annotation:\n\n"
        "  python scripts/annotation_pilot.py start 1\n"
        "  python scripts/annotation_pilot.py stop 1"
    )
    return 0


def load_timing(create: bool = False) -> dict:
    """The timing file, refusing to proceed before `draw` has written one.

    Args:
        create: return an empty skeleton instead of failing. Only the
            classification pass needs this: it necessarily runs before the
            draw, because the draw selects from what it produced.
    """
    if not TIMING.exists():
        if create:
            return {
                "experiment": "E-019",
                "what": "curation cost pilot",
                "classification": {"started": None, "seconds": None, "count": None},
                "rows": [],
            }
        raise SystemExit(
            f"No pilot at {TIMING.as_posix()}.\n  python scripts/annotation_pilot.py draw"
        )
    return json.loads(TIMING.read_text(encoding="utf-8"))


def classify(args: argparse.Namespace) -> int:
    """Time the classification pass over the whole candidate pool.

    One wall-clock block, not per question: classification is done in a sitting
    over the sheet, and `--count` records how many candidates it covered so the
    per-candidate cost is a division rather than a guess.
    """
    payload = load_timing(create=True)
    block = payload.setdefault(
        "classification", {"started": None, "seconds": None, "count": None}
    )
    if args.phase == "start":
        if block["seconds"] is not None:
            print(f"** classification already recorded at {block['seconds']}s — restarting.")
            block["seconds"] = None
        block["started"] = time.time()
        print("classification: started.  Stop with:  "
              "python scripts/annotation_pilot.py classify stop --count N")
    else:
        if block["started"] is None:
            raise SystemExit(
                "Classification was never started. Elapsed time is not "
                "reconstructable after the fact."
            )
        if not args.count:
            raise SystemExit(
                "--count is required: how many candidates this pass classified. "
                "Without it the per-candidate cost is a guess, and the whole "
                "point of this pilot is that it is not."
            )
        block["seconds"] = round(time.time() - block["started"], 1)
        block["started"] = None
        block["count"] = args.count
        per = block["seconds"] / args.count / 60
        print(
            f"classification: {block['seconds'] / 60:.1f} min over {args.count} "
            f"candidate(s) — {per:.1f} min each."
        )
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def resolve(target: str, rows: list[dict]) -> int:
    """A pilot number or a question id, to a row index.

    Raises:
        SystemExit: when the target names no row, rather than timing whichever
            row happened to be first.
    """
    if target.isdigit():
        index = int(target) - 1
        if not 0 <= index < len(rows):
            raise SystemExit(f"{target} is not one of 1..{len(rows)}.")
        return index
    for index, row in enumerate(rows):
        if row["question_id"] == target:
            return index
    raise SystemExit(f"No question {target!r} in the pilot.")


def start(args: argparse.Namespace) -> int:
    """Mark one annotation as begun. Restarting is allowed and announced."""
    payload = load_timing()
    row = payload["rows"][resolve(args.target, payload["rows"])]
    if row["seconds"] is not None:
        print(f"** {row['question_id']} already recorded at {row['seconds']}s — restarting it.")
        row["seconds"] = None
    row["started"] = time.time()
    TIMING.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{row['question_id']}: started.  Stop with:  "
          f"python scripts/annotation_pilot.py stop {args.target}")
    return 0


def stop(args: argparse.Namespace) -> int:
    """Record elapsed seconds for one annotation."""
    payload = load_timing()
    row = payload["rows"][resolve(args.target, payload["rows"])]
    if row["started"] is None:
        raise SystemExit(
            f"{row['question_id']} was never started. Elapsed time is not "
            "reconstructable after the fact, and guessing it would put an "
            "invented number where the whole point is a measured one."
        )
    row["seconds"] = round(time.time() - row["started"], 1)
    row["started"] = None
    if args.note:
        row["note"] = args.note
    TIMING.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    done = [r for r in payload["rows"] if r["seconds"] is not None]
    print(f"{row['question_id']}: {row['seconds'] / 60:.1f} min.")
    print(f"{len(done)} of {len(payload['rows'])} timed.")
    if len(done) == len(payload["rows"]):
        print("Run `python scripts/annotation_pilot.py report`.")
    return 0


def hours_for(n: int, annotate_minutes: float, classify_minutes: float | None) -> float:
    """Total human hours to reach n annotated questions of this stratum.

    Annotation is paid n times. **Classification is paid on every candidate it
    takes to find those n**, which at the golden set's yield is about 2.6
    candidates per keeper — the cost a projection over n alone leaves out.
    """
    total = n * annotate_minutes
    if classify_minutes is not None:
        total += (n / CLASSIFY_YIELD) * classify_minutes
    return total / 60


def verdict(
    median_minutes: float, classify_minutes: float | None = None
) -> tuple[str, str]:
    """The three pre-fixed outcomes, applied to measured times.

    Returns:
        A branch id and the sentence that goes in the amendment. The branch
        ids exist so that the branch **not** taken is testable, which is what
        E-018's analysis added after the fact and this has from the start.
    """
    hours_at = {
        n: hours_for(n, median_minutes, classify_minutes) for n in (TARGET_N, FLOOR_N)
    }
    if hours_at[TARGET_N] <= BUDGET_HOURS:
        return "1", (
            f"Proceed at n = {TARGET_N}. Projected "
            f"{hours_at[TARGET_N]:.1f}h against a {BUDGET_HOURS:.0f}h budget. "
            "E-019 stands as registered."
        )
    if hours_at[FLOOR_N] <= BUDGET_HOURS:
        return "2", (
            f"Amend E-019 to n = {FLOOR_N} per stratum and restate the power as "
            f"{POWER_AT[FLOOR_N]:.2f}, not 0.78. Projected "
            f"{hours_at[FLOOR_N]:.1f}h at {FLOOR_N} against {BUDGET_HOURS:.0f}h. "
            "The amendment says the entry is now more likely than not to return "
            "inconclusive, and the author decides whether that is worth "
            "curating for."
        )
    return "3", (
        f"Design B is not curatable at this budget: {hours_at[FLOOR_N]:.1f}h "
        f"even at the floor of {FLOOR_N}, where power is already "
        f"{POWER_AT[FLOOR_N]:.2f}. E-019 needs a different design, not a "
        "smaller n. Curating below the floor reproduces E-025 — an entry that "
        "returns inconclusive at every n it can reach."
    )


def report(args: argparse.Namespace) -> int:
    """The measured cost, projected, against the rule fixed before the timing.

    Raises:
        SystemExit: on a partial pilot, or while the budget is unconfirmed. A
            projection from three of five is a projection from whichever three
            finished first.
    """
    if not BUDGET_CONFIRMED:
        raise SystemExit(
            f"BUDGET_HOURS is still {BUDGET_HOURS:.0f} and marked unconfirmed.\n"
            "It is the author's number, not the instrument's, and the verdict "
            "is a function of it.\nSet BUDGET_CONFIRMED = True in this file "
            "once the author has confirmed or replaced it — before reading any "
            "timing, not after."
        )
    payload = load_timing()
    rows = payload["rows"]
    blank = [r["question_id"] for r in rows if r["seconds"] is None]
    if blank:
        raise SystemExit(
            f"{len(blank)} not timed: {', '.join(blank)}.\n"
            "No projection from a partial pilot."
        )

    minutes = sorted(r["seconds"] / 60 for r in rows)
    median = statistics.median(minutes)

    print(f"{RULE}\nE-019 CURATION PILOT — {len(rows)} {STRATUM} annotations\n{RULE}\n")
    for row in rows:
        note = f"   {row['note']}" if row.get("note") else ""
        print(f"  {row['question_id']:<12}{row['seconds'] / 60:>7.1f} min{note}")
    print(
        f"\n  median {median:.1f} min   range {minutes[0]:.1f}-{minutes[-1]:.1f}"
        f"   total {sum(minutes) / 60:.1f}h"
    )
    print(
        "\nFive is enough to separate 15 minutes from 90 and is not enough to\n"
        "estimate a mean. The median of five is what this reports, and the\n"
        "range is printed because it is the part that decides whether a\n"
        "projection means anything."
    )

    block = payload.get("classification") or {}
    classify_minutes = None
    if block.get("seconds") is not None and block.get("count"):
        classify_minutes = block["seconds"] / block["count"] / 60
        print(
            f"\n  classification: {classify_minutes:.1f} min per candidate, "
            f"measured over {block['count']}"
        )
    else:
        print(
            "\n** Classification was not timed, so the projection below prices "
            "annotation only.\n"
            "   It runs over every candidate, not over the keepers, and at the "
            "golden set's\n"
            "   yield that is about 2.6 candidates per keeper. The numbers "
            "below are a floor."
        )

    print(f"\n{THIN}\nPROJECTION\n{THIN}")
    for n, power in sorted(POWER_AT.items(), reverse=True):
        hours = hours_for(n, median, classify_minutes)
        flag = "  <- registered" if n == TARGET_N else ("  <- floor" if n == FLOOR_N else "")
        candidates = f"  ({n / CLASSIFY_YIELD:.0f} candidates)" if classify_minutes else ""
        print(f"  n={n:>3}   power {power:.2f}   {hours:>6.1f}h{candidates}{flag}")
    print(f"\n  budget: {BUDGET_HOURS:.0f}h (author's, confirmed)")
    print(
        f"  yield assumed: {CLASSIFY_YIELD:.2f} — {STRATUM} was 30 of the "
        "golden set's 77 rows.\n  If RulesGuru's mix differs, every candidate "
        "count above moves with it."
    )

    branch, sentence = verdict(median, classify_minutes)
    print(f"\n{RULE}\nBRANCH {branch}\n{RULE}\n{sentence}")
    print(
        "\nThis verdict was fixed in `verdict()` before any question was timed. "
        "If it reads as the wrong call now, that is an argument for amending "
        "E-019, not for editing the rule that just produced it."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    classifier = sub.add_parser("classify", help="time the classification pass over the pool")
    classifier.add_argument("phase", choices=("start", "stop"))
    classifier.add_argument(
        "--count", type=int, default=None, help="candidates this pass covered (required on stop)"
    )
    sub.add_parser("draw", help="draw five at the recorded seed, once")
    starter = sub.add_parser("start", help="begin timing one annotation")
    starter.add_argument("target", help="pilot number 1..5, or a question id")
    stopper = sub.add_parser("stop", help="record elapsed time for one annotation")
    stopper.add_argument("target", help="pilot number 1..5, or a question id")
    stopper.add_argument("--note", default=None, help="what made this one slow or fast")
    sub.add_parser("report", help="the projection and the pre-fixed verdict")
    args = parser.parse_args()
    commands = {
        "classify": classify,
        "draw": draw,
        "start": start,
        "stop": stop,
        "report": report,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
