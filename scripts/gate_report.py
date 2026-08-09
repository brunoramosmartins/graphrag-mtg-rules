#!/usr/bin/env python
"""Run extraction candidates through the gate offline and report per reason.

The per-round readout for `notes/phase3-extraction.md`: no Neo4j and no
API — valid rule numbers come from the downloaded CR, source texts from
the frozen sample's todo file. Run it after every extractor round:

    python -m graphrag_mtg.extraction.extractor --ids ... --yes
    python scripts/gate_report.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from graphrag_mtg.extraction.gate import gate_candidates
from graphrag_mtg.extraction.schemas import RuleCitation

CANDIDATES_PATH = Path("data/interim/citations_candidates.jsonl")
TODO_PATH = Path("data/interim/extraction_annotation_todo.jsonl")
CR_TXT = Path("data/raw/comprehensive_rules.txt")

# Subrules ("613.4b ") and chapters ("613. ") both define citable numbers.
_CR_SUBRULE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s", re.MULTILINE)
_CR_CHAPTER = re.compile(r"^(\d{3})\.\s", re.MULTILINE)


# Chapter -> readable family, coarse enough to see a collapse at a glance.
_FAMILIES = {
    "601": "casting (601)",
    "608": "resolving (608)",
    "613": "layers (613)",
    "701": "keyword action (701)",
    "702": "keyword ability (702)",
    "704": "state-based (704)",
}


def _family(rule_number: str) -> str:
    chapter = rule_number.split(".")[0]
    return _FAMILIES.get(chapter, f"other ({chapter})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_PATH)
    parser.add_argument("--todo", type=Path, default=TODO_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT)
    parser.add_argument("--show", type=int, default=10, help="rejected examples to print")
    args = parser.parse_args()

    cr_text = args.cr.read_text(encoding="utf-8-sig")
    known_rules = set(_CR_SUBRULE.findall(cr_text)) | set(_CR_CHAPTER.findall(cr_text))

    source_texts = {
        row["ruling_id"]: row["text"]
        for row in map(json.loads, args.todo.open(encoding="utf-8"))
    }
    candidates = [
        RuleCitation.model_validate_json(line)
        for line in args.candidates.open(encoding="utf-8")
    ]

    result = gate_candidates(
        candidates,
        source_texts=source_texts,
        known_rules=known_rules,
        known_cards=frozenset(),
    )
    print(f"candidates: {len(candidates)}  accepted: {len(result.accepted)}")
    print(f"rejected: {dict(result.rejected) or 'none'}")

    accepted_keys = {(t.source_key, t.target_key) for t in result.accepted}
    rules_cited = Counter(t.target_key for t in result.accepted)
    print(f"distinct rules cited: {len(rules_cited)}; top: {rules_cited.most_common(5)}")

    # Shape of the output, not just its error rate. Round 2 passed the gate
    # at 90% while citing keyword rules exclusively — a topical collapse the
    # rejection count alone could never show.
    families = Counter(_family(t.target_key) for t in result.accepted)
    total = sum(families.values()) or 1
    print("cited rule families:")
    for family, n in families.most_common():
        print(f"  {family:<24} {n:>3}  ({n / total:.0%})")
    covered = len({t.source_key for t in result.accepted})
    print(f"rulings with >=1 accepted citation: {covered}")

    shown = 0
    for candidate in candidates:
        if (candidate.ruling_id, candidate.rule_number) in accepted_keys or shown >= args.show:
            continue
        print(
            f"  REJ rule={candidate.rule_number} conf={candidate.confidence} "
            f'span="{candidate.span.text[:70]}"'
        )
        shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
