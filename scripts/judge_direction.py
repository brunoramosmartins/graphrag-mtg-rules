#!/usr/bin/env python
"""Does the judge disagree with the human at random, or in one direction?

A re-analysis of E-011a's existing labels. No API, no new annotation: the 55
audited answers were labelled in September and this reads them again asking a
question the original entry did not.

**Why the question is worth asking.** E-011a reported three-way agreement of
0.727 [0.598, 0.827] and concluded that `partial` is the instrument's weak
point. True, and it leaves two things unmeasured:

1. **The published figures do not use the three-way labels.** E-001 registered a
   two-way collapse, `correct` against everything else. An audit of a
   distinction no published number depends on is auditing the wrong thing.
2. **A disagreement has a direction.** Agreement counts treat "the judge said
   `incorrect` where the human said `partial`" and its reverse as the same
   event. If every disagreement runs one way, the judge is not noisy — it is
   *biased*, and a uniformly biased grader applied to both arms leaves a
   comparison intact while making the absolute figures a floor.

Both are answered by counting cells that already exist.

Usage:
    python scripts/judge_direction.py
"""

from __future__ import annotations

import argparse
import json
import sys
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

#: The human passes E-011a froze, batch 1 and batch 2. `m1` is the first pass;
#: `m2` is the blind re-read used for the self-agreement threshold and is not
#: the comparand here.
HUMAN_FILES = (
    Path("data/golden/p6_correctness_m1.json"),
    Path("data/golden/p6_correctness_b2_m1.json"),
)

#: The runs those answers were drawn from, named in each file's `sources`.
JUDGE_FILES = (
    Path("runs/e007_verdicts_audit.jsonl"),
    Path("runs/e007_verdicts_dev.jsonl"),
    Path("runs/e001_C-tfidf-routed_verdicts_dev.jsonl"),
)

#: Ordered from best to worst. The ordering is what makes "the judge never
#: scored *up*" a statement rather than an impression: it is the claim that the
#: confusion matrix is zero below its diagonal.
LADDER = ("correct", "partial", "incorrect")

#: E-011's registered pass mark: the lower bound of the human's own
#: self-agreement interval. Not chosen here and not adjustable here.
THRESHOLD = 0.720

#: E-011 gates per label at this size. Reported against, never quietly relaxed.
GATE_N = 30

#: E-011a's published three-way figure, checked against on every run. A
#: re-analysis that cannot reproduce the original number is re-analysing
#: something else.
PUBLISHED_THREE_WAY = (40, 55)


def wilson(hits: int, total: int) -> tuple[float, float]:
    """Wilson score interval, the project's standard for a proportion."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.96
    rate = hits / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    half = z * sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_labels() -> tuple[dict[str, str], dict[str, str]]:
    """The human's first-pass labels and the judge's, keyed by question.

    Raises:
        SystemExit: when a file is missing, naming it. Silently auditing
            whichever batch happened to be on disk is how a pooled figure
            becomes a batch figure without anyone noticing.
    """
    human: dict[str, str] = {}
    for path in HUMAN_FILES:
        if not path.exists():
            raise SystemExit(f"Missing human pass: {path.as_posix()}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for qid, record in payload["labels"].items():
            human[qid] = record["label"]

    judge: dict[str, str] = {}
    for path in JUDGE_FILES:
        if not path.exists():
            raise SystemExit(f"Missing judge verdicts: {path.as_posix()}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                judge.setdefault(row["question_id"], row["label"])
    return human, judge


def confusion(
    human: dict[str, str], judge: dict[str, str], ids: list[str]
) -> dict[tuple[str, str], int]:
    """Counts of (human label, judge label) over the audited answers."""
    table: dict[tuple[str, str], int] = {}
    for qid in ids:
        key = (human[qid], judge[qid])
        table[key] = table.get(key, 0) + 1
    return table


def scored_up(table: dict[tuple[str, str], int]) -> int:
    """Answers the judge graded **better** than the human did.

    Zero is the finding. Anything else means the judge is noisy rather than
    strict, and every conclusion below about the figures being a floor stops
    holding.
    """
    rank = {label: index for index, label in enumerate(LADDER)}
    return sum(count for (h, j), count in table.items() if rank[j] < rank[h])


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    human, judge = load_labels()
    ids = sorted(set(human) & set(judge))
    table = confusion(human, judge, ids)

    print(f"{RULE}\nE-011a RE-ANALYSED — the direction of the judge's disagreements\n{RULE}\n")

    three = sum(count for (h, j), count in table.items() if h == j)
    hits, total = PUBLISHED_THREE_WAY
    if (three, len(ids)) != (hits, total):
        raise SystemExit(
            f"This reproduces {three}/{len(ids)} three-way, and E-011a published "
            f"{hits}/{total}.\nA re-analysis that cannot reproduce the original "
            "figure is re-analysing a different population. Reconcile first."
        )
    low3, high3 = wilson(three, len(ids))
    print(
        f"Reproduces E-011a exactly: three-way {three}/{len(ids)} = "
        f"{three / len(ids):.3f} [{low3:.3f}, {high3:.3f}]."
    )

    print(f"\n{THIN}\nCONFUSION — human (rows) against judge (columns)\n{THIN}")
    print(f"{'':<12}" + "".join(f"{label:>11}" for label in LADDER))
    for h in LADDER:
        print(f"{h:<12}" + "".join(f"{table.get((h, j), 0):>11}" for j in LADDER))

    up = scored_up(table)
    print(f"\n  answers the judge graded BETTER than the human: **{up}**")
    if up == 0:
        print(
            "  Every disagreement runs one way. The judge is not noisy about\n"
            "  correctness; it is strict, and a uniformly strict grader applied to\n"
            "  both arms leaves the comparison intact while making each arm's\n"
            "  absolute figure a floor rather than an estimate."
        )

    print(f"\n{THIN}\nTHE COLLAPSE E-001 ACTUALLY PUBLISHES\n{THIN}")
    collapsed = sum(
        count for (h, j), count in table.items() if (h == "correct") == (j == "correct")
    )
    low2, high2 = wilson(collapsed, len(ids))
    print(
        f"  two-way (`correct` against everything else): {collapsed}/{len(ids)} = "
        f"{collapsed / len(ids):.3f} [{low2:.3f}, {high2:.3f}]"
    )
    for name, want in (("human correct", True), ("human not correct", False)):
        cells = [
            (k, v) for k, v in table.items() if (k[0] == "correct") == want
        ]
        cell_total = sum(v for _, v in cells)
        cell_hits = sum(v for (h, j), v in cells if (j == "correct") == want)
        low, high = wilson(cell_hits, cell_total)
        gate = "" if cell_total >= GATE_N else f"   ** below the registered gate of {GATE_N}"
        print(
            f"    {name:<20}{cell_hits:>3}/{cell_total:<4}"
            f"{cell_hits / cell_total:>8.3f} [{low:.3f}, {high:.3f}]{gate}"
        )

    print(f"\n  E-011's registered pass mark: {THRESHOLD:.3f}")
    print(
        f"    pooled three-way lower bound {low3:.3f}\n"
        f"    pooled two-way   lower bound {low2:.3f}"
    )
    print(
        "\n  ** Neither pooled figure is the gate. E-011 gates PER LABEL, and\n"
        "     pooling is what makes the collapse look strong: it merges the cell\n"
        "     the judge is weakest on with one it gets right 37 of 37 times."
    )
    worst = min(
        (
            wilson(
                sum(v for (h, j), v in table.items() if (h == "correct") == want and (j == "correct") == want),
                sum(v for (h, _), v in table.items() if (h == "correct") == want),
            )[0],
            "correct" if want else "not correct",
        )
        for want in (True, False)
    )
    print(
        f"     Per cell, the weakest is `{worst[1]}` at a lower bound of "
        f"{worst[0]:.3f},\n     which is {'above' if worst[0] >= THRESHOLD else 'BELOW'} "
        f"{THRESHOLD:.3f}. **The collapse does not rescue the gate.**\n"
        "     What it changes is the size of the gap, not its sign."
    )

    correct_cells = sum(v for (h, _), v in table.items() if h == "correct")
    rate = correct_cells / len(ids)
    print(
        f"\n  To reach n = {GATE_N} in the thinner cell at the observed rate of\n"
        f"  {rate:.3f}: roughly **{round(GATE_N / rate)}** audited answers, so about\n"
        f"  **{round(GATE_N / rate) - len(ids)}** more than the {len(ids)} already labelled."
    )

    print(f"\n{THIN}\nBUT CAN THE GATE EVER FIRE? — asked before any label is bought\n{THIN}")
    cell_hits = table.get(("correct", "correct"), 0)
    cell_total = sum(v for (h, _), v in table.items() if h == "correct")
    observed = cell_hits / cell_total
    print(
        f"  The `correct` cell's observed agreement is {cell_hits}/{cell_total} = "
        f"{observed:.3f},\n  and the registered bar is {THRESHOLD:.3f}. The bar is on the "
        "**lower bound**,\n  so it can only be cleared by driving the interval to near-zero "
        "width.\n"
    )
    print(f"  {'n':>7}{'lower bound at that rate':>28}")
    reachable = None
    for size in (GATE_N, 100, 400, 1600, 6400):
        low, _ = wilson(round(observed * size), size)
        print(f"  {size:>7}{low:>28.3f}")
    for size in range(GATE_N, 50_001):
        if wilson(round(observed * size), size)[0] >= THRESHOLD:
            reachable = size
            break
    if reachable is None:
        print(
            "\n  **No sample size up to 50,000 clears it at the observed rate.**\n"
            "  The audit is registered against a bar its own measurement cannot\n"
            "  reach, which is E-025's defect in a different entry: an instrument\n"
            "  designed to return `fail` or `not measured` at every n available.\n\n"
            "  Buying more labels does not change this. The legitimate paths are\n"
            "  to raise the judge's accuracy (E-011b's rubric revision) and then\n"
            "  audit, or to publish correctness as permanently unvalidated with\n"
            "  the directional finding above as its characterisation. Moving the\n"
            "  bar after seeing the number is not one of them."
        )
    else:
        print(f"\n  Clears the bar at n = {reachable}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
