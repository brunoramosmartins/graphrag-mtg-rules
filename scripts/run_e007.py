#!/usr/bin/env python
"""E-007's two runs: retrieval first (free), generation second (paid).

Split in two on purpose, because the binding order of the experiment sits
between them:

    retrieve   ->  audit_answers.py sufficiency init / freeze  ->  generate

Retrieval touches no LLM and can be re-run at will. Generation refuses to
start until the sufficiency labels are frozen, since labelling a subgraph
after reading the answer it produced is how the refusal rule stops meaning
anything.

Registered configuration (E-007), printed on every run so the run log
cannot disagree with what actually ran: temperature 0, `rule_search` on,
`text2cypher` **off**, oracle-text expansions on, `token_budget` and
`kind_cap` at the `subgraph.py` defaults.

`text2cypher` is off for a reason worth stating: it would put a generated
Cypher query underneath a generated answer, and a failure could then
belong to either model. E-007 measures whether answers cite what they
claim, not whether two models compose.

Usage:
    python scripts/run_e007.py retrieve --pool data/golden/e007_audit_pool.jsonl
    python scripts/run_e007.py generate --split dev --limit 2 --dry-run
    python scripts/run_e007.py generate --split dev
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import PROMPT_VERSION, SYSTEM, answer, build_prompt
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import keyword_definition_rows
from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.rule_search import RuleSearch
from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    DEFAULT_TOKEN_BUDGET,
    Evidence,
    Outcome,
    Subgraph,
    serialize,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POOL_PATH = Path("data/golden/e007_audit_pool.jsonl")
CACHE_DIR = Path("data/interim/e007_cache")
SPLIT_PATH = Path("data/golden/e007_split.json")
RETRIEVAL_PATH = Path("runs/e007_retrieval.jsonl")
ANSWERS_PATH = Path("runs/e007_answers.jsonl")
SUFFICIENCY_PATH = Path("data/golden/e007_sufficiency.json")

#: Output cap per answer. Generous for a rule-by-rule walk, small enough
#: that a runaway answer cannot quietly multiply the bill.
MAX_ANSWER_TOKENS = 700


def question_text(question_id: str, cache: Path) -> str:
    """Read a question's text from the gitignored cache.

    The committed pool carries ids and our annotations only — the licence
    posture the golden set already uses — so the text lives here and never
    in the repo.
    """
    path = cache / f"{question_id}.json"
    if not path.exists():
        raise SystemExit(f"No cached text for {question_id} at {path}. Re-run the draw.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("questionSimple") or payload.get("question") or ""


def side_ids(pool: Path, split: Path, side: str) -> set[str] | None:
    """Question ids on one side of the 10/30 split, or None for all of them.

    `split_golden.py` records the development ids and defines the other
    side as the complement — the same shape the Phase 4 golden split uses,
    so a question added to the pool later lands on the audit side by
    default rather than quietly joining the tuning set.
    """
    if side == "all":
        return None
    if not split.exists():
        raise SystemExit(f"No split at {split}. Draw the 10/30 split before running a side.")
    dev = set(json.loads(split.read_text(encoding="utf-8"))["dev_ids"])
    if side == "dev":
        return dev
    everything = {
        json.loads(line)["id"]
        for line in pool.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return everything - dev


def load_pool(pool: Path, split: Path, side: str) -> list[dict]:
    """Pool rows, optionally narrowed to one side of the 10/30 split."""
    rows = [
        json.loads(line)
        for line in pool.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    wanted = side_ids(pool, split, side)
    return rows if wanted is None else [row for row in rows if row["id"] in wanted]


def build_stack(cr: Path, *, extra_cards: list[dict] | None = None, extra_keywords=()):
    """Assemble the shipped retrieval stack, exactly as E-006 ran it.

    Args:
        cr: The Comprehensive Rules text to parse.
        extra_cards: Cards to add to the lexicon beyond the Scryfall bulk.
            E-008 loads fictional cards into the graph, and a linker that
            cannot resolve them would score a retrieval miss as a leak.
        extra_keywords: Keyword display names likewise absent from the CR.
    """
    doc = parse_cr(cr)
    cards = list(iter_bulk(bulk_path(ORACLE_CARDS_STEM))) + list(extra_cards or [])
    lexicon = build_card_lexicon(cards)
    keywords_by_oracle = {c["oracle_id"]: c.get("keywords", []) for c in cards}
    oracle_text = {c["oracle_id"]: c.get("oracle_text", "") for c in cards}
    keyword_names = {row["display_name"] for row in keyword_definition_rows(doc)}
    keyword_names |= set(extra_keywords)
    with driver_session() as probe:
        formats = [r["name"] for r in probe.run("MATCH (f:Format) RETURN f.name AS name")]
    linker = QueryLinker(lexicon, keyword_names, keywords_by_oracle, formats=formats)
    return linker, RuleSearch(doc), oracle_text


def run_retrieval(args: argparse.Namespace) -> int:
    """Retrieve for every question and dump the subgraphs. No LLM, no cost."""
    rows = load_pool(args.pool, args.split, args.side)
    if not rows:
        raise SystemExit(f"No questions in {args.pool}. Draw the pool first.")

    linker, searcher, oracle_text = build_stack(args.cr)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with driver_session() as session, args.out.open("w", encoding="utf-8") as handle:
        run = neo4j_runner(session)
        for row in rows:
            text = question_text(row["id"], args.cache_dir)
            subgraph = retrieve(
                text,
                linker=linker,
                run=run,
                rule_search=searcher,
                oracle_text=oracle_text,
                token_budget=args.token_budget,
                kind_cap=args.kind_cap,
            )
            handle.write(
                json.dumps(
                    {
                        "question_id": row["id"],
                        "outcome": str(subgraph.outcome),
                        "note": subgraph.note,
                        "citations": subgraph.citations(),
                        "templates_run": subgraph.templates_run,
                        "tokens": subgraph.tokens,
                        "dropped": dict(subgraph.dropped),
                        "capped": dict(subgraph.capped),
                        # The full evidence, not just the handles: the
                        # renderer builds citation paths from it, and
                        # generation must run on exactly what the
                        # sufficiency labels were assigned to.
                        "evidence": (ev := [asdict(item) for item in subgraph.evidence]),
                        "evidence_sha256": evidence_fingerprint(ev),
                        "context": serialize(subgraph),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"Retrieved {len(rows)} question(s) -> {args.out}")
    print("\nNext, and in this order:")
    print(f"  python scripts/audit_answers.py sufficiency init --retrieval {args.out}")
    print("  ... label every row, then ...")
    print("  python scripts/audit_answers.py sufficiency freeze")
    print("Only then may `generate` run. Reading an answer before that voids E-007.")
    return 0


def evidence_fingerprint(evidence: list[dict]) -> str:
    """Hash the evidence itself — not how it happens to be rendered.

    What a sufficiency label describes is *what was retrieved*: these nodes,
    this text, reached by these paths. It does not describe the formatting
    of the context block. Comparing serialized strings conflated the two and
    fired on a presentation change — rulings moving to a short ordinal —
    while a genuine change of evidence would have looked no different.

    So the guard hashes the fields a label actually depends on, in order.
    A presentation change passes; a node appearing, disappearing or changing
    text does not.
    """
    payload = "\n".join(
        f"{item['kind']}|{item['key']}|{item['text']}|{item['template']}|"
        f"{item['path']}|{item['distance']}"
        for item in evidence
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rebuild(record: dict, question: str) -> Subgraph:
    """Reconstruct the exact subgraph that was retrieved and labelled.

    Generation replays the dump rather than re-querying, so the answers are
    provably built on the evidence the sufficiency labels were assigned to.
    Re-running retrieval in between would let the graph move underneath a
    frozen label, and nothing downstream could tell.

    Raises:
        SystemExit: if the evidence differs from what was dumped. That means
            the graph moved, and the labels no longer describe what the
            model would see.
    """
    subgraph = Subgraph(
        question=question,
        outcome=Outcome(record["outcome"]),
        evidence=[Evidence(**item) for item in record.get("evidence", [])],
        templates_run=list(record.get("templates_run", [])),
        dropped=Counter(record.get("dropped", {})),
        capped=Counter(record.get("capped", {})),
        note=record.get("note", ""),
    )
    recorded = record.get("evidence_sha256")
    if recorded and recorded != evidence_fingerprint(record["evidence"]):
        raise SystemExit(
            f"{record['question_id']}: the dumped evidence does not match its own "
            "fingerprint — the file was edited. Re-run `retrieve`."
        )
    return subgraph


def answers_path(args: argparse.Namespace) -> Path:
    """Where this side's answers go — one file per side, never a shared one.

    A single default path let the audit run overwrite the development run,
    and `runs/` is gitignored, so those answers were not recoverable. The
    claim worksheet derived from them survives and the numbers were in the
    run log, but the text a label described did not.
    """
    return args.out or ANSWERS_PATH.with_name(f"e007_answers_{args.side}.jsonl")


def run_generation(args: argparse.Namespace) -> int:
    """Generate answers for retrieved questions, after the labels are frozen."""
    meta = json.loads(args.sufficiency.read_text(encoding="utf-8")) if args.sufficiency.exists() else {}
    if not meta.get("frozen"):
        raise SystemExit(
            f"{args.sufficiency} is not frozen. Label every subgraph and run "
            "`audit_answers.py sufficiency freeze` first — generating before that "
            "voids the run, and nothing downstream can detect it afterwards."
        )

    out = answers_path(args)
    if out.exists() and not args.force and not args.dry_run:
        raise SystemExit(
            f"{out} already exists. Generated answers are the only copy of what a claim "
            "label describes, and `runs/` is gitignored — pass --force only if you mean "
            "to destroy them."
        )

    records = [
        json.loads(line)
        for line in args.retrieval.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    wanted = side_ids(args.pool, args.split, args.side)
    if wanted is not None:
        records = [r for r in records if r["question_id"] in wanted]
    if args.limit:
        records = records[: args.limit]
    if not records:
        raise SystemExit("Nothing to generate.")

    prepared = [
        (record, question_text(record["question_id"], args.cache_dir)) for record in records
    ]
    prompts = [
        build_prompt(question, rebuild(record, question)) for record, question in prepared
    ]
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    estimate = estimate_cost(
        prompts, model=client.model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    print(f"model {client.model} @ temperature 0, prompt {PROMPT_VERSION}")
    print(f"budget {args.token_budget} tokens, kind cap {args.kind_cap}")
    print("rule_search on, text2cypher off, oracle-text expansions on")
    print(f"estimate: {estimate}")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record, question in prepared:
            subgraph = rebuild(record, question)
            # A failed or empty subgraph never reaches the model — answer()
            # short-circuits and no tokens are spent.
            result = answer(
                question,
                subgraph,
                lambda system, prompt: client.complete_text(prompt, system=system),
            )
            handle.write(
                json.dumps(
                    {
                        "question_id": record["question_id"],
                        "text": result.text,
                        "rendered": result.rendered,
                        "refused": result.refused,
                        "generated": result.generated,
                        "unknown_handles": result.unknown,
                        "prompt_version": result.prompt_version,
                        "model": client.model,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(f"  {record['question_id']}: {'refused' if result.refused else 'answered'}")

    print(f"\nWrote {len(records)} answer(s) -> {out}")
    print(f"Next: python scripts/audit_answers.py segment --answers {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pool", type=Path, default=POOL_PATH)
    common.add_argument("--split", type=Path, default=SPLIT_PATH)
    common.add_argument(
        "--side",
        choices=("dev", "audit", "all"),
        default="all",
        help="dev = the 10 prompt-development questions; audit = the 30 scored once",
    )
    common.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    common.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    common.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)

    ret = sub.add_parser("retrieve", parents=[common], help="retrieve subgraphs (no LLM)")
    ret.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    ret.add_argument("--out", type=Path, default=RETRIEVAL_PATH)
    ret.set_defaults(func=run_retrieval)

    gen = sub.add_parser("generate", parents=[common], help="generate answers (costs tokens)")
    gen.add_argument("--retrieval", type=Path, default=RETRIEVAL_PATH)
    gen.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    gen.add_argument("--out", type=Path, default=None, help="defaults to runs/e007_answers_<side>.jsonl")
    gen.add_argument("--force", action="store_true", help="overwrite an existing answers file")
    gen.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    gen.add_argument("--limit", type=int, default=0, help="answer at most N questions")
    gen.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    gen.set_defaults(func=run_generation)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
