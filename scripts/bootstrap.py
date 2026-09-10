#!/usr/bin/env python
"""Clean machine to first answer, one command, with every step timed.

    docker compose --profile app up -d --wait
    docker compose exec app python scripts/bootstrap.py

Every step is idempotent, and that is the whole design. The download skips
sources whose hash the manifest already records; the loader skips sources
whose hash the graph already carries; the schema statements are `IF NOT
EXISTS`. So the **first** run is the cold path and every run after it is
the warm path, and the difference between the two numbers is the honest
onboarding figure.

**What this covers, and what it does not.** These four steps build the
*graph*, which is what arms B and C retrieve from — arm C being the
shipped system. Arm A is a vector baseline over a separate 115,547-document
index, and building it costs an embedding API call per document and about
twenty minutes; it is deliberately not on this path, and
`run_eval.py index` is where it lives. An onboarding that quietly spent
twenty minutes and real money would be a worse first impression than one
that says which arm it just made ready.

The last step answers a question. Retrieval needs no credentials, so it
always runs; generation needs an LLM key and is skipped with a note when
there is none, because "the graph answers this question with these
citations" is already the thing a first run needs to prove.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_mtg.config import get_settings
from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, RULINGS_STEM, bulk_path
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH
from graphrag_mtg.etl.download import main as download_main
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import graph_stats, load_all
from graphrag_mtg.graph.schema import apply_schema
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e007 import build_stack

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN = Path("data/golden/authored_v0.jsonl")

#: The question the last step answers. Authored, and committed to the repo
#: — the golden set's RulesGuru questions are carried as ids plus a
#: gitignored fetch, so one of those would make this script fail on a
#: clean machine for a licensing reason rather than a technical one.
FALLBACK_QUESTION = "What does deathtouch do?"

RULE = "-" * 70


@dataclass
class Timing:
    """One step's name and what it cost."""

    name: str
    seconds: float
    detail: str


@dataclass
class Report:
    """Every step, in order, plus whether this run had anything to do."""

    timings: list[Timing] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(timing.seconds for timing in self.timings)

    def add(self, name: str, seconds: float, detail: str) -> None:
        self.timings.append(Timing(name, seconds, detail))

    def as_dict(self) -> dict:
        return {
            "total_seconds": round(self.total, 1),
            "steps": [
                {"name": t.name, "seconds": round(t.seconds, 1), "detail": t.detail}
                for t in self.timings
            ],
        }


def timed(report: Report, name: str, work: Callable[[], str]) -> None:
    """Run one step, print it as it goes, and record what it cost."""
    print(f"\n[{name}]", flush=True)
    started = time.monotonic()
    detail = work()
    elapsed = time.monotonic() - started
    report.add(name, elapsed, detail)
    print(f"  {detail}   ({elapsed:.1f}s)", flush=True)


#: What the graph load needs on disk. Checked by name after the download
#: rather than inferred from its exit code: `resolve_comprehensive_rules`
#: prints a message and returns an empty list when it cannot find the CR
#: link, and the run still exits 0. Left unchecked, the missing file
#: surfaces two steps later as a `FileNotFoundError` from the CR parser,
#: which names the file but not the reason.
REQUIRED = (
    ("comprehensive rules", lambda: CR_TXT_PATH),
    ("Scryfall oracle cards", lambda: bulk_path(ORACLE_CARDS_STEM)),
    ("Scryfall rulings", lambda: bulk_path(RULINGS_STEM)),
)


def step_download(args: argparse.Namespace) -> str:
    """Scryfall bulk and the Comprehensive Rules, skipped when current.

    `--no-download` exists because "current" is a shorter interval than it
    looks. **Scryfall regenerates its bulk daily**, so the second run of
    this script on the second day is not the warm path: it fetches ~30 MB,
    the card hash changes, the loader reloads all three sources, and any
    vector index built over the old corpus stops matching — arm A's cache
    is keyed on a hash of the indexed text, so a few hundred new cards
    invalidate 116,248 embeddings.

    That is the loader behaving correctly; a graph quietly serving
    yesterday's card data would be worse. But it means an unattended
    onboarding run can cost twenty minutes of re-embedding that nobody
    asked for, so the choice is made visible rather than made silently.
    """
    if args.no_download:
        return "skipped (--no-download)"
    download_main(["--force"] if args.force else [])

    # `bulk_path` returns the path a fresh download *would* write when
    # nothing is there, so existence is the only test that means anything.
    missing = [label for label, locate in REQUIRED if not locate().exists()]
    if missing:
        raise SystemExit(
            f"The download left {', '.join(missing)} absent, and the graph cannot be "
            "built without them. The Comprehensive Rules URL is the usual cause: the "
            "rules page is JS-rendered, so it is not auto-discoverable and CR_TXT_URL "
            "must be set in .env. See .env.example for where to find the current one."
        )
    return "sources present and current"


def step_schema(args: argparse.Namespace) -> str:
    return f"{apply_schema()} constraint/index statement(s) applied"


def step_graph(args: argparse.Namespace) -> str:
    reports = load_all(force=args.force)
    loaded = [r.source for r in reports if not r.skipped]
    skipped = [r.source for r in reports if r.skipped]
    if not loaded:
        return f"already loaded: {', '.join(skipped)}"
    return f"loaded {', '.join(loaded)}" + (f"; skipped {', '.join(skipped)}" if skipped else "")


def step_answer(args: argparse.Namespace) -> str:
    """Retrieve for one question, and answer it when a key is configured."""
    question = first_authored_question()
    linker, searcher, oracle_text = build_stack(args.cr)
    with driver_session() as session:
        subgraph = retrieve(
            question,
            linker=linker,
            run=neo4j_runner(session),
            rule_search=searcher,
            oracle_text=oracle_text,
        )
    print(f"  question: {question}")
    print(f"  outcome:  {subgraph.outcome} — {subgraph.note}")
    print(f"  cited:    {', '.join(subgraph.citations()[:6]) or 'nothing'}")

    settings = get_settings()
    if not (settings.anthropic_api_key or settings.openai_api_key):
        return (
            f"retrieved {len(subgraph.evidence)} item(s); generation skipped, "
            "no LLM key configured"
        )

    # Imported here rather than at the top: an onboarding run with no key
    # must not depend on the generation stack being importable to get as
    # far as saying it has no key.
    from graphrag_mtg.extraction.llm import LlmClient
    from graphrag_mtg.generation.answerer import answer

    client = LlmClient(max_tokens=500, temperature=0.0)
    result = answer(
        question, subgraph, lambda system, prompt: client.complete_text(prompt, system=system)
    )
    print(f"\n  {result.rendered or result.text}\n")
    return f"answered with {len(result.handles)} citation(s), model {client.model}"


def first_authored_question() -> str:
    """An authored golden question, or a hand-written fallback.

    Authored rows carry their text inline and are in the repo; RulesGuru
    rows carry `null` and keep theirs in a gitignored cache. Reaching for
    one of those here would make a clean machine fail for a licensing
    reason dressed as a missing file.
    """
    if not GOLDEN.exists():
        return FALLBACK_QUESTION
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("question"):
            return row["question"]
    return FALLBACK_QUESTION


STEPS: tuple[tuple[str, Callable[[argparse.Namespace], str]], ...] = (
    ("download", step_download),
    ("schema", step_schema),
    ("graph", step_graph),
    ("answer", step_answer),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument(
        "--force", action="store_true", help="re-download and reload even when unchanged"
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="use the sources already on disk; Scryfall's bulk is daily, and a fresh "
        "one reloads the graph and invalidates any vector index built over the old corpus",
    )
    parser.add_argument(
        "--timings", type=Path, default=None, help="write the per-step seconds here as JSON"
    )
    parser.add_argument("--stats", action="store_true", help="print graph counts and exit")
    args = parser.parse_args()

    if args.stats:
        with driver_session() as session:
            print(json.dumps(graph_stats(session), indent=2, sort_keys=True))
        return 0

    print(RULE)
    print("graphrag-mtg-rules — clean machine to first answer")
    print(RULE)
    print("Building the GRAPH, which arms B and C retrieve from; arm C is the")
    print("shipped system. Arm A's vector index is a separate ~116,000-document")
    print("build that costs an embedding call per document and about twenty")
    print("minutes: `python scripts/run_eval.py index`, when you want it.")
    if not args.no_download:
        print()
        print("Scryfall regenerates its bulk daily. If today's differs from the one")
        print("on disk, the graph reloads (~2 min) and any vector index built over")
        print("the old corpus stops matching — the cache is keyed on a hash of the")
        print("indexed text. Pass --no-download to use what is already here.")

    report = Report()
    for name, work in STEPS:
        timed(report, name, lambda work=work: work(args))

    print(f"\n{RULE}")
    for timing in report.timings:
        print(f"{timing.name:<12}{timing.seconds:>8.1f}s   {timing.detail}")
    print(f"{'total':<12}{report.total:>8.1f}s")
    print(RULE)
    print("Every step above is idempotent: the download skips sources the manifest")
    print("already has, and the loader skips sources whose hash the graph already")
    print("carries. Run this again for the warm-path figure.")

    if args.timings:
        args.timings.parent.mkdir(parents=True, exist_ok=True)
        args.timings.write_text(
            json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"\ntimings -> {args.timings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
