#!/usr/bin/env python
"""E-001's harness. Arm B first, on the development split only.

The evaluation split is 57 questions and is opened once, in Phase 8. Every
command here defaults to `--split dev` and prints which side it ran, because
the one irreversible mistake available in this file is touching the other
one early.

    retrieve   arm B's subgraphs for the 20 development questions (free)
    generate   answers over that dump (paid, ~20 calls)
    ceiling    hand those answers to the correctness worksheet as batch 2

Registered configuration this implements, from E-001's amendments:

  * **Pin 11 — the incompleteness notice is suppressed on every arm.**
    `subgraph.serialize` normally appends "NOTICE: this context is
    incomplete … Say so if the answer depends on what is missing", and a
    passage retriever truncating at *k* cannot emit one. Leaving it on
    would hand arms B and C an invitation to hedge that arm A never
    receives — and refusals score as incorrect — in the experiment
    predicting B beats A. `context_incomplete` is recorded regardless, so
    the rate is still published.
  * **Arm B is single-shot by construction today.** Iterative retrieval is
    a protocol variable ablated on every arm that can accept it; arm B
    cannot yet, and that is declared rather than quietly enjoyed by A.
  * **`--limit` and a printed estimate before any spend**, per the
    project's cost rule.

What this file does **not** do yet, named so its absence is not read as a
result: arm A does not exist, arm C is not configured, and nothing here
judges. The dress rehearsal is binding and is not complete until all three
arms and the judge have run end to end on these 20.

Usage:
    python scripts/run_eval.py retrieve --arm B
    python scripts/run_eval.py generate --arm B --dry-run
    python scripts/run_eval.py generate --arm B
    python scripts/run_eval.py ceiling
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.evaluation.corpus import build_corpus, corpus_sha256, counts_by_kind
from graphrag_mtg.evaluation.dense import (
    BATCH,
    DEFAULT_EMBEDDING_MODEL,
    OpenAiEncoder,
    VectorCache,
    estimate_embedding_cost,
)
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import PROMPT_VERSION, SYSTEM, answer, build_prompt
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    serialize,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e007 import (  # sibling scripts; the sys.path line above enables them
    MAX_ANSWER_TOKENS,
    build_stack,
    evidence_fingerprint,
    rebuild,
)
from split_golden import QUESTION_FILES, load_questions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN_DIR = Path("data/golden")
SPLIT_PATH = Path("data/golden/phase4_dev_ids.json")
CACHE_DIR = Path("data/interim/golden_cache")

RETRIEVAL = "runs/e001_{arm}_retrieval_{split}.jsonl"
ANSWERS = "runs/e001_{arm}_answers_{split}.jsonl"

#: E-001 pin 11. Flipping this to True is a change to the registered
#: protocol, not a flag to try — it is here so the suppression is visible
#: rather than buried in a call.
NOTICE = False

#: Arms this file can retrieve and generate with. C is registered and not
#: built; naming it here keeps `--arm` from implying B is the experiment.
ARMS = {"B": "graph-only traversal"}
UNBUILT = {"C": "hybrid (ADR-007)"}

RULINGS_PATH = Path("data/raw/scryfall_rulings.json")
VECTORS_PATH = Path("data/interim/e001_vectors.bin")

#: Characters a document may contribute to one embedding request. The
#: provider's limit is 8,192 tokens; this is comfortably under it at the
#: chars/4 heuristic. Truncation is counted and printed rather than
#: applied quietly — a document silently cut in half is a retrieval miss
#: with no visible cause.
MAX_EMBED_CHARS = 24_000


def question_rows(golden: Path, split: Path, side: str) -> list[dict]:
    """Golden questions on one side of the frozen split.

    Raises:
        SystemExit: for the evaluation side, unless the caller has said in
            so many words that Phase 8 has arrived. There is no second
            draw, and E-006's first run needed one.
    """
    rows = load_questions(golden, QUESTION_FILES)
    dev = set(json.loads(split.read_text(encoding="utf-8"))["dev_ids"])
    if side == "dev":
        return [row for row in rows if row["id"] in dev]
    return [row for row in rows if row["id"] not in dev]


def text_of(row: dict, cache: Path) -> str:
    """A question's text, from the row or from the gitignored cache.

    Authored and generated questions carry their text inline; RulesGuru
    rows carry `null` and keep it in the cache, which is the licence
    posture the golden set already uses.
    """
    if row.get("question"):
        return row["question"]
    path = cache / f"{row['id']}.json"
    if not path.exists():
        raise SystemExit(f"No cached text for {row['id']} at {path}.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("questionSimple") or payload.get("question") or ""


def guard_side(args: argparse.Namespace) -> str:
    if args.split_side == "eval" and not args.open_the_evaluation_split:
        raise SystemExit(
            "The evaluation split is 57 questions opened once, in Phase 8. Pass "
            "--open-the-evaluation-split to mean it, and write the journal entry first."
        )
    return args.split_side


def run_retrieval(args: argparse.Namespace) -> int:
    """Arm B's subgraphs for every question on the side. No LLM, no cost."""
    side = guard_side(args)
    rows = question_rows(args.golden, args.split, side)
    if not rows:
        raise SystemExit(f"No {side} questions under {args.golden}.")
    if args.limit:
        rows = rows[: args.limit]

    linker, searcher, oracle_text = build_stack(args.cr)
    out = args.out or Path(RETRIEVAL.format(arm=args.arm, split=side))
    out.parent.mkdir(parents=True, exist_ok=True)

    outcomes: Counter[str] = Counter()
    with driver_session() as session, out.open("w", encoding="utf-8") as handle:
        run = neo4j_runner(session)
        for row in rows:
            question = text_of(row, args.cache_dir)
            subgraph = retrieve(
                question,
                linker=linker,
                run=run,
                rule_search=searcher,
                oracle_text=oracle_text,
                token_budget=args.token_budget,
                kind_cap=args.kind_cap,
            )
            outcomes[str(subgraph.outcome)] += 1
            handle.write(
                json.dumps(
                    {
                        "question_id": row["id"],
                        "arm": args.arm,
                        "split": side,
                        "stratum": row["stratum"],
                        "outcome": str(subgraph.outcome),
                        "note": subgraph.note,
                        "citations": subgraph.citations(),
                        "templates_run": subgraph.templates_run,
                        "tokens": subgraph.tokens,
                        "dropped": dict(subgraph.dropped),
                        "capped": dict(subgraph.capped),
                        "evidence": (ev := [asdict(item) for item in subgraph.evidence]),
                        "evidence_sha256": evidence_fingerprint(ev),
                        # Stored as the model will see it — notice suppressed
                        # — so the dump is not a friendlier context than the
                        # one the answers were built on.
                        "context": serialize(subgraph, notice=NOTICE),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"arm {args.arm} ({ARMS[args.arm]})   split {side}   {len(rows)} question(s)")
    print(f"budget {args.token_budget} tokens, kind cap {args.kind_cap}, notice {NOTICE}")
    print(f"outcomes: {dict(outcomes)}")
    print(f"-> {out}")
    if UNBUILT:
        print(f"\nNot run because not built: {', '.join(f'{k} ({v})' for k, v in UNBUILT.items())}.")
        print("The dress rehearsal is not complete until all three arms and the judge have.")
    return 0


def run_generation(args: argparse.Namespace) -> int:
    """Answer every retrieved question. Costs tokens; estimate prints first."""
    side = guard_side(args)
    retrieval = args.retrieval or Path(RETRIEVAL.format(arm=args.arm, split=side))
    out = args.out or Path(ANSWERS.format(arm=args.arm, split=side))
    if not retrieval.exists():
        raise SystemExit(f"No retrieval dump at {retrieval}. Run `retrieve` first.")
    if out.exists() and not args.force and not args.dry_run:
        raise SystemExit(
            f"{out} already exists. Generated answers are the only copy of what a label "
            "describes, and `runs/` is gitignored — pass --force only if you mean to "
            "destroy them."
        )

    records = [
        json.loads(line)
        for line in retrieval.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        records = records[: args.limit]
    rows = {row["id"]: row for row in question_rows(args.golden, args.split, side)}

    prepared = [(record, text_of(rows[record["question_id"]], args.cache_dir)) for record in records]
    prompts = [
        build_prompt(question, rebuild(record, question), notice=NOTICE)
        for record, question in prepared
    ]
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    estimate = estimate_cost(
        prompts, model=client.model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    print(f"arm {args.arm}   split {side}   model {client.model} @ temperature 0")
    print(f"prompt {PROMPT_VERSION}, incompleteness notice {'on' if NOTICE else 'SUPPRESSED'}")
    print(f"estimate: {estimate}")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record, question in prepared:
            subgraph = rebuild(record, question)
            result = answer(
                question,
                subgraph,
                lambda system, prompt: client.complete_text(prompt, system=system),
                notice=NOTICE,
            )
            handle.write(
                json.dumps(
                    {
                        "question_id": record["question_id"],
                        "arm": args.arm,
                        "split": side,
                        "stratum": record["stratum"],
                        "text": result.text,
                        "rendered": result.rendered,
                        "refused": result.refused,
                        "generated": result.generated,
                        "unknown_handles": result.unknown,
                        "context_incomplete": result.context_incomplete,
                        "prompt_version": result.prompt_version,
                        "notice": NOTICE,
                        "model": client.model,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(f"  {record['question_id']}: {'refused' if result.refused else 'answered'}")

    print(f"\nWrote {len(prepared)} answer(s) -> {out}")
    print(f"Next: python scripts/run_eval.py ceiling --answers {out}")
    return 0


def load_corpus(args: argparse.Namespace) -> list:
    """Build arm A's document set from the raw sources."""
    cr = parse_cr(args.cr)
    cards = list(iter_bulk(bulk_path(ORACLE_CARDS_STEM)))
    rulings = json.loads(args.rulings.read_text(encoding="utf-8"))
    return build_corpus(cr, cards, rulings)


def index(args: argparse.Namespace) -> int:
    """Build the corpus and embed it, resumably, printing the cost first."""
    documents = load_corpus(args)
    corpus_hash = corpus_sha256(documents)
    texts = [d.text[:MAX_EMBED_CHARS] for d in documents]
    oversized = sum(1 for d in documents if len(d.text) > MAX_EMBED_CHARS)

    print(f"corpus {len(documents):,} documents   sha256 {corpus_hash[:12]}")
    print(f"by kind: {counts_by_kind(documents)}")
    print(f"estimate: {estimate_embedding_cost(texts, model=args.model)}")
    if oversized:
        print(f"{oversized} document(s) truncated to {MAX_EMBED_CHARS:,} chars for embedding.")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    encoder = OpenAiEncoder(model=args.model)
    cache = VectorCache(args.vectors)
    done = cache.resume_count(corpus_hash=corpus_hash, encoder=encoder.name)
    if done >= len(documents):
        print(f"\nAlready embedded: {done:,} vectors at {args.vectors}. Nothing to do.")
        return 0
    if done:
        print(f"\nResuming at {done:,} of {len(documents):,} — {len(documents) - done:,} to go.")

    started = time.time()
    for start in range(done, len(documents), BATCH):
        batch = texts[start : start + BATCH]
        done = cache.append(
            encoder.encode(batch), corpus_hash=corpus_hash, encoder=encoder.name, done=done
        )
        elapsed = time.time() - started
        print(
            f"  {done:>7,}/{len(documents):,}  {done / len(documents):5.1%}  "
            f"{elapsed:6.0f}s elapsed",
            flush=True,
        )
    print(f"\nEmbedded {done:,} document(s) -> {args.vectors} in {time.time() - started:.0f}s")
    print(f"corpus sha256 {corpus_hash} — the cache is keyed on it, so a corpus change")
    print("invalidates these vectors rather than scoring new documents against old ones.")
    return 0


def ceiling(args: argparse.Namespace) -> int:
    """Hand these answers to the correctness worksheet as a labelling batch."""
    out = args.answers or Path(ANSWERS.format(arm=args.arm, split="dev"))
    if not out.exists():
        raise SystemExit(f"No answers at {out}. Run `generate` first.")
    print("These answers are E-011a's batch 2 — the strata batch 1 has none of.")
    print("Build the worksheet with:\n")
    print(f"  python scripts/audit_correctness.py build --answers {out} \\")
    print("      --batch b2 --out data/golden/p6_correctness_b2_m1.json")
    print("\nIt is a separate pass with its own freeze and its own five-day clock;")
    print("`reaudit score --also` pools the two and names each batch's contribution.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--arm", choices=sorted(ARMS), default="B")
    common.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    common.add_argument("--split", type=Path, default=SPLIT_PATH)
    common.add_argument("--split-side", choices=("dev", "eval"), default="dev")
    common.add_argument("--open-the-evaluation-split", action="store_true")
    common.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    common.add_argument("--limit", type=int, default=0, help="run at most N questions")

    ret = sub.add_parser("retrieve", parents=[common], help="arm B subgraphs (no LLM)")
    ret.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    ret.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    ret.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)
    ret.add_argument("--out", type=Path, default=None)
    ret.set_defaults(func=run_retrieval)

    gen = sub.add_parser("generate", parents=[common], help="answers (costs tokens)")
    gen.add_argument("--retrieval", type=Path, default=None)
    gen.add_argument("--out", type=Path, default=None)
    gen.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    gen.add_argument("--force", action="store_true")
    gen.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    gen.set_defaults(func=run_generation)

    idx = sub.add_parser("index", help="build arm A's corpus and embed it (costs tokens)")
    idx.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    idx.add_argument("--rulings", type=Path, default=RULINGS_PATH)
    idx.add_argument("--vectors", type=Path, default=VECTORS_PATH)
    idx.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    idx.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    idx.set_defaults(func=index)

    cei = sub.add_parser("ceiling", parents=[common], help="hand the answers to E-011a")
    cei.add_argument("--answers", type=Path, default=None)
    cei.set_defaults(func=ceiling)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
