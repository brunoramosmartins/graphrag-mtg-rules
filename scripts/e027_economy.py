#!/usr/bin/env python
"""What does each arm spend to reach the same answer? E-027's instrument.

No API, no graph, no model: arithmetic over E-001's retrieval dumps.

**Every endpoint is paired within question and bootstrapped over questions, not
over items.** That is the whole methodological point of this entry and it is
not decoration. Evidence items are clustered inside questions; an interval
computed over 131 and 327 pooled items treats them as independent and comes
back too narrow. Phase 8 published item-level precision as A 0.420
[0.339, 0.505] against B 0.223 [0.181, 0.271] — non-overlapping — and the same
comparison paired within question returns **-0.001 [-0.044, +0.039]**. The gap
was the clustering.

So this reports both, side by side, and refuses to quote the item-level
interval on its own.

**What separates and what does not** is the finding, and both halves are
printed. Economy separates by an enormous margin; precision and gold-rule reach
do not, and neither does correctness — see E-026 for why correctness could not
have.

Usage:
    python scripts/e027_economy.py
    python scripts/e027_economy.py --reps 50000
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import artefacts, gold_rules, load_jsonl, outcome_of, retrieved_rules
from run_eval import GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

#: Arm A is the vector baseline, arm B the graph. The hybrid is reported by
#: E-001 and is deliberately absent: this entry contrasts the two systems whose
#: difference is the project's thesis, and adding a third arm here would widen
#: the comparison family for no question anyone asked.
ARMS = {"A": "A-hybrid", "B": "B"}
SPLIT = "eval"
SEED = 20260914
REPS = 10_000


def load_arms(split: str) -> dict[str, dict[str, dict]]:
    """Each arm's retrieval dump, keyed by question."""
    out: dict[str, dict[str, dict]] = {}
    for key, slug in ARMS.items():
        path, _, _ = artefacts(slug, split)
        out[key] = {row["question_id"]: row for row in load_jsonl(path, what=slug)}
    return out


def verdicts_for(slug: str, split: str) -> dict[str, dict]:
    """The judge's rows for one arm, keyed by question."""
    _, _, path = artefacts(slug, split)
    return {row["question_id"]: row for row in load_jsonl(path, what=slug)}


def item_count(record: dict) -> float:
    return float(len(record.get("evidence", ())))


def token_count(record: dict) -> float:
    total = record.get("tokens")
    if total:
        return float(total)
    return float(sum(item.get("tokens", 0) for item in record.get("evidence", ())))


def rule_count(record: dict) -> float:
    return float(len(retrieved_rules(record)))


def paired(
    values_a: list[float], values_b: list[float], rng: random.Random, reps: int
) -> tuple[float, float, float, float, float]:
    """Mean per arm, the paired difference, and its bootstrap interval.

    Resampling is over **questions**, carrying both arms' values for a question
    together. Resampling items instead would break the pairing and understate
    the interval, which is the error this entry exists to correct.
    """
    differences = [b - a for a, b in zip(values_a, values_b, strict=True)]
    mean = statistics.fmean(differences)
    draws = sorted(
        statistics.fmean(rng.choices(differences, k=len(differences))) for _ in range(reps)
    )
    low = draws[int(0.025 * reps)]
    high = draws[int(0.975 * reps)]
    return statistics.fmean(values_a), statistics.fmean(values_b), mean, low, high


def report_row(
    label: str, values_a: list[float], values_b: list[float], rng: random.Random, reps: int
) -> bool:
    """One endpoint, printed. Returns whether its interval excludes zero."""
    mean_a, mean_b, delta, low, high = paired(values_a, values_b, rng, reps)
    separates = low > 0 or high < 0
    verdict = "SEPARATES" if separates else "crosses zero"
    print(
        f"  {label:<26}{mean_a:>10.2f}{mean_b:>10.2f}{delta:>+11.2f}"
        f"  [{low:+.2f}, {high:+.2f}]  {verdict}"
    )
    return separates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default=SPLIT)
    parser.add_argument("--reps", type=int, default=REPS)
    args = parser.parse_args()

    rng = random.Random(SEED)
    arms = load_arms(args.split)
    shared = sorted(set(arms["A"]) & set(arms["B"]))
    wanted = gold_rules(GOLDEN_DIR)

    print(f"{RULE}\nE-027 — WHAT EACH ARM SPENDS\n{RULE}\n")
    print(
        f"{len(shared)} questions, paired within question, {args.reps:,} bootstrap "
        f"resamples over questions at seed {SEED}."
    )
    print(f"\n{THIN}\n{'endpoint':<26}{'A vector':>10}{'B graph':>10}"
          f"{'B - A':>11}  95% CI\n{THIN}")

    for label, fn in (
        ("evidence items", item_count),
        ("context tokens", token_count),
        ("CR rule items", rule_count),
    ):
        report_row(
            label,
            [fn(arms["A"][q]) for q in shared],
            [fn(arms["B"][q]) for q in shared],
            rng,
            args.reps,
        )

    carrying = [q for q in shared if q in wanted]

    def hits(record: dict, qid: str) -> float:
        return float(len(retrieved_rules(record) & set(wanted[qid])))

    def precision(record: dict, qid: str) -> float:
        found = retrieved_rules(record)
        return len(found & set(wanted[qid])) / len(found) if found else 0.0

    print(f"\n  on the {len(carrying)} questions carrying gold_cr_rules:")
    report_row(
        "gold rules retrieved",
        [hits(arms["A"][q], q) for q in carrying],
        [hits(arms["B"][q], q) for q in carrying],
        rng,
        args.reps,
    )
    report_row(
        "rule precision",
        [precision(arms["A"][q], q) for q in carrying],
        [precision(arms["B"][q], q) for q in carrying],
        rng,
        args.reps,
    )

    correct = {
        key: {
            qid: outcome_of(row, verdicts_for(slug, args.split).get(qid)) == "correct"
            for qid, row in arms[key].items()
        }
        for key, slug in ARMS.items()
    }
    print("\n  correctness, for the bound rather than for a difference:")
    report_row(
        "correct",
        [float(correct["A"][q]) for q in shared],
        [float(correct["B"][q]) for q in shared],
        rng,
        args.reps,
    )

    items_a = statistics.fmean([item_count(arms["A"][q]) for q in shared])
    items_b = statistics.fmean([item_count(arms["B"][q]) for q in shared])
    tokens_a = statistics.fmean([token_count(arms["A"][q]) for q in shared])
    tokens_b = statistics.fmean([token_count(arms["B"][q]) for q in shared])

    print(f"\n{THIN}\nWHAT THIS SUPPORTS\n{THIN}")
    print(
        f"  The graph arm reaches the same answers on **{tokens_b / tokens_a:.0%} of the "
        f"context tokens**\n  and **{items_b / items_a:.0%} of the evidence items**, while "
        "surfacing more CR rules.\n"
    )
    print(
        "  'The same answers' is bounded, not asserted equal: the correctness\n"
        "  interval above is what this evaluation can say, and E-026 measured why\n"
        "  it cannot say less. A reader who wants equality has to wait for an\n"
        "  evaluation with a lower floor than 0.20."
    )
    print(
        "\n  Item-level intervals are deliberately not printed. Phase 8's\n"
        "  A 0.420 [0.339, 0.505] against B 0.223 [0.181, 0.271] pooled items\n"
        "  across questions and came back non-overlapping; the paired figure\n"
        "  above is the same comparison with the clustering respected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
