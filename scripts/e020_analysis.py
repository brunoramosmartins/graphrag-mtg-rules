#!/usr/bin/env python
"""E-020's decision rule: order against the same-prompt floor, paired.

Two indicators per question, both collapsed to `correct` against everything
else:

    floor   `A1` and `A2` disagree — byte-identical prompt, so decoding only
    order   `A1` disagrees with `B` or with `C` — decoding **plus** order

They are compared **within question** by exact McNemar, because the same
question contributes both and an unpaired comparison would throw that away.

The registered bar is **0.175**, placed off the 1/n grid on purpose: at n near
20 every rate is a multiple of 0.05, and E-018 put two bars on multiples of
0.05 and landed exactly on both, which decided nothing.

Usage:
    python scripts/e020_analysis.py
    python scripts/e020_analysis.py --run runs/e020.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median

from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_analysis import ALPHA
from e001_inspect import load_jsonl
from e018_analysis import CORRECT, ORDINAL
from run_e020 import EFFECT_BAR, RUN_PATH, SAMPLES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78


def by_sample(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """Question id to sample name to its row."""
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        out.setdefault(row["question_id"], {})[row["sample"]] = row
    return out


def indicators(samples: dict[str, dict]) -> tuple[bool, bool]:
    """`(floor disagreed, order disagreed)` for one question, collapsed.

    `order` is *either* different ordering disagreeing with `A1`, not both.
    Requiring both would ask a stricter question than the entry registered and
    would understate a real effect; averaging them would invent a third
    quantity nobody fixed in advance.
    """
    correct = {name: samples[name]["label"] == CORRECT for name in SAMPLES}
    floor = correct["A1"] != correct["A2"]
    order = correct["A1"] != correct["B"] or correct["A1"] != correct["C"]
    return floor, order


def label_shift(samples: dict[str, dict]) -> bool:
    """Whether the three-label verdict moved at all, collapse or not.

    Reported beside the collapsed figure because the judge is weakest at the
    `correct`/`partial` boundary (E-011a: 4/14 agreement on `partial`), and a
    movement confined to that boundary is a different finding from one that
    crosses it — not a smaller version of the same one.
    """
    return len({samples[name]["label"] for name in SAMPLES}) > 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN_PATH)
    args = parser.parse_args()

    rows = load_jsonl(args.run, what="E-020 run")
    grouped = by_sample(rows)
    complete = {q: s for q, s in grouped.items() if set(s) == set(SAMPLES)}
    if len(complete) != len(grouped):
        missing = sorted(set(grouped) - set(complete))
        raise SystemExit(
            f"{len(missing)} question(s) do not carry all four samples: {missing[:5]}.\n"
            f"A question contributing to one indicator and not the other is not paired."
        )

    ids = sorted(complete)
    floors, orders = zip(*(indicators(complete[q]) for q in ids), strict=True)
    floors, orders = list(floors), list(orders)
    n = len(ids)

    print(f"E-020 — {n} question(s), 4 samples each, paired within question")
    print(f"outcome: `{CORRECT}` against everything else\n")

    print(f"{THIN}\nDISAGREEMENT RATES")
    for name, flags in (("same prompt (floor)", floors), ("different order", orders)):
        rate = sum(flags) / n
        interval = wilson_interval(sum(flags), n)
        print(f"  {name:<22} {sum(flags):>2}/{n}   {rate:.3f}  "
              f"[{interval.low:.3f}, {interval.high:.3f}]")

    gap = (sum(orders) - sum(floors)) / n
    test = mcnemar(floors, orders)
    print(f"\n{THIN}\nPAIRED CONTRAST — exact McNemar, one contrast, no correction")
    print(f"  discordant {test.improved}:{test.regressed}   exact p={test.p_value:.4f}")
    print(f"  order minus floor: {gap:+.3f}   registered bar {EFFECT_BAR:+.3f}   "
          f"{'met' if gap >= EFFECT_BAR else 'not met'}")
    moved_only_order = [q for q, f, o in zip(ids, floors, orders, strict=True) if o and not f]
    moved_only_floor = [q for q, f, o in zip(ids, floors, orders, strict=True) if f and not o]
    if moved_only_order:
        print(f"  moved on order only:  {', '.join(moved_only_order)}")
    if moved_only_floor:
        print(f"  moved on floor only:  {', '.join(moved_only_floor)}")

    shifted = [q for q in ids if label_shift(complete[q])]
    print(f"\n{THIN}\nTHREE-LABEL MOVEMENT — what the collapse hides")
    print(f"  {len(shifted)} of {n} question(s) returned more than one label across samples")
    for q in shifted:
        labels = "  ".join(f"{name}={complete[q][name]['label']}" for name in SAMPLES)
        print(f"    {q:<40} {labels}")
    print(f"  labels ordered {ORDINAL}; a movement confined to the correct/partial")
    print("  boundary is a different finding from one that crosses it.")

    print(f"\n{THIN}\nDOES CONTEXT SIZE PREDICT MOVEMENT? (prediction 3)")
    for flag, name in ((True, "moved on order"), (False, "did not move")):
        sizes = [complete[q]["A1"]["items"] for q, o in zip(ids, orders, strict=True) if o == flag]
        if sizes:
            # `statistics.median`, not `sorted(x)[len(x) // 2]`. The latter
            # returns the UPPER value on an even-length list, so at n = 2 it
            # reports the maximum and dresses a two-point sample as a central
            # tendency — which is how the first reading of this run made
            # prediction 3 look supported when the four largest contexts had
            # not moved at all. The full sorted list is printed beside it.
            print(f"  {name:<16} n={len(sizes):>2}  median {median(sizes):>5.1f}  "
                  f"items {sorted(sizes, reverse=True)}")
    print("  Prediction 3 said the movers carry the most evidence. A median over two")
    print("  questions is not a tendency — read the lists, not the summary.")

    print(f"\n{THIN}\nDOES STRATUM PREDICT MOVEMENT?")
    strata: dict[str, list[int]] = {}
    for qid in ids:
        row = strata.setdefault(complete[qid]["A1"]["stratum"], [0, 0])
        row[0] += label_shift(complete[qid])
        row[1] += 1
    for name, (moved, total) in sorted(strata.items(), key=lambda kv: -kv[1][0] / kv[1][1]):
        print(f"  {name:<24} {moved}/{total}")
    print("  Exploratory: this cut was not registered and the entry fires no branch")
    print("  on it. It is printed because a cut by size was registered and a cut by")
    print("  stratum explains the same rows better, which is worth saying out loud.")

    print(f"\n{RULE}\nVERDICT — the branches as registered")
    rejects = test.p_value <= ALPHA
    if rejects and gap >= EFFECT_BAR:
        print("\nBRANCH 1 — evidence order is a variance source nobody controlled.")
        print("E-019 holds one ordering fixed across conditions; every published paired")
        print("figure gains a caveat naming this entry; and retrieval order becomes a")
        print("Phase 9 front, because an ordering that is chosen rather than incidental")
        print("is free.")
    elif rejects:
        print("\nBRANCH 1 NOT MET — the contrast clears its test but the gap is")
        print(f"{gap:+.3f} against a registered {EFFECT_BAR:+.3f}. Reported as real and")
        print("smaller than the bar this project set for acting on it.")
    elif sum(orders) <= sum(floors):
        print("\nBRANCH 2 — order and the same prompt are indistinguishable.")
        print("E-018's secondary reading was the hand-def stratum being fragile near the")
        print("correct/partial boundary, not order. That reading is retracted in the")
        print("journal where it was recorded, and E-019 proceeds without an ordering")
        print("control.")
    else:
        print("\nBRANCH 3 — INCONCLUSIVE, and it is the default.")
        print(f"The gap is {gap:+.3f} and the test does not separate the two at n={n}.")
        print("Nothing is cancelled and nothing is adopted. The entry states that these")
        print("paired questions cannot separate order from decoding noise.")
    print(f"\n{RULE}")
    print("Three orderings sample the permutation space of this context almost not at")
    print("all, so the rate above is a LOWER BOUND on order sensitivity, not an")
    print("estimate of it. Measured on the development split; no rate transfers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
