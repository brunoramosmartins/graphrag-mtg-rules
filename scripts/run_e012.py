#!/usr/bin/env python
"""E-012: is long-context generation failing on size, or on depth?

E-002 measured that the generator uses a third of what retrieval hands it at
three hops. It cannot say why. Its 3-hop subgraphs are deeper *and* far
larger at once — a median 206 evidence items against 17 at two hops — so
"cannot chain three facts" and "cannot find the fact among 206" fit the same
data and imply opposite repairs.

    explore   12a — correctness against context size and depth, on the runs
              that already exist. EXPLORATORY: it chooses the buckets 12b
              uses and decides nothing.

12b, the confirmatory arm that holds size constant and varies depth, is
registered in `experiments/registry.md` and lands here as further
subcommands. Nothing in `explore` spends a token.

Usage:
    python scripts/run_e012.py explore
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from graphrag_mtg.evaluation.metaqa import HOPS
from graphrag_mtg.evaluation.metrics import wilson_interval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RETRIEVAL = "runs/e002_retrieval_{hops}hop.jsonl"
ANSWERS = "runs/e002_answers_{hops}hop.jsonl"

#: Context-size buckets, roughly logarithmic. Fixed here rather than derived
#: from the data's quantiles, so the same edges hold when 12b re-measures and
#: the two arms remain comparable.
BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1-8", 1, 8),
    ("9-32", 9, 32),
    ("33-128", 33, 128),
    ("129-512", 129, 512),
    ("513+", 513, 10**9),
)

RULE = "-" * 78


def bucket_of(size: int) -> str:
    for label, low, high in BUCKETS:
        if low <= size <= high:
            return label
    return BUCKETS[-1][0]


def rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"Missing {path}. E-012a reads the completed E-002 runs.")
    return {
        json.loads(line)["qid"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def explore(args: argparse.Namespace) -> int:
    """12a — the exploratory cut, which chooses buckets and decides nothing."""
    cells: dict[tuple[int, str], list[bool]] = {}
    sizes: dict[int, list[int]] = {}

    for hops in HOPS:
        retrieval = rows(Path(RETRIEVAL.format(hops=hops)))
        answers = rows(Path(ANSWERS.format(hops=hops)))
        for qid, answer in answers.items():
            record = retrieval.get(qid)
            # Conditioning on the answer being shown is post-selection, and
            # is why this arm cannot decide anything: it asks what the model
            # did with evidence that provably contained the answer.
            if record is None or not record["answer_shown"]:
                continue
            size = record["evidence"]
            cells.setdefault((hops, bucket_of(size)), []).append(bool(answer["correct"]))
            sizes.setdefault(hops, []).append(size)

    print("E-012a — EXPLORATORY. Chooses the buckets 12b uses; decides nothing.")
    print("Restricted to questions whose answer was present in the evidence shown.\n")

    print(f"{'context size':<14}" + "".join(f"{f'{h}-hop':<26}" for h in HOPS))
    print(RULE)
    for label, _, _ in BUCKETS:
        line = f"{label:<14}"
        for hops in HOPS:
            scored = cells.get((hops, label), [])
            if len(scored) < args.min_n:
                line += f"{f'(n={len(scored)})':<26}"
            else:
                interval = wilson_interval(sum(scored), len(scored))
                line += f"{f'{interval.point:.3f} [{interval.low:.3f},{interval.high:.3f}] n={len(scored)}':<26}"
        print(line)
    print(RULE)

    print("\ncontext size actually seen, per hop:")
    for hops in HOPS:
        seen = sorted(sizes.get(hops, []))
        if not seen:
            continue
        median = seen[len(seen) // 2]
        print(f"  {hops}-hop  n={len(seen)}  median {median}  min {seen[0]}  max {seen[-1]}")

    print("\nRead down a column for the effect of size at fixed depth.")
    print("Read across a row for the effect of depth at roughly fixed size —")
    print("roughly, because these buckets were observed and not assigned, which")
    print("is exactly the confound 12b removes by setting k itself.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    explorer = sub.add_parser("explore", help="12a — exploratory, free, decides nothing")
    explorer.add_argument(
        "--min-n",
        type=int,
        default=15,
        help="cells thinner than this print their count instead of a rate",
    )
    explorer.set_defaults(func=explore)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
