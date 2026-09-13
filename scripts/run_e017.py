#!/usr/bin/env python
"""E-017: is the three-hop haystack the depth, or the untyped walk?

E-016 returned branch 2 — the trim is not the lever — and recorded that
three-hop retrieval needs a different *walk*. This tests that sentence before
P3 builds anything on it.

The cheapest version of the decomposition thesis needs no agent: expand along
the relation the question is about instead of expanding along everything.
MetaQA has nine relations. If typing alone puts the chain inside the shipped
budget, P3 would be writing a planner for a problem a `WHERE type(r) = $rel`
already solved, and it should know that first.

**This entry measures size, not reach.** The relation sequence is read off the
gold answer chain, so the typed walk reaches the answer by construction and a
reach figure would be a tautology dressed as a result. What it bounds is what
typing could buy *if something chose the relations correctly*; nothing here
chooses them, and no number below is a system score.

The bar was fixed before the run: the untyped pool is a median 199,146 tokens
against a 6,000-token budget, so a typed walk must be at least 33x smaller to
fit at all.

Usage:
    python scripts/run_e017.py run
    python scripts/run_e017.py run --limit 10
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metaqa import ENTITY_LABEL
from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.graph.connection import driver_session, metaqa_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e002 import _require_bolt, collect
from run_e012 import METAQA_DIR, SPLITS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78

#: The untyped walk this is measured against, and the budget it has to fit.
#: Both fixed in the registration before the run.
TOKEN_BUDGET = 6000
MIN_REDUCTION_TO_FIT = 33

#: `kind_cap` at the setting E-016 used for its larger pool, so the untyped
#: figure here sits beside that entry's without a population caveat.
FRONTIER_CAP = 1600
KIND_CAP = 4000
HOPS = 3

#: Registered branch boundaries on the fit rate.
BRANCH_1_FIT = 0.80
BRANCH_2_FIT = 0.30

#: The typed expansion. Mirrors `EXPAND_FRONTIER` exactly — undirected match,
#: true direction recovered from the relationship — with one relation type
#: added. Any other difference would make the comparison measure the query
#: rather than the typing.
EXPAND_TYPED = f"""
UNWIND $names AS name
MATCH (a:{ENTITY_LABEL} {{name: name}})-[r]-(b:{ENTITY_LABEL})
WHERE type(r) = $rel
RETURN DISTINCT startNode(r).name AS head, type(r) AS relation, endNode(r).name AS tail
"""


def relations_of(chain: list) -> list[str]:
    """The prefixed relationship types along an answer chain, seed-first.

    Read off the gold chain, which is what makes this entry a ceiling: it asks
    what a typed walk would cost if something picked these, and nothing here
    picks them.
    """
    types: list[str] = []
    for item in chain:
        head, relation, tail = item.text.split(" | ")
        types.append(metaqa.Triple(head, relation, tail).rel_type)
    return types


def typed_walk(session, seed: str, rel_types: list[str]) -> tuple[list[metaqa.Triple], list[int]]:
    """Follow one relation per hop from the seed, and report the fan-out.

    Mirrors `collect`'s bookkeeping — frontier, visited, deduped triples — so
    the only difference from the untyped walk is the relation filter.

    Returns:
        ``(triples, reached_per_hop)``.
    """
    frontier = [seed]
    visited = {seed}
    seen: set[tuple[str, str, str]] = set()
    triples: list[metaqa.Triple] = []
    fan_out: list[int] = []

    for rel_type in rel_types:
        if not frontier:
            fan_out.append(0)
            continue
        rows = session.run(EXPAND_TYPED, names=frontier, rel=rel_type).data()
        fresh: list[metaqa.Triple] = []
        for row in rows:
            identity = (row["head"], row["relation"], row["tail"])
            if identity in seen:
                continue
            seen.add(identity)
            fresh.append(
                metaqa.Triple(
                    head=row["head"],
                    relation=metaqa.display_relation(row["relation"]),
                    tail=row["tail"],
                )
            )
        triples.extend(fresh)
        reached = sorted({t.head for t in fresh} | {t.tail for t in fresh})
        nxt = [name for name in reached if name not in visited]
        visited.update(nxt)
        fan_out.append(len(nxt))
        frontier = nxt
    return triples, fan_out


def tokens_of(triples: list[metaqa.Triple]) -> int:
    """Token cost under the same estimate the budget is enforced with."""
    return sum(
        item.tokens for item in metaqa.triple_evidence(triples, distance=1, start=1)
    )


def quartiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    if len(ordered) < 4:
        median = statistics.median(ordered) if ordered else 0.0
        return (median, median, median)
    lower, upper = statistics.quantiles(ordered, n=4)[0], statistics.quantiles(ordered, n=4)[2]
    return (lower, statistics.median(ordered), upper)


def run(args: argparse.Namespace) -> int:
    _, _, path = SPLITS[args.split]
    if not path.exists():
        raise SystemExit(f"No {args.split} split at {path}.")
    questions = [q for q in metaqa.load_frozen(path, args.metaqa_dir) if q.hops == HOPS]
    if args.limit:
        questions = questions[: args.limit]

    print(f"E-017 — {len(questions)} {HOPS}-hop question(s) from the {args.split} split.")
    print("Zero model calls. This measures SIZE. A reach figure from this design")
    print("would be a tautology: the walk follows the gold chain's own relations.\n")

    rows: list[dict] = []
    excluded = 0
    started = time.monotonic()
    with driver_session(_require_bolt(metaqa_target())) as session:
        for question in questions:
            untyped, _ = collect(
                session,
                question,
                frontier_cap=FRONTIER_CAP,
                kind_cap=KIND_CAP,
                token_budget=10**9,
            )
            chain = metaqa.answer_path(
                untyped.evidence, question.seed, question.answers, hops=question.hops
            )
            if chain is None:
                # No chain in the pool, so no relation sequence to read off.
                # Counted, never quietly skipped: E-015's amendment exists
                # because an exclusion rule was read as a property of the data.
                excluded += 1
                continue
            rel_types = relations_of(chain)
            triples, fan_out = typed_walk(session, question.seed, rel_types)
            typed_tokens = tokens_of(triples)
            # The harness check, and it can fail: following the chain's own
            # relations must reproduce the chain. If it does not, the query,
            # the direction handling or the visited rule is wrong, and no size
            # figure below is readable.
            wanted = {(t.head, t.relation, t.tail) for t in triples}
            chain_present = all(
                tuple(item.text.split(" | ")) in wanted for item in chain
            )
            rows.append({
                "qid": question.qid,
                "relations": [metaqa.display_relation(r) for r in rel_types],
                "typed_triples": len(triples),
                "typed_tokens": typed_tokens,
                "untyped_tokens": untyped.tokens,
                "reduction": untyped.tokens / typed_tokens if typed_tokens else 0.0,
                "fits": typed_tokens <= TOKEN_BUDGET,
                "fan_out": fan_out,
                "chain_present": chain_present,
            })
    print(f"  {round(time.monotonic() - started, 1)}s")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(rows)} row(s) -> {args.out}")

    return report(rows, excluded)


def report(rows: list[dict], excluded: int) -> int:
    if not rows:
        raise SystemExit("No question produced a chain, so nothing can be measured.")
    n = len(rows)

    intact = sum(row["chain_present"] for row in rows)
    print(f"\n{RULE}\nHARNESS CHECK — the typed walk must reproduce the chain "
          f"it followed: {intact}/{n}")
    if intact < n:
        print("  ** It does not. The query, the direction handling or the visited")
        print("     rule is wrong, and no size figure below is readable.")
        return 1
    print("  passed.")

    fit = wilson_interval(sum(row["fits"] for row in rows), n)
    low, median, high = quartiles([row["reduction"] for row in rows])
    typed = quartiles([float(row["typed_tokens"]) for row in rows])
    untyped_median = statistics.median(row["untyped_tokens"] for row in rows)

    print(f"\n{RULE}\n{n} question(s) measured, {excluded} excluded (no chain in the pool)")
    print(RULE)
    print(f"  fit rate at {TOKEN_BUDGET} tokens   {fit.point:.3f} "
          f"[{fit.low:.3f},{fit.high:.3f}]  {sum(row['fits'] for row in rows)}/{n}")
    print(f"  typed tokens              median {typed[1]:,.0f}  "
          f"(q1 {typed[0]:,.0f}, q3 {typed[2]:,.0f})")
    print(f"  untyped tokens            median {untyped_median:,.0f}")
    print(f"  reduction factor          median {median:,.1f}x  "
          f"(q1 {low:,.1f}x, q3 {high:,.1f}x)  bar was {MIN_REDUCTION_TO_FIT}x")

    print("\n  FAN-OUT — entities newly reached at each hop, median.")
    for hop in range(HOPS):
        values = [row["fan_out"][hop] for row in rows if len(row["fan_out"]) > hop]
        print(f"    hop {hop + 1}: {statistics.median(values):,.0f}  "
              f"(max {max(values):,})")

    print(f"\n{RULE}\nREGISTERED DECISION RULE")
    if fit.point >= BRANCH_1_FIT:
        print("BRANCH 1 — typed expansion alone puts the chain inside the budget.")
        print("  - P3's first registered experiment is TYPED EXPANSION, not an agent.")
        print("  - An agent is justified only by what typing leaves on the table.")
        print("  - The next entry measures the price of choosing the relations")
        print("    without the gold chain, which this entry did not pay.")
    elif fit.point <= BRANCH_2_FIT:
        print("BRANCH 2 — typing is not the saving.")
        print("  - The fan-out is inherent to this KB at depth three.")
        print("  - E-016's reading that 'the walk is the problem' is wrong or")
        print("    incomplete: no walk of this family fits, typed or not.")
        print("  - The decomposition thesis does not inherit E-016 as support,")
        print("    and P3 has to justify itself on something else.")
    else:
        print(f"BRANCH 3 — fit rate between {BRANCH_2_FIT} and {BRANCH_1_FIT}.")
        print("  - No build direction is decided here. The reduction factor is")
        print("    carried into P3's registration as a prior, not as a verdict.")

    print("\nThe relation sequence came from the gold chain. This bounds what typing")
    print("could buy if something chose correctly; nothing here chose. Not a score.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="typed versus untyped expansion size (free)")
    runner.add_argument("--split", choices=sorted(SPLITS), default="dev")
    runner.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    runner.add_argument("--limit", type=int, default=0)
    runner.add_argument("--out", type=Path, default=Path("runs/e017_dev.jsonl"))
    runner.set_defaults(func=run)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
