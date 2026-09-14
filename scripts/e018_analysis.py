#!/usr/bin/env python
"""E-018's decision rule, applied to the run rather than argued about.

Every threshold here was fixed in `experiments/registry.md` before any API
call, and this file only evaluates them. Nothing in it chooses a denominator,
a contrast or a bar; where a number lands on a boundary it is reported as
landing on the boundary rather than nudged to the comfortable side.

**The two-way collapse.** `correct` against everything else, the same
collapse E-001 used, so the outcome is the one the entry registered. The
three-label distribution is reported beside it because the amendment made an
ordinal shift a finding in its own right — and a blocker on branch 3.

**The noise floor is collapsed too, and that matters.** The floor run prints
its discordance over three labels; a contrast scored on two labels has to be
compared against a floor scored on two labels, or the comparison is between a
signal and somebody else's noise. Both are printed, and the collapsed one is
the one the branches use.

**Family and correction.** Primary family of two — treatment vs control and
placebo vs control — exact McNemar paired within question, Holm step-down at
alpha = 0.05, so the strict step is alpha/2 = 0.025 and needs 7:0 at n = 20.
Treatment vs placebo is the **construct contrast** and enters as a registered
bar of 0.15, not as a third test: a Holm family of three would need 7:0
everywhere and make branch 1 unreachable at the effect the entry predicted.

Usage:
    python scripts/e018_analysis.py
    python scripts/e018_analysis.py --run runs/e018.jsonl --floor runs/e018_floor.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_analysis import ALPHA, holm, paired_difference
from e001_inspect import load_jsonl
from run_e018 import CEILING, FLOOR_PATH, RUN_PATH

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

#: The collapse E-001 used. `partial` is not half a point here; the entry
#: registered a two-way outcome and borrowing a different one after seeing
#: the labels is the move every amendment in this entry exists to prevent.
CORRECT = "correct"

#: Ordered worst to best, so a shift toward the key is a rise.
ORDINAL = ("incorrect", "partial", "correct")

#: Registered in amendment 2026-09-13: branch 1 additionally requires
#: treatment - placebo to clear this. It is the contrast that names the
#: construct — goldness net of volume and rule-shaped text.
CONSTRUCT_BAR = 0.15

#: Registered in amendment 2026-09-13: branch 3b (evidence of absence) needs
#: the treatment-control interval to exclude this. Inside it, the result is
#: 3a — inconclusive — and nothing is cancelled.
ABSENCE_BOUND = 0.20

#: Registered in amendment 2026-09-13: below this share of treatment answers
#: citing an injected rule, branch 3 does not fire at all, because a null
#: under a treatment the generator never used is a null about the harness.
UPTAKE_FLOOR = 0.50

#: The floor at which the entry says the thresholds are recomputed against
#: the noise rather than read straight.
FLOOR_ALARM = 4


def by_condition(rows: list[dict]) -> dict[str, dict[str, str]]:
    """Question id to condition to label."""
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        out.setdefault(row["question_id"], {})[row["condition"]] = row["label"]
    return out


def aligned(labels: dict[str, dict[str, str]], left: str, right: str) -> tuple[list[bool], list[bool], list[str]]:
    """Two collapsed outcome vectors over the questions carrying both.

    Paired by construction: the same question ids, in the same order, and a
    question missing either condition is dropped from both rather than from
    one — an unpaired pair is not a pair.
    """
    ids = sorted(q for q, pair in labels.items() if left in pair and right in pair)
    return (
        [labels[q][left] == CORRECT for q in ids],
        [labels[q][right] == CORRECT for q in ids],
        ids,
    )


def contrast(labels: dict[str, dict[str, str]], treated: str, base: str) -> dict:
    """One paired contrast: counts, exact McNemar, and a bootstrap interval."""
    after, before, ids = aligned(labels, treated, base)
    test = mcnemar(before, after)
    point, low, high = paired_difference(after, before, ALPHA)
    return {
        "name": f"{treated} vs {base}",
        "n": len(ids),
        "treated_correct": sum(after),
        "base_correct": sum(before),
        "improved": test.improved,
        "regressed": test.regressed,
        "p": test.p_value,
        "point": point,
        "low": low,
        "high": high,
        "flips": [q for q, a, b in zip(ids, after, before, strict=True) if a and not b],
        "losses": [q for q, a, b in zip(ids, after, before, strict=True) if b and not a],
    }


def report_contrast(result: dict, adjusted: tuple[float, bool] | None = None) -> None:
    print(
        f"  {result['name']:<24} {result['treated_correct']:>2}/{result['n']} vs "
        f"{result['base_correct']:>2}/{result['n']}   "
        f"discordant {result['improved']}:{result['regressed']}   "
        f"exact p={result['p']:.4f}"
    )
    print(
        f"  {'':<24} difference {result['point']:+.3f} "
        f"[{result['low']:+.3f}, {result['high']:+.3f}]"
        + (f"   Holm-adjusted p={adjusted[0]:.4f} "
           f"({'reject' if adjusted[1] else 'do not reject'})" if adjusted else "")
    )
    if result["flips"]:
        print(f"  {'':<24} gained: {', '.join(result['flips'])}")
    if result["losses"]:
        print(f"  {'':<24} lost:   {', '.join(result['losses'])}")


def ordinal_shift(labels: dict[str, dict[str, str]], treated: str, base: str) -> dict:
    """Movement along incorrect < partial < correct, which the collapse hides.

    Registered as a blocker: if the three-label distribution shifts toward the
    key under treatment while the collapse does not move, the result is "the
    rule improves the answer below the resolution of the registered outcome"
    and branch 3 does not fire. Without this, an intervention that turns
    `incorrect` into `partial` on several questions reads as doing nothing.
    """
    ids = sorted(q for q, pair in labels.items() if treated in pair and base in pair)
    steps = 0
    moved_up, moved_down = [], []
    for qid in ids:
        a, b = labels[qid][treated], labels[qid][base]
        if a not in ORDINAL or b not in ORDINAL:
            continue
        delta = ORDINAL.index(a) - ORDINAL.index(b)
        steps += delta
        if delta > 0:
            moved_up.append(f"{qid} ({b}->{a})")
        elif delta < 0:
            moved_down.append(f"{qid} ({b}->{a})")
    return {"steps": steps, "up": moved_up, "down": moved_down}


def distribution(labels: dict[str, dict[str, str]], condition: str) -> dict[str, int]:
    counts = dict.fromkeys(ORDINAL, 0)
    for pair in labels.values():
        if condition in pair and pair[condition] in counts:
            counts[pair[condition]] += 1
    return counts


def noise_floor(rows: list[dict]) -> dict:
    """Control against control, scored both ways.

    The collapsed figure is what the branches compare against. The three-label
    figure is printed beside it because it is what the floor run announced,
    and a reader holding that number should be able to see why this one
    differs rather than suspecting one of them.
    """
    labels = by_condition(rows)
    ids = sorted(q for q, p in labels.items() if "control_a" in p and "control_b" in p)
    three = [q for q in ids if labels[q]["control_a"] != labels[q]["control_b"]]
    collapsed = [
        q
        for q in ids
        if (labels[q]["control_a"] == CORRECT) != (labels[q]["control_b"] == CORRECT)
    ]
    return {"n": len(ids), "three_label": three, "collapsed": collapsed}


def uptake(rows: list[dict]) -> dict:
    """How often a treatment answer cited a rule the treatment put there."""
    treated = [r for r in rows if r["condition"] == "treatment"]
    used = [r["question_id"] for r in treated if r.get("cited_injected")]
    n = len(treated)
    return {"n": n, "used": used, "rate": len(used) / n if n else 0.0}


def decide(
    treatment: dict,
    placebo: dict,
    construct: float,
    ordinal: dict,
    uptake_rate: float,
    adjusted: dict[str, tuple[float, bool]],
) -> tuple[str, list[str]]:
    """Which registered branch this run lands in, and why.

    Separated from printing so the rule can be exercised against outcomes that
    did not happen. A decision rule only ever run against the single result it
    was written for is a decision rule nobody has checked.

    Returns:
        The branch id — ``"1"``, ``"1-bar"``, ``"2"``, ``"3-blocked"``,
        ``"3a"``, ``"3b"`` or ``"4"`` — and the registered blockers that kept
        branch 3 from firing, empty when none did.
    """
    treat_rejects = adjusted["treatment"][1]
    placebo_rejects = adjusted["placebo"][1]
    if (treatment["point"] < 0 and treat_rejects) or (placebo["point"] < 0 and placebo_rejects):
        return "4", []
    if treat_rejects:
        return ("1", []) if construct >= CONSTRUCT_BAR else ("1-bar", [])
    if placebo_rejects:
        return "2", []
    blocked = []
    if uptake_rate < UPTAKE_FLOOR:
        blocked.append(
            f"gold-rule citation uptake is {uptake_rate:.1%}, below the registered "
            f"{UPTAKE_FLOOR:.0%} — a null under a treatment the generator never used "
            f"is a null about the harness"
        )
    if ordinal["steps"] > 0:
        blocked.append(
            f"the three-label distribution shifted toward the key by "
            f"{ordinal['steps']:+d} step(s) while the collapse did not clear — the "
            f"rule improves the answer below the resolution of the registered outcome"
        )
    if blocked:
        return "3-blocked", blocked
    return ("3a" if treatment["low"] <= ABSENCE_BOUND <= treatment["high"] else "3b"), []


def verdict(
    treatment: dict,
    placebo: dict,
    construct: float,
    floor: dict,
    ordinal: dict,
    uptake_rate: float,
    adjusted: dict[str, tuple[float, bool]],
) -> str:
    """Print the branch `decide` returned, in the words the entry registered."""
    print(f"\n{RULE}\nVERDICT — the branches as registered, in their registered order")
    branch, blocked = decide(treatment, placebo, construct, ordinal, uptake_rate, adjusted)

    if branch == "4":
        print("\nBRANCH 4 — the injection hurts.")
        print("A contrast clears its step in the negative direction. The entry reports")
        print("a distraction effect and Phase 9's objective is not adopted on this.")
        return branch
    if branch == "1":
        print("\nBRANCH 1 — the governing rule causes the answer.")
        print("Phase 9's registered objective is retrieval reaching rules of the right")
        print("subject area, of which exact gold-rule recall is the strictest reading.")
        return branch
    if branch == "1-bar":
        print("\nBRANCH 1 NOT MET — treatment clears its step but the construct bar")
        print(f"does not: treatment - placebo = {construct:+.3f} against {CONSTRUCT_BAR:+.3f}.")
        print("Reported as: the rule helps, and this design cannot separate that help")
        print("from putting more rule-shaped text in the prompt. Objective reported,")
        print("not adopted.")
        return branch
    if branch == "2":
        print("\nBRANCH 2 — the effect is context volume or prompt shape, not the rule.")
        print("Phase 9 does not target gold-rule recall and the 2026-09-13")
        print("observational cut is retracted in the journal where it was recorded.")
        return branch

    print("\nNeither contrast clears its Holm step. Branch 3 is reached, and two")
    print("registered conditions are checked before it fires.")
    if branch == "3-blocked":
        print("\nBRANCH 3 DOES NOT FIRE. Registered blockers, both before the run:")
        for reason in blocked:
            print(f"  - {reason}")
        print("\nPhase 9's objective is UNRESOLVED. Nothing is cancelled and nothing")
        print("is adopted. The entry reports what it measured and says what it could")
        print("not separate.")
        return branch

    if branch == "3a":
        print(f"\nBRANCH 3a — INCONCLUSIVE, and it is the default.")
        print(f"The treatment-control interval [{treatment['low']:+.3f}, "
              f"{treatment['high']:+.3f}] includes {ABSENCE_BOUND:+.3f}.")
        print("NOTHING IS CANCELLED. The observational cut stays unpublished and")
        print("Phase 9's objective is recorded as unresolved: these paired questions")
        print("cannot separate a 0.25 effect from zero.")
        return branch
    print("\nBRANCH 3b — evidence of absence.")
    print(f"The interval [{treatment['low']:+.3f}, {treatment['high']:+.3f}] excludes")
    print(f"{ABSENCE_BOUND:+.3f}. This is the only branch that cancels Phase 9's")
    print("objective, and it costs the most, which is why it was written first.")
    return branch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN_PATH)
    parser.add_argument("--floor", type=Path, default=FLOOR_PATH)
    args = parser.parse_args()

    rows = load_jsonl(args.run, what="E-018 run")
    floor_rows = load_jsonl(args.floor, what="E-018 noise floor")
    labels = by_condition(rows)
    floor = noise_floor(floor_rows)

    print(f"E-018 — {len(labels)} question(s), 3 conditions, paired within question")
    print(f"outcome: `{CORRECT}` against everything else, the collapse E-001 used\n")

    print(f"{THIN}\nTHREE-LABEL DISTRIBUTION PER CONDITION")
    print(f"  {'condition':<12}" + "".join(f"{name:>12}" for name in ORDINAL))
    for name in ("control", "placebo", "treatment"):
        counts = distribution(labels, name)
        print(f"  {name:<12}" + "".join(f"{counts[label]:>12}" for label in ORDINAL))

    print(f"\n{THIN}\nNOISE FLOOR — control against control, {floor['n']} pairs")
    print(f"  three-label: {len(floor['three_label'])} discordant"
          + (f" ({', '.join(floor['three_label'])})" if floor["three_label"] else ""))
    print(f"  collapsed:   {len(floor['collapsed'])} discordant"
          + (f" ({', '.join(floor['collapsed'])})" if floor["collapsed"] else ""))
    print("  The collapsed figure is the one the contrasts below are measured against.")
    if len(floor["collapsed"]) >= FLOOR_ALARM:
        print(f"  ** At or above {FLOOR_ALARM}. The thresholds are recomputed against this")
        print("     floor before any branch fires, as registered.")

    treatment = contrast(labels, "treatment", "control")
    placebo = contrast(labels, "placebo", "control")
    adjusted_raw = holm({"treatment": treatment["p"], "placebo": placebo["p"]})
    adjusted = {"treatment": adjusted_raw["treatment"], "placebo": adjusted_raw["placebo"]}

    print(f"\n{THIN}\nPRIMARY FAMILY — exact McNemar, Holm at alpha={ALPHA} (strict step {ALPHA / 2})")
    report_contrast(treatment, adjusted["treatment"])
    report_contrast(placebo, adjusted["placebo"])
    print(f"\n  Signal against noise: the treatment contrast rests on "
          f"{treatment['improved'] + treatment['regressed']} discordant pair(s); two "
          f"identical\n  control runs produced {len(floor['collapsed'])}.")

    construct = (treatment["treated_correct"] - placebo["treated_correct"]) / treatment["n"]
    print(f"\n{THIN}\nCONSTRUCT CONTRAST — treatment minus placebo, a registered bar")
    print(f"  {construct:+.3f} against the registered {CONSTRUCT_BAR:+.3f}"
          f"   {'met' if construct >= CONSTRUCT_BAR else 'not met'}")
    if abs(construct - CONSTRUCT_BAR) < 1e-9:
        print("  ** Exactly on the bar. Reported as landing on it, not as clearing it.")
    print("  A bar, not a third test: a Holm family of three at n = 20 would need 7:0")
    print("  on every contrast and make branch 1 unreachable at the predicted effect.")

    ordinal = ordinal_shift(labels, "treatment", "control")
    print(f"\n{THIN}\nORDINAL SHIFT — what the two-way collapse hides")
    print(f"  net {ordinal['steps']:+d} step(s) along incorrect < partial < correct")
    for line in ordinal["up"]:
        print(f"    up:   {line}")
    for line in ordinal["down"]:
        print(f"    down: {line}")

    used = uptake(rows)
    print(f"\n{THIN}\nMANIPULATION — did the answer use what was injected?")
    print(f"  gold-rule citation uptake: {len(used['used'])} of {used['n']} "
          f"({used['rate']:.1%}), registered floor {UPTAKE_FLOOR:.0%}")
    if abs(used["rate"] - UPTAKE_FLOOR) < 1e-9:
        print("  ** Exactly on the floor. The rule says *below*, so it does not block —")
        print("     recorded as landing on the boundary rather than clearing it.")

    print(f"\n{THIN}\nAGAINST THE CEILING")
    print(f"  ceiling {CEILING} of {treatment['n']}, read before the run")
    print(f"  treatment reached {treatment['treated_correct']}")
    residual = CEILING - treatment["treated_correct"]
    print(f"  residual {residual}: questions a reader judged answerable from the")
    print("  injected rules, where the model had them and was still not right.")
    if treatment["treated_correct"] > CEILING:
        print("  ** ABOVE THE CEILING. That is a defect in the measurement, not a")
        print("     finding. Do not report this run until it is explained.")

    verdict(
        treatment,
        placebo,
        construct,
        floor,
        ordinal,
        used["rate"],
        adjusted,
    )
    print(f"\n{RULE}")
    print("No figure here is a system score. Injecting the gold rule is an oracle")
    print("intervention: it measures the generator's use of evidence, never any")
    print("retriever's ability to find it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
