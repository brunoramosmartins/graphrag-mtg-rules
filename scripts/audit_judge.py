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
from graphrag_mtg.evaluation.rubric import JUDGED

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


def collect(worksheet: Path, verdict_paths: list[Path], allow_unfrozen: bool) -> tuple[dict, list, list]:
    """One batch's (human, judge) label pairs, after its guards.

    `verdict_paths` is a list because a batch's answers can be split
    across files — E-011a's batch 1 is E-007's audit side and dev side,
    generated separately — and a batch scored on only one of them would
    silently shrink its own denominator.
    """
    human = load_worksheet(worksheet)
    if not human.get("frozen") and not allow_unfrozen:
        raise SystemExit(
            f"{worksheet} is not frozen. A human pass finished with the judge's "
            "verdicts available is not a blind pass, and freezing is what makes the "
            "ordering checkable afterwards."
        )
    verdicts: dict[str, dict] = {}
    for path in verdict_paths:
        verdicts.update(load_verdicts(path))
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
            raise SystemExit(f"{qid} is unlabelled in {worksheet}.")
        if qid not in verdicts:
            missing.append(qid)
            continue
        pairs.append((qid, label, verdicts[qid]["label"]))

    return human, pairs, missing


def per_label(pairs: list) -> None:
    """Agreement broken down by the human's label.

    E-011 gates per label rather than in aggregate: a judge perfect on
    `incorrect` and hopeless on `partial` passes an aggregate and should
    not. The floor applies per label too, which is why each row says
    whether it is gated or descriptive.
    """
    print("  per label (human's label is the denominator):")
    for label in JUDGED:
        rows = [(h, j) for _, h, j in pairs if h == label.value]
        if not rows:
            continue
        hits = [h == j for h, j in rows]
        cell = wilson_interval(sum(hits), len(hits))
        gate = "gated" if len(rows) >= AUDIT_FLOOR else "descriptive"
        print(f"    {label.value:<12} {sum(hits):>3}/{len(rows):<3} = {cell.point:.3f} "
              f"[{cell.low:.3f}, {cell.high:.3f}]   {gate}")


def report(human: dict, pairs: list, missing: list, verdict_paths: list[Path]) -> list[bool]:
    """Print one batch's figures; return the hits the pool should carry."""
    print(f"\nbatch {human.get('batch', '?')}   arm {human.get('arm', '?')}   "
          f"{len(pairs)} pair(s)")
    print(f"  judge   {', '.join(path.name for path in verdict_paths)}")
    if missing:
        print(f"  {len(missing)} labelled answer(s) have no verdict: "
              f"{', '.join(missing[:5])}")

    # One answer is one question is one cluster for correctness, unlike the
    # claim-level labels where several claims share a question. Printed
    # rather than assumed, because E-011 requires n_clusters beside n and a
    # figure that silently equates them elsewhere would be wrong.
    clusters = len({qid for qid, _, _ in pairs})
    agreed = [h == j for _, h, j in pairs]
    interval = wilson_interval(sum(agreed), len(agreed))
    print(f"  exact agreement {sum(agreed)}/{len(agreed)} = {interval.point:.3f} "
          f"[{interval.low:.3f}, {interval.high:.3f}]   n_clusters {clusters}")
    per_label(pairs)

    confusion = Counter((h, j) for _, h, j in pairs if h != j)
    if confusion:
        print("  confusion (human -> judge), disagreements only:")
        for (h, j), count in confusion.most_common():
            print(f"    {h:<10} -> {j:<10} {count}")
    return agreed


def score(args: argparse.Namespace) -> int:
    """Every batch's agreement, then the pool, then the gate.

    Batches are pooled because the ceiling they are read against is
    pooled: E-011a's rule reads one interval over both, and comparing a
    per-batch judge figure to a pooled human ceiling would put two
    different samples on the two sides of the same inequality.
    """
    batches = [
        collect(worksheet, verdicts, args.allow_unfrozen)
        for worksheet, verdicts in zip(args.worksheet, args.verdicts, strict=True)
    ]
    rubrics = {human.get("rubric_hash") for human, _, _ in batches}
    if len(rubrics) > 1:
        raise SystemExit(
            "The batches were labelled under different rubrics. Pooling them would "
            "average two instruments."
        )
    print(f"rubric  {batches[0][0].get('rubric_version')} @ {str(next(iter(rubrics)))[:12]}")
    print(RULE)

    agreed: list[bool] = []
    pooled_pairs: list = []
    for (human, pairs, missing), verdicts in zip(batches, args.verdicts, strict=True):
        agreed.extend(report(human, pairs, missing, verdicts))
        pooled_pairs.extend(pairs)

    print(RULE)
    interval = wilson_interval(sum(agreed), len(agreed))
    names = ", ".join(human.get("batch", "?") for human, _, _ in batches)
    print(f"pooled over {len(batches)} batch(es) ({names}): {sum(agreed)}/{len(agreed)} = "
          f"{interval.point:.3f} [{interval.low:.3f}, {interval.high:.3f}]")
    per_label(pooled_pairs)

    print(RULE)
    # The sample-size status prints whether or not a ceiling was supplied.
    # The restructure that split this function moved it inside the gating
    # branch, so a run without a ceiling said nothing about how thin its
    # sample was — and a reader seeing 0.895 with no floor warning is a
    # reader being invited to believe it. Size is a fact about the audit,
    # not a step in the gate.
    thin = [
        label.value
        for label in JUDGED
        if len([1 for _, h, _ in pooled_pairs if h == label.value]) < AUDIT_FLOOR
    ]
    if thin:
        print(f"below the registered floor of {AUDIT_FLOOR}: {', '.join(thin)}")
        # The consequence, not just the status. An earlier rewrite kept the
        # "descriptive" half and dropped "no correctness figure may be
        # published as validated on them", which is the only part that
        # tells a reader what they may not do with the number above.
        print("Those labels are descriptive and gate nothing, and no correctness figure")
        print("may be published as validated on them.")

    if args.ceiling_low is None:
        print("\nNo ceiling supplied, so nothing is gated. Pass --ceiling-low with the lower")
        print("bound printed by `audit_correctness.py reaudit score` — E-011 permits no")
        print("other mapping from a ceiling to a threshold.")
        reference_band()
        return 0

    print(f"\nceiling lower bound (the registered threshold): {args.ceiling_low:.3f}")
    gated = 0
    for label in JUDGED:
        rows = [(h, j) for _, h, j in pooled_pairs if h == label.value]
        if len(rows) < AUDIT_FLOOR:
            print(f"  {label.value:<12} n={len(rows)} < {AUDIT_FLOOR} — not gated, descriptive")
            continue
        gated += 1
        cell = wilson_interval(sum(h == j for h, j in rows), len(rows))
        verdict = "PASS" if cell.low >= args.ceiling_low else "FAIL"
        print(f"  {label.value:<12} lower bound {cell.low:.3f} vs {args.ceiling_low:.3f}  {verdict}")
    if not gated:
        print("\nNo label reaches the registered floor, so the judge is neither passed nor "
              "failed.")
        print("That is a fact about the audit's size, not about the judge.")
    reference_band()
    return 0


def reference_band() -> None:
    """The intra-rater ceilings, each labelled with where it came from.

    E-011 point 8 corrected an earlier claim that a judge *cannot* exceed a
    human's self-agreement — judge-vs-human is inter-rater and these are
    intra-rater, and a judge sharing the first pass's bias can exceed it.
    Printed on every path: the restructure that split `score` dropped it
    from the no-ceiling branch, and a band that appears only sometimes is
    a band a reader cannot rely on.
    """
    print("\nreference band — other labels' intra-rater ceilings, not bounds on this:")
    for name, (value, note) in CEILINGS.items():
        print(f"  {name:<28} {value:.3f}   {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scorer = sub.add_parser("score", help="judge against frozen human passes")
    scorer.add_argument("--worksheet", type=Path, nargs="+", required=True)
    scorer.add_argument(
        "--verdicts",
        type=Path,
        nargs="+",
        action="append",
        required=True,
        help="one --verdicts per --worksheet; repeat the flag, listing that batch's files",
    )
    scorer.add_argument(
        "--ceiling-low",
        type=float,
        default=None,
        help="the lower bound from `audit_correctness.py reaudit score`; without it "
        "nothing is gated",
    )
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
