#!/usr/bin/env python
"""Arm A's good-faith tuning sweep — pin 7's artefact, published whatever it says.

The roadmap's risk register marks a strawman baseline **critical** for
credibility, and pin 7 fixes the remedy: tune on the 20 frozen development
questions and publish the sweep. The claim E-001 may then make is not "the
graph beat the vector arm" but "the graph beat a vector arm tuned on the
development split, and here is the sweep".

Registered before this ran, and not renegotiated here:

  * **Objective** — gold-rule recall over the 15 development questions with
    a non-empty `gold_cr_rules`. `legality_1hop`'s five are excluded
    because the metric is undefined there and pin 9 gives that stratum its
    own. The known defect is that rule recall is close to blind on
    `interaction_multihop`, where the answer-bearing evidence is a ruling
    carrying no CR number, so the sweep is driven mostly by the other
    strata. **No second objective was invented to fix that** — choosing a
    metric after watching the registered one read low is exactly what pin 7
    forbids, and it would be the same move whether or not it favoured
    arm A.
  * **Adoption** — the best cell wins, **ties break toward the published
    defaults**, and a margin under **2 gold rules of 26** keeps the
    defaults. Fifteen questions cannot separate two cells that differ by
    one rule, and drifting off a default on noise is overfitting with
    extra steps. A sweep that must produce a change to count is not a
    sweep.

The whole grid is free: `k1`, `b` and RRF `k` are scoring parameters that
never touch the postings, so one index is built and re-scored, and the 20
query embeddings are computed once and passed into every cell.

Usage:
    python scripts/sweep_arm_a.py --out docs/sweeps/e001-arm-a.md
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections import Counter
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk, load_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.evaluation.baseline_vector import (
    BM25_B,
    BM25_K1,
    CANDIDATE_DEPTH,
    RRF_K,
    build_arm,
    gold_rules_found,
)
from graphrag_mtg.evaluation.corpus import build_corpus, corpus_sha256
from graphrag_mtg.evaluation.dense import DEFAULT_EMBEDDING_MODEL, OpenAiEncoder, VectorCache

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import (
    CACHE_DIR,
    GOLDEN_DIR,
    RULINGS_PATH,
    SPLIT_PATH,
    VECTORS_PATH,
    question_rows,
    text_of,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: The registered grid. The published defaults are a cell in it, not the
#: centre it is measured against.
GRID = {
    "k1": (0.9, 1.2, 1.6, 2.0),
    "b": (0.4, 0.75, 1.0),
    "rrf_k": (10, 30, 60),
    # Extended from (50, 100, 200) after the first sweep put every top
    # cell at 200, the largest value swept. A parameter that wins at
    # the boundary of its range has not been swept, it has been
    # truncated. Extending makes arm A stronger, and arm A is the
    # control this experiment predicts losing, so the change cannot
    # manufacture the predicted outcome.
    "depth": (50, 100, 200, 400, 800, 1600),
    "mode": ("hybrid", "dense", "lexical"),
    "iterative": (False, True),
}

DEFAULTS = {
    "k1": BM25_K1,
    "b": BM25_B,
    "rrf_k": RRF_K,
    "depth": CANDIDATE_DEPTH,
    "mode": "hybrid",
    "iterative": False,
}

#: Registered adoption margin, in gold rules out of 26.
ADOPTION_MARGIN = 2

#: Where the artefact lands. Pin 7 requires the sweep **published**, so it
#: goes under `docs/` and into the repo — not into the gitignored `runs/`,
#: where the claim "and here is the sweep" would point at nothing a reader
#: can open.
DEFAULT_OUT = Path("docs/sweeps/e001-arm-a.md")


def cells() -> list[dict]:
    """Every configuration, with the ones a parameter cannot reach removed.

    `k1` and `b` do nothing in `dense` mode and `rrf_k` does nothing when
    only one ranking exists, so those cells are duplicates of each other.
    Leaving them in would inflate the grid and, worse, let a duplicate win
    a tie against the defaults on nothing.
    """
    out: list[dict] = []
    seen: set[tuple] = set()
    for combo in itertools.product(*GRID.values()):
        cell = dict(zip(GRID.keys(), combo, strict=True))
        if cell["mode"] == "dense":
            cell = {**cell, "k1": DEFAULTS["k1"], "b": DEFAULTS["b"]}
        if cell["mode"] != "hybrid":
            cell = {**cell, "rrf_k": DEFAULTS["rrf_k"]}
        key = tuple(sorted(cell.items()))
        if key not in seen:
            seen.add(key)
            out.append(cell)
    return out


def is_default(cell: dict) -> bool:
    return all(cell[name] == value for name, value in DEFAULTS.items())


def distance_from_defaults(cell: dict) -> int:
    """How many parameters this cell moves away from the published defaults."""
    return sum(1 for name, value in DEFAULTS.items() if cell[name] != value)


def rank_key(cell: dict) -> tuple:
    """Sort order implementing "ties break toward the published defaults".

    The first version sorted on `(-found, not is_default)`, which
    distinguishes only the exact defaults cell and leaves every other tie
    to dictionary order. That was enough to matter: twelve cells tie at
    the top of the depth probe, differing in `rrf_k` and `iterative`, and
    the arbitrary winner would have been wired into arm A as "the tuned
    configuration". Component-wise now — fewest parameters moved first,
    then the cheapest depth, then a deterministic order — so the adopted
    cell is the least surprising member of its tie rather than the
    luckiest.
    """
    return (
        -cell["found"],
        distance_from_defaults(cell),
        cell["depth"],
        cell["iterative"],
        cell["rrf_k"],
        cell["k1"],
        cell["b"],
        cell["mode"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--split", type=Path, default=SPLIT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument("--rulings", type=Path, default=RULINGS_PATH)
    parser.add_argument("--vectors", type=Path, default=VECTORS_PATH)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--top", type=int, default=15, help="rows to print in the artefact")
    # Overrides exist so a follow-up probe runs through this same code
    # rather than a scratch script. The first sweep's winner sat at
    # `depth=200`, the largest value swept — a parameter that wins at the
    # edge of its grid has not been swept, it has been truncated — and
    # checking that needs the same scoring path, not a lookalike.
    parser.add_argument("--depths", type=int, nargs="+", default=None)
    parser.add_argument("--k1", type=float, nargs="+", default=None)
    parser.add_argument("--b", type=float, nargs="+", default=None)
    parser.add_argument("--rrf-k", type=int, nargs="+", default=None)
    parser.add_argument("--modes", nargs="+", default=None)
    parser.add_argument("--label", default="", help="a note recorded in the artefact")
    args = parser.parse_args()

    for name, override in (
        ("depth", args.depths), ("k1", args.k1), ("b", args.b),
        ("rrf_k", args.rrf_k), ("mode", args.modes),
    ):
        if override:
            GRID[name] = tuple(override)

    documents = build_corpus(
        parse_cr(args.cr),
        list(iter_bulk(bulk_path(ORACLE_CARDS_STEM))),
        load_bulk(args.rulings),
    )
    vectors = VectorCache(args.vectors).load(
        corpus_hash=corpus_sha256(documents),
        encoder=DEFAULT_EMBEDDING_MODEL,
        count=len(documents),
    )
    if vectors is None:
        raise SystemExit("No vectors for this corpus. Run `run_eval.py index` first.")
    encoder = OpenAiEncoder()

    rows = [r for r in question_rows(args.golden, args.split, "dev") if r.get("gold_cr_rules")]
    questions = [(r, text_of(r, args.cache_dir)) for r in rows]
    wanted = sum(len(dict.fromkeys(r["gold_cr_rules"])) for r in rows)
    print(f"{len(rows)} development questions carry gold rules, {wanted} rules in total")
    print(f"strata: {dict(Counter(r['stratum'] for r in rows))}")

    # Embedded once. A paid call inside a grid loop is how a sweep quietly
    # becomes unaffordable, and the sweep varies only scoring and fusion.
    print("embedding the questions once ...", flush=True)
    embedded = {r["id"]: encoder.encode([q])[0] for r, q in questions}

    arms = {
        mode: build_arm(
            documents,
            mode=mode,
            vectors=vectors,
            encoder=encoder if mode in {"hybrid", "dense"} else None,
            token_budget=10**9,
        )
        for mode in GRID["mode"]
    }

    grid = cells()
    # The adoption rule is defined relative to the published defaults, so a
    # run whose grid does not contain them has no baseline to compare
    # against. The first attempt at the depth probe narrowed `k1` and `b`
    # to the winning values, dropped the defaults out of the grid, and
    # crashed on `next()` after 405 seconds of scoring — which is the right
    # failure, because the alternative is silently treating some other cell
    # as the baseline. Fixed by always scoring the defaults, so every
    # artefact this script emits is comparable to every other.
    defaults_swept = any(is_default(cell) for cell in grid)
    if not defaults_swept:
        grid.append(dict(DEFAULTS))
    print(f"{len(grid)} distinct cells"
          f"{'' if defaults_swept else ' (the published defaults added as a baseline)'}\n",
          flush=True)
    started = time.time()
    results: list[dict] = []
    for index, cell in enumerate(grid, start=1):
        found = 0
        per_stratum: Counter[str] = Counter()
        for row, question in questions:
            got = arms[cell["mode"]].retrieve(
                question,
                depth=cell["depth"],
                iterative=cell["iterative"],
                k1=cell["k1"],
                b=cell["b"],
                rrf_k=cell["rrf_k"],
                query_vector=embedded[row["id"]],
            )
            hits, _ = gold_rules_found(got, row["gold_cr_rules"])
            found += hits
            per_stratum[row["stratum"]] += hits
        results.append({**cell, "found": found, "by_stratum": dict(per_stratum)})
        if index % 20 == 0 or index == len(grid):
            print(f"  {index}/{len(grid)}  {time.time() - started:5.0f}s", flush=True)

    baseline = next(r for r in results if is_default(r))
    ranked = sorted(results, key=rank_key)
    best = ranked[0]
    margin = best["found"] - baseline["found"]
    adopt = margin >= ADOPTION_MARGIN and not is_default(best)

    lines = [
        f"# E-001 arm A — good-faith tuning sweep{f' — {args.label}' if args.label else ''}",
        "",
        *( [f"**{args.label}**", ""] if args.label else [] ),
        "Pin 7's artefact. Published whatever it says. Registered before it ran:",
        "the objective is gold-rule recall on the development questions carrying",
        "gold rules, ties break toward the published defaults, and a margin under",
        f"{ADOPTION_MARGIN} gold rules keeps the defaults.",
        "",
        f"- questions: **{len(rows)}** of 20 (the five `legality_1hop` carry no gold rule)",
        f"- gold rules available: **{wanted}**",
        f"- cells: **{len(grid)}**, no LLM call, {time.time() - started:.0f}s"
        + ("" if defaults_swept else " (the published defaults scored as a baseline outside the grid)"),
        f"- corpus: `{corpus_sha256(documents)[:12]}`, encoder `{DEFAULT_EMBEDDING_MODEL}`",
        "",
        "## Result",
        "",
        f"- published defaults: **{baseline['found']}/{wanted}**",
        f"- best cell: **{best['found']}/{wanted}**  "
        f"(`k1={best['k1']} b={best['b']} rrf_k={best['rrf_k']} depth={best['depth']} "
        f"mode={best['mode']} iterative={best['iterative']}`)",
        f"- margin: **{margin:+d}** gold rules",
        "",
        (
            f"**Adopted.** The margin reaches the registered {ADOPTION_MARGIN}."
            if adopt
            else f"**Not adopted.** The margin is under the registered {ADOPTION_MARGIN}, so "
            "the published defaults stand and this sweep found nothing. A sweep that must "
            "produce a change to count is not a sweep."
        ),
        "",
        f"## Top {args.top} cells",
        "",
        "| found | k1 | b | rrf_k | depth | mode | iterative |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in ranked[: args.top]:
        mark = "  ← defaults" if is_default(row) else ""
        lines.append(
            f"| {row['found']}/{wanted}{mark} | {row['k1']} | {row['b']} | {row['rrf_k']} | "
            f"{row['depth']} | {row['mode']} | {row['iterative']} |"
        )
    lines += [
        "",
        "## By mode, best cell in each",
        "",
        "| mode | best found | at |",
        "|---|---|---|",
    ]
    for mode in GRID["mode"]:
        top = max((r for r in results if r["mode"] == mode), key=lambda r: r["found"])
        lines.append(
            f"| {mode} | {top['found']}/{wanted} | "
            f"`k1={top['k1']} b={top['b']} rrf_k={top['rrf_k']} depth={top['depth']} "
            f"iterative={top['iterative']}` |"
        )
    lines += [
        "",
        "## Known defect of the objective",
        "",
        "Rule recall is close to blind on `interaction_multihop`: the",
        "answer-bearing evidence there is a Scryfall ruling, which carries no CR",
        "number and therefore scores zero however well it was retrieved. This",
        "sweep is driven mostly by the other strata, and that is stated rather",
        "than discovered. No second objective was invented to fix it — choosing a",
        "metric after watching the registered one read low is what pin 7 forbids,",
        "and it would be the same move whether or not it favoured arm A.",
        "",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    # The full grid beside the artefact. A top-15 table is a summary, and
    # the questions this sweep raised — does `b` help at the default depth,
    # where does the depth curve turn — are all answerable from the raw
    # cells and none of them from the table.
    args.out.with_suffix(".jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in ranked) + "\n",
        encoding="utf-8",
    )

    print(f"\ndefaults {baseline['found']}/{wanted}   best {best['found']}/{wanted}   "
          f"margin {margin:+d}")
    print("ADOPTED" if adopt else "NOT ADOPTED — the defaults stand")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
