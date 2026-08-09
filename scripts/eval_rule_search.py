#!/usr/bin/env python
"""Does lexical CR retrieval reach a question's gold rules? Development split only.

The evidence behind ADR-007's text half. It reports, per stratum, how
often at least one `gold_cr_rules` entry appears in the top-k lexical
hits — exactly, and at the rule-family level, because E-003a established
that bag-of-words is good at the rule *area* and structurally blind to
depth (a rule and its subrule share nearly the same bag).

**Development split only, and it refuses to run on anything else.**
`data/golden/phase4_dev_ids.json` names the 20 questions Phase 4 may
iterate against; the other 57 are E-001's and are touched once, in Phase
6. Retrieval parameters chosen because they fix an evaluation question
are parameters fitted to the test set.

    python scripts/eval_rule_search.py
    python scripts/eval_rule_search.py --k 12 --no-expansions

Read the `interaction_multihop` row first. It is the stratum ADR-007
routes here precisely because the graph cannot seed it, and it is the one
this measurement says is not rescued.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.evaluation.metrics import rule_family
from graphrag_mtg.retrieval.rule_search import DEFAULT_K, RuleSearch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN_DIR = Path("data/golden")
SPLIT_PATH = Path("data/golden/phase4_dev_ids.json")
QUESTION_FILES = ("authored_v0.jsonl", "definitions_v0.jsonl", "ids_v0.jsonl")


def load_dev_questions(golden: Path, split: Path) -> list[dict]:
    """Golden-set questions on the development side that name gold rules."""
    dev = set(json.loads(split.read_text(encoding="utf-8"))["dev_ids"])
    rows = []
    for name in QUESTION_FILES:
        path = golden / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["id"] in dev and row.get("gold_cr_rules"):
                    rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--split", type=Path, default=SPLIT_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument(
        "--no-expansions",
        action="store_true",
        help="search the question alone, without the named cards' oracle text",
    )
    args = parser.parse_args()

    if not args.split.exists():
        print(f"No development split at {args.split}. Run scripts/split_golden.py draw.")
        return 1
    rows = load_dev_questions(args.golden, args.split)
    if not rows:
        print("No development questions carry gold CR rules.")
        return 1

    search = RuleSearch(parse_cr(args.cr), k=args.k)
    cards = {c["name"]: c.get("oracle_text", "") for c in iter_bulk(bulk_path(ORACLE_CARDS_STEM))}

    per: dict[str, list[int]] = {}
    for row in rows:
        expansions = (
            ()
            if args.no_expansions
            else [cards.get(name, "") for name in (row.get("gold_entities") or [])]
        )
        hits = {h.number for h in search.search(row.get("question") or "", expansions)}
        gold = set(row["gold_cr_rules"])
        bucket = per.setdefault(row["stratum"], [0, 0, 0])
        bucket[0] += bool(gold & hits)
        bucket[1] += bool({rule_family(g) for g in gold} & {rule_family(h) for h in hits})
        bucket[2] += 1

    mode = "question only" if args.no_expansions else "question + card oracle text"
    print(f"Development split, {len(rows)} questions with gold rules, k={args.k} ({mode}).")
    print(f"  {'stratum':<22} {'exact':<10} {'family':<10}")
    for stratum, (exact, family, total) in sorted(per.items()):
        print(f"  {stratum:<22} {exact:>2}/{total:<7} {family:>2}/{total:<7}")
    totals = [sum(v[i] for v in per.values()) for i in range(3)]
    print(f"  {'overall':<22} {totals[0]:>2}/{totals[2]:<7} {totals[1]:>2}/{totals[2]:<7}")
    print(
        "\nThis is retrieval reach, not an answer score: it asks whether the rule the\n"
        "question needs is anywhere in the candidates, which is the ceiling any later\n"
        "ranking or generation step inherits. Development split only — the E-001\n"
        "evaluation set stays untouched until Phase 6."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
