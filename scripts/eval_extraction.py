#!/usr/bin/env python
"""Score linking and citation output against the manual annotations (E-003).

Consumes the published gold (`data/golden/extraction_annotations.jsonl`)
plus whatever the pipeline produced, and reports micro P/R/F1 with
per-document bootstrap CIs, stratified by sampling stratum — the report
`docs/evaluation.md` and the E-003 registry entry expect.

Item keys, both exact-match:

- linking: ``(ruling_id, start, oracle_id)`` — a mention counts only when
  the *occurrence* and the target agree. Offsets are in the key on
  purpose: a system that links the right card at the wrong place has not
  found the mention that a citation would hang on.
- citations: ``(ruling_id, rule_number)`` — spans are not in the key, so
  a right rule justified by a slightly different clause still counts;
  the gate already enforces that the span is verbatim.

Gold rows where ``target_oracle_id`` is null are **negatives**: the word
looks like a card name and is not one. They never enter the gold set, so
a system that links them takes a false positive — which is exactly how
the homonym tail gets measured.

Usage:
    python scripts/eval_extraction.py --split annotation
    python scripts/eval_extraction.py --split dev --citations data/interim/citations_candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Hashable
from pathlib import Path

from graphrag_mtg.evaluation.metrics import StratumReport, evaluate_by_stratum
from graphrag_mtg.extraction.schemas import CardMention, RuleCitation

GOLD_PATH = Path("data/golden/extraction_annotations.jsonl")
MENTIONS_PATH = Path("data/interim/mentions_candidates.jsonl")
CITATIONS_PATH = Path("data/interim/citations_candidates.jsonl")


def load_gold(path: Path, split: str) -> tuple[dict, dict, dict]:
    """Return (mentions_by_doc, citations_by_doc, stratum_by_doc) for one split."""
    mentions: dict[str, set[Hashable]] = {}
    citations: dict[str, set[Hashable]] = {}
    strata: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["split"] != split:
                continue
            rid = row["ruling_id"]
            strata[rid] = row["stratum"]
            mentions[rid] = {
                (rid, m["start"], m["target_oracle_id"])
                for m in row["mentions"]
                if m["target_oracle_id"] is not None
            }
            citations[rid] = {
                (rid, c.get("rule_number") or c.get("rule")) for c in row["cited_rules"]
            }
    return mentions, citations, strata


def load_predicted_mentions(path: Path, docs: set[str]) -> dict[str, set[Hashable]]:
    """Predicted mentions, keyed like the gold; unresolved ones are ignored."""
    predicted: dict[str, set[Hashable]] = {}
    if not path.exists():
        return predicted
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            rid = row["ruling_id"]
            if rid not in docs or row.get("oracle_id") is None:
                continue
            mention = CardMention.model_validate(
                {k: v for k, v in row.items() if k != "candidate_oracle_ids"}
            )
            predicted.setdefault(rid, set()).add(
                (rid, mention.span.start, mention.oracle_id)
            )
    return predicted


def load_predicted_citations(path: Path, docs: set[str]) -> dict[str, set[Hashable]]:
    """Predicted citations, keyed like the gold."""
    predicted: dict[str, set[Hashable]] = {}
    if not path.exists():
        return predicted
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            citation = RuleCitation.model_validate_json(line)
            if citation.ruling_id not in docs:
                continue
            predicted.setdefault(citation.ruling_id, set()).add(
                (citation.ruling_id, citation.rule_number)
            )
    return predicted


def print_report(title: str, reports: list[StratumReport]) -> None:
    """Print one task's stratified table, overall row first."""
    print(f"\n{title}")
    print(f"  {'stratum':<14} {'P':<22} {'R':<22} {'F1':<22} counts")
    for report in reports:
        counts = report.counts
        print(
            f"  {report.stratum:<14} {report.precision!s:<22} {report.recall!s:<22} "
            f"{report.f1!s:<22} tp={counts.tp} fp={counts.fp} fn={counts.fn}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--split", choices=("dev", "annotation"), default="annotation")
    parser.add_argument("--mentions", type=Path, default=MENTIONS_PATH)
    parser.add_argument("--citations", type=Path, default=CITATIONS_PATH)
    args = parser.parse_args()

    if not args.gold.exists():
        print(f"No published gold at {args.gold}. Annotate, then run:")
        print("  python scripts/check_extraction_annotations.py --publish")
        return 1

    gold_mentions, gold_citations, strata = load_gold(args.gold, args.split)
    if not strata:
        print(f"No {args.split!r} rows in {args.gold}.")
        return 1
    docs = set(strata)
    print(f"Split {args.split!r}: {len(docs)} annotated rulings.")

    predicted_mentions = load_predicted_mentions(args.mentions, docs)
    predicted_citations = load_predicted_citations(args.citations, docs)

    print_report(
        "Card-mention linking (ruling, offset, oracle_id)",
        evaluate_by_stratum(
            {k: frozenset(v) for k, v in predicted_mentions.items()},
            {k: frozenset(v) for k, v in gold_mentions.items()},
            stratum_by_doc=strata,
        ),
    )
    print_report(
        "Rule citations (ruling, rule_number)",
        evaluate_by_stratum(
            {k: frozenset(v) for k, v in predicted_citations.items()},
            {k: frozenset(v) for k, v in gold_citations.items()},
            stratum_by_doc=strata,
        ),
    )
    print(
        "\nThresholds (E-003 / roadmap DoD): linking F1 >= 0.9, citation F1 >= 0.75.\n"
        "Read the interval, not the point estimate."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
