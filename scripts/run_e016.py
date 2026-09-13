#!/usr/bin/env python
"""E-016: can a trim that knows nothing about the answer keep the answer?

E-015 measured that `enforce_budget` discards the hop the answer lives on, and
refused to change shipped trimming off the back of a guard firing. This is the
entry it promised.

The ceiling, registered before this file existed and measured from the same
collections this script trims: the evidence answering a three-hop question
costs about **90 tokens**, the budget is **6,000**, the chain is in the
retrieved pool on **92 of 100** questions, and the shipped policy delivers it
on **3**. No arm here can exceed 0.920; anything above it is a bug.

Four eviction policies, all oracle-free, all trimming the **identical**
pre-trim pool — retrieval runs once per (question, kind_cap) and the arms are
applied in memory, so the contrast is paired by construction and no arm can win
by having been handed a different retrieval.

    A  shipped: nearest first, earliest first within a distance
    B  proportional: round-robin across hop distances
    D  connectivity first: within a level, evidence joined to what
       shallower levels reached comes before evidence that is not
    R  random at a recorded seed — the control, and the falsifier

If R matches B and D, nothing the designed policies do matters and only
ceasing to evict by descending distance helped. That smaller claim is what
gets reported.

Chain reach is a retrieval metric. It says the evidence could support an
answer, never that one would be right.

Usage:
    python scripts/run_e016.py run
    python scripts/run_e016.py run --limit 10        # a pilot
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval
from graphrag_mtg.graph.connection import driver_session, metaqa_target
from graphrag_mtg.retrieval.subgraph import Subgraph

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e016_policies import ARMS, apply_arm
from run_e002 import _require_bolt, collect
from run_e012 import METAQA_DIR, SPLITS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78

#: Held at what E-015's grid named, so this entry varies the policy and
#: nothing else. The budget stays at the shipped 6,000 on purpose: E-015
#: already showed 96,000 buys 0.650 with the naive trim, and the question here
#: is how much of the ceiling a better policy delivers without paying that.
FRONTIER_CAP = 1600
TOKEN_BUDGET = 6000
KIND_CAPS: tuple[int, ...] = (1000, 4000)
HOPS = 3

#: Registered before the run: the untrimmed pool holds the chain this often.
#: No arm can beat its own cap, and one that does is a measurement bug.
CEILING = {1000: 0.650, 4000: 0.920}

#: Branch 1 needs the better designed arm to clear A by this much, clear its
#: Holm step, and beat R.
MIN_GAIN_OVER_A = 0.20
ALPHA = 0.05

#: The primary family. R is the falsifier and is reported whatever it says,
#: so it is not corrected as though it were a hypothesis under test.
PRIMARY = ("B", "D")


def holm(pvalues: dict[str, float], alpha: float = ALPHA) -> dict[str, tuple[float, bool]]:
    """Holm-Bonferroni: adjusted p as the running max of (m-i)*p, and the flag."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, tuple[float, bool]] = {}
    running = 0.0
    rejecting = True
    for index, (key, p) in enumerate(ordered):
        value = min(1.0, max(running, (m - index) * p))
        running = value
        if rejecting and p > alpha / (m - index):
            rejecting = False
        adjusted[key] = (value, rejecting)
    return adjusted


def collect_once(session, question: metaqa.Question, kind_cap: int) -> Subgraph:
    """The pool every arm trims. Collected once, deliberately."""
    subgraph, _ = collect(
        session,
        question,
        frontier_cap=FRONTIER_CAP,
        kind_cap=kind_cap,
        token_budget=10**9,  # no trimming here; the arms do the trimming
    )
    return subgraph


def score(subgraph: Subgraph, question: metaqa.Question) -> dict[str, bool]:
    """Whether each arm's kept evidence still holds a chain of the declared depth."""
    outcome: dict[str, bool] = {}
    for arm in ARMS:
        kept = apply_arm(subgraph.evidence, arm, TOKEN_BUDGET)
        outcome[arm] = bool(
            metaqa.answer_path(kept, question.seed, question.answers, hops=question.hops)
        )
    return outcome


def report(results: dict[int, dict[str, dict[str, bool]]]) -> int:
    """Per-arm reach, the registered contrasts, and the branch."""
    failed = 0
    for kind_cap, per_question in sorted(results.items()):
        ids = sorted(per_question)
        n = len(ids)
        reach = {
            arm: wilson_interval(sum(per_question[q][arm] for q in ids), n) for arm in ARMS
        }
        print(f"\n{RULE}\nkind_cap {kind_cap} — {n} question(s), budget {TOKEN_BUDGET}, "
              f"ceiling {CEILING[kind_cap]:.3f}")
        print(RULE)
        for arm in ARMS:
            interval = reach[arm]
            label = {"A": "shipped", "B": "proportional", "D": "connectivity", "R": "random"}[arm]
            over = ""
            if interval.point > CEILING[kind_cap] + 1e-9:
                over = "  ** ABOVE THE REGISTERED CEILING — a measurement bug, not a result"
                failed = 1
            print(f"  {arm} {label:<14} {interval.point:.3f} "
                  f"[{interval.low:.3f},{interval.high:.3f}]  "
                  f"{sum(per_question[q][arm] for q in ids)}/{n}{over}")

        print("\n  PRIMARY — paired within question against A, exact McNemar, Holm over 2.")
        pvalues: dict[str, float] = {}
        gains: dict[str, float] = {}
        for arm in PRIMARY:
            result = mcnemar(
                [per_question[q]["A"] for q in ids], [per_question[q][arm] for q in ids]
            )
            pvalues[arm] = result.p_value
            gains[arm] = reach[arm].point - reach["A"].point
            print(f"    {arm} vs A  +{result.improved}/-{result.regressed}  "
                  f"p={result.p_value:.5f}  gain {gains[arm]:+.3f}")
        adjusted = holm(pvalues)
        for arm in PRIMARY:
            value, rejected = adjusted[arm]
            print(f"    {arm} adjusted p={value:.4f}  "
                  f"{'significant' if rejected else 'not significant'}")

        best = max(PRIMARY, key=lambda arm: reach[arm].point)
        falsifier = mcnemar(
            [per_question[q]["R"] for q in ids], [per_question[q][best] for q in ids]
        )
        print(f"\n  FALSIFIER — {best} vs R (random): +{falsifier.improved}/"
              f"-{falsifier.regressed}  p={falsifier.p_value:.5f}")
        print(f"    R reach {reach['R'].point:.3f} [{reach['R'].low:.3f},{reach['R'].high:.3f}]")

        beats_r = falsifier.p_value <= ALPHA and reach[best].point > reach["R"].point
        if gains[best] >= MIN_GAIN_OVER_A and adjusted[best][1] and beats_r:
            print(f"\n  BRANCH 1 — {best} clears A by {gains[best]:+.3f}, clears its Holm")
            print("             step, and beats random.")
            print("    The policy is added to enforce_budget as an option, OFF BY DEFAULT,")
            print("    with this measurement in its docstring. It ships off because the")
            print("    Magic corpus does not hit the budget at all (E-013: dropped empty")
            print("    on all 26), so adopting it as the default would be changing shipped")
            print("    behaviour on calibration data.")
        elif gains[best] < MIN_GAIN_OVER_A:
            print(f"\n  BRANCH 2 — no arm clears A by {MIN_GAIN_OVER_A}. The trim is not the")
            print("             lever; nothing is added to enforce_budget, and three-hop")
            print("             retrieval is recorded as needing a different walk.")
        else:
            print("\n  BRANCH 3 — a designed arm beats A, but random matches it.")
            print("    Reported as: abandoning descending-distance eviction is what")
            print("    mattered. The specific policy is NOT credited.")

    print(f"\n{RULE}")
    print("Chain reach is a retrieval metric. It says the evidence could support an")
    print("answer at this budget, and nothing about whether one would be right.")
    return failed


def run(args: argparse.Namespace) -> int:
    _, _, path = SPLITS[args.split]
    if not path.exists():
        raise SystemExit(f"No {args.split} split at {path}.")
    questions = [q for q in metaqa.load_frozen(path, args.metaqa_dir) if q.hops == HOPS]
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit(f"No {HOPS}-hop questions in the {args.split} split.")

    print(f"E-016 — {len(questions)} {HOPS}-hop question(s) from the {args.split} split.")
    print(f"Zero model calls. Four arms trim the same pool at a {TOKEN_BUDGET}-token budget.\n")

    results: dict[int, dict[str, dict[str, bool]]] = {}
    rows: list[dict] = []
    with driver_session(_require_bolt(metaqa_target())) as session:
        for kind_cap in KIND_CAPS:
            started = time.monotonic()
            print(f"  collecting kind_cap={kind_cap} ...", flush=True)
            per_question: dict[str, dict[str, bool]] = {}
            for question in questions:
                subgraph = collect_once(session, question, kind_cap)
                outcome = score(subgraph, question)
                per_question[question.qid] = outcome
                rows.append({"qid": question.qid, "kind_cap": kind_cap,
                             "pool_items": len(subgraph.evidence), **outcome})
            results[kind_cap] = per_question
            print(f"    {round(time.monotonic() - started, 1)}s", flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {len(rows)} row(s) -> {args.out}")

    return report(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="four policies over the same pool (free)")
    runner.add_argument("--split", choices=sorted(SPLITS), default="dev")
    runner.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    runner.add_argument("--limit", type=int, default=0)
    runner.add_argument("--out", type=Path, default=Path("runs/e016_dev.jsonl"))
    runner.set_defaults(func=run)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
