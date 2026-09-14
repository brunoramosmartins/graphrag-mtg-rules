#!/usr/bin/env python
"""E-020: does reordering identical evidence change the answer?

E-018's secondary subset ran 13 questions on which the treatment injected
nothing, so all three conditions carried **identical content** — and different
orderings, because the runner shuffled once per condition. Collapsed
discordance across those orderings was 4 of 13, against the 0.050 that entry
published as its floor, which had been measured by generating twice from the
**same** prompt.

It was the generator, not the judge. On `hand-def-flying` the control answer
contains the clause the key requires and the same five items reordered produced
an answer that omits it.

**Why this is bigger than one entry.** E-001 measured a between-arm difference
of 0.01 and published `inconclusive`. If reordering identical evidence moves
the judged outcome at anything near 0.20, every paired figure this project has
published sits below a variance source nobody controlled, and E-019 cannot run
until it is controlled.

**Four samples per question, from one seed:**

    A1  ordering A
    A2  ordering A again      -> A1 vs A2 is the same-prompt floor
    B   ordering B            -> A1 vs B carries order as well
    C   ordering C            -> A1 vs C carries order as well

The floor is measured **in this run**, on these questions. E-018's 0.050 was
measured on a different split and is motivation here, never a comparator.

**Checks that can fail**, all before a single token is spent:

    every ordering carries the identical multiset of handles
    no two of the three orderings are the same sequence
    every question has more than one evidence item, so order can vary at all
    nothing is dropped or capped

Development split only. This entry needs no gold key of any kind and takes no
reading of the evaluation split.

Usage:
    python scripts/run_e020.py --dry-run
    python scripts/run_e020.py --limit 3
    python scripts/run_e020.py
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable
from pathlib import Path

from graphrag_mtg.evaluation.judge import CORRECTNESS_SYSTEM, JUDGE_PROMPT_VERSION, score
from graphrag_mtg.evaluation.judge import correctness_prompt as judge_prompt
from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION, rubric_hash
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import (
    PROMPT_VERSION,
    SYSTEM,
    answer,
    build_prompt,
    prompt_digest,
)
from graphrag_mtg.retrieval.subgraph import Subgraph, enforce_budget

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_correctness import CACHE_DIR as E007_CACHE_DIR
from audit_correctness import question_and_key
from e001_inspect import artefacts, load_jsonl
from run_e007 import MAX_ANSWER_TOKENS, rebuild
from run_e018 import TOKEN_BUDGET, check_budget
from run_eval import CACHE_DIR, GOLDEN_DIR, NOTICE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THIN = "-" * 78

ARM = "B"
SPLIT = "dev"
RUN_PATH = Path("runs/e020.jsonl")

#: The four samples. `A1` and `A2` share an ordering and are the floor; `B` and
#: `C` are different orderings of the same items.
SAMPLES = ("A1", "A2", "B", "C")

#: Which ordering each sample uses. `A1` and `A2` must map to the same one or
#: the floor stops being a floor.
ORDER_OF = {"A1": "A", "A2": "A", "B": "B", "C": "C"}

#: The permutations and nothing else. Recorded so the run is reproducible.
RANDOM_SEED = 20260913

#: Registered in E-020 and placed **off the grid on purpose**: at n = 20 every
#: rate is a multiple of 0.05, and E-018 put two bars on multiples of 0.05 and
#: landed exactly on both, which decided nothing. A bar between attainable
#: values cannot be landed on.
EFFECT_BAR = 0.175


#: Attempts at drawing three orderings that render as three different prompts.
DRAW_ATTEMPTS = 200


def orderings(
    evidence: list, rng: random.Random, render: Callable[[list], str]
) -> dict[str, list] | None:
    """Three permutations that render as three **different prompts**, or None.

    Distinctness is checked on the rendered prompt and not on the evidence
    sequence, because `serialize` groups the evidence by kind before writing
    it: two different list orders can produce the same text, and a pair that
    does would be a second floor reported as an order comparison — the same
    shape of mistake as E-018's floor measuring decoding noise while the
    contrast carried order.

    Returns None when the context cannot produce three distinct prompts. That
    is a question this design cannot move, not a failure: it is excluded and
    counted, because including it would dilute the rate with questions that
    were never at risk.
    """
    chosen: list[list] = []
    seen: set[str] = set()
    for _ in range(DRAW_ATTEMPTS):
        candidate = list(evidence)
        rng.shuffle(candidate)
        text = render(candidate)
        if text not in seen:
            seen.add(text)
            chosen.append(candidate)
        if len(chosen) == 3:
            return {"A": chosen[0], "B": chosen[1], "C": chosen[2]}
    return None


def check_same_items(qid: str, built: dict[str, Subgraph]) -> None:
    """Every ordering must carry the identical multiset of handles.

    This entry claims to vary order and nothing else. If an ordering also
    varied content, the result would be E-018's contrast under a new name.

    Raises:
        SystemExit: on any difference in what the orderings contain.
    """
    signatures = {name: sorted(item.cite() for item in sub.evidence) for name, sub in built.items()}
    first = next(iter(signatures.values()))
    for name, signature in signatures.items():
        if signature != first:
            raise SystemExit(
                f"{qid} ({name}): this ordering does not carry the same items as the "
                f"others. E-020 varies order and nothing else; a content difference "
                f"here would make the contrast a different experiment."
            )


def check_distinct(qid: str, prompts: dict[str, str]) -> None:
    """`A1` and `A2` must match; `B` and `C` must differ from `A` and each other.

    Raises:
        SystemExit: if the floor pair differs, or if an order sample matches
            the floor's ordering — either one turns a reported order effect
            into a second measurement of decoding noise.
    """
    if prompts["A1"] != prompts["A2"]:
        raise SystemExit(f"{qid}: the floor pair does not share a prompt. It is not a floor.")
    for name in ("B", "C"):
        if prompts[name] == prompts["A1"]:
            raise SystemExit(
                f"{qid} ({name}): this ordering produced the same prompt as A. "
                f"It would be reported as an order comparison and measure decoding noise."
            )
    if prompts["B"] == prompts["C"]:
        raise SystemExit(f"{qid}: orderings B and C are the same sequence.")


def prepare(args: argparse.Namespace) -> list[dict]:
    """Every question's four prompts, built and checked before any spend."""
    retrieval_path, _, _ = artefacts(ARM, SPLIT)
    records = load_jsonl(retrieval_path, what="retrieval")
    if args.limit:
        records = records[: args.limit]
    rng = random.Random(RANDOM_SEED)

    prepared: list[dict] = []
    excluded: list[str] = []
    for record in records:
        qid = record["question_id"]
        if len(record.get("evidence", ())) < 2:
            # A one-item context cannot be reordered. Counting it would dilute
            # the rate with a question that was never at risk of moving.
            excluded.append(qid)
            print(f"  {qid}: one evidence item, cannot be reordered — excluded")
            continue
        question, key = question_and_key(qid, args.caches, args.golden)
        base = rebuild(record, question)

        def render(items: list, *, question: str = question, base: Subgraph = base) -> str:
            trial = Subgraph(question=question, outcome=base.outcome, evidence=list(items))
            return build_prompt(question, trial, notice=NOTICE)

        drawn = orderings(list(base.evidence), rng, render)
        if drawn is None:
            # `serialize` groups by kind, so a context whose items are all one
            # kind in a fixed render order cannot be permuted into a different
            # prompt at all. Excluded and counted.
            excluded.append(qid)
            print(f"  {qid}: no three distinct prompts exist for this context — excluded")
            continue

        built, prompts = {}, {}
        for name in SAMPLES:
            subgraph = Subgraph(
                question=question,
                outcome=base.outcome,
                evidence=list(drawn[ORDER_OF[name]]),
                templates_run=list(base.templates_run),
                note=base.note,
            )
            enforce_budget(subgraph, TOKEN_BUDGET)
            check_budget(qid, name, subgraph)
            built[name] = subgraph
            prompts[name] = build_prompt(question, subgraph, notice=NOTICE)
        check_same_items(qid, built)
        check_distinct(qid, prompts)
        prepared.append(
            {
                "question_id": qid,
                "question": question,
                "key": key,
                "stratum": record["stratum"],
                "items": len(base.evidence),
                "subgraphs": built,
                "prompts": prompts,
            }
        )
    if not prepared:
        raise SystemExit("No question in this split can be reordered.")
    if excluded:
        total = len(excluded) + len(prepared)
        print(
            f"\n{len(excluded)} of {total} question(s) excluded: their context cannot be"
            f"\nrendered in three different orders. The rate below is measured over the"
            f"\n{len(prepared)} that can, and that is the denominator every figure from"
            f"\nthis run carries."
        )
    return prepared


def run(args: argparse.Namespace) -> int:
    """Four samples per question, interleaved, then the floor and the rate."""
    prepared = prepare(args)
    print(f"\nE-020   arm {ARM}   split {SPLIT}   {len(prepared)} question(s), 4 samples")
    print(f"budget {TOKEN_BUDGET:,}   seed {RANDOM_SEED}   prompt {PROMPT_VERSION}")
    print(f"ceiling {len(prepared)} of {len(prepared)} — every question can be reordered")
    print(f"effect bar {EFFECT_BAR}, registered and deliberately off the 1/n grid")

    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    generate = lambda system, prompt: client.complete_text(prompt, system=system)  # noqa: E731
    prompts = [row["prompts"][name] for row in prepared for name in SAMPLES]
    generation = estimate_cost(
        prompts, model=client.model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    judged = estimate_cost(
        [judge_prompt(row["question"], "x" * 800, row["key"]) for row in prepared for _ in SAMPLES],
        model=client.model,
        output_tokens_per_call=300,
        system=CORRECTNESS_SYSTEM,
    )
    print(
        f"\nestimate: {generation.n_calls} generation(s) + {judged.n_calls} judge call(s), "
        f"about US$ {generation.usd + judged.usd:.2f}"
    )
    if args.dry_run:
        print("\nDry run: nothing was sent. Every check above passed.")
        return 0
    if RUN_PATH.exists():
        raise SystemExit(f"{RUN_PATH} already exists. Move it aside if you mean to re-run.")

    rows = []
    for row in prepared:
        for name in SAMPLES:
            result = answer(
                row["question"], row["subgraphs"][name], generate, notice=NOTICE, model=client.model
            )
            verdict = score(
                row["question_id"],
                row["question"],
                result.text,
                row["key"],
                generate,
                model=client.model,
                refused=result.refused,
            )
            rows.append(
                {
                    "question_id": row["question_id"],
                    "sample": name,
                    "ordering": ORDER_OF[name],
                    "stratum": row["stratum"],
                    "items": row["items"],
                    "text": result.text,
                    "refused": result.refused,
                    "handles": result.handles,
                    "label": str(verdict.label),
                    "rationale": verdict.rationale,
                    "tokens": row["subgraphs"][name].tokens,
                    "prompt_sha256": prompt_digest(SYSTEM, row["prompts"][name]),
                    "prompt_version": PROMPT_VERSION,
                    "rubric_version": RUBRIC_VERSION,
                    "rubric_hash": rubric_hash(),
                    "judge_prompt_version": JUDGE_PROMPT_VERSION,
                    "model": client.model,
                    "arm": ARM,
                    "split": SPLIT,
                }
            )
            print(f"  {row['question_id']:<34} {name:<3} {verdict.label}")

    RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(rows)} row(s) -> {RUN_PATH}")
    print(f"Next: python scripts/e020_analysis.py --run {RUN_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    parser.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    parser.add_argument("--limit", type=int, default=0, help="run at most N questions")
    parser.add_argument("--dry-run", action="store_true", help="build and check, send nothing")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
