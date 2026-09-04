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

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metaqa import HOPS
from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import answer, build_prompt
from graphrag_mtg.graph.connection import driver_session, metaqa_target
from graphrag_mtg.retrieval.subgraph import DEFAULT_TOKEN_BUDGET, Subgraph

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e002 import (  # sibling script; the sys.path line above enables it
    DEFAULT_FRONTIER_CAP,
    E002_KIND_CAP,
    MAX_ANSWER_TOKENS,
    PROMPTS,
    _require_bolt,
    collect,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RETRIEVAL = "runs/e002_retrieval_{hops}hop.jsonl"
ANSWERS = "runs/e002_answers_{hops}hop.jsonl"

METAQA_DIR = Path("data/raw/metaqa")
E002_SUBSET = Path("data/golden/metaqa_subset.json")

#: The two draws, both made before the first paid call — the structure E-002
#: did not have. `dev` carries every pilot and sanity check; `conf` is
#: touched once, at the end, and is what the decision rule reads.
SPLITS: dict[str, tuple[int, int, Path]] = {
    "dev": (100, 20260903, Path("data/golden/metaqa_e012_dev.json")),
    "conf": (300, 20260904, Path("data/golden/metaqa_e012_conf.json")),
}

#: Context sizes, amended from {16, 64, 256} by E-012a — which is what
#: E-012a was registered to decide. `0` means the untrimmed subgraph.
SIZES: tuple[int, ...] = (8, 16, 64, 256, 0)

#: Prompt held fixed. E-012 is not a prompt experiment, and editing it here
#: would void every comparison the entry registers.
PROMPT_KEY = "a3"

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
        for qid, graded in answers.items():
            record = retrieval.get(qid)
            # Conditioning on the answer being shown is post-selection, and
            # is why this arm cannot decide anything: it asks what the model
            # did with evidence that provably contained the answer.
            if record is None or not record["answer_shown"]:
                continue
            size = record["evidence"]
            cells.setdefault((hops, bucket_of(size)), []).append(bool(graded["correct"]))
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


# ─────────────────────────────────────────────────────────────────────────────
# 12b — size assigned, depth free to vary
# ─────────────────────────────────────────────────────────────────────────────


def sample(args: argparse.Namespace) -> int:
    """Draw both splits from outside E-002's subset, and freeze them."""
    spoken_for = set(json.loads(E002_SUBSET.read_text(encoding="utf-8"))["ids"])
    for name, (n, seed, path) in SPLITS.items():
        if path.exists():
            print(f"{name}: {path} already frozen, left alone")
            continue
        drawn: list[metaqa.Question] = []
        for hops in HOPS:
            pool = [
                q
                for q in metaqa.read_questions(
                    metaqa.question_path(args.metaqa_dir, hops), hops
                )
                if q.qid not in spoken_for
            ]
            drawn.extend(metaqa.sample(pool, n, seed=seed))
        metaqa.freeze(drawn, path, seed=seed)
        spoken_for |= {q.qid for q in drawn}
        print(f"{name}: {len(drawn)} ids at seed {seed} -> {path}")
    print("\nNeither split shares a question with E-002 or with the other.")
    return 0


def run(args: argparse.Namespace) -> int:
    """Answer every question at every assigned context size."""
    _, _, path = SPLITS[args.split]
    if not path.exists():
        raise SystemExit(f"No {args.split} split at {path}. Run `sample` first.")
    questions = metaqa.load_frozen(path, args.metaqa_dir)
    if args.hops:
        questions = [q for q in questions if q.hops == args.hops]
    if args.limit:
        questions = questions[: args.limit]

    done: set[tuple[str, int]] = set()
    if args.resume and args.out.exists():
        done = {(row["qid"], row["k"]) for row in _jsonl(args.out)}
        print(f"resuming {args.out}: {len(done)} cell(s) already answered")
    elif args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} exists — pass --resume or --force.")

    system, version = PROMPTS[PROMPT_KEY]
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    excluded = 0
    pending: list[tuple[metaqa.Question, int, Subgraph]] = []

    with driver_session(_require_bolt(metaqa_target())) as session:
        for question in questions:
            subgraph, _ = collect(
                session,
                question,
                frontier_cap=DEFAULT_FRONTIER_CAP,
                kind_cap=E002_KIND_CAP,
                token_budget=DEFAULT_TOKEN_BUDGET,
            )
            chain = metaqa.answer_path(subgraph.evidence, question.seed, question.answers)
            if chain is None:
                # The answer is not reachable through the evidence, so no
                # size can hold it. Excluded and counted: a size comparison
                # on a context that never contained the answer measures the
                # retrieval, not the generator.
                excluded += 1
                continue
            for k in SIZES:
                if (question.qid, k) in done:
                    continue
                kept = (
                    subgraph.evidence if k == 0 else metaqa.reduce_to_k(subgraph.evidence, chain, k)
                )
                cell = Subgraph(question=question.text, evidence=list(kept))
                pending.append((question, k, cell))

    print(f"{len(questions)} question(s), {excluded} excluded (answer unreachable)")
    if not pending:
        print("Nothing to answer.")
        return 0

    estimate = estimate_cost(
        [build_prompt(q.text, sg) for q, _, sg in pending],
        model=client.model,
        output_tokens_per_call=MAX_ANSWER_TOKENS,
        system=system,
    )
    print(f"model {client.model} @ temperature 0, prompt {version}, sizes {SIZES}")
    print(f"estimate: {estimate}")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a" if done else "w", encoding="utf-8") as handle:
        for index, (question, k, cell) in enumerate(pending, start=1):
            result = answer(
                question.text,
                cell,
                lambda system_text, prompt: client.complete_text(prompt, system=system_text),
                system=system,
            )
            predicted = metaqa.parse_prediction(result.text)
            handle.write(
                json.dumps(
                    {
                        "qid": question.qid,
                        "hops": question.hops,
                        "k": k,
                        "items": len(cell.evidence),
                        "predicted": predicted,
                        "correct": metaqa.hits_at_1(predicted, question),
                        "refused": result.refused,
                        "prompt_version": version,
                        "model": client.model,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            if index % 100 == 0:
                print(f"  {index}/{len(pending)}")

    print(f"\nWrote {len(pending)} cell(s) -> {args.out}")
    return 0


def report(args: argparse.Namespace) -> int:
    """Hits@1 by depth and assigned size, and the registered contrast."""
    rows_ = _jsonl(args.answers)
    if not rows_:
        raise SystemExit(f"No answers at {args.answers}.")

    cells: dict[tuple[int, int], list[bool]] = {}
    paired: dict[int, dict[int, dict[str, bool]]] = {}
    for row in rows_:
        cells.setdefault((row["hops"], row["k"]), []).append(bool(row["correct"]))
        paired.setdefault(row["hops"], {}).setdefault(row["k"], {})[row["qid"]] = bool(
            row["correct"]
        )

    print(f"E-012b — {len(rows_)} cell(s), prompt {rows_[0]['prompt_version']}\n")
    print(f"{'k':<10}" + "".join(f"{f'{h}-hop':<28}" for h in HOPS))
    print(RULE)
    for k in SIZES:
        label = "untrimmed" if k == 0 else str(k)
        line = f"{label:<10}"
        for hops in HOPS:
            scored = cells.get((hops, k), [])
            if not scored:
                line += f"{'—':<28}"
            else:
                ci = wilson_interval(sum(scored), len(scored))
                line += f"{f'{ci.point:.3f} [{ci.low:.3f},{ci.high:.3f}] n={len(scored)}':<28}"
        print(line)
    print(RULE)

    print("\nDEPTH AT MATCHED SIZE — the registered contrast.")
    print("Flat rows mean size; falling rows mean depth.\n")
    for k in SIZES:
        label = "untrimmed" if k == 0 else f"k={k}"
        points = [
            (h, wilson_interval(sum(cells[(h, k)]), len(cells[(h, k)])))
            for h in HOPS
            if cells.get((h, k))
        ]
        if len(points) < 2:
            continue
        spread = max(p.point for _, p in points) - min(p.point for _, p in points)
        overlap = all(
            points[i][1].low <= points[j][1].high and points[j][1].low <= points[i][1].high
            for i in range(len(points))
            for j in range(i + 1, len(points))
        )
        shape = "flat (intervals overlap)" if overlap else "separated"
        print(f"  {label:<12} " + "  ".join(f"{h}-hop {p.point:.3f}" for h, p in points))
        print(f"  {'':<12} spread {spread:.3f} — {shape}")

    print("\nSIZE AT FIXED DEPTH — paired within question, exact McNemar.")
    print("Holm correction over the family; alpha = 0.05.\n")
    tests: list[tuple[str, float, int, int]] = []
    for hops in HOPS:
        by_k = paired.get(hops, {})
        if 8 not in by_k or 0 not in by_k:
            continue
        ids = sorted(set(by_k[8]) & set(by_k[0]))
        if not ids:
            continue
        result = mcnemar([by_k[0][i] for i in ids], [by_k[8][i] for i in ids])
        tests.append((f"{hops}-hop untrimmed -> k=8", result.p_value, result.improved, result.regressed))
    for rank, (name, p, up, down) in enumerate(sorted(tests, key=lambda t: t[1])):
        threshold = 0.05 / (len(tests) - rank)
        verdict = "significant" if p <= threshold else "not significant"
        print(f"  {name:<32} +{up}/-{down}  p={p:.5f}  Holm alpha={threshold:.4f}  {verdict}")
    return 0


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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

    drawer = sub.add_parser("sample", help="freeze the dev and confirmatory splits")
    drawer.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    drawer.set_defaults(func=sample)

    runner = sub.add_parser("run", help="12b — answer at every assigned size (paid)")
    runner.add_argument("--split", choices=sorted(SPLITS), default="dev")
    runner.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    runner.add_argument("--hops", type=int, choices=HOPS, default=0)
    runner.add_argument("--out", type=Path, default=None)
    runner.add_argument("--model", default=None)
    runner.add_argument("--limit", type=int, default=0)
    runner.add_argument("--dry-run", action="store_true")
    runner.add_argument("--resume", action="store_true")
    runner.add_argument("--force", action="store_true")
    runner.set_defaults(func=run)

    rep = sub.add_parser("report", help="apply the registered decision rule")
    rep.add_argument("--answers", type=Path, default=Path("runs/e012_conf.jsonl"))
    rep.set_defaults(func=report)

    args = parser.parse_args()
    if getattr(args, "out", None) is None and args.command == "run":
        args.out = Path(f"runs/e012_{args.split}.jsonl")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
