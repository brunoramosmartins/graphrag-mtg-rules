#!/usr/bin/env python
"""Carve a development subset out of the golden set, once, before Phase 4.

Phase 4 writes traversal templates. Without this split it would write them
against the same 77 questions E-001 measures on, which is fitting the
retriever to the test set — the failure the whole registry exists to
prevent, and the one Phase 3 spent its effort avoiding on the extraction
side.

The fix is only cheap **before** the first template exists. Afterwards
there is nothing left to fix, only something to declare.

    python scripts/split_golden.py draw --n 20
    python scripts/split_golden.py check

The draw is stratified proportionally so the development subset looks like
the set it is carved from, seeded, and frozen in
`data/golden/phase4_dev_ids.json`. Everything not listed there is the
E-001 evaluation set and stays untouched until Phase 6.

One consequence is stated rather than hidden: `keyword_rule_2hop` has 3
questions in total, so a proportional draw leaves 1 in dev and 2 in
evaluation. Neither side can support a per-stratum claim about it. The
alternative — leaving all 3 in evaluation — would mean writing that
stratum's template with no example to develop against, which trades a
reporting limitation for a contamination risk. The limitation is the
better trade, and it is written down.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN_DIR = Path("data/golden")
SPLIT_PATH = Path("data/golden/phase4_dev_ids.json")
DEFAULT_N = 20
DEFAULT_SEED = 20260809

# Files holding golden-set questions. Other .jsonl files in the directory
# are extraction artifacts and must not be swept in.
QUESTION_FILES = ("authored_v0.jsonl", "definitions_v0.jsonl", "ids_v0.jsonl")


def load_questions(directory: Path, files: Sequence[str] = QUESTION_FILES) -> list[dict]:
    """Questions from the named files under ``directory``.

    ``files`` is overridable so the same seeded, largest-remainder draw can
    split a pool that is not the golden set — E-007 needs 10 of its 40
    audit questions for prompt development, and a second implementation of
    "draw a stratified subset" is a second thing that can be subtly wrong.
    """
    rows = []
    for name in files:
        path = directory / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                # `gold_path` marks a golden-set row; an E-007 pool skeleton
                # has no gold path and is admitted on its stratum alone.
                if "gold_path" in row or "stratum" in row:
                    rows.append(row)
    return rows


def allocate(counts: Mapping[str, int], n: int) -> dict[str, int]:
    """Split ``n`` draws across strata proportionally (largest remainder)."""
    total = sum(counts.values())
    if total == 0:
        return {}
    if n >= total:
        return dict(counts)
    exact = {s: c * n / total for s, c in counts.items()}
    base = {s: int(v) for s, v in exact.items()}
    order = sorted(counts, key=lambda s: (-(exact[s] - base[s]), s))
    for stratum in order[: n - sum(base.values())]:
        base[stratum] += 1
    return base


def draw(rows: list[dict], n: int, seed: int) -> list[str]:
    """Pick ``n`` question ids, stratified proportionally and seeded."""
    by_stratum: dict[str, list[str]] = {}
    for row in rows:
        by_stratum.setdefault(row["stratum"], []).append(row["id"])
    rng = random.Random(seed)
    quota = allocate({s: len(ids) for s, ids in by_stratum.items()}, n)
    picked: list[str] = []
    for stratum in sorted(quota):
        picked.extend(rng.sample(sorted(by_stratum[stratum]), quota[stratum]))
    return sorted(picked)


def composition(rows: list[dict], ids: set[str]) -> dict[str, int]:
    """Stratum counts for the subset named by ``ids``."""
    counts: dict[str, int] = {}
    for row in rows:
        if row["id"] in ids:
            counts[row["stratum"]] = counts.get(row["stratum"], 0) + 1
    return counts


def cmd_draw(args: argparse.Namespace) -> int:
    """Freeze the development subset. Refuses to redraw."""
    if args.split.exists() and not args.force:
        print(f"error: {args.split} already exists — the split is frozen.")
        print("Redrawing after templates exist would defeat its purpose. Use --force")
        print("only if no retrieval code has been written against it yet.")
        return 1

    rows = load_questions(args.golden, args.questions or QUESTION_FILES)
    if not rows:
        print(f"No questions in {args.golden}.")
        return 1
    dev_ids = draw(rows, args.n, args.seed)
    dev = set(dev_ids)

    args.split.parent.mkdir(parents=True, exist_ok=True)
    args.split.write_text(
        json.dumps(
            {
                "purpose": "Phase 4 development subset — templates are written against these only",
                "seed": args.seed,
                "n": len(dev_ids),
                "total": len(rows),
                "drawn_at": date.today().isoformat(),
                "dev_strata": composition(rows, dev),
                "eval_strata": composition(rows, {r["id"] for r in rows} - dev),
                "rule": (
                    "Everything not listed here is the E-001 evaluation set. "
                    "Retrieval code may be iterated against dev ids only; the "
                    "evaluation set is touched once, in Phase 6."
                ),
                "dev_ids": dev_ids,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Dev: {len(dev_ids)} of {len(rows)} questions (seed {args.seed}).")
    print(f"  dev  strata: {composition(rows, dev)}")
    print(f"  eval strata: {composition(rows, {r['id'] for r in rows} - dev)}")
    print(f"  frozen in {args.split}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report the split and verify every listed id still exists."""
    if not args.split.exists():
        print(f"No split at {args.split}. Run `split_golden.py draw` first.")
        return 1
    meta = json.loads(args.split.read_text(encoding="utf-8"))
    rows = load_questions(args.golden, args.questions or QUESTION_FILES)
    known = {row["id"] for row in rows}
    missing = [qid for qid in meta["dev_ids"] if qid not in known]

    print(f"Split drawn {meta['drawn_at']} (seed {meta['seed']}): "
          f"{meta['n']} dev / {meta['total'] - meta['n']} evaluation.")
    print(f"  dev  strata: {meta['dev_strata']}")
    print(f"  eval strata: {meta['eval_strata']}")
    if missing:
        print(f"\nERROR: {len(missing)} dev ids no longer exist in the golden set: {missing}")
        return 1
    if len(rows) != meta["total"]:
        print(
            f"\nWARNING: the golden set now has {len(rows)} questions, not {meta['total']}."
            "\nNew questions default to the evaluation side; that is safe, but say so"
            "\nin docs/evaluation.md rather than leaving the reader to infer it."
        )
    print("\nEvery dev id resolves. The evaluation set is everything else.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--split", type=Path, default=SPLIT_PATH)
    parser.add_argument(
        "--questions",
        action="append",
        default=[],
        help=(
            "file name(s) under --golden to split, instead of the golden set. "
            "Used for E-007's 10/30 draw over its own audit pool."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    drawer = sub.add_parser("draw", help="freeze the development subset")
    drawer.add_argument("--n", type=int, default=DEFAULT_N)
    drawer.add_argument("--seed", type=int, default=DEFAULT_SEED)
    drawer.add_argument("--force", action="store_true")
    drawer.set_defaults(func=cmd_draw)

    checker = sub.add_parser("check", help="report the split and validate it")
    checker.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
