#!/usr/bin/env python
"""E-001 — apply the registered decision rule to the evaluation split.

`run_eval.py report` prints per-stratum correctness with uncorrected p-values,
and says so. This script is the registered analysis: **B vs A on the four
strata with n >= 7, exact McNemar over paired questions, Holm-corrected at
alpha = 0.05**, with the three-valued per-stratum verdict amendment 2026-08-15c
pinned before any arm ran — *confirmed* (corrected p < 0.05 in the predicted
direction), *falsified* (corrected p < 0.05 in the opposite direction),
*inconclusive* otherwise.

Everything else is exploratory by registration and is printed under that name:
C vs A, C vs B, `keyword_rule_2hop`, and the pairwise preference head-to-head.

The predicted direction per stratum comes from the `vector_should` label the
golden rows carried **before any retrieval system existed** — `fail` and `lose`
predict the graph ahead, `tie` predicts no difference and is the declared
falsifier. `tie` is therefore scored by equivalence (TOST: the 90% interval of
the paired difference inside +/- 0.15), never by a failed test, because "no
significant difference" is what an underpowered test returns whatever is true.

Outcome encoding is read from the producer. `run_eval.py` writes one verdict
per question per arm with `label` in the rubric's vocabulary, and the unit here
is the registered two-way collapse: `correct` against everything else.
`partial` counts as not-correct (E-007c: a middle category absorbs uncertainty,
and letting it count as a win lets the headline move with how generously it was
applied).

Usage:
    python scripts/e001_analysis.py
    python scripts/e001_analysis.py --side dev     # the dress rehearsal
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_golden import QUESTION_FILES, load_questions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78
GOLDEN = Path("data/golden")
SPLIT = Path("data/golden/phase4_dev_ids.json")
VERDICTS = "runs/e001_{slug}_verdicts_{side}.jsonl"
PAIRS = "runs/e001_pairs_{left}_vs_{right}_{side}.jsonl"

CONTROL = "A-hybrid"
GRAPH = "B"
HYBRID = "C-vector-hybrid-routed"
ARMS = (CONTROL, GRAPH, HYBRID)

#: Amendment 2026-08-15c: the primary family is the strata with n >= 7.
MIN_PRIMARY_N = 7
ALPHA = 0.05

#: E-011, registered before any pair existed: above this rate of orderings
#: disagreeing, the pairwise win rate is not published as the head-to-head.
ORDER_DISAGREEMENT_GATE = 0.20

#: Amendment 2026-08-15c, the `tie` stratum's equivalence bound.
TOST_BOUND = 0.15
TOST_ALPHA = 0.10

#: Frozen in the decision journal on 2026-09-12, before anything on the
#: evaluation side was judged. A run whose verdicts carry a different rubric
#: is not the registered run.
FROZEN_RUBRIC = "p6-c1"

RESAMPLES = 10_000
SEED = 20260912


def die(message: str) -> None:
    raise SystemExit(f"VALIDITY GUARD FAILED — no numbers printed.\n  {message}")


def verdicts(slug: str, side: str) -> dict[str, dict]:
    path = Path(VERDICTS.format(slug=slug, side=side))
    if not path.exists():
        die(f"missing {path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["question_id"]: row for row in rows}


def holm(pvalues: dict[str, float], alpha: float = ALPHA) -> dict[str, tuple[float, bool]]:
    """Holm-Bonferroni, returning the adjusted p and the reject flag per key.

    Step-down: sort ascending, test p_(i) against alpha/(m-i), and once a
    hypothesis fails to reject, every later one fails too. The adjusted p is
    the running maximum of (m-i) * p_(i), clipped at 1 — reported rather than
    only the flag, so the write-up quotes a number instead of a verdict.
    """
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, tuple[float, bool]] = {}
    running = 0.0
    still_rejecting = True
    for index, (key, p) in enumerate(ordered):
        value = min(1.0, max(running, (m - index) * p))
        running = value
        if still_rejecting and p > alpha / (m - index):
            still_rejecting = False
        adjusted[key] = (value, still_rejecting)
    return adjusted


def paired_difference(
    left: list[bool], right: list[bool], alpha: float
) -> tuple[float, float, float]:
    """Bootstrap interval for the paired accuracy difference (left - right)."""
    rng = random.Random(SEED)
    n = len(left)
    draws = []
    for _ in range(RESAMPLES):
        picked = [rng.randrange(n) for _ in range(n)]
        draws.append(
            sum(left[i] for i in picked) / n - sum(right[i] for i in picked) / n
        )
    draws.sort()
    point = sum(left) / n - sum(right) / n
    return (
        point,
        draws[int((alpha / 2) * RESAMPLES)],
        draws[min(RESAMPLES - 1, int((1 - alpha / 2) * RESAMPLES))],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--side", choices=("eval", "dev"), default="eval")
    args = parser.parse_args()
    side = args.side

    rows = load_questions(GOLDEN, QUESTION_FILES)
    dev = set(json.loads(SPLIT.read_text(encoding="utf-8"))["dev_ids"])
    wanted = {
        row["id"]: row
        for row in rows
        if (row["id"] in dev) == (side == "dev")
    }

    scored = {slug: verdicts(slug, side) for slug in ARMS}

    # --- validity guards, before a single number -----------------------------
    for slug, table in scored.items():
        if set(table) != set(wanted):
            missing = sorted(set(wanted) - set(table))
            extra = sorted(set(table) - set(wanted))
            die(f"{slug}: verdict ids do not match the {side} split "
                f"(missing {len(missing)}, unexpected {len(extra)}) e.g. {(missing + extra)[:3]}")
        bad = {q: r["label"] for q, r in table.items() if r.get("label") not in
               {"correct", "partial", "incorrect"}}
        if bad:
            die(f"{slug}: labels outside the rubric vocabulary: {list(bad.items())[:3]}")
        if any(r.get("smoke") for r in table.values()):
            die(f"{slug}: smoke rows in an experiment artefact")
        sides = {r.get("split") for r in table.values()}
        if sides != {side}:
            die(f"{slug}: verdict rows claim split(s) {sides}, expected {{'{side}'}}")
        versions = {r.get("rubric_version") for r in table.values()}
        if versions != {FROZEN_RUBRIC}:
            die(f"{slug}: rubric version(s) {versions}, frozen value is {FROZEN_RUBRIC}")
    hashes = {r.get("rubric_hash") for table in scored.values() for r in table.values()}
    if len(hashes) != 1:
        die(f"arms were judged under {len(hashes)} different rubric hashes: {hashes}")

    shared = sorted(wanted)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for qid in shared:
        by_stratum[wanted[qid]["stratum"]].append(qid)

    # `vector_should` was recorded before any retrieval system existed; it is
    # the predicted direction and is not re-derived from the data.
    predicted: dict[str, set[str]] = defaultdict(set)
    for qid in shared:
        predicted[wanted[qid]["stratum"]].add(wanted[qid].get("vector_should"))

    correct = {
        slug: {q: scored[slug][q]["label"] == "correct" for q in shared} for slug in ARMS
    }

    print(f"E-001 — registered analysis, {side} split, {len(shared)} paired question(s)")
    print(f"rubric {FROZEN_RUBRIC} @ {next(iter(hashes))[:12]}   "
          f"unit: `correct` against everything else")
    print(RULE)

    print("PER STRATUM — point and 95% Wilson interval")
    header = f"{'stratum':<24}{'n':>4}  " + "".join(f"{slug:>26}" for slug in ARMS)
    print(header)
    for stratum in sorted(by_stratum):
        qids = by_stratum[stratum]
        cells = []
        for slug in ARMS:
            hits = sum(correct[slug][q] for q in qids)
            interval = wilson_interval(hits, len(qids))
            cells.append(f"{hits/len(qids):.2f} [{interval.low:.2f},{interval.high:.2f}]")
        print(f"{stratum:<24}{len(qids):>4}  " + "".join(f"{c:>26}" for c in cells))
    cells = []
    for slug in ARMS:
        hits = sum(correct[slug][q] for q in shared)
        interval = wilson_interval(hits, len(shared))
        cells.append(f"{hits/len(shared):.2f} [{interval.low:.2f},{interval.high:.2f}]")
    print(f"{'ALL':<24}{len(shared):>4}  " + "".join(f"{c:>26}" for c in cells))
    print(RULE)

    # --- the primary family --------------------------------------------------
    primary = sorted(s for s, q in by_stratum.items() if len(q) >= MIN_PRIMARY_N)
    print(f"PRIMARY FAMILY — {GRAPH} vs {CONTROL}, exact McNemar, Holm at alpha={ALPHA}")
    print(f"strata with n >= {MIN_PRIMARY_N}: {', '.join(primary)}")
    print()
    raw: dict[str, float] = {}
    detail: dict[str, tuple[int, int]] = {}
    for stratum in primary:
        qids = by_stratum[stratum]
        before = [correct[CONTROL][q] for q in qids]
        after = [correct[GRAPH][q] for q in qids]
        result = mcnemar(before, after)
        raw[stratum] = result.p_value
        detail[stratum] = (result.improved, result.regressed)
    adjusted = holm(raw)

    for stratum in primary:
        gained, lost = detail[stratum]
        p_adj, reject = adjusted[stratum]
        want = predicted[stratum]
        qids = by_stratum[stratum]
        point, low, high = paired_difference(
            [correct[GRAPH][q] for q in qids], [correct[CONTROL][q] for q in qids], ALPHA
        )
        print(f"  {stratum}  (n={len(qids)}, predicted {sorted(want)})")
        print(f"    discordant +{gained}/-{lost}   raw p={raw[stratum]:.4f}   "
              f"Holm-adjusted p={p_adj:.4f}")
        print(f"    B - A = {point:+.3f}  95% [{low:+.3f}, {high:+.3f}]")

        if want == {"tie"}:
            # Scored by equivalence, never by a failed test: "no significant
            # difference" is the default output of an underpowered test.
            _, lo90, hi90 = paired_difference(
                [correct[GRAPH][q] for q in qids],
                [correct[CONTROL][q] for q in qids],
                TOST_ALPHA,
            )
            inside = -TOST_BOUND <= lo90 and hi90 <= TOST_BOUND
            print(f"    TOST 90% [{lo90:+.3f}, {hi90:+.3f}] vs +/-{TOST_BOUND:.2f}  ->  "
                  f"{'EQUIVALENCE SHOWN' if inside else 'equivalence NOT shown'}")
            verdict = "confirmed" if inside else "inconclusive"
            if reject and point > 0:
                verdict = "FALSIFIER FIRED — the graph wins on the tie stratum"
        elif reject:
            verdict = "confirmed" if point > 0 else "FALSIFIED"
        else:
            verdict = "inconclusive"
        print(f"    -> {verdict}")
        print()
    print(RULE)

    # --- exploratory ---------------------------------------------------------
    print("EXPLORATORY — registered as such; cannot confirm or falsify the hypothesis")
    for left, right in ((HYBRID, CONTROL), (HYBRID, GRAPH)):
        before = [correct[right][q] for q in shared]
        after = [correct[left][q] for q in shared]
        result = mcnemar(before, after)
        point, low, high = paired_difference(
            [correct[left][q] for q in shared], [correct[right][q] for q in shared], ALPHA
        )
        print(f"  {left} vs {right}: +{result.improved}/-{result.regressed}  "
              f"uncorrected p={result.p_value:.4f}   diff {point:+.3f} "
              f"[{low:+.3f}, {high:+.3f}]")
    for stratum, qids in sorted(by_stratum.items()):
        if len(qids) < MIN_PRIMARY_N:
            print(f"  {stratum} (n={len(qids)}): below the primary threshold; "
                  "no per-stratum claim is reportable")
    print(RULE)

    # --- the secondary head-to-head, and its registered gate -----------------
    print("SECONDARY — pairwise preference, and the gate registered before any pair")
    for left, right in ((GRAPH, CONTROL), (HYBRID, CONTROL), (HYBRID, GRAPH)):
        path = Path(PAIRS.format(left=left, right=right, side=side))
        if not path.exists():
            print(f"  {left} vs {right}: no artefact at {path}")
            continue
        pairs = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        tally = Counter(row["winner"] for row in pairs)
        disagreed = sum(1 for row in pairs if row.get("order_disagreed"))
        rate = disagreed / len(pairs)
        print(f"  {left} vs {right}: {dict(tally)}")
        print(f"    order disagreement {disagreed}/{len(pairs)} = {rate:.3f}", end="  ")
        if rate > ORDER_DISAGREEMENT_GATE:
            print(f"-> ABOVE {ORDER_DISAGREEMENT_GATE:.2f}: WITHDRAWN, not the head-to-head")
        else:
            print(f"-> at or below {ORDER_DISAGREEMENT_GATE:.2f}: reportable")
    print(RULE)
    print("The per-stratum correctness comparison above is the registered primary")
    print("and stands whatever the pairwise gate does.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
