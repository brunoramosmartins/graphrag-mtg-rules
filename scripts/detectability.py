#!/usr/bin/env python
"""What is the smallest effect this evaluation can see, and has it ever seen one?

E-026's instrument. No API, no graph, no model: every number here is arithmetic
over runs that already exist.

**The question, in words before it is a number.** Of the paired correctness
comparisons this project has run on the Magic side, how many produced an effect
large enough that a comparison of that size could have distinguished it from
zero at 80% power? The answer, at the time of writing, is **none of them** —
and that is a property of the evaluation, not of any one entry.

**What else would make that count return zero?** Three things, and the report
prints what it needs to rule each out:

1. A discordance rate so high that the floor is unreachable by construction.
   The pooled rate is printed; it is ordinary.
2. An error in the floor itself. Two estimators are computed — a normal
   approximation and, with `--simulate`, an exact permutation — and disagreement
   is reported rather than averaged.
3. The effects being real but small. That is the finding, and it is why the
   report prints the n each effect *would* have needed rather than only a
   verdict.

The floor is not a criticism of any entry. An entry that registers its decision
rule and returns `inconclusive` did its job. What this measures is whether the
instrument was ever capable of returning anything else.

Usage:
    python scripts/detectability.py
    python scripts/detectability.py --simulate
    python scripts/detectability.py --disc 0.25
"""

from __future__ import annotations

import argparse
import statistics
import sys
from math import erf, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

ALPHA = 0.05
TARGET_POWER = 0.80

#: Pooled discordance for B against A on E-001's evaluation split: 17 questions
#: of 57 where exactly one arm was `correct`. Var(d) for a paired difference of
#: proportions is p_b + p_c - (p_b - p_c) squared, and the subtracted term is at most
#: 0.0004 across every contrast here, so the discordance rate *is* the variance
#: to three decimals. Using the pooled rate rather than a per-contrast one is
#: deliberate: a floor computed from each contrast's own discordance moves with
#: the thing being judged.
POOLED_DISCORDANCE = 17 / 57

#: Every paired correctness comparison this project has run on the Magic side,
#: with the counts that produced it. Not a selection: if a contrast is missing
#: from here the floor below is being computed over a chosen subset, which is
#: the defect this file exists to catch elsewhere.
MEASURED: tuple[tuple[str, int, int, int], ...] = (
    # (label, wins for the treatment/graph arm, wins for the control/vector arm, n)
    ("E-001 overall, B vs A", 9, 8, 57),
    ("E-001 legality_1hop", 3, 1, 15),
    ("E-001 definition_1hop", 3, 1, 11),
    ("E-001 negative_temporal", 1, 0, 7),
    ("E-001 interaction_multihop", 2, 5, 22),
    ("E-001 keyword_rule_2hop", 0, 1, 2),
    ("E-018 treatment vs control", 8, 6, 20),
    ("E-018 placebo vs control", 5, 6, 20),
    ("E-020 order vs floor", 2, 1, 19),
)


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1 + erf(z / sqrt(2)))


def power(delta: float, se: float) -> float:
    """Two-sided power at `delta` given a standard error."""
    z = abs(delta) / se
    return 1 - phi(1.96 - z) + phi(-1.96 - z)


def se_simple(n: int, discordance: float) -> float:
    """SE of a paired difference of proportions over n questions."""
    return sqrt(discordance / n)


def se_interaction(n: int, discordance: float) -> float:
    """SE of a difference between two such differences, **n per group**.

    Twice the variance of one group, which is why an interaction costs about
    four times the questions of the simple effect it is built from — the single
    arithmetic fact that decided Phase 10. The factor is four and not two
    because **both** halves apply: matching a simple contrast's SE needs 2n per
    group, and an interaction needs two groups, so 2 x 2n = 4n questions. At the
    pooled rate, the simple floor at n = 57 is 0.203 and an interaction reaches
    it at 114 per group, which is 228 questions — exactly 4.00x.

    **`n` here is per group, and every caller has to say so**, because the same
    `n` in :func:`se_simple` is a total. An audit in September reproduced this
    arithmetic correctly and still stopped at the convention, which is the
    evidence that the convention needed printing rather than implying.
    """
    return sqrt(2 * discordance / n)


def mde(n: int, discordance: float, interaction: bool = False) -> float:
    """Smallest |effect| detectable at `TARGET_POWER`, by bisection."""
    se = se_interaction(n, discordance) if interaction else se_simple(n, discordance)
    low, high = 0.0, 2.0
    for _ in range(60):
        mid = (low + high) / 2
        if power(mid, se) < TARGET_POWER:
            low = mid
        else:
            high = mid
    return high


def n_for(delta: float, discordance: float, interaction: bool = False) -> int | None:
    """Questions needed to detect `delta`, or None beyond a reporting limit."""
    if delta == 0:
        return None
    for n in range(2, 5001):
        se = se_interaction(n, discordance) if interaction else se_simple(n, discordance)
        if power(delta, se) >= TARGET_POWER:
            return n
    return None


def simulate_mde(n: int, discordance: float, seed: int = 20260914) -> float:
    """The floor again, by exact permutation, as a check on the approximation.

    The registered tests in this project are permutation and exact-McNemar
    tests, not z-tests. Where the two estimators disagree the report says so
    rather than picking one: a floor computed one way is a floor nobody
    checked.
    """
    import random

    rng = random.Random(seed)
    half = discordance / 2
    for step in range(1, 200):
        delta = step / 100
        pb = min(half + delta / 2, 1.0)
        pc = max(half - delta / 2, 0.0)
        hits = 0
        trials = 200
        for _ in range(trials):
            draws = [
                1 if (u := rng.random()) < pb else (-1 if u < pb + pc else 0)
                for _ in range(n)
            ]
            observed = abs(statistics.fmean(draws))
            worse = 0
            reps = 200
            for _ in range(reps):
                flipped = [d * rng.choice((-1, 1)) for d in draws]
                if abs(statistics.fmean(flipped)) >= observed - 1e-12:
                    worse += 1
            if (worse + 1) / (reps + 1) < ALPHA:
                hits += 1
        if hits / trials >= TARGET_POWER:
            return delta
    return float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disc",
        type=float,
        default=POOLED_DISCORDANCE,
        help="discordance rate to compute the floor from (default: E-001's pooled 17/57)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="check the floor with an exact permutation test (slow)",
    )
    args = parser.parse_args()
    disc = args.disc

    print(f"{RULE}\nE-026 — THE FLOOR OF THIS EVALUATION\n{RULE}\n")
    print(
        f"Pooled discordance, B against A on E-001's evaluation split: "
        f"{disc:.3f} ({17} of {57}).\nOrdinary, not extreme — the floor below "
        "is not an artefact of an unstable comparison."
    )

    print(f"\n{THIN}\nSMALLEST DETECTABLE EFFECT at {TARGET_POWER:.0%} power, "
          f"alpha={ALPHA}\n{THIN}")
    # The two columns are read at DIFFERENT total sample sizes and the header
    # has to say so. `n` is total questions for the simple contrast and
    # questions PER GROUP for the interaction, which needs two of them — so the
    # interaction row at n is a study of 2n questions. Printing one `n` over
    # both columns let a reader take "57 -> 0.287" as an interaction reachable
    # with 57 questions; at 57 total it is 0.409. Labelled 2026-09-14, after an
    # external audit reproduced the arithmetic and stopped at the convention.
    print(f"{'n':>6}{'simple (n total)':>24}{'interaction (n/group)':>24}{'= questions':>14}")
    for n in (20, 30, 40, 57, 80, 120, 200, 400):
        print(
            f"{n:>6}{mde(n, disc):>24.3f}"
            f"{mde(n, disc, interaction=True):>24.3f}{2 * n:>14}"
        )
    print(
        "\nAn interaction costs about four times the questions of the simple\n"
        "effect it is built from. That is the arithmetic, not a judgement."
    )

    if args.simulate:
        print(f"\n{THIN}\nTHE SAME FLOOR BY PERMUTATION, as a check\n{THIN}")
        for n in (20, 57, 120):
            approx, exact = mde(n, disc), simulate_mde(n, disc)
            note = "" if abs(approx - exact) < 0.05 else "   ** DISAGREE by >0.05"
            print(f"  n={n:>4}   approximation {approx:.3f}   permutation {exact:.3f}{note}")

    print(f"\n{THIN}\nEVERY PAIRED CORRECTNESS EFFECT MEASURED ON THE MAGIC SIDE\n{THIN}")
    print(f"{'contrast':<32}{'d':>8}{'n':>5}{'floor':>8}{'n needed':>10}   verdict")
    seen = 0
    for label, b_wins, a_wins, n in MEASURED:
        d = (b_wins - a_wins) / n
        floor = mde(n, disc)
        needed = n_for(abs(d), disc)
        detectable = abs(d) >= floor
        seen += detectable
        print(
            f"{label:<32}{d:>+8.3f}{n:>5}{floor:>8.3f}"
            f"{(str(needed) if needed else '—'):>10}   "
            f"{'DETECTABLE' if detectable else 'below the floor'}"
        )

    print(
        f"\nOf the {len(MEASURED)} paired correctness comparisons this project "
        f"has run, **{seen}** produced\nan effect its own sample could have "
        "distinguished from zero at 80% power."
    )
    print(
        "\nThe reading this does NOT support: that the effects are zero. It "
        "supports\nexactly one thing — that this evaluation could not have told "
        "the difference,\nso every `inconclusive` it returned was the only "
        "answer available to it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
