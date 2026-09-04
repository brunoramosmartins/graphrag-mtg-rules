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
from graphrag_mtg.evaluation.arm_c import VectorRuleSearch
from graphrag_mtg.evaluation.baseline_vector import build_arm
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    Outcome,
    Subgraph,
    add_evidence,
    enforce_budget,
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

#: The three registered arms. A is the control, B is the thesis, C is the
#: shipped system and the README figure.
ARMS = {
    "A": "vector baseline, no graph",
    "B": "graph-only traversal",
    "C": "hybrid — graph plus the shared text retriever (shipped)",
}

#: What remains unbuilt, named so a run does not read as the whole
#: rehearsal. The rehearsal is binding only when the judge has run too.
UNBUILT: dict[str, str] = {}

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


def vector_only_subgraph(
    question: str, searcher: VectorRuleSearch, token_budget: int, kind_cap: int
) -> Subgraph:
    """Arm A's retrieval, in the same container every other arm produces.

    Arm A touches no graph, but it renders through `subgraph.serialize`
    and reaches the model through the same `build_prompt` as arms B and C.
    That is pin 1's "one protocol" made structural rather than careful: a
    second renderer for one arm is a place where the two can drift, and
    the drift would land on the citation-quality comparison pin 1 runs.
    """
    subgraph = Subgraph(question=question, outcome=Outcome.RESOLVED, note="vector retrieval")
    subgraph.templates_run.append(searcher.template_name)
    add_evidence(subgraph, searcher.evidence(question), kind_cap=kind_cap)
    enforce_budget(subgraph, token_budget)
    if subgraph.is_empty:
        subgraph.outcome = Outcome.NO_MATCH
        subgraph.note = "vector retrieval returned nothing"
    return subgraph


def vector_searcher(args: argparse.Namespace) -> VectorRuleSearch:
    """Arm A's retriever, wrapped in arm B's contract.

    Built with a generous internal budget so it does not pre-trim: the
    Subgraph's `enforce_budget` is the single budget authority for every
    arm, and two trims with two token estimates is a drift hazard dressed
    as belt and braces.
    """
    documents = load_corpus(args)
    vectors = None
    if args.mode in {"hybrid", "dense"}:
        vectors = VectorCache(args.vectors).load(
            corpus_hash=corpus_sha256(documents),
            encoder=args.embedding_model,
            count=len(documents),
        )
        if vectors is None:
            raise SystemExit(
                f"No vectors at {args.vectors} for this corpus and encoder. "
                "Run `run_eval.py index` first, or pass --mode lexical."
            )
    arm = build_arm(
        documents,
        mode=args.mode,
        vectors=vectors,
        encoder=OpenAiEncoder(model=args.embedding_model) if vectors is not None else None,
        token_budget=10**9,
    )
    return VectorRuleSearch(arm, iterative=args.iterative)


def configure(args: argparse.Namespace):
    """The retrieval configuration for one arm, from the arm alone.

    Returns `(text_searcher, uses_graph, always_text)`.

    This function exists because the harness previously passed
    `rule_search` unconditionally and labelled the result **arm B**. Text
    search fires on 2 of the 20 development questions, so the run was arm
    C routed with TF-IDF wearing arm B's name, and nothing in the output
    said otherwise. Arm identity now determines configuration in one
    place, so a mislabel would have to be written here on purpose.
    """
    if args.arm == "A":
        return vector_searcher(args), False, True
    if args.arm == "B":
        # Graph-only means graph-only: no text retriever is passed at all,
        # so a routed question comes back as NO_SEED rather than quietly
        # reaching for the text half arm B is defined as not having.
        return None, True, False
    text = vector_searcher(args) if args.text == "vector" else "tfidf"
    return text, True, args.always_text


def run_retrieval(args: argparse.Namespace) -> int:
    """One arm's contexts for every question on the side. No LLM, no cost."""
    side = guard_side(args)
    rows = question_rows(args.golden, args.split, side)
    if not rows:
        raise SystemExit(f"No {side} questions under {args.golden}.")
    if args.limit:
        rows = rows[: args.limit]

    searcher, uses_graph, always_text = configure(args)
    linker, tfidf, oracle_text = build_stack(args.cr)
    if searcher == "tfidf":
        searcher = tfidf
    out = args.out or Path(RETRIEVAL.format(arm=args.arm, split=side))
    out.parent.mkdir(parents=True, exist_ok=True)

    outcomes: Counter[str] = Counter()
    with driver_session() as session, out.open("w", encoding="utf-8") as handle:
        run = neo4j_runner(session)
        for row in rows:
            question = text_of(row, args.cache_dir)
            if uses_graph:
                subgraph = retrieve(
                    question,
                    linker=linker,
                    run=run,
                    rule_search=searcher,
                    oracle_text=oracle_text,
                    token_budget=args.token_budget,
                    kind_cap=args.kind_cap,
                    always_text_search=always_text,
                )
            else:
                subgraph = vector_only_subgraph(
                    question, searcher, args.token_budget, args.kind_cap
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
    print(f"  {describe(args)}")
    print(f"  budget {args.token_budget} tokens, kind cap {args.kind_cap}, notice {NOTICE}")
    print(f"outcomes: {dict(outcomes)}")
    print(f"-> {out}")
    if UNBUILT:
        print(f"\nNot run because not built: {', '.join(f'{k} ({v})' for k, v in UNBUILT.items())}.")
    print("\nThe dress rehearsal is binding only once every arm and the judge have run.")
    return 0


def describe(args: argparse.Namespace) -> str:
    """The configuration, printed on every run so the log names the arm.

    The harness previously passed a text retriever unconditionally and
    labelled the output arm B. Text search fires on 2 of 20 development
    questions, so nothing in the numbers looked wrong. A line that spells
    out the configuration is what makes that visible next time.
    """
    if args.arm == "A":
        return f"vector only, mode {args.mode}, iterative {args.iterative}"
    if args.arm == "B":
        return "graph only, no text retriever passed"
    routing = "always-on" if args.always_text else "routed (shipped)"
    return f"graph + {args.text} text half, {routing}, mode {args.mode}, iterative {args.iterative}"


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
    common.add_argument("--arm", choices=sorted(ARMS), default="C")
    common.add_argument(
        "--mode",
        choices=("hybrid", "dense", "lexical"),
        default="hybrid",
        help="the vector retriever's mode; dense and lexical are pin 2's ablations",
    )
    common.add_argument(
        "--text",
        choices=("vector", "tfidf"),
        default="vector",
        help="arm C's text half; tfidf is pin 12's registered ablation",
    )
    common.add_argument(
        "--always-text",
        action="store_true",
        help="arm C: run text retrieval on every question, not only where routed",
    )
    common.add_argument(
        "--iterative",
        action="store_true",
        help="pin 13's protocol variable, offered to every arm that can accept it",
    )
    common.add_argument("--vectors", type=Path, default=VECTORS_PATH)
    common.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    common.add_argument("--rulings", type=Path, default=RULINGS_PATH)
    common.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    common.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    common.add_argument("--split", type=Path, default=SPLIT_PATH)
    common.add_argument("--split-side", choices=("dev", "eval"), default="dev")
    common.add_argument("--open-the-evaluation-split", action="store_true")
    common.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    common.add_argument("--limit", type=int, default=0, help="run at most N questions")

    ret = sub.add_parser("retrieve", parents=[common], help="one arm's contexts (no LLM)")
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

    idx = sub.add_parser("index", help="build the shared corpus and embed it (costs tokens)")
    idx.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    idx.add_argument("--rulings", type=Path, default=RULINGS_PATH)
    idx.add_argument("--vectors", type=Path, default=VECTORS_PATH)
    idx.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    idx.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    idx.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    idx.set_defaults(func=index)

    cei = sub.add_parser("ceiling", parents=[common], help="hand the answers to E-011a")
    cei.add_argument("--answers", type=Path, default=None)
    cei.set_defaults(func=ceiling)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
