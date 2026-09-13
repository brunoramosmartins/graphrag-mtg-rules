#!/usr/bin/env python
"""E-015: does the three-hop chain survive retrieval, and what destroys it?

E-012 was registered to decide whether `enforce_budget`'s distance-first trim
is a hazard for multi-hop questions, and chose branch 2 — keep the trim — on a
size null measured at fixed depth. That null could not see this hazard: every
E-012 cell had the answer chain reinstated by `reduce_to_k` before the model
was called, so the design repaired the damage before measuring it.

What E-002 already recorded, and nobody read until 2026-09-13:

    1-hop     0 / 500 questions had evidence dropped by the budget
    2-hop   121 / 500
    3-hop   498 / 500      and 497 / 500 had the frontier truncated

`enforce_budget` sorts by (-distance, -index), so distance-3 evidence is the
first thing evicted — on a 3-hop question, the hop the answer lives on. And
`frontier_cap` cuts upstream of that, removing entities before the third
expansion runs at all.

This measures how often retrieval delivers a chain of the declared depth, as a
function of those two limits, and prices each setting. **Zero model calls.**

A chain present is necessary, not sufficient: no number here is a correctness
score, and the distance between those two is precisely the mistake E-012's
amendment corrects.

Usage:
    python scripts/run_e015.py sweep                    # the dev grid
    python scripts/run_e015.py sweep --split conf --frontier 400 --budget 6000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.graph.connection import driver_session, metaqa_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e002 import (  # sibling script; the sys.path line above enables it
    E002_KIND_CAP,
    _require_bolt,
    collect,
)
from run_e012 import METAQA_DIR, SPLITS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78

#: The two limits this entry varies, and only these. The walk itself, the
#: expansion depth and `kind_cap` are held at what E-002 shipped — E-015 is
#: about what retrieval discards, not about how it searches.
FRONTIER_CAPS: tuple[int, ...] = (400, 1600)
TOKEN_BUDGETS: tuple[int, ...] = (6000, 24000, 96000)

#: Added by amendment 2026-09-13b. The original grid varied `frontier_cap`,
#: which turned out to be inert: raising it admitted 2.5x more candidate
#: triples and `add_evidence` discarded every extra one, because its cap is
#: per (template, kind) and the template is `metaqa_expand_{distance}` — a
#: thousand triples per level. The entry named the wrong second limit.
KIND_CAPS: tuple[int, ...] = (E002_KIND_CAP,)

#: Registered before the run. Branch 1 needs reach above 0.50; branch 2 is
#: every cell below 0.20; anything else is branch 3 and draws no consequence
#: for shipped trimming.
BRANCH_1_REACH = 0.50
BRANCH_2_REACH = 0.20

#: The depth this entry is about. One and two hops are already at full reach
#: and are collected only as the control that the harness is behaving.
HOPS = 3


def median(values: list[int]) -> int:
    return sorted(values)[len(values) // 2] if values else 0


def cell(
    session,
    questions: list[metaqa.Question],
    frontier_cap: int,
    token_budget: int,
    kind_cap: int = E002_KIND_CAP,
) -> dict:
    """One grid cell: chain reach, and what it cost in items and tokens."""
    reached = 0
    items: list[int] = []
    tokens: list[int] = []
    for question in questions:
        subgraph, _ = collect(
            session,
            question,
            frontier_cap=frontier_cap,
            kind_cap=kind_cap,
            token_budget=token_budget,
        )
        items.append(len(subgraph.evidence))
        tokens.append(subgraph.tokens)
        # The repaired guard: a chain of exactly the declared depth, or None.
        # A shorter chain reaches an accepted answer string without answering
        # the question, which is the defect E-012's amendment records.
        if metaqa.answer_path(
            subgraph.evidence, question.seed, question.answers, hops=question.hops
        ):
            reached += 1
    interval = wilson_interval(reached, len(questions))
    return {
        "frontier_cap": frontier_cap,
        "token_budget": token_budget,
        "kind_cap": kind_cap,
        "n": len(questions),
        "reached": reached,
        "reach": interval.point,
        "low": interval.low,
        "high": interval.high,
        "median_items": median(items),
        "median_tokens": median(tokens),
    }


def monotonicity(rows: list[dict]) -> list[str]:
    """Registered prediction 2, as a check that can return negative.

    Raising a cap or a budget can only add evidence, so reach cannot fall. A
    cell that violates this is a harness bug and not a finding, and the entry
    says no number is read until it is explained.
    """
    complaints: list[str] = []
    by_key: dict[tuple[int, int, int], dict] = {}
    for row in rows:
        # Every limit is part of the key. Amendment 2026-09-13b added a third
        # axis, and a key that still named two would have collapsed two cells
        # onto one entry and dropped a comparison without saying so.
        key = (row["frontier_cap"], row["token_budget"], row.get("kind_cap", 0))
        if key in by_key:
            complaints.append(f"two cells share the setting {key}")
        by_key[key] = row
    for smaller, row in sorted(by_key.items()):
        for bigger in sorted(by_key):
            if bigger == smaller:
                continue
            # strict=True: both keys are built by the same expression above, so
            # a future fourth axis added to one and not the other raises here
            # instead of silently comparing a prefix and calling it dominance.
            if any(b < s for b, s in zip(bigger, smaller, strict=True)):
                continue
            if by_key[bigger]["reached"] < row["reached"]:
                complaints.append(
                    f"reach falls from {row['reached']}/{row['n']} at "
                    f"(frontier {smaller[0]}, budget {smaller[1]}, kind_cap {smaller[2]}) "
                    f"to {by_key[bigger]['reached']}/{by_key[bigger]['n']} at "
                    f"(frontier {bigger[0]}, budget {bigger[1]}, kind_cap {bigger[2]})"
                )
    return complaints


def branch(rows: list[dict]) -> str:
    """The registered rule as a pure function, so it can be tested without a run.

    Branch 1 needs one cell above 0.50; branch 2 needs *every* cell below 0.20.
    A grid straddling the two is branch 3, which draws no consequence for
    shipped trimming — the same bar E-013 was held to.
    """
    if any(row["reach"] > BRANCH_1_REACH for row in rows):
        return "1"
    if all(row["reach"] < BRANCH_2_REACH for row in rows):
        return "2"
    return "3"


def verdict(rows: list[dict]) -> None:
    """Read the registered branch off the grid. It is not chosen."""
    chosen = branch(rows)
    best = max(rows, key=lambda row: row["reach"])
    print(f"\n{RULE}\nREGISTERED DECISION RULE")
    print(f"Best cell: frontier {best['frontier_cap']}, budget {best['token_budget']} "
          f"-> reach {best['reach']:.3f} at {best['median_items']} median items.")
    if chosen == "1":
        clearing = [row for row in rows if row["reach"] > BRANCH_1_REACH]
        cheapest = min(clearing, key=lambda row: (row["median_items"], row["median_tokens"]))
        print("BRANCH 1 — the three-hop failure is substantially an artefact of")
        print("           these two limits.")
        print(f"  Cheapest cell clearing {BRANCH_1_REACH}: frontier "
              f"{cheapest['frontier_cap']}, budget {cheapest['token_budget']}, "
              f"{cheapest['median_items']} median items.")
        print("  - E-012's branch-2 consequence about enforce_budget is amended:")
        print("    it was inferred from a null that could not see this.")
        print("  - Any future 3-hop work uses that setting.")
        print("  - E-014 becomes answerable again there, with its own amendment.")
        print("\n  Reach is not correctness. This says the evidence COULD support")
        print("  an answer at that setting, and nothing about whether one is right.")
    elif chosen == "2":
        print("BRANCH 2 — breadth-first expansion from a seed does not reach")
        print("           three-hop answers at any setting worth paying for.")
        print("  - The finding is about the retrieval STRATEGY, not its limits.")
        print("  - E-014 stays suspended in its current form permanently.")
        print("  - P3 inherits this: decomposition replaces one three-hop")
        print("    retrieval with three one-hop retrievals, and one-hop reach is 1.0.")
    else:
        above = [row for row in rows if row["reach"] >= BRANCH_2_REACH]
        cheapest = min(above, key=lambda row: (row["median_items"], row["median_tokens"]))
        print(f"BRANCH 3 — reach clears {BRANCH_2_REACH} but not {BRANCH_1_REACH}.")
        print(f"  Cheapest cell above {BRANCH_2_REACH}: frontier "
              f"{cheapest['frontier_cap']}, budget {cheapest['token_budget']}.")
        print("  - Reported. No consequence drawn for shipped trimming: a change")
        print("    that cheap should not need a close reading to justify, which is")
        print("    the bar E-013 was held to.")


def sweep(args: argparse.Namespace) -> int:
    _, _, path = SPLITS[args.split]
    if not path.exists():
        raise SystemExit(f"No {args.split} split at {path}.")
    questions = [q for q in metaqa.load_frozen(path, args.metaqa_dir) if q.hops == HOPS]
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit(f"No {HOPS}-hop questions in the {args.split} split.")

    frontiers = (args.frontier,) if args.frontier else FRONTIER_CAPS
    budgets = (args.budget,) if args.budget else TOKEN_BUDGETS
    caps = tuple(args.kind_caps) if args.kind_caps else KIND_CAPS

    print(f"E-015 — {len(questions)} {HOPS}-hop question(s) from the {args.split} split.")
    print("Zero model calls. Chain reach is a RETRIEVAL metric, never a score.\n")

    rows: list[dict] = []
    with driver_session(_require_bolt(metaqa_target())) as session:
        for frontier_cap in frontiers:
            for token_budget in budgets:
                for kind_cap in caps:
                    started = time.monotonic()
                    print(
                        f"  collecting frontier={frontier_cap} budget={token_budget} "
                        f"kind_cap={kind_cap} ...",
                        flush=True,
                    )
                    row = cell(session, questions, frontier_cap, token_budget, kind_cap)
                    row["seconds"] = round(time.monotonic() - started, 1)
                    rows.append(row)

    print(f"\n{RULE}")
    print(f"{'frontier':>10}{'budget':>10}{'kind_cap':>10}{'reach':>28}{'items':>10}{'tokens':>10}")
    print(RULE)
    for row in rows:
        reach = f"{row['reach']:.3f} [{row['low']:.3f},{row['high']:.3f}] {row['reached']}/{row['n']}"
        print(f"{row['frontier_cap']:>10}{row['token_budget']:>10}{row['kind_cap']:>10}"
              f"{reach:>28}{row['median_items']:>10}{row['median_tokens']:>10}")
    print(RULE)

    complaints = monotonicity(rows)
    if complaints:
        print("\n** MONOTONICITY VIOLATED — registered prediction 2.")
        for line in complaints:
            print(f"   {line}")
        print("   Raising a limit can only add evidence, so this is a harness bug")
        print("   and not a finding. No number above is read until it is explained.")
        return 1
    print("\nMonotonicity holds: reach never falls as a limit rises.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(rows)} cell(s) -> {args.out}")

    if len(rows) < 2:
        print("\nSingle cell: no branch printed. The rule reads a grid.")
        return 0
    verdict(rows)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sweeper = sub.add_parser("sweep", help="chain reach across the registered grid")
    sweeper.add_argument("--split", choices=sorted(SPLITS), default="dev")
    sweeper.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    sweeper.add_argument("--frontier", type=int, default=0, help="one cap instead of the grid")
    sweeper.add_argument("--budget", type=int, default=0, help="one budget instead of the grid")
    sweeper.add_argument(
        "--kind-caps",
        type=int,
        nargs="+",
        default=None,
        dest="kind_caps",
        help="amendment 2026-09-13b: the per-(template, kind) cap, which is what binds",
    )
    sweeper.add_argument("--limit", type=int, default=0)
    sweeper.add_argument("--out", type=Path, default=None)
    sweeper.set_defaults(func=sweep)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
