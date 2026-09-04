#!/usr/bin/env python
"""Judge against human, read against the ceiling the human set.

E-011 withdrew the hand-picked 0.90 / 0.85 pass marks and replaced them
with one rule: **the judge passes a gated label if the lower bound of the
judge-human agreement interval is at or above the lower bound of that
label's human-ceiling interval.** No other mapping is permitted, so this
script computes exactly that and refuses to print a verdict it cannot
support.

**The human pass is not built here, on purpose.** A blind human pass over
answers already exists — `audit_correctness.py` produces one, and its
worksheets are frozen, seeded and blind to the producing arm. Building a
second worksheet format for the judge audit would be a second instrument
measuring the same thing, and the two would drift. So this reads a
correctness worksheet as the human side and a verdicts file as the judge
side.

The blindness E-011 point 5 asks for — the judge's verdict withheld until
the human's is entered — is satisfied structurally for the dress rehearsal
rather than by a tool: batch 2 was labelled on 2026-09-04, before
`judge.py` existed. For any later audit, `build` draws the sample and the
human labels it before the judge is run over the same rows; `score`
refuses while the worksheet is unfrozen, which is what stops a human pass
from being finished with the verdicts on screen.

Usage:
    python scripts/audit_judge.py score \\
        --worksheet data/golden/p6_correctness_b2_m1.json \\
        --verdicts runs/e001_C-tfidf-routed_verdicts_dev.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.evaluation.rubric import JUDGED, Correctness

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: Registered in E-011: below this many answers *and* this many question
#: clusters, a label is reported descriptively and gates nothing.
AUDIT_FLOOR = 30

#: The reference band, each figure labelled with the sample it came from
#: and how many days separated the two passes. E-011 point 8 corrected an
#: earlier claim that a judge *cannot* exceed a human's self-agreement:
#: judge-vs-human is inter-rater and these are intra-rater, and a judge
#: sharing the first pass's bias can exceed it. They are a band to read
#: against, not a bound.
CEILINGS = {
    "claim factual/non-factual": (0.969, "E-003a, intra-rater, second pass days later"),
    "claim support": (0.818, "E-003a, 8 clusters, interval 0.18 wide"),
    "subgraph sufficiency": (0.500, "E-007c, 10 of 42, not gated"),
}


def load_worksheet(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"No worksheet at {path}.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_verdicts(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"No verdicts at {path}. Run `run_eval.py judge` first.")
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["question_id"]] = row
    return out


def score(args: argparse.Namespace) -> int:
    """Agreement between the judge and the frozen human pass."""
    human = load_worksheet(args.worksheet)
    if not human.get("frozen") and not args.allow_unfrozen:
        raise SystemExit(
            f"{args.worksheet} is not frozen. A human pass finished with the judge's "
            "verdicts available is not a blind pass, and freezing is what makes the "
            "ordering checkable afterwards."
        )
    verdicts = load_verdicts(args.verdicts)
    if verdicts and human.get("rubric_hash"):
        first = next(iter(verdicts.values()))
        if first.get("rubric_hash") and first["rubric_hash"] != human["rubric_hash"]:
            raise SystemExit(
                "The judge and the human read different rubrics. Their agreement would "
                "not describe one instrument."
            )

    pairs: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for qid, row in human["labels"].items():
        label = (row.get("label") or "").strip()
        if not label:
            raise SystemExit(f"{qid} is unlabelled in {args.worksheet}.")
        if qid not in verdicts:
            missing.append(qid)
            continue
        pairs.append((qid, label, verdicts[qid]["label"]))

    print(f"human   {args.worksheet}   batch {human.get('batch', '?')}   "
          f"arm {human.get('arm', '?')}")
    print(f"judge   {args.verdicts}")
    print(f"rubric  {human.get('rubric_version')} @ {str(human.get('rubric_hash'))[:12]}")
    if missing:
        print(f"{len(missing)} labelled answer(s) have no verdict: {', '.join(missing[:5])}")
    print(RULE)

    # One answer is one question is one cluster for correctness, unlike the
    # claim-level labels where several claims share a question. Printed
    # rather than assumed, because E-011 requires n_clusters beside n and a
    # figure that silently equates them elsewhere would be wrong.
    clusters = len({qid for qid, _, _ in pairs})
    agreed = [h == j for _, h, j in pairs]
    interval = wilson_interval(sum(agreed), len(agreed))
    print(f"exact agreement {sum(agreed)}/{len(agreed)} = {interval.point:.3f} "
          f"[{interval.low:.3f}, {interval.high:.3f}]   n_clusters {clusters}")

    print("\nper label (human's label is the denominator):")
    for label in JUDGED:
        rows = [(h, j) for _, h, j in pairs if h == label.value]
        if not rows:
            continue
        hits = [h == j for h, j in rows]
        cell = wilson_interval(sum(hits), len(hits))
        gate = "gated" if len(rows) >= AUDIT_FLOOR else "descriptive"
        print(f"  {label.value:<12} {sum(hits):>3}/{len(rows):<3} = {cell.point:.3f} "
              f"[{cell.low:.3f}, {cell.high:.3f}]   {gate}")

    print("\nconfusion (human -> judge), disagreements only:")
    confusion = Counter((h, j) for _, h, j in pairs if h != j)
    for (h, j), count in confusion.most_common():
        print(f"  {h:<10} -> {j:<10} {count}")

    print(RULE)
    if len(pairs) < AUDIT_FLOOR or clusters < AUDIT_FLOOR:
        print(f"{len(pairs)} answers and {clusters} clusters, below the registered floor of "
              f"{AUDIT_FLOOR}.")
        print("Reported descriptively. This gates nothing, and no correctness figure may")
        print("be published as validated on it.")
    else:
        print("The gate is the correctness ceiling's lower bound, once that ceiling exists.")
        print("E-011 permits no other mapping, and the ceiling's second pass is not due yet.")

    print("\nreference band — other labels' intra-rater ceilings, not bounds on this:")
    for name, (value, note) in CEILINGS.items():
        print(f"  {name:<28} {value:.3f}   {note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scorer = sub.add_parser("score", help="judge against a frozen human pass")
    scorer.add_argument("--worksheet", type=Path, required=True)
    scorer.add_argument("--verdicts", type=Path, required=True)
    scorer.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="score against an unfrozen human pass; records nothing and is for smoke runs",
    )
    scorer.set_defaults(func=score)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
