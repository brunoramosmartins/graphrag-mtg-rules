#!/usr/bin/env python
"""E-013 — does an edge the graph already has reach the rules it misses?

Registered 2026-09-11 before the router was touched. Phase 8's error
analysis attributed 74% of failures to evidence the graph cannot reach, and
one Cypher query said why: `Keyword-[:DEFINED_BY]->Rule` lands only in
chapter 700, `HAS_SUBRULE` to depth two stays there, and the first edge that
leaves is `REFERENCES` — walked by `rule_neighbourhood`, a template the
routed plan never invokes because it takes a rule number and the plan starts
from cards.

**The ceiling is arithmetic and was registered before this ran.** Of the 52
distinct gold rules needed and missed, 18 are one `REFERENCES` hop from a
rule the graph already had. So gold-rule recall can rise from 7/64 = 0.109 to
at most 25/64 = 0.391. A figure above that is a bug here, not a result.

**Nothing is generated and nothing is judged.** The primary metric asks
whether a question's `gold_cr_rules` appear in the retrieved evidence, which
is a set comparison over files that already exist plus one retrieval pass.

Usage:
    python scripts/run_e013.py --limit 3      # smoke it against the graph
    python scripts/run_e013.py                # the registered run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.retrieval.pipeline import retrieve

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: Registered in E-013 before the run. Printed beside every result so a
#: reader never has to take the ceiling on trust.
CEILING_REACHABLE = 18
CEILING_MISSED = 52
BASELINE_HITS, GOLD_TOTAL = 7, 64

#: The population the error analysis attributed: failures with a
#: contemporaneous retrieval record and gold rules recorded.
POPULATION = Path("data/interim/error_taxonomy.jsonl")

OUT = Path("runs/e013_reference_hop.jsonl")


def gold_rules() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(Path("data/golden").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("id") and row.get("gold_cr_rules"):
                found.setdefault(row["id"], [str(r) for r in row["gold_cr_rules"]])
    return found


def covered(want: str, got: set[str]) -> bool:
    """A gold rule counts as retrieved if a retrieved rule is it or contains it.

    `613.4b` is covered by `613.4b` and by `613.4`; a subrule satisfies a
    parent and a parent satisfies a subrule, because the context block
    carries a rule's text either way. Strict equality would score the
    retrieval on the granularity the annotator happened to write.
    """
    return any(key == want or key.startswith(want) or want.startswith(key) for key in got)


def measure(args: argparse.Namespace) -> int:
    if not POPULATION.exists():
        raise SystemExit(f"No population at {POPULATION}. Run scripts/error_taxonomy.py build.")

    gold = gold_rules()
    rows = [
        json.loads(line)
        for line in POPULATION.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = [r for r in rows if r["question_id"] in gold]
    if args.limit:
        questions = questions[: args.limit]

    from graphrag_mtg.etl.cards import load_oracle_cards
    from graphrag_mtg.graph.connection import driver_session
    from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon

    print(f"E-013 — {len(questions)} question(s), no model call, no answer regenerated.")
    print(f"registered ceiling: {CEILING_REACHABLE} of {CEILING_MISSED} missing rules "
          f"reachable; recall at most {(BASELINE_HITS + CEILING_REACHABLE)}/{GOLD_TOTAL} "
          f"= {(BASELINE_HITS + CEILING_REACHABLE) / GOLD_TOTAL:.3f}")
    print(RULE)

    cards = [card.model_dump() if hasattr(card, "model_dump") else card
             for card in load_oracle_cards(limit=args.cards)]
    lexicon = build_card_lexicon(cards)
    keywords = sorted({k for c in cards for k in (c.get("keywords") or [])})
    by_oracle = {c["oracle_id"]: (c.get("keywords") or []) for c in cards}
    linker = QueryLinker(lexicon, keywords=keywords, keywords_by_oracle=by_oracle)

    results = []
    with driver_session() as session:
        def run(cypher, params):
            return [record.data() for record in session.run(cypher, **dict(params))]

        for row in questions:
            qid = row["question_id"]
            question = row.get("question") or ""
            if not question:
                # The worksheet carries the answer and the record, not the
                # question text; it lives in the gitignored fetch cache.
                cached = Path("data/interim/e007_cache") / f"{qid}.json"
                if cached.exists():
                    payload = json.loads(cached.read_text(encoding="utf-8"))
                    question = payload.get("questionSimple") or payload.get("question") or ""
            if not question:
                print(f"  {qid}: no question text; skipped")
                continue

            for hop in (False, True):
                subgraph = retrieve(
                    question,
                    linker=linker,
                    run=run,
                    token_budget=args.token_budget,
                    kind_cap=args.kind_cap,
                    reference_hop=hop,
                )
                got = {e.key for e in subgraph.evidence if e.kind == "rule"}
                want = gold[qid]
                results.append(
                    {
                        "question_id": qid,
                        "reference_hop": hop,
                        "gold": want,
                        "hit": [w for w in want if covered(w, got)],
                        # The rules actually retrieved, so the per-question
                        # ceiling can be computed from what this question had
                        # rather than from what the graph holds somewhere.
                        "retrieved_rules": sorted(got),
                        "evidence_n": len(subgraph.evidence),
                        "tokens": subgraph.tokens,
                        "dropped": dict(subgraph.dropped),
                        "capped": dict(subgraph.capped),
                        "templates_run": list(subgraph.templates_run),
                        "outcome": str(subgraph.outcome),
                    }
                )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        for record in results:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}\n")
    return report(results)


def report(results: list[dict]) -> int:
    print(RULE)
    for hop in (False, True):
        rows = [r for r in results if r["reference_hop"] == hop]
        if not rows:
            continue
        hits = sum(len(r["hit"]) for r in rows)
        total = sum(len(r["gold"]) for r in rows)
        interval = wilson_interval(hits, total)
        dropped = sum(1 for r in rows if r["dropped"])
        tokens = sum(r["tokens"] for r in rows) / len(rows)
        evidence = sum(r["evidence_n"] for r in rows) / len(rows)
        label = "with the REFERENCES hop" if hop else "as shipped"
        print(f"  {label}")
        print(f"    gold-rule recall  {hits}/{total} = {hits/total:.3f}   "
              f"[{interval.low:.3f}, {interval.high:.3f}]")
        print(f"    evidence/question {evidence:.1f}   tokens/question {tokens:.0f}")
        print(f"    questions whose context was dropped: {dropped}/{len(rows)}")
    print(RULE)

    before = [r for r in results if not r["reference_hop"]]
    after = [r for r in results if r["reference_hop"]]
    if not (before and after):
        return 0
    gained = sum(len(r["hit"]) for r in after) - sum(len(r["hit"]) for r in before)
    print(f"gold rules gained by the hop: {gained}")
    print(f"registered ceiling on this population: {CEILING_REACHABLE}")
    print("\nThe decision rule is in E-013 and is not restated here, so that reading")
    print("the number and applying the rule stay separate acts. This is a")
    print("development figure: the repair was chosen after reading these questions.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, default=0, help="run at most N questions")
    parser.add_argument("--cards", type=int, default=None, help="cap the lexicon, for smoke")
    parser.add_argument("--token-budget", type=int, default=6000)
    parser.add_argument("--kind-cap", type=int, default=25)
    args = parser.parse_args()
    return measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
