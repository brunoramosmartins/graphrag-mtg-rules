#!/usr/bin/env python
"""E-010 part (a) — apply the registered rule to the finished relevance pass.

`run_e010.py report` prints per-arm proportions with independent Wilson
intervals and says, correctly, that those are not the comparison. This script
is the comparison: the registered analysis is a **cluster bootstrap over
questions** (amendment 2026-08-15b item 6), the registered prediction is an
**aggregate** one on the **token-normalised** figure (item 3), and the
registered blinding rule (item 4) either fires or does not.

Outcome encoding is read from the producer, not assumed. `run_e010.py` writes
one JSON object per slot to `data/interim/e010_labels.jsonl` with:

    relevance  "relevant" | "irrelevant"   (`label`, `batch`)
    guess      "A" | "graph"               (`guess`, `batch`; subsample only)

and the arm truth lives in the versioned sample, collapsed A-versus-graph for
the blinding check exactly as `report()` collapses it — B and C share a
retrieval core and telling them apart is not what blinding is for.

Usage:
    python scripts/e010_analysis.py
    python scripts/e010_analysis.py --interim   # descriptives only, no verdict
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from graphrag_mtg.evaluation.metrics import wilson_interval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78
SAMPLE = Path("data/golden/e010_sample.json")
ITEMS = Path("data/interim/e010_items.jsonl")
LABELS = Path("data/interim/e010_labels.jsonl")
GOLDEN = Path("data/golden")

RELEVANCE = {"relevant", "irrelevant"}
GUESSES = {"A", "graph"}

#: Registered in the entry's prediction; `legality_1hop` is named there and is
#: checked for below because a stratum that vanishes silently is the failure
#: mode this project has already hit twice (E-013's ceiling, E-009's coverage).
REGISTERED_STRATA = ("definition_1hop", "legality_1hop", "interaction_multihop")

#: Three pairwise contrasts are printed; one of them (A vs B, token-normalised)
#: is the registered prediction and the other two are descriptive. Bonferroni
#: is applied over all three regardless — declaring the family after seeing the
#: numbers is how a family of three becomes a family of one.
FAMILY = 3

BLIND_WITHDRAWN_ABOVE = 0.70
RESAMPLES = 10_000
SEED = 20260912


def die(message: str) -> None:
    raise SystemExit(f"VALIDITY GUARD FAILED — no numbers printed.\n  {message}")


def load() -> tuple[dict, dict[str, dict], dict[str, dict]]:
    """Read the three files, hard-failing on anything a number would hide."""
    for path in (SAMPLE, ITEMS, LABELS):
        if not path.exists():
            die(f"missing {path}")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    items = {
        json.loads(line)["slot"]: json.loads(line)
        for line in ITEMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = {
        json.loads(line)["slot"]: json.loads(line)
        for line in LABELS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return sample, items, rows


def guard(sample: dict, items: dict, rows: dict, *, interim: bool) -> None:
    slots = {s["slot"] for s in sample["slots"]}
    subsample = set(sample["blinding_subsample"])

    if slots - set(items):
        die(f"{len(slots - set(items))} sampled slot(s) have no rendered item")
    if set(rows) - slots:
        die(f"labels exist for slot(s) not in the sample: {sorted(set(rows) - slots)[:5]}")

    bad = {s: r.get("relevance") for s, r in rows.items() if r.get("relevance") not in RELEVANCE
           and r.get("relevance") is not None}
    if bad:
        die(f"relevance values outside {sorted(RELEVANCE)}: {bad}")
    bad_guess = {s: r["guess"] for s, r in rows.items()
                 if r.get("guess") and r["guess"] not in GUESSES}
    if bad_guess:
        die(f"guesses outside {sorted(GUESSES)}: {bad_guess}")

    # A guess recorded outside the subsample is not a harmless extra: the
    # published blinding figure has a denominator, and a stray guess changes it.
    stray = {s for s, r in rows.items() if r.get("guess") and s not in subsample}
    if stray:
        die(f"guess(es) recorded outside the blinding subsample: {sorted(stray)}")

    unlabelled = sorted(s for s in slots if not rows.get(s, {}).get("relevance"))
    unguessed = sorted(s for s in subsample if not rows.get(s, {}).get("guess"))
    if interim:
        print(f"[INTERIM] {len(slots) - len(unlabelled)}/{len(slots)} labelled, "
              f"{len(subsample) - len(unguessed)}/{len(subsample)} guessed.")
        return
    if unlabelled:
        die(f"{len(unlabelled)} slot(s) unlabelled — run with --interim or finish the pass")
    if unguessed:
        die(f"{len(unguessed)} blinding-subsample slot(s) without a guess: {unguessed[:5]}")

    per_arm = Counter(s["arm"] for s in sample["slots"])
    if len(set(per_arm.values())) != 1:
        die(f"arms are unbalanced: {dict(per_arm)} — the design is paired by construction")


def strata() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(GOLDEN.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") and row.get("stratum"):
                    found[row["id"]] = row["stratum"]
    return found


def truth(arm: str) -> str:
    return "A" if arm == "A" else "graph"


def blinding(sample: dict, items: dict, rows: dict) -> float:
    """The registered check, and then the two baselines it has to clear.

    The 0.70 threshold in amendment item 4 was written as though the guess were
    a coin flip. It is not: the subsample is whatever the seeded draw produced,
    and "always say graph" scores the majority share for free. A published
    accuracy that does not say what chance alone buys is not interpretable, so
    both baselines are printed beside it — neither of them can rescue the claim,
    they only say how much of it is real.
    """
    subsample = sorted(sample["blinding_subsample"])
    by_slot = {s["slot"]: s for s in sample["slots"]}
    pairs = [(rows[s]["guess"], truth(by_slot[s]["arm"])) for s in subsample]
    right = sum(1 for guess, actual in pairs if guess == actual)
    n = len(pairs)
    accuracy = right / n
    interval = wilson_interval(right, n)

    print(f"  guess accuracy {right}/{n} = {accuracy:.3f} "
          f"[{interval.low:.3f}, {interval.high:.3f}]")

    counts = Counter(actual for _, actual in pairs)
    majority = max(counts.values()) / n
    print(f"    subsample truth {dict(counts)} — majority-class baseline {majority:.3f}")

    # Held-out kind rule: the arm's marginal by evidence kind, fitted on the 144
    # slots OUTSIDE the subsample and applied to the 36 inside it. Fitting it on
    # all 180 and scoring the 36 would score it on its own training data.
    outside = [s for s in by_slot if s not in set(subsample)]
    table: dict[str, Counter] = defaultdict(Counter)
    for slot in outside:
        table[items[slot]["kind"]][truth(by_slot[slot]["arm"])] += 1
    rule = {kind: counter.most_common(1)[0][0] for kind, counter in table.items()}
    kind_right = sum(
        1 for slot in subsample
        if rule.get(items[slot]["kind"], "graph") == truth(by_slot[slot]["arm"])
    )
    print(f"    kind-only baseline {kind_right}/{n} = {kind_right/n:.3f}   "
          f"(argmax arm per evidence kind, fitted on the other {len(outside)} slots)")
    print(f"      the rule it fits: {rule}")

    sensitivity = Counter()
    for guess, actual in pairs:
        sensitivity[actual] += 1 if guess == actual else 0
    for actual, hits in sorted(sensitivity.items()):
        total = counts[actual]
        print(f"    identified {actual:6s} {hits}/{total} = {hits/total:.3f}")
    return accuracy


def cells(sample: dict, items: dict, rows: dict) -> dict[tuple[str, str], dict]:
    """Per question per arm: hits, n, relevant tokens, total tokens."""
    by_slot = {s["slot"]: s for s in sample["slots"]}
    cell: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"hits": 0, "n": 0, "rel_tokens": 0, "tokens": 0}
    )
    for slot, meta in by_slot.items():
        row = rows.get(slot, {})
        if not row.get("relevance"):
            continue
        hit = row["relevance"] == "relevant"
        size = items[slot]["tokens"]
        entry = cell[(meta["question_id"], meta["arm"])]
        entry["hits"] += int(hit)
        entry["n"] += 1
        entry["rel_tokens"] += size * int(hit)
        entry["tokens"] += size
    return cell


def pooled(cell: dict, questions: list[str], arm: str) -> tuple[float, float]:
    hits = sum(cell[(q, arm)]["hits"] for q in questions if (q, arm) in cell)
    n = sum(cell[(q, arm)]["n"] for q in questions if (q, arm) in cell)
    rel = sum(cell[(q, arm)]["rel_tokens"] for q in questions if (q, arm) in cell)
    tok = sum(cell[(q, arm)]["tokens"] for q in questions if (q, arm) in cell)
    return (hits / n if n else 0.0), (rel / tok if tok else 0.0)


def paired_diff(
    cell: dict, questions: list[str], left: str, right: str, index: int, alpha: float
) -> tuple[float, float, float]:
    """Paired cluster bootstrap: resample QUESTIONS, recompute both arms on the
    same resample, take the difference.

    Resampling slots would treat four items drawn from one question's evidence
    as four independent observations. They are not — they share a question, a
    key, and a retrieval call — and the interval would come out too narrow.
    Resampling the question carries the whole cluster, both arms together,
    which is what makes the contrast paired.
    """
    rng = random.Random(SEED)
    n = len(questions)
    draws = []
    for _ in range(RESAMPLES):
        picked = [questions[rng.randrange(n)] for _ in range(n)]
        draws.append(pooled(cell, picked, left)[index] - pooled(cell, picked, right)[index])
    draws.sort()
    lo = draws[int((alpha / 2) * RESAMPLES)]
    hi = draws[min(RESAMPLES - 1, int((1 - alpha / 2) * RESAMPLES))]
    point = pooled(cell, questions, left)[index] - pooled(cell, questions, right)[index]
    return point, lo, hi


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interim", action="store_true",
                        help="tolerate a partial pass; print descriptives and refuse a verdict")
    args = parser.parse_args()

    sample, items, rows = load()
    guard(sample, items, rows, interim=args.interim)

    questions = sorted({s["question_id"] for s in sample["slots"]})
    arms = sorted({s["arm"] for s in sample["slots"]})
    stratum = strata()

    print("E-010 part (a) — the human relevance pass, read against its registered rule")
    print(f"{len(sample['slots'])} slot(s), {len(questions)} question cluster(s), arms {arms}")
    print(RULE)

    print("BLINDING — reported first, because a comparison read before its own")
    print("blinding check is a comparison the reader cannot weigh.")
    accuracy = blinding(sample, items, rows) if not args.interim else None
    print(RULE)

    cell = cells(sample, items, rows)
    alpha_corrected = 0.05 / FAMILY
    print("PER ARM — independent intervals, raw and Bonferroni-corrected for a")
    print(f"pre-declared family of {FAMILY} pairwise contrasts. These are descriptives;")
    print("the contrast below is the comparison.")
    for arm in arms:
        hits = sum(c["hits"] for (q, a), c in cell.items() if a == arm)
        n = sum(c["n"] for (q, a), c in cell.items() if a == arm)
        rel = sum(c["rel_tokens"] for (q, a), c in cell.items() if a == arm)
        tok = sum(c["tokens"] for (q, a), c in cell.items() if a == arm)
        raw = wilson_interval(hits, n)
        corrected = wilson_interval(hits, n, alpha=alpha_corrected)
        print(f"  arm {arm}")
        print(f"    item precision      {hits}/{n} = {hits/n:.3f}  "
              f"95% [{raw.low:.3f}, {raw.high:.3f}]  "
              f"{100*(1-alpha_corrected):.2f}% [{corrected.low:.3f}, {corrected.high:.3f}]")
        print(f"    token-normalised    {rel}/{tok} = {rel/tok:.3f}   <- the registered figure")
    print(RULE)

    print("PAIRED CONTRASTS — cluster bootstrap over questions, "
          f"{RESAMPLES} resamples, seed {SEED}")
    labels = {0: "item precision", 1: "token-normalised"}
    contrasts = [("A", "B"), ("A", "C"), ("B", "C")]
    results: dict[tuple[str, str, int], tuple[float, float, float]] = {}
    for index in (0, 1):
        print(f"  {labels[index]}")
        for left, right in contrasts:
            point, lo, hi = paired_diff(cell, questions, left, right, index, 0.05)
            _, clo, chi = paired_diff(cell, questions, left, right, index, alpha_corrected)
            results[(left, right, index)] = (point, lo, hi)
            crosses = "crosses 0" if lo <= 0 <= hi else "excludes 0"
            print(f"    {left} - {right}  {point:+.3f} pp  95% [{lo:+.3f}, {hi:+.3f}] {crosses}"
                  f"   corrected [{clo:+.3f}, {chi:+.3f}]")
    print(RULE)

    print("DEVIATIONS FROM THE REGISTERED CONFIGURATION")
    present = Counter(stratum.get(q, "(unknown)") for q in questions)
    print(f"  strata present: {dict(present)}")
    for name in REGISTERED_STRATA:
        if name not in present:
            print(f"  ** {name} is named in the registered prediction and is ABSENT "
                  "from the sample **")
    print(f"  clusters: {len(questions)}, against the 20 development questions the entry names")
    print("  ceiling (amendment item 5: a blind second pass over >= 50 judgements on")
    print("  >= 10 questions): NOT RUN. The entry calls it mandatory.")
    print(RULE)

    if args.interim:
        print("INTERIM — no verdict. The registered rule runs once, on the complete design.")
        return 0

    print("VERDICT — each branch below was written before the data existed.")
    print()
    print(f"  [amendment item 4] blinding: accuracy {accuracy:.3f} vs threshold "
          f"{BLIND_WITHDRAWN_ABOVE:.2f}")
    if accuracy > BLIND_WITHDRAWN_ABOVE:
        print("    -> ABOVE. The blind claim is WITHDRAWN. Every figure above is")
        print("       published as an UNBLINDED comparison, per the registered rule.")
    else:
        print("    -> at or below. The blind claim stands.")
    print()
    point, lo, hi = results[("A", "B", 1)]
    print("  [amendment item 3] prediction: arm A's token-normalised precision is")
    print("  LOWER than arm B's, in aggregate over question clusters.")
    print(f"    -> A - B = {point:+.3f} pp, 95% [{lo:+.3f}, {hi:+.3f}]")
    direction = "CONFIRMED in direction" if point < 0 else "FALSIFIED in direction"
    certainty = "and the interval excludes 0" if hi < 0 else "but the interval crosses 0"
    print(f"    -> {direction}, {certainty}.")
    print()
    print("  [entry, and amendment item 7] decision rule: DESCRIPTIVE, no threshold.")
    print("    -> Nothing is gated on these numbers. The entry says so, and it said so")
    print("       before the run: a registered figure with no threshold cannot be gamed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
