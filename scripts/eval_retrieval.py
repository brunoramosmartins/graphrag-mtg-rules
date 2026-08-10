#!/usr/bin/env python
"""E-006: what does retrieval actually reach? Development split only.

Runs the shipped stack — linking, routing, traversals, and lexical CR
retrieval where the route calls for it — over the 20 questions frozen in
`data/golden/phase4_dev_ids.json`, and reports:

- **entity recall**, the share of a question's `gold_entities` present in
  the subgraph. The Phase 4 DoD's threshold applies to this, on the 1-2
  hop strata only;
- **rule recall**, the share of its `gold_cr_rules` present. Reported
  beside entity recall and never averaged into it — reaching *Humility*
  and reaching *613.4b* are not interchangeable achievements, and merging
  them lets the easy one hide the hard one;
- **outcome coverage**, since the DoD asks for a non-empty subgraph *or an
  explicit failure* for every question, never silence;
- **wall-clock**, against the p95 < 2 s criterion.

Registered in `experiments/registry.md` (E-006) before its first run. It
refuses to touch the 57 evaluation questions, which belong to E-001 and
are read once, in Phase 6.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --show   # print every question's route

Requires a live Neo4j with the corpus loaded.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import keyword_definition_rows
from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon
from graphrag_mtg.retrieval.pipeline import neo4j_runner, retrieve
from graphrag_mtg.retrieval.rule_search import RuleSearch
from graphrag_mtg.retrieval.subgraph import Outcome

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN_DIR = Path("data/golden")
SPLIT_PATH = Path("data/golden/phase4_dev_ids.json")
QUESTION_FILES = ("authored_v0.jsonl", "definitions_v0.jsonl", "ids_v0.jsonl")

#: Strata the roadmap's Entity Recall criterion covers. `interaction_multihop`
#: is out of scope by the roadmap's own wording ("1-2 hops"), and both
#: reachability.py and eval_rule_search.py have already measured it as beyond
#: either retrieval half.
THRESHOLD_STRATA = ("definition_1hop", "keyword_rule_2hop", "legality_1hop")
ENTITY_RECALL_FLOOR = 0.9
LATENCY_P95_SECONDS = 2.0


def load_dev_questions(golden: Path, split: Path) -> list[dict]:
    """Golden-set questions on the development side."""
    dev = set(json.loads(split.read_text(encoding="utf-8"))["dev_ids"])
    rows = []
    for name in QUESTION_FILES:
        path = golden / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip() and (row := json.loads(line))["id"] in dev:
                    rows.append(row)
    return rows


def recall(wanted: list[str], found: set[str]) -> float | None:
    """Share of ``wanted`` present in ``found``; None when nothing was wanted."""
    if not wanted:
        return None
    return sum(1 for item in wanted if item in found) / len(wanted)


def percentile(values: list[float], share: float) -> float:
    """Simple order-statistic percentile; the sample is 20, not 20,000."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--split", type=Path, default=SPLIT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument("--show", action="store_true", help="print every question's route")
    args = parser.parse_args()

    questions = load_dev_questions(args.golden, args.split)
    if not questions:
        print(f"No development questions found. Is {args.split} present?")
        return 1

    doc = parse_cr(args.cr)
    cards = list(iter_bulk(bulk_path(ORACLE_CARDS_STEM)))
    lexicon = build_card_lexicon(cards)
    keywords_by_oracle = {c["oracle_id"]: c.get("keywords", []) for c in cards}
    oracle_text = {c["oracle_id"]: c.get("oracle_text", "") for c in cards}
    keyword_names = {row["display_name"] for row in keyword_definition_rows(doc)}
    with driver_session() as probe:
        formats = [r["name"] for r in probe.run("MATCH (f:Format) RETURN f.name AS name")]
    linker = QueryLinker(lexicon, keyword_names, keywords_by_oracle, formats=formats)
    searcher = RuleSearch(doc)

    per_stratum: dict[str, list[tuple[float | None, float | None]]] = {}
    outcomes: dict[str, int] = {}
    durations: list[float] = []

    with driver_session() as session:
        run = neo4j_runner(session)
        for row in questions:
            started = time.perf_counter()
            subgraph = retrieve(
                row.get("question") or " ".join(row.get("gold_entities") or []),
                linker=linker,
                run=run,
                rule_search=searcher,
                oracle_text=oracle_text,
            )
            durations.append(time.perf_counter() - started)
            outcomes[str(subgraph.outcome)] = outcomes.get(str(subgraph.outcome), 0) + 1

            keys = {e.key for e in subgraph.evidence}
            normalized = {normalize_name(k) for k in keys}
            entity_hit = recall(
                [normalize_name(e) for e in row.get("gold_entities") or []], normalized
            )
            rule_hit = recall(row.get("gold_cr_rules") or [], keys)
            per_stratum.setdefault(row["stratum"], []).append((entity_hit, rule_hit))

            if args.show:
                print(f"\n[{row['id']}] {row['stratum']}  {subgraph.outcome}")
                print(f"  entity {entity_hit} | rule {rule_hit} | {len(subgraph.evidence)} items")
                print(f"  {subgraph.note}")

    print(f"\nE-006 — development split, {len(questions)} questions.")
    print(f"  {'stratum':<22} {'entity recall':<16} {'rule recall':<16} n")
    for stratum, pairs in sorted(per_stratum.items()):
        entity = [e for e, _ in pairs if e is not None]
        rules = [r for _, r in pairs if r is not None]
        entity_text = f"{statistics.fmean(entity):.2f}" if entity else "n/a"
        rule_text = f"{statistics.fmean(rules):.2f}" if rules else "n/a"
        print(f"  {stratum:<22} {entity_text:<16} {rule_text:<16} {len(pairs)}")

    scored = [e for s in THRESHOLD_STRATA for e, _ in per_stratum.get(s, []) if e is not None]
    if scored:
        point = statistics.fmean(scored)
        verdict = "PASS" if point >= ENTITY_RECALL_FLOOR else "FAIL"
        print(
            f"\n  1-2 hop entity recall: {point:.3f} over {len(scored)} questions, "
            f"against the {ENTITY_RECALL_FLOOR} floor -> {verdict}"
        )
        print("  (n is small; read this as a smoke test, not as E-001)")

    print(f"\n  outcomes: {outcomes}")
    print(f"  every question got a subgraph or a named failure: {sum(outcomes.values()) == len(questions)}")
    print(
        f"  latency: median {statistics.median(durations):.2f}s, "
        f"p95 {percentile(durations, 0.95):.2f}s against the {LATENCY_P95_SECONDS}s criterion"
    )
    print(f"  named failures: {[k for k in outcomes if k != str(Outcome.RESOLVED)] or 'none'}")
    print("\nDevelopment split only. E-001's 57 evaluation questions are untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
