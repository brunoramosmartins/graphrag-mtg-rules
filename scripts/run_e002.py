#!/usr/bin/env python
"""E-002: does the traversal-and-grounding spine reproduce published behaviour?

The claim this experiment may support is narrow and was registered as such.
What ships is heavily MTG-specific — the linker resolves card names against a
Scryfall lexicon, and all nine retrieval templates are written in `Card` /
`Keyword` / `Rule` / `Ruling` / `Format`. None of that runs on a movie KG.

What does transfer is the spine: typed traversal out from a seeded entity,
the `Subgraph` budget and `kind_cap`, evidence with citable handles, and
generation that answers only from what it was given. That is what runs here,
against a benchmark with an answer key.

    sample        draw the registered subset and freeze it (no database)
    load          build the KB on the MetaQA instance, counted
    verify        traverse only: is the answer reachable at all? (free)
    run           one grounded answer per question (paid)
    report        Hits@1 per hop, against the floor and beside the band
    verify-clean  prove the corpus instance carries nothing of this
    teardown      the command that destroys the instance, and the check

`verify` before `run` is not ceremony. It splits a retrieval failure from a
reasoning failure before any tokens are spent, which is what E-006 and E-007
had to be re-run to learn.

Isolation is a **separate instance**, not a namespace — see the E-002
amendment of 2026-09-02. Everything here that touches a graph goes through
`metaqa_target()`, which refuses to resolve to the corpus.

Usage:
    python scripts/run_e002.py sample --metaqa-dir data/raw/metaqa
    python scripts/run_e002.py load
    python scripts/run_e002.py verify
    python scripts/run_e002.py run --limit 10 --dry-run
    python scripts/run_e002.py report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from neo4j.exceptions import ServiceUnavailable

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import answer, build_prompt
from graphrag_mtg.graph.connection import driver_session, metaqa_target
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    Outcome,
    Subgraph,
    add_evidence,
    enforce_budget,
)

if TYPE_CHECKING:
    from neo4j import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

METAQA_DIR = Path("data/raw/metaqa")
SUBSET_PATH = Path("data/golden/metaqa_subset.json")
RETRIEVAL_PATH = Path("runs/e002_retrieval.jsonl")
ANSWERS_PATH = Path("runs/e002_answers.jsonl")

#: Registered configuration: 500 questions per hop, drawn once at this seed.
SUBSET_SEED = 20260815
SUBSET_N = 500

#: One line plus a citation marker. Generous by a factor of several; the
#: format is a single entity name, and anything longer is a prompt failure
#: this cap should not hide.
MAX_ANSWER_TOKENS = 200

#: Pass/fail, and the only one. MetaQA 1-hop is a single typed edge lookup
#: against a KB with no ambiguity; a spine that cannot reach this is broken,
#: and the divergence is chased as a defect before anything is written up.
FLOOR_1HOP = 0.90

#: Published Hits@1, primary-sourced, full-KB setting — per the amendment of
#: 2026-09-02. Reported beside our figure; it decides nothing. Every system
#: behind these numbers is trained on MetaQA and this project's spine is not.
BAND: dict[int, tuple[float, float]] = {1: (0.970, 0.975), 2: (0.988, 1.000), 3: (0.914, 1.000)}

#: Ceiling on how many entities one level may push into the next. A 3-hop
#: ball in a 135k-triple movie KG is enormous, and an uncapped expansion is
#: a query that never returns rather than an experiment. Truncation is
#: counted per question and reported — it is a third way to lose evidence,
#: alongside `dropped` and `capped`, and hiding it would corrupt exactly the
#: prediction this experiment registered about budget.
DEFAULT_FRONTIER_CAP = 400

RULE = "-" * 78


# ─────────────────────────────────────────────────────────────────────────────
# Sample — drawn once, frozen as ids
# ─────────────────────────────────────────────────────────────────────────────


def sample(args: argparse.Namespace) -> int:
    """Draw the registered subset from the local release and freeze it."""
    drawn: list[metaqa.Question] = []
    for hops in metaqa.HOPS:
        path = metaqa.question_path(args.metaqa_dir, hops, args.split)
        pool = metaqa.read_questions(path, hops)
        drawn.extend(metaqa.sample(pool, args.n, seed=args.seed))
        print(f"{hops}-hop: {len(pool)} available, {args.n} drawn")

    metaqa.freeze(drawn, args.out, seed=args.seed)
    print(f"\nFrozen {len(drawn)} ids at seed {args.seed} -> {args.out}")
    print("Ids only: the text and answers stay in the local release.")
    print("Next: python scripts/run_e002.py load")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Load — into a separate instance, and counted
# ─────────────────────────────────────────────────────────────────────────────


def load(args: argparse.Namespace) -> int:
    """Build the MetaQA KB on its own instance, asserting created == declared."""
    triples = metaqa.read_kb(args.metaqa_dir / "kb.txt")
    names = metaqa.entity_names(triples)
    grouped = metaqa.by_relation(triples)
    distinct_edges = sum(len(rows) for rows in grouped.values())
    print(f"read {len(triples)} triples, {len(names)} entities, {len(grouped)} relations")

    with driver_session(metaqa_target()) as session:
        metaqa.assert_database_is_empty(session)
        session.run(metaqa.CONSTRAINT_ENTITY_NAME)

        for start in range(0, len(names), args.batch):
            session.run(metaqa.MERGE_ENTITIES, names=names[start : start + args.batch])
        created_nodes = session.run(metaqa.COUNT_PREFIXED).single()["nodes"]

        for rel_type, rows in sorted(grouped.items()):
            statement = metaqa.edge_statement(rel_type)
            for start in range(0, len(rows), args.batch):
                session.run(statement, rows=rows[start : start + args.batch])
            print(f"  {rel_type}: {len(rows)}")

        total_nodes = session.run(metaqa.COUNT_ALL).single()["nodes"]
        total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]

    print(f"\nnodes {total_nodes}  relationships {total_rels}")
    if created_nodes != len(names) or total_nodes != len(names):
        raise SystemExit(
            f"declared {len(names)} entities, the graph holds {total_nodes} "
            f"({created_nodes} prefixed). A count that does not match what this "
            "load declared means the target was not what it claimed to be."
        )
    if total_rels > distinct_edges:
        raise SystemExit(
            f"declared at most {distinct_edges} edges, the graph holds {total_rels}."
        )
    print("Next: python scripts/run_e002.py verify")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Traversal — the spine, with every loss counted
# ─────────────────────────────────────────────────────────────────────────────


def collect(
    session: Session,
    question: metaqa.Question,
    *,
    frontier_cap: int,
    kind_cap: int,
    token_budget: int,
) -> tuple[Subgraph, dict[str, object]]:
    """Walk out from the seed entity to the question's own depth.

    Expansion is done a level at a time from Python rather than as one
    variable-length Cypher pattern, so the frontier can be bounded and the
    bounding can be counted. An unbounded 3-hop pattern on this KB is a
    query that does not return.

    Returns:
        The subgraph, and a stats dict recording every way evidence was
        lost: `truncated` from the frontier cap, plus the subgraph's own
        `dropped` and `capped` counters.
    """
    subgraph = Subgraph(question=question.text)
    seed_exists = session.run(
        f"MATCH (e:{metaqa.ENTITY_LABEL} {{name: $name}}) RETURN count(e) AS n",
        name=question.seed,
    ).single()["n"]
    if not seed_exists:
        subgraph.outcome = Outcome.NO_SEED
        subgraph.note = f"seed entity {question.seed!r} is not in the KB"
        return subgraph, {"truncated": 0, "entities": [], "triples": 0}

    frontier = [question.seed]
    visited = {question.seed}
    entities = {question.seed}
    seen: set[tuple[str, str, str]] = set()
    truncated = 0
    ordinal = 1

    for distance in range(1, question.hops + 1):
        if not frontier:
            break
        rows = session.run(metaqa.EXPAND_FRONTIER, names=frontier).data()

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

        add_evidence(
            subgraph,
            metaqa.triple_evidence(fresh, distance=distance, start=ordinal),
            kind_cap=kind_cap,
        )
        ordinal += len(fresh)
        subgraph.templates_run.append(f"metaqa_expand_{distance}")

        reached = sorted({t.head for t in fresh} | {t.tail for t in fresh})
        entities.update(reached)
        nxt = [name for name in reached if name not in visited]
        if len(nxt) > frontier_cap:
            truncated += len(nxt) - frontier_cap
            nxt = nxt[:frontier_cap]
        visited.update(nxt)
        frontier = nxt

    enforce_budget(subgraph, token_budget)
    if subgraph.is_empty:
        subgraph.outcome = Outcome.NO_MATCH
    return subgraph, {
        "truncated": truncated,
        "entities": sorted(entities),
        "triples": len(seen),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Verify — the reach ceiling, before a token is spent
# ─────────────────────────────────────────────────────────────────────────────


def verify(args: argparse.Namespace) -> int:
    """Traverse every question and record whether the answer is reachable.

    This is the ceiling Hits@1 is read against. An answer the traversal
    never retrieved cannot be produced by any prompt, and scoring generation
    against it would blame the model for the graph.
    """
    questions = _subset(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    reach: Counter[int] = Counter()
    totals: Counter[int] = Counter()
    with driver_session(metaqa_target()) as session, args.out.open("w", encoding="utf-8") as fh:
        for question in questions:
            subgraph, stats = collect(
                session,
                question,
                frontier_cap=args.frontier_cap,
                kind_cap=args.kind_cap,
                token_budget=args.token_budget,
            )
            present = any(metaqa.hits_at_1(name, question) for name in stats["entities"])
            totals[question.hops] += 1
            reach[question.hops] += int(present)
            fh.write(
                json.dumps(
                    {
                        "qid": question.qid,
                        "hops": question.hops,
                        "seed": question.seed,
                        "outcome": str(subgraph.outcome),
                        "answer_reachable": present,
                        "evidence": len(subgraph.evidence),
                        "triples_seen": stats["triples"],
                        "truncated": stats["truncated"],
                        "dropped": dict(subgraph.dropped),
                        "capped": dict(subgraph.capped),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"Verified {len(questions)} question(s) -> {args.out}\n")
    print("reach ceiling (answer entity present in the traversed subgraph):")
    for hops in sorted(totals):
        interval = wilson_interval(reach[hops], totals[hops])
        print(f"  {hops}-hop  {interval}")
    print("\nHits@1 cannot exceed this. A gap here is retrieval, not reasoning.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Run — paid, and only against verified retrieval
# ─────────────────────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> int:
    """One grounded answer per question, at temperature 0."""
    questions = _subset(args)
    if args.limit:
        questions = questions[: args.limit]
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} exists — pass --force only if you mean to replace it.")

    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)

    with driver_session(metaqa_target()) as session:
        prepared = [
            (question, *collect(
                session,
                question,
                frontier_cap=args.frontier_cap,
                kind_cap=args.kind_cap,
                token_budget=args.token_budget,
            ))
            for question in questions
        ]
        prompts = [_prompt(q, s) for q, s, _ in prepared]
        estimate = estimate_cost(
            prompts,
            model=client.model,
            output_tokens_per_call=MAX_ANSWER_TOKENS,
            system=metaqa.SYSTEM,
        )
        print(f"model {client.model} @ temperature 0, prompt {metaqa.PROMPT_VERSION}")
        print(f"estimate: {estimate}")
        if args.dry_run:
            print("\nDry run: nothing was sent.")
            return 0

        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for question, subgraph, stats in prepared:
                result = answer(
                    question.text,
                    subgraph,
                    lambda system, prompt: client.complete_text(prompt, system=system),
                    system=metaqa.SYSTEM,
                )
                predicted = metaqa.parse_prediction(result.text)
                correct = metaqa.hits_at_1(predicted, question)
                fh.write(
                    json.dumps(
                        {
                            "qid": question.qid,
                            "hops": question.hops,
                            "question": question.text,
                            "predicted": predicted,
                            "answers": list(question.answers),
                            "correct": correct,
                            "refused": result.refused,
                            "generated": result.generated,
                            "outcome": str(subgraph.outcome),
                            "unknown_handles": result.unknown,
                            "truncated": stats["truncated"],
                            "dropped": dict(subgraph.dropped),
                            "capped": dict(subgraph.capped),
                            "prompt_version": metaqa.PROMPT_VERSION,
                            "model": client.model,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                print(f"  {question.qid}: {'hit' if correct else 'miss'} ({predicted!r})")

    print(f"\nWrote {len(prepared)} answer(s) -> {args.out}")
    print("Next: python scripts/run_e002.py report")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Report — the registered rule, applied
# ─────────────────────────────────────────────────────────────────────────────


def report(args: argparse.Namespace) -> int:
    """Hits@1 per hop against the floor, beside the band, with the counters."""
    rows = _jsonl(args.answers)
    if not rows:
        raise SystemExit(f"No answers at {args.answers}. Run `run` first.")

    by_hop: dict[int, list[dict]] = {}
    for row in rows:
        by_hop.setdefault(row["hops"], []).append(row)

    print(f"E-002 — MetaQA calibration, {len(rows)} question(s)")
    print(f"prompt {rows[0]['prompt_version']}, model {rows[0]['model']}\n")
    print(f"{'hop':<6}{'Hits@1':<34}{'published band':<20}{'reading'}")
    print(RULE)

    verdicts: dict[int, str] = {}
    for hops in sorted(by_hop):
        answers = by_hop[hops]
        hits = sum(1 for r in answers if r["correct"])
        interval = wilson_interval(hits, len(answers))
        low, high = BAND[hops]
        if interval.point > high:
            reading = "ABOVE — run the leakage check before calling this a result"
        elif interval.point < low:
            reading = "below the band"
        else:
            reading = "inside the band"
        verdicts[hops] = reading
        print(f"{hops}-hop {str(interval):<34}[{low:.3f}, {high:.3f}]{'':<7}{reading}")

    print(RULE)
    one_hop = by_hop.get(1, [])
    if one_hop:
        floor_value = sum(1 for r in one_hop if r["correct"]) / len(one_hop)
        passed = floor_value >= FLOOR_1HOP
        print(f"\nFLOOR (the only pass/fail): 1-hop Hits@1 >= {FLOOR_1HOP:.2f}")
        print(f"  measured {floor_value:.3f} — {'PASS' if passed else 'FAIL'}")
        if not passed:
            print("  Below the floor the divergence is chased as a defect, not written up.")
            print("  Suspect the harness first: E-006's 0.067 was two harness bugs.")
    else:
        print("\nNo 1-hop questions in this run — the floor was not exercised.")

    print("\nWhere the losses were, per hop (the registered budget prediction):")
    for hops in sorted(by_hop):
        answers = by_hop[hops]
        misses = [r for r in answers if not r["correct"]]
        hits = [r for r in answers if r["correct"]]
        print(
            f"  {hops}-hop  misses with a non-empty counter: "
            f"{_share(misses)}   hits: {_share(hits)}"
        )
    print(
        "\nThe prediction is confirmed only if the miss share is materially higher\n"
        "than the hit share. Similar shares mean the failure is not budget."
    )

    refused = sum(1 for r in rows if r["refused"])
    ungrounded = sum(1 for r in rows if r["unknown_handles"])
    print(f"\nrefusals {refused}/{len(rows)}   answers citing a handle not in context: {ungrounded}")
    print("\nEvery figure above is the spine, not the pipeline. Linking, the MTG")
    print("templates and the Magic prompt were not exercised by this run.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Isolation — proving where this did and did not run
# ─────────────────────────────────────────────────────────────────────────────


def verify_clean(args: argparse.Namespace) -> int:
    """Prove the corpus instance holds nothing of MetaQA's, and say where it does."""
    with driver_session() as session:
        stray = session.run(metaqa.COUNT_PREFIXED).single()["nodes"]
    print(f"corpus instance: {stray} prefixed node(s)")
    if stray:
        raise SystemExit(
            f"{stray} {metaqa.ENTITY_LABEL} node(s) are in the corpus graph. MetaQA was "
            "loaded into the wrong instance. Nothing else may run until that is zero."
        )

    target = metaqa_target()
    try:
        with driver_session(target) as session:
            present = session.run(metaqa.COUNT_ALL).single()["nodes"]
        print(f"metaqa instance ({target.uri}): reachable, {present} node(s)")
        if present:
            print("Still loaded. Teardown when the run is finished.")
    except ServiceUnavailable:
        print(f"metaqa instance ({target.uri}): unreachable — the teardown state")
    print("\nThe corpus is clean.")
    return 0


def teardown(args: argparse.Namespace) -> int:
    """Name the command that destroys the instance, then check it happened.

    Deliberately does not run it. Teardown by container destruction is the
    whole point of the 2026-09-02 amendment — E-008's teardown was a DELETE
    that matched three real CR rules — and a script that can destroy things
    on its own is the shape of the problem, not the fix.
    """
    print("Teardown is destroying the container. The data has no volume:\n")
    print("  docker compose --profile metaqa rm -sf\n")
    return verify_clean(args)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _subset(args: argparse.Namespace) -> list[metaqa.Question]:
    if not args.subset.exists():
        raise SystemExit(f"No frozen subset at {args.subset}. Run `sample` first.")
    questions = metaqa.load_frozen(args.subset, args.metaqa_dir, split=args.split)
    if args.hops:
        questions = [q for q in questions if q.hops == args.hops]
    return questions


def _prompt(question: metaqa.Question, subgraph: Subgraph) -> str:
    return build_prompt(question.text, subgraph)


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _share(rows: list[dict]) -> str:
    """Share of rows that lost evidence to the budget, the cap or the frontier."""
    if not rows:
        return "n/a"
    lossy = sum(1 for r in rows if r["dropped"] or r["capped"] or r["truncated"])
    return f"{lossy}/{len(rows)} ({lossy / len(rows):.2f})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    common.add_argument("--subset", type=Path, default=SUBSET_PATH)
    common.add_argument("--split", default="test")
    common.add_argument("--hops", type=int, choices=metaqa.HOPS, default=0)
    common.add_argument("--frontier-cap", type=int, default=DEFAULT_FRONTIER_CAP)
    common.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)
    common.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)

    drawer = sub.add_parser("sample", help="draw and freeze the registered subset")
    drawer.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    drawer.add_argument("--split", default="test")
    drawer.add_argument("--out", type=Path, default=SUBSET_PATH)
    drawer.add_argument("--n", type=int, default=SUBSET_N)
    drawer.add_argument("--seed", type=int, default=SUBSET_SEED)
    drawer.set_defaults(func=sample)

    loader = sub.add_parser("load", help="build the KB on the MetaQA instance")
    loader.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    loader.add_argument("--batch", type=int, default=5000)
    loader.set_defaults(func=load)

    ver = sub.add_parser("verify", parents=[common], help="traverse only; is the answer reachable?")
    ver.add_argument("--out", type=Path, default=RETRIEVAL_PATH)
    ver.set_defaults(func=verify)

    runner = sub.add_parser("run", parents=[common], help="one grounded answer per question (paid)")
    runner.add_argument("--out", type=Path, default=ANSWERS_PATH)
    runner.add_argument("--model", default=None)
    runner.add_argument("--limit", type=int, default=0)
    runner.add_argument("--dry-run", action="store_true")
    runner.add_argument("--force", action="store_true")
    runner.set_defaults(func=run)

    rep = sub.add_parser("report", help="apply the registered decision rule")
    rep.add_argument("--answers", type=Path, default=ANSWERS_PATH)
    rep.set_defaults(func=report)

    clean = sub.add_parser("verify-clean", help="prove the corpus holds no MetaQA nodes")
    clean.set_defaults(func=verify_clean)

    down = sub.add_parser("teardown", help="the destroy command, and the check")
    down.set_defaults(func=teardown)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
