#!/usr/bin/env python
"""E-001's harness: three arms, on the development split only.

The evaluation split is 57 questions and is opened once, in Phase 8. Every
command here defaults to `--split dev` and prints which side it ran, because
the one irreversible mistake available in this file is touching the other
one early.

    run        the whole pipeline for one arm, in one process
    index      build the shared corpus and embed it (paid, once)
    retrieve   one arm's contexts for the 20 development questions (free)
    generate   answers over that dump (paid, ~20 calls)
    judge      score those answers against the keys (paid)
    compare    the pairwise head-to-head (paid)
    report     per-stratum correctness, with figures (free)
    ceiling    hand those answers to the correctness worksheet as a batch

`run` is the reproducibility deliverable and the only command whose **trace**
covers a whole question: every other one is a single stage with a JSONL
between it and the next, so a `retrieve` trace and a `generate` trace are two
traces about one question that no viewer can join.

`--smoke` swaps the corpus for `tests/fixtures/smoke/`, the generator for one
that cites the first handle it is handed, and the judge for one that returns a
fixed label. Every stage executes; nothing is measured. **CI tests the wiring,
not the quality** — whether the prompt still works is a regression only a real
model can show, and that is E-001's job, gated on the correctness ceiling.

**Arm identity decides configuration**, in `plan_arm`, and every run prints
what it used. That is not tidiness: the harness once passed a text retriever
unconditionally and recorded the result as arm B. Text search fires on 2 of
these 20 questions, so every summary number looked exactly as a graph-only
arm would look, and the mislabel survived a full run and a registry entry.

**Run files are named by configuration, not by arm.** `runs/` is gitignored,
so a generated answers file is the only copy of the prose a label describes:
E-007 lost ten answers to a shared default path, and E-011a's batch 2 points
at one of these files with finished labels behind it. Arm C's ablations
differ only in flags, so an arm-only name would let one overwrite another.

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

What this file does **not** do, named so its absence is not read as a
result: nothing here judges, and the judge's human audit does not exist yet.
The dress rehearsal is binding only once all three arms and the judge have
run end to end on these 20.

Usage:
    python scripts/run_eval.py run --smoke --arm A --mode lexical   # no key, no DB
    python scripts/run_eval.py run --arm C --figures docs/figures --trace
    python scripts/run_eval.py index --dry-run
    python scripts/run_eval.py retrieve --arm A
    python scripts/run_eval.py generate --arm A --dry-run
    python scripts/run_eval.py retrieve --arm C --text tfidf   # pin 12's ablation
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

from graphrag_mtg.etl.bulk import (
    ORACLE_CARDS_STEM,
    RULINGS_STEM,
    bulk_path,
    iter_bulk,
    load_bulk,
)
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.evaluation.arm_c import VectorRuleSearch
from graphrag_mtg.evaluation.baseline_vector import build_arm
from graphrag_mtg.evaluation.corpus import build_corpus, corpus_sha256, counts_by_kind
from graphrag_mtg.evaluation.dense import (
    BATCH,
    DEFAULT_EMBEDDING_MODEL,
    OpenAiEncoder,
    VectorCache,
    estimate_embedding_cost,
)
from graphrag_mtg.evaluation.judge import (
    CORRECTNESS_SYSTEM,
    JUDGE_PROMPT_VERSION,
    PREFERENCE_SYSTEM,
    compare,
    correctness_prompt,
    order_disagreement_rate,
    preference_prompt,
    resolve_pair,
    score,
)
from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval
from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION, render_for_judgement, rubric_hash
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import PROMPT_VERSION, SYSTEM, answer, build_prompt
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.observability import spans, tracing
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
# `CACHE_DIR` here is the golden-set cache; E-007's is a different directory
# and lives in `audit_correctness`. Imported under an alias rather than
# written out again, because the judge and the human worksheet must look in
# the same places — a second copy of the path is a second thing to update.
from audit_correctness import CACHE_DIR as E007_CACHE_DIR
from audit_correctness import question_and_key
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

RETRIEVAL = "runs/e001_{slug}_retrieval_{split}.jsonl"
ANSWERS = "runs/e001_{slug}_answers_{split}.jsonl"
VERDICTS = "runs/e001_{slug}_verdicts_{split}.jsonl"
PAIRS = "runs/e001_pairs_{left}_vs_{right}_{split}.jsonl"

#: E-011 point 7. Above this share of order-disagreeing pairs the pairwise
#: win rate is not published as the head-to-head — the per-stratum
#: correctness comparison becomes the headline. Registered there, not
#: chosen here.
ORDER_DISAGREEMENT_GATE = 0.20

#: Output cap per verdict. Two lines is the required format; this is
#: generous enough for a model that reasons first and small enough that a
#: runaway verdict cannot quietly multiply the bill.
MAX_JUDGE_TOKENS = 200

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

#: Resolved through `bulk_path`, not spelled out. It used to be the literal
#: `data/raw/scryfall_rulings.json` — the legacy array format — while the
#: card half of the same corpus went through `bulk_path` and got the
#: current `.jsonl.gz`. Arm A was therefore indexing today's cards beside
#: rulings from whenever the last array download happened, and nothing said
#: so: `corpus_sha256` covered both halves and simply described the mixture.
RULINGS_PATH = bulk_path(RULINGS_STEM)
VECTORS_PATH = Path("data/interim/e001_vectors.bin")

#: Characters a document may contribute to one embedding request. The
#: provider's limit is 8,192 tokens; this is comfortably under it at the
#: chars/4 heuristic. Truncation is counted and printed rather than
#: applied quietly — a document silently cut in half is a retrieval miss
#: with no visible cause.
MAX_EMBED_CHARS = 24_000

RULE_LINE = "-" * 78

# ── Smoke: the wiring, with no key, no corpus and no database ────────────────
#
# A pull request cannot hold an API key, a 115k-document corpus, or a loaded
# graph. The smoke therefore runs the **real** pipeline over a fixture corpus
# with a fake generator and a fake judge: every stage executes and every
# format is checked against the next one, and nothing is measured.
#
# What it does not test is stated in `tests/fixtures/smoke/README.md` and
# bears repeating wherever it might be forgotten: **CI tests the wiring, not
# the quality.** Whether the prompt still works is a regression only a real
# model can show, and it is E-001's job, not CI's.

SMOKE_DIR = Path("tests/fixtures/smoke")
SMOKE_CR = Path("tests/fixtures/cr_excerpt.txt")

#: Written into `model` on every row a smoke run produces. A synthetic
#: figure that reaches an analysis has to say so from inside the data —
#: a banner on a console that scrolled past is not a guard.
SMOKE_MODEL = "smoke-fake"

#: What the fake judge returns for every answer. Fixed, not sampled: a
#: varied fake would produce a *distribution*, and a distribution invites
#: being read as a finding.
SMOKE_LABEL = "correct"

#: The first citation handle in a serialized context, which is what the
#: fake generator answers with.
FIRST_HANDLE = re.compile(r"\[[a-z_]+:[^\]\s][^\]]*\]")

#: Printed on every smoke report, and written into the markdown one. The
#: sentence that has to survive is the last: a green CI badge is a claim
#: about the wiring, and this is where it stops being read as a claim
#: about the answers.
SMOKE_BANNER = (
    "SMOKE RUN — the generator and the judge are both fakes and every figure\n"
    "below is an artefact of the fixture, not a measurement. CI tests the\n"
    "wiring, not the quality: whether the prompt still works is a regression\n"
    "only a real model can show, and it is E-001's job, gated on the\n"
    "correctness ceiling. Nothing here is evidence about any arm."
)


def smoke_paths(args: argparse.Namespace) -> None:
    """Point every source at the fixture. Mutates `args` in place."""
    args.cr = SMOKE_CR
    args.cards = SMOKE_DIR / "cards.json"
    args.rulings = SMOKE_DIR / "rulings.json"
    args.golden = SMOKE_DIR / "golden"
    args.split = SMOKE_DIR / "golden" / "split.json"
    # The fixture's questions carry their text and their keys inline, so
    # there is no cache to consult. Pointed at the fixture directory rather
    # than left on the real one so a smoke run cannot read a gitignored
    # RulesGuru file that happens to exist on a developer's machine.
    args.cache_dir = SMOKE_DIR / "golden"
    args.caches = [SMOKE_DIR / "golden"]
    # A fixture split whose every id is on the development side. Forced
    # rather than trusted: `--smoke --split-side eval` must not be a way to
    # reach the guard's error message and think the evaluation split moved.
    args.split_side = "dev"


def smoke_generate(system: str, prompt: str) -> str:
    """Answer by citing the first handle the context offers.

    Structurally a real answer — it has prose and a citation, so citation
    expansion, the unknown-handle check, the refusal test and the judge all
    receive what they expect. Semantically nothing at all, which is the
    point: an answer that looked plausible would be worse, not better.
    """
    handle = FIRST_HANDLE.search(prompt)
    cited = handle.group(0) if handle else ""
    return f"Smoke answer. No model was called. {cited}".strip()


def smoke_score(system: str, prompt: str) -> str:
    """A verdict in the judge's own format, saying it is not one."""
    return f"LABEL: {SMOKE_LABEL}\nWHY: smoke run; no judge was called."


def artefact(template: str, args: argparse.Namespace, **fields: object) -> Path:
    """The run file for this configuration, under the right prefix.

    Smoke output is `runs/smoke_*`, never `runs/e001_*`. `runs/` is
    gitignored and its files are the only copy of what a label describes,
    so the one thing a synthetic run must never do is land where a real one
    is looked for.

    `--tag` is the same rule for the general case. A run made to capture a
    trace or to reproduce a bug is real — real model, real spend — but it is
    not E-001, and the guard that refuses to overwrite an existing answers
    file is the only thing standing between such a run and a set of judged
    answers that cannot be regenerated for free.
    """
    path = Path(template.format(**fields))
    prefix = "smoke" if getattr(args, "smoke", False) else getattr(args, "tag", None)
    if prefix:
        return path.with_name(f"{prefix}_" + path.name.removeprefix("e001_"))
    return path


def generator_for(args: argparse.Namespace) -> tuple[Callable[[str, str], str], str]:
    """The `(generate, model)` pair this run answers with."""
    if getattr(args, "smoke", False):
        return smoke_generate, SMOKE_MODEL
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    return (lambda system, prompt: client.complete_text(prompt, system=system)), client.model


def judge_for(args: argparse.Namespace) -> tuple[Callable[[str, str], str], str]:
    """The `(score, model)` pair this run judges with."""
    if getattr(args, "smoke", False):
        return smoke_score, SMOKE_MODEL
    client = LlmClient(model=args.model, max_tokens=MAX_JUDGE_TOKENS, temperature=0.0)
    return (lambda system, prompt: client.complete_text(prompt, system=system)), client.model


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


def guard_recorded_questions(rows: list[dict], args: argparse.Namespace) -> None:
    """Refuse to put licensed question text on a span.

    `--record-questions` exists for the README's trace screenshot, and a
    screenshot is the public repo. The rule it enforces is the one the
    golden set already follows: text the repo versions inline may be
    recorded, text the repo keeps in a gitignored cache may not.

    Naming the property rather than the file matters here. A guard reading
    "not ids_v0.jsonl" would pass the moment a RulesGuru row arrived from
    somewhere else; this one asks whether the row itself carries its text,
    which is the same question `text_of` asks.
    """
    if not getattr(args, "record_questions", False):
        return
    cached = [row["id"] for row in rows if not row.get("question")]
    if cached:
        raise SystemExit(
            f"--record-questions would put {len(cached)} licensed question(s) on a span: "
            f"{', '.join(cached[:5])}{'...' if len(cached) > 5 else ''}. These rows keep "
            "their text in the gitignored cache, and a trace is a thing that gets "
            "screenshotted into a public README. Run without the flag, or limit the "
            "batch to questions this repo carries inline."
        )


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
            if getattr(args, "smoke", False):
                # Embedding the fixture would need a paid encoder, which is
                # the one thing the smoke exists to do without.
                raise SystemExit(
                    f"--mode {args.mode} needs embeddings, and embedding the smoke fixture "
                    "would need an API key. Pass --mode lexical: the smoke tests the "
                    "wiring, and the lexical half exercises all of it."
                )
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


@dataclass(frozen=True)
class ArmPlan:
    """What an arm is, decided from the arm and nothing else.

    Attributes:
        uses_graph: Whether traversal runs at all.
        retriever: `vector`, `tfidf`, or None for no text retrieval.
        always_text: Whether text retrieval fires on every question rather
            than only where the router sends it.
    """

    uses_graph: bool
    retriever: str | None
    always_text: bool


def config_slug(args: argparse.Namespace) -> str:
    """A filename fragment naming the exact configuration that ran.

    Not decoration. `runs/` is gitignored, so a generated answers file is
    the only copy of the prose a label describes — E-007 lost ten answers
    to a shared default path, and E-011a's batch 2 points at one of these
    files with 19 finished labels behind it. Arm C's ablations differ only
    in flags, so a name carrying just the arm would have let the vector
    run overwrite the TF-IDF run that the ceiling is measured on.
    """
    plan = plan_arm(args)
    if args.arm == "A":
        parts = ["A", args.mode]
    elif args.arm == "B":
        parts = ["B"]
    else:
        parts = ["C", plan.retriever, "always" if plan.always_text else "routed"]
        if plan.retriever == "vector":
            parts.insert(2, args.mode)
    if getattr(args, "iterative", False):
        parts.append("iter")
    return "-".join(parts)


def plan_arm(args: argparse.Namespace) -> ArmPlan:
    """The retrieval plan for one arm — a decision, with no I/O.

    Deliberately separate from building anything. The harness previously
    passed `rule_search` unconditionally and labelled the result **arm B**;
    text search fires on 2 of the 20 development questions, so the run was
    arm C routed with TF-IDF wearing arm B's name and no number disagreed.
    The decision is what was wrong, so the decision is what is isolated
    here and tested — a version that had to build a 115k-document corpus
    to be exercised is a version whose test gets skipped.
    """
    if args.arm == "A":
        # No graph, and its retriever runs on every question by
        # definition: there is no router to send it anywhere.
        return ArmPlan(uses_graph=False, retriever="vector", always_text=True)
    if args.arm == "B":
        # Graph-only means graph-only: no text retriever is passed at all,
        # so a routed question comes back as NO_SEED rather than quietly
        # reaching for the half arm B is defined as not having.
        return ArmPlan(uses_graph=True, retriever=None, always_text=False)
    return ArmPlan(uses_graph=True, retriever=args.text, always_text=args.always_text)


@dataclass
class Stack:
    """Everything one arm needs to retrieve, built once per run.

    `run` is None for arm A, and that is the point rather than an
    omission: the harness used to open a Neo4j session and read the
    Scryfall bulk before every run, arm A included. `plan_arm` has always
    said arm A touches no graph and a test has always asserted it — of the
    *plan*. The harness disagreed, silently, and the cost was only ever a
    slow start until CI needed to run arm A with no database at all.
    """

    plan: ArmPlan
    searcher: object | None
    linker: object | None = None
    oracle_text: dict | None = None
    run: object | None = None


def build_retrieval_stack(args: argparse.Namespace, stack: ExitStack) -> Stack:
    """Assemble one arm's retrieval stack, opening only what it uses."""
    plan = plan_arm(args)
    if not plan.uses_graph:
        # No linker, no router, no session, no bulk read.
        return Stack(plan=plan, searcher=vector_searcher(args))

    # `--cards` replaces the bulk rather than adding to it: the smoke has
    # no 196 MB of gitignored Scryfall data, and a lexicon built from the
    # bulk would resolve names the fixture graph does not contain.
    fixture_cards = load_cards(args) if getattr(args, "cards", None) else None
    linker, tfidf, oracle_text = build_stack(args.cr, cards=fixture_cards)
    searcher = tfidf if plan.retriever == "tfidf" else None
    if plan.retriever == "vector":
        searcher = vector_searcher(args)
    session = stack.enter_context(driver_session())
    return Stack(
        plan=plan,
        searcher=searcher,
        linker=linker,
        oracle_text=oracle_text,
        run=neo4j_runner(session),
    )


def require_a_populated_graph(stack: Stack) -> None:
    """Refuse to traverse an empty graph.

    Every question against one comes back `NO_MATCH`, which is a run that
    completes, writes files, prints a report and tested nothing. In CI that
    is a passing smoke with no subject; in a real run it is the loader
    having silently not loaded. Both are worth one COUNT query.
    """
    if stack.run is None:
        return
    rows = list(stack.run("MATCH (r:Rule) RETURN count(r) AS n", {}))
    if rows and rows[0]["n"]:
        return
    raise SystemExit(
        "The graph holds no Rule nodes, so every traversal would return nothing and "
        "the run would report NO_MATCH for every question without anything being "
        "wrong with retrieval. Load the corpus, or `python scripts/load_smoke_graph.py` "
        "for the fixture."
    )


def retrieve_one(question: str, stack: Stack, args: argparse.Namespace) -> Subgraph:
    """One question's evidence, on whichever arm this is.

    The single retrieval body. Two copies of it is how the two commands
    that answer the same question could come to answer it differently.
    """
    if stack.plan.uses_graph:
        return retrieve(
            question,
            linker=stack.linker,
            run=stack.run,
            rule_search=stack.searcher,
            oracle_text=stack.oracle_text,
            token_budget=args.token_budget,
            kind_cap=args.kind_cap,
            always_text_search=stack.plan.always_text,
        )
    return vector_only_subgraph(question, stack.searcher, args.token_budget, args.kind_cap)


def retrieval_row(row: dict, subgraph: Subgraph, args: argparse.Namespace, side: str) -> dict:
    """One line of the retrieval dump."""
    evidence = [asdict(item) for item in subgraph.evidence]
    return {
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
        "evidence": evidence,
        "evidence_sha256": evidence_fingerprint(evidence),
        # Stored as the model will see it — notice suppressed — so the dump
        # is not a friendlier context than the one the answers were built on.
        "context": serialize(subgraph, notice=NOTICE),
    }


def run_retrieval(args: argparse.Namespace) -> int:
    """One arm's contexts for every question on the side. No LLM, no cost."""
    side = guard_side(args)
    rows = question_rows(args.golden, args.split, side)
    if not rows:
        raise SystemExit(f"No {side} questions under {args.golden}.")
    if args.limit:
        rows = rows[: args.limit]

    out = args.out or artefact(RETRIEVAL, args, slug=config_slug(args), split=side)
    out.parent.mkdir(parents=True, exist_ok=True)

    outcomes: Counter[str] = Counter()
    with ExitStack() as resources:
        stack = build_retrieval_stack(args, resources)
        handle = resources.enter_context(out.open("w", encoding="utf-8"))
        for row in rows:
            question = text_of(row, args.cache_dir)
            subgraph = retrieve_one(question, stack, args)
            outcomes[str(subgraph.outcome)] += 1
            handle.write(
                json.dumps(retrieval_row(row, subgraph, args, side), ensure_ascii=False) + "\n"
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


def answer_row(
    record: dict, result, args: argparse.Namespace, side: str, model_name: str
) -> dict:
    """One line of the answers dump.

    `smoke` is written into the row, not only printed. A console banner
    scrolls past; a field travels with the data into whatever reads it
    next, which is the only place the distinction can still be made.
    """
    return {
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
        "model": model_name,
        "smoke": bool(getattr(args, "smoke", False)),
    }


def run_generation(args: argparse.Namespace) -> int:
    """Answer every retrieved question. Costs tokens; estimate prints first."""
    side = guard_side(args)
    slug = config_slug(args)
    retrieval = args.retrieval or artefact(RETRIEVAL, args, slug=slug, split=side)
    out = args.out or artefact(ANSWERS, args, slug=slug, split=side)
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
    generate, model_name = generator_for(args)
    estimate = estimate_cost(
        prompts, model=model_name, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    print(f"arm {args.arm}   split {side}   model {model_name} @ temperature 0")
    print(f"prompt {PROMPT_VERSION}, incompleteness notice {'on' if NOTICE else 'SUPPRESSED'}")
    print(f"estimate: {estimate}" if not args.smoke else "estimate: none — the generator is a fake")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record, question in prepared:
            subgraph = rebuild(record, question)
            result = answer(question, subgraph, generate, notice=NOTICE, model=model_name)
            handle.write(
                json.dumps(answer_row(record, result, args, side, model_name), ensure_ascii=False)
                + "\n"
            )
            print(f"  {record['question_id']}: {'refused' if result.refused else 'answered'}")

    print(f"\nWrote {len(prepared)} answer(s) -> {out}")
    print(f"Next: python scripts/run_eval.py ceiling --answers {out}")
    return 0


def load_cards(args: argparse.Namespace) -> list[dict]:
    """Card records: the Scryfall bulk, or a fixture when one is named.

    `--cards` exists for the smoke and for nothing else. The bulk is 196 MB
    of gitignored data that a pull request does not have, and `is_playable`
    — the predicate pin 8 shares between the graph loader and arm A's
    index — runs the same either way.
    """
    if getattr(args, "cards", None):
        return json.loads(Path(args.cards).read_text(encoding="utf-8"))
    return list(iter_bulk(bulk_path(ORACLE_CARDS_STEM)))


def load_corpus(args: argparse.Namespace) -> list:
    """Build arm A's document set from the raw sources."""
    cr = parse_cr(args.cr)
    return build_corpus(cr, load_cards(args), load_bulk(args.rulings))


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


def run_judge(args: argparse.Namespace) -> int:
    """Score one arm's answers against the keys. Costs tokens.

    Rubric iteration is permitted on **dress-rehearsal** answers and
    forbidden on the evaluation split, so this defaults to `dev` like
    everything else here and the version and hash it ran under are written
    into every verdict.
    """
    side = guard_side(args)
    slug = config_slug(args)
    answers_path = args.answers or artefact(ANSWERS, args, slug=slug, split=side)
    out = args.out or artefact(VERDICTS, args, slug=slug, split=side)
    if not answers_path.exists():
        raise SystemExit(f"No answers at {answers_path}. Run `generate` first.")
    if out.exists() and not args.force and not args.dry_run:
        raise SystemExit(f"{out} already exists — pass --force only if you mean to replace it.")

    rows = [
        json.loads(line)
        for line in answers_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        rows = rows[: args.limit]
    # Looked up through the same resolver the human worksheet uses, rather
    # than from the golden split. The judge has to score whatever answers
    # it is pointed at — E-007's 42 are what E-011a's batch 1 labelled, and
    # they are not golden rows — and two lookups for one thing is how a
    # blank key reaches a judge that then scores prose against nothing.
    caches = [Path(c) for c in args.caches]
    pairs = {qid: question_and_key(qid, caches, args.golden) for qid in {r["question_id"] for r in rows}}
    questions = {qid: pair[0] for qid, pair in pairs.items()}
    keys = {qid: pair[1] for qid, pair in pairs.items()}

    billed = [r for r in rows if not r["refused"] and render_for_judgement(r["text"]).strip()]
    judge, model_name = judge_for(args)
    prompts = [
        correctness_prompt(questions[r["question_id"]], r["text"], keys[r["question_id"]])
        for r in billed
    ]
    estimate = estimate_cost(
        prompts,
        model=model_name,
        output_tokens_per_call=MAX_JUDGE_TOKENS,
        system=CORRECTNESS_SYSTEM,
    )
    print(f"arm {args.arm} ({slug})   split {side}   rubric {RUBRIC_VERSION} @ {rubric_hash()[:12]}")
    print(f"judge {model_name} @ temperature 0, prompt {JUDGE_PROMPT_VERSION}")
    print(f"{len(rows) - len(billed)} scored by rule (refused or empty), {len(billed)} billed")
    print(f"estimate: {estimate}" if not args.smoke else "estimate: none — the judge is a fake")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    tally: Counter[str] = Counter()
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            qid = row["question_id"]
            verdict = score(
                qid,
                questions[qid],
                row["text"],
                keys[qid],
                judge,
                model=model_name,
                refused=row["refused"],
            )
            tally[verdict.label.value] += 1
            handle.write(json.dumps(verdict_row(verdict, args, slug, side), ensure_ascii=False) + "\n")
    print(f"\n{dict(tally)}  -> {out}")
    print("Judged, not audited. No figure from this may be published until the")
    print("judge-versus-human agreement in E-011 has been measured against the ceiling.")
    return 0


def verdict_row(verdict, args: argparse.Namespace, slug: str, side: str) -> dict:
    """One line of the verdicts dump."""
    return {
        **asdict(verdict),
        "label": verdict.label.value,
        "arm": args.arm,
        "slug": slug,
        "split": side,
        "smoke": bool(getattr(args, "smoke", False)),
    }


def load_answers(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"No answers at {path}. Run `generate` for that configuration first.")
    return {
        row["question_id"]: row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def run_compare(args: argparse.Namespace) -> int:
    """Pairwise head-to-head between two configurations, in both orders.

    Every pair is judged twice with the two answers swapped, because a
    model that reads position rather than content answers differently when
    they trade places. A pair whose orderings disagree is a **tie**,
    registered in E-011 before any pair existed, and above an overall
    disagreement rate of 0.20 the pairwise win rate is **not** published as
    the head-to-head at all — the per-stratum correctness comparison
    becomes the headline instead.
    """
    side = guard_side(args)
    left_path = args.left_answers or artefact(ANSWERS, args, slug=args.left, split=side)
    right_path = args.right_answers or artefact(ANSWERS, args, slug=args.right, split=side)
    out = args.out or artefact(PAIRS, args, left=args.left, right=args.right, split=side)
    if out.exists() and not args.force and not args.dry_run:
        raise SystemExit(f"{out} already exists — pass --force only if you mean to replace it.")

    left, right = load_answers(left_path), load_answers(right_path)
    rows = {r["id"]: r for r in question_rows(args.golden, args.split, side)}
    shared = [q for q in rows if q in left and q in right]
    if args.limit:
        shared = shared[: args.limit]
    if not shared:
        raise SystemExit("The two files share no question.")

    def blank(row: dict) -> bool:
        return bool(row["refused"]) or not render_for_judgement(row["text"]).strip()

    billed = [q for q in shared if not (blank(left[q]) and blank(right[q]))]
    client = LlmClient(model=args.model, max_tokens=MAX_JUDGE_TOKENS, temperature=0.0)
    prompts = [
        preference_prompt(
            text_of(rows[q], args.cache_dir),
            left[q]["text"],
            right[q]["text"],
            key_for(rows[q], args.cache_dir),
        )
        for q in billed
    ]
    estimate = estimate_cost(
        prompts * 2,
        model=client.model,
        output_tokens_per_call=MAX_JUDGE_TOKENS,
        system=PREFERENCE_SYSTEM,
    )
    print(f"{args.left}  vs  {args.right}   split {side}   {len(shared)} shared question(s)")
    print(f"judge {client.model} @ temperature 0, prompt {JUDGE_PROMPT_VERSION}, "
          f"rubric {RUBRIC_VERSION} @ {rubric_hash()[:12]}")
    print(f"both orders on {len(billed)}, {len(shared) - len(billed)} tied by rule (both blank)")
    print(f"estimate: {estimate}")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    generate = lambda system, prompt: client.complete_text(prompt, system=system)  # noqa: E731
    pairs: list[tuple] = []
    results: list[dict] = []
    for qid in shared:
        question, key = text_of(rows[qid], args.cache_dir), key_for(rows[qid], args.cache_dir)
        if qid not in billed:
            results.append({"question_id": qid, "stratum": rows[qid]["stratum"],
                            "winner": "tie", "by_rule": True, "order_disagreed": False})
            continue
        first = compare(qid, question, left[qid]["text"], right[qid]["text"], key, generate,
                        left_arm=args.left, right_arm=args.right)
        second = compare(qid, question, right[qid]["text"], left[qid]["text"], key, generate,
                         left_arm=args.right, right_arm=args.left)
        pairs.append((first, second))
        results.append({
            "question_id": qid,
            "stratum": rows[qid]["stratum"],
            "winner": resolve_pair(first, second),
            "by_rule": False,
            "order_disagreed": first.choice() != second.choice(),
            "first": asdict(first),
            "second": asdict(second),
        })
        print(f"  {qid:<52} {results[-1]['winner']}"
              f"{'  [orders disagreed]' if results[-1]['order_disagreed'] else ''}")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in results:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    rate = order_disagreement_rate(pairs)
    tally = Counter(r["winner"] for r in results)
    print(f"\n{dict(tally)}   -> {out}")
    print(f"order disagreement {rate:.3f} over {len(pairs)} judged pair(s)")
    if rate > ORDER_DISAGREEMENT_GATE:
        print(f"Above the registered gate of {ORDER_DISAGREEMENT_GATE:.2f}: this win rate is")
        print("NOT the head-to-head. The per-stratum correctness comparison is the headline.")
    else:
        print(f"At or below the registered gate of {ORDER_DISAGREEMENT_GATE:.2f}.")
    print("\nUnaudited and on the development split. Not a result.")
    return 0


def labels_for(slug: str, args: argparse.Namespace, side: str) -> dict[str, str]:
    """One configuration's verdicts, as ``question_id -> label``."""
    path = artefact(VERDICTS, args, slug=slug, split=side)
    if not path.exists():
        raise SystemExit(f"No verdicts at {path}. Run `judge` for {slug} first.")
    return {
        row["question_id"]: row["label"]
        for row in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def correctness_table(
    rows: dict[str, dict],
    arms: dict[str, dict[str, str]],
    shared: list[str],
    order: list[str],
) -> list[tuple[str, int, list]]:
    """Per-stratum correctness with intervals, one row per stratum plus ALL.

    Returned rather than printed so the console table and the figure are
    the same numbers by construction. Two renderers computing their own is
    how a chart comes to disagree with the table above it.
    """
    if not shared:
        raise SystemExit(
            "No question is judged on every named configuration. A comparison "
            "over an empty intersection is not a comparison."
        )
    strata = sorted({rows[q]["stratum"] for q in shared})
    table = []
    for stratum in [*strata, "ALL"]:
        ids = [q for q in shared if stratum in ("ALL", rows[q]["stratum"])]
        intervals = [
            wilson_interval(sum(arms[slug][q] == "correct" for q in ids), len(ids))
            for slug in order
        ]
        table.append((stratum, len(ids), intervals))
    return table


# ── Figures ──────────────────────────────────────────────────────────────────
#
# Hand-written SVG rather than a plotting library. Three reasons, in order
# of weight: CI installs no plotting stack to draw five bars; an SVG is a
# text file that diffs, so a figure changing is visible in review the way a
# number changing is; and GitHub renders it inline in the README.
#
# A forest plot rather than bars, because the interval *is* the finding.
# The project's rule is that no proportion is reported bare, and a bar
# chart of point estimates is exactly a bare proportion with ink on it.

FIGURE_WIDTH = 780
FIGURE_LEFT = 250
FIGURE_RIGHT = 750
ROW_HEIGHT = 20
GROUP_GAP = 12
ARM_COLOURS = ("#1f6f8b", "#b8562f", "#4a7c59", "#7a5c9e", "#8a6d3b")


def _x(value: float) -> float:
    """A proportion, in figure coordinates."""
    return FIGURE_LEFT + (FIGURE_RIGHT - FIGURE_LEFT) * value


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def forest_svg(
    cells: list[tuple[str, int, list]], order: list[str], side: str, *, smoke: bool
) -> str:
    """A forest plot of per-stratum correctness, one line per arm."""
    body: list[str] = []
    y = 74
    for stratum, n, intervals in cells:
        body.append(
            f'<text x="16" y="{y + 4}" class="lbl">{_escape(stratum)} '
            f'<tspan class="dim">n={n}</tspan></text>'
        )
        for index, interval in enumerate(intervals):
            colour = ARM_COLOURS[index % len(ARM_COLOURS)]
            row = y + index * ROW_HEIGHT
            body.append(
                f'<line x1="{_x(interval.low):.1f}" x2="{_x(interval.high):.1f}" '
                f'y1="{row}" y2="{row}" stroke="{colour}" stroke-width="2.5" '
                f'stroke-linecap="round"/>'
                f'<circle cx="{_x(interval.point):.1f}" cy="{row}" r="4" fill="{colour}"/>'
                f'<text x="{FIGURE_RIGHT + 8}" y="{row + 4}" class="num">'
                f"{interval.point:.2f}</text>"
            )
        y += len(intervals) * ROW_HEIGHT + GROUP_GAP
    height = y + 46

    ticks = "".join(
        f'<line x1="{_x(t):.1f}" x2="{_x(t):.1f}" y1="56" y2="{y - GROUP_GAP + 6}" '
        # `:g`, not `:.1f`: the quarter ticks are at 0.25 and 0.75, and one
        # decimal place labels them 0.2 and 0.8 — an axis that misreports
        # its own gridlines by a fortieth of the range.
        f'class="grid"/><text x="{_x(t):.1f}" y="48" class="tick">{t:g}</text>'
        for t in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    legend = "".join(
        f'<circle cx="{18 + i * 128}" cy="{height - 18}" r="4" '
        f'fill="{ARM_COLOURS[i % len(ARM_COLOURS)]}"/>'
        f'<text x="{28 + i * 128}" y="{height - 14}" class="key">{_escape(slug)}</text>'
        for i, slug in enumerate(order)
    )
    title = f"Per-stratum correctness, {side} split — point and 95% Wilson interval"
    note = (
        "SMOKE — fake generator and fake judge; not a measurement"
        if smoke
        else "judge-scored correctness, `correct` against everything else"
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{FIGURE_WIDTH}" height="{height}" \
viewBox="0 0 {FIGURE_WIDTH} {height}" role="img" aria-label="{_escape(title)}">
<style>
  text {{ font-family: ui-sans-serif, "Segoe UI", Helvetica, Arial, sans-serif; }}
  .ttl {{ font-size: 13px; font-weight: 600; fill: #111827; }}
  .sub {{ font-size: 11px; fill: {"#b8562f" if smoke else "#6b7280"}; }}
  .lbl {{ font-size: 11px; fill: #111827; }}
  .dim {{ fill: #6b7280; }}
  .num {{ font-size: 10px; fill: #374151; font-variant-numeric: tabular-nums; }}
  .tick {{ font-size: 10px; fill: #6b7280; text-anchor: middle; }}
  .key  {{ font-size: 10px; fill: #374151; }}
  .grid {{ stroke: #e5e7eb; stroke-width: 1; }}
</style>
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="16" y="24" class="ttl">{_escape(title)}</text>
<text x="16" y="40" class="sub">{_escape(note)}</text>
{ticks}
{"".join(body)}
{legend}
</svg>
"""


def report_markdown(
    cells: list[tuple[str, int, list]], order: list[str], side: str, *, smoke: bool
) -> str:
    """The same table as the console, linkable and diffable."""
    head = [f"# Per-stratum correctness — {side} split", ""]
    if smoke:
        head += ["> **" + SMOKE_BANNER.replace("\n", "\n> ") + "**", ""]
    head += [
        "Point estimate with its 95% Wilson interval. Unit is judge-scored "
        "correctness, `correct` against everything else.",
        "",
        "| stratum | n | " + " | ".join(order) + " |",
        "|---|---:|" + "---|" * len(order),
    ]
    for stratum, n, intervals in cells:
        figures = " | ".join(
            f"{i.point:.2f} [{i.low:.2f}, {i.high:.2f}]" for i in intervals
        )
        head.append(f"| {stratum} | {n} | {figures} |")
    head += ["", f"![forest plot](correctness_{side}.svg)", ""]
    return "\n".join(head)


def write_figures(
    directory: Path,
    cells: list[tuple[str, int, list]],
    order: list[str],
    side: str,
    *,
    smoke: bool,
) -> list[Path]:
    """Write the forest plot and the markdown table. Returns what it wrote."""
    directory.mkdir(parents=True, exist_ok=True)
    svg = directory / f"correctness_{side}.svg"
    markdown = directory / f"correctness_{side}.md"
    svg.write_text(forest_svg(cells, order, side, smoke=smoke), encoding="utf-8")
    markdown.write_text(report_markdown(cells, order, side, smoke=smoke), encoding="utf-8")
    return [svg, markdown]


def run_report(args: argparse.Namespace) -> int:
    """The per-stratum correctness comparison — E-001's registered primary.

    Free: it reads verdicts that already exist. The pairwise win rate is
    the *secondary* head-to-head and E-011 point 7 can withdraw it; this
    is what the decision rule was always written against, so it is what
    runs when the pairwise gate fires and what runs when it does not.

    Unit is judge-scored answer correctness, `correct` against everything
    else. `partial` counts as not-correct: E-007c found a middle category
    absorbs uncertainty, and letting it count as a win would let the
    headline move with how generously it was applied.
    """
    side = guard_side(args)
    rows = {r["id"]: r for r in question_rows(args.golden, args.split, side)}
    arms = {slug: labels_for(slug, args, side) for slug in args.arms}
    shared = sorted(set.intersection(*(set(v) for v in arms.values())))
    print(f"split {side}   {len(shared)} shared question(s)   arms {', '.join(args.arms)}")
    print("unit: judge-scored correctness, `correct` against everything else")
    if getattr(args, "smoke", False):
        print(SMOKE_BANNER)
    print(RULE_LINE)

    cells = correctness_table(rows, arms, shared, args.arms)
    header = f"{'stratum':<24}{'n':>4}" + "".join(f"{a:>26}" for a in args.arms)
    print(header)
    for stratum, n, intervals in cells:
        line = f"{stratum:<24}{n:>4}"
        for interval in intervals:
            line += f"{f'{interval.point:.2f} [{interval.low:.2f},{interval.high:.2f}]':>26}"
        print(line)

    if getattr(args, "figures", None):
        written = write_figures(args.figures, cells, args.arms, side, smoke=args.smoke)
        print(f"\nfigures -> {', '.join(str(p) for p in written)}")

    print(RULE_LINE)
    print("paired comparisons (exact McNemar over shared questions, uncorrected):")
    for i, left in enumerate(args.arms):
        for right in args.arms[i + 1 :]:
            before = [arms[right][q] == "correct" for q in shared]
            after = [arms[left][q] == "correct" for q in shared]
            result = mcnemar(before, after)
            print(f"  {left} vs {right:<28} +{result.improved}/-{result.regressed}  "
                  f"p={result.p_value:.4f}")
    print("\nUncorrected and unaudited, on the development split. E-001's registered")
    print("family is Holm-corrected over four strata on the evaluation split, and it")
    print("cannot run until the judge is audited against the correctness ceiling.")
    return 0


def key_for(row: dict, cache: Path) -> str:
    """A question's answer key, from the row or the gitignored cache."""
    if row.get("answer"):
        return row["answer"]
    path = cache / f"{row['id']}.json"
    if not path.exists():
        raise SystemExit(f"No cached key for {row['id']} at {path}.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = payload.get("answerSimple") or payload.get("answer") or ""
    if not key:
        raise SystemExit(f"{row['id']} has no answer key. It cannot be judged against nothing.")
    return key


def ceiling(args: argparse.Namespace) -> int:
    """Hand these answers to the correctness worksheet as a labelling batch."""
    out = args.answers or artefact(ANSWERS, args, slug=config_slug(args), split="dev")
    if not out.exists():
        raise SystemExit(f"No answers at {out}. Run `generate` first.")
    print("These answers are E-011a's batch 2 — the strata batch 1 has none of.")
    print("Build the worksheet with:\n")
    print(f"  python scripts/audit_correctness.py build --answers {out} \\")
    print("      --batch b2 --out data/golden/p6_correctness_b2_m1.json")
    print("\nIt is a separate pass with its own freeze and its own five-day clock;")
    print("`reaudit score --also` pools the two and names each batch's contribution.")
    return 0


def ceiling_estimate(n: int, *, model: str, budget: int, output_tokens: int, system: str):
    """An upper bound on spend, computed before a single prompt exists.

    `run` interleaves retrieval and generation so that one question is one
    trace, which means the real prompts are not available until money could
    already have been spent. The token budget bounds the context by
    construction, so a bound is available — and a bound printed before the
    loop honours the cost rule better than an exact figure printed after it
    would.
    """
    return estimate_cost(
        ["x" * (4 * budget)] * n,
        model=model,
        output_tokens_per_call=output_tokens,
        system=system,
    )


def run_all(args: argparse.Namespace) -> int:
    """Every stage for one arm, in one process: retrieval to figures.

    Two things live here that live nowhere else.

    **The reproducibility deliverable.** One command, one arm, from the raw
    sources to a markdown report and a figure.

    **A complete trace.** Every other command is one stage with a JSONL
    between it and the next, so a `retrieve` trace and a `generate` trace
    are two traces about one question and no viewer can join them. Here
    retrieval, generation and judging happen inside one `query_span`, which
    is what makes "a multi-hop question produces a readable trace" true
    rather than nearly true.
    """
    if args.smoke:
        smoke_paths(args)
    side = guard_side(args)

    if args.trace:
        print(f"tracing -> {tracing.configure(args.otlp_endpoint)}")

    rows = question_rows(args.golden, args.split, side)
    if not rows:
        raise SystemExit(f"No {side} questions under {args.golden}.")
    if args.limit:
        rows = rows[: args.limit]

    slug = config_slug(args)
    retrieval_path = artefact(RETRIEVAL, args, slug=slug, split=side)
    answers_path = artefact(ANSWERS, args, slug=slug, split=side)
    verdicts_path = artefact(VERDICTS, args, slug=slug, split=side)
    for path in (answers_path, verdicts_path):
        if path.exists() and not args.force and not args.dry_run:
            raise SystemExit(
                f"{path} already exists. Generated answers and the verdicts over them "
                "are the only copy of what a label describes, and `runs/` is gitignored "
                "— pass --force only if you mean to destroy them."
            )

    guard_recorded_questions(rows, args)
    generate, gen_model = generator_for(args)
    judge, judge_model = judge_for(args)

    print(f"arm {args.arm} ({ARMS[args.arm]})   split {side}   {len(rows)} question(s)")
    print(f"  {describe(args)}")
    print(f"  budget {args.token_budget} tokens, kind cap {args.kind_cap}, notice {NOTICE}")
    print(f"  generator {gen_model}, judge {judge_model}, prompt {PROMPT_VERSION}")
    print(f"  rubric {RUBRIC_VERSION} @ {rubric_hash()[:12]}")
    if args.smoke:
        print(f"\n{SMOKE_BANNER}\n")
        print("estimate: none — both models are fakes and nothing is sent.")
    else:
        answers = ceiling_estimate(
            len(rows),
            model=gen_model,
            budget=args.token_budget,
            output_tokens=MAX_ANSWER_TOKENS,
            system=SYSTEM,
        )
        verdicts = ceiling_estimate(
            len(rows),
            model=judge_model,
            budget=args.token_budget,
            output_tokens=MAX_JUDGE_TOKENS,
            system=CORRECTNESS_SYSTEM,
        )
        print(f"\nceiling — answers: {answers}")
        print(f"ceiling — verdicts: {verdicts}")
        print("Upper bounds: every context is capped at the token budget.")
    if args.dry_run:
        print("\nDry run: nothing was sent and nothing was written.")
        return 0

    caches = [Path(cache) for cache in args.caches]
    retrieval_path.parent.mkdir(parents=True, exist_ok=True)
    outcomes: Counter[str] = Counter()
    tally: Counter[str] = Counter()

    try:
        with ExitStack() as resources:
            stack = build_retrieval_stack(args, resources)
            require_a_populated_graph(stack)
            retrieval_out = resources.enter_context(retrieval_path.open("w", encoding="utf-8"))
            answers_out = resources.enter_context(answers_path.open("w", encoding="utf-8"))
            verdicts_out = resources.enter_context(verdicts_path.open("w", encoding="utf-8"))

            for row in rows:
                question = text_of(row, args.cache_dir)
                with spans.query_span(
                    question,
                    arm=args.arm,
                    question_id=row["id"],
                    record_question=args.record_questions,
                ):
                    subgraph = retrieve_one(question, stack, args)
                    outcomes[str(subgraph.outcome)] += 1
                    retrieval_out.write(
                        json.dumps(retrieval_row(row, subgraph, args, side), ensure_ascii=False)
                        + "\n"
                    )

                    result = answer(
                        question, subgraph, generate, notice=NOTICE, model=gen_model
                    )
                    record = {"question_id": row["id"], "stratum": row["stratum"]}
                    answers_out.write(
                        json.dumps(
                            answer_row(record, result, args, side, gen_model), ensure_ascii=False
                        )
                        + "\n"
                    )

                    _, key = question_and_key(row["id"], caches, args.golden)
                    verdict = score(
                        row["id"],
                        question,
                        result.text,
                        key,
                        judge,
                        model=judge_model,
                        refused=result.refused,
                    )
                    tally[verdict.label.value] += 1
                    verdicts_out.write(
                        json.dumps(verdict_row(verdict, args, slug, side), ensure_ascii=False)
                        + "\n"
                    )
                print(
                    f"  {row['id']:<8} {subgraph.outcome!s:<12} "
                    f"{'refused' if result.refused else 'answered':<9} {verdict.label.value}"
                )
    finally:
        if args.trace:
            # A batch processor holds spans for up to five seconds, and this
            # process is usually shorter than that. Flushed even on the way
            # out of a failure, because the failing run is the one worth
            # looking at.
            tracing.shutdown()

    print(f"\noutcomes: {dict(outcomes)}")
    print(f"labels:   {dict(tally)}")
    print(f"-> {retrieval_path}\n-> {answers_path}\n-> {verdicts_path}\n")
    print(RULE_LINE)

    args.arms = [slug]
    return run_report(args)


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
    common.add_argument(
        "--cards",
        type=Path,
        default=None,
        help="card records to index instead of the Scryfall bulk (smoke fixture only)",
    )
    common.add_argument(
        "--smoke",
        action="store_true",
        help="fixture corpus, fake generator, fake judge: the wiring, with no key and no spend",
    )
    common.add_argument(
        "--tag",
        default=None,
        help="write under `runs/<tag>_*` instead of `runs/e001_*`, for a run that is "
        "not the experiment (capturing a trace, reproducing a bug) and must not land "
        "where the experiment is looked for",
    )

    run = sub.add_parser(
        "run",
        parents=[common],
        help="the whole pipeline for one arm, in one process",
    )
    run.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    run.add_argument("--kind-cap", type=int, default=DEFAULT_KIND_CAP)
    run.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    run.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    run.add_argument("--figures", type=Path, default=None, help="write the SVG and markdown here")
    run.add_argument("--force", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="print the ceiling, send nothing")
    run.add_argument(
        "--trace",
        action="store_true",
        help="export OTel spans; this is the only command whose trace covers a whole question",
    )
    run.add_argument(
        "--otlp-endpoint",
        default=None,
        help="defaults to OTEL_EXPORTER_OTLP_ENDPOINT, then to the local Phoenix",
    )
    run.add_argument(
        "--record-questions",
        action="store_true",
        help="put the question text on the trace; off by default because traces get screenshotted",
    )
    run.set_defaults(func=run_all)

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

    jud = sub.add_parser("judge", parents=[common], help="score an arm's answers (costs tokens)")
    jud.add_argument("--answers", type=Path, default=None)
    jud.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    jud.add_argument("--out", type=Path, default=None)
    jud.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    jud.add_argument("--force", action="store_true")
    jud.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    jud.set_defaults(func=run_judge)

    cmp_ = sub.add_parser("compare", parents=[common], help="pairwise head-to-head (costs tokens)")
    cmp_.add_argument("--left", required=True, help="a configuration slug, e.g. A-hybrid")
    cmp_.add_argument("--right", required=True, help="a configuration slug, e.g. B")
    cmp_.add_argument("--left-answers", type=Path, default=None)
    cmp_.add_argument("--right-answers", type=Path, default=None)
    cmp_.add_argument("--out", type=Path, default=None)
    cmp_.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    cmp_.add_argument("--force", action="store_true")
    cmp_.add_argument("--dry-run", action="store_true", help="print the estimate, send nothing")
    cmp_.set_defaults(func=run_compare)

    rep = sub.add_parser("report", parents=[common], help="per-stratum correctness (free)")
    rep.add_argument("--arms", nargs="+", required=True, help="configuration slugs to compare")
    rep.add_argument("--figures", type=Path, default=None, help="write the SVG and markdown here")
    rep.set_defaults(func=run_report)

    cei = sub.add_parser("ceiling", parents=[common], help="hand the answers to E-011a")
    cei.add_argument("--answers", type=Path, default=None)
    cei.set_defaults(func=ceiling)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
