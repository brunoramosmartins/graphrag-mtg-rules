#!/usr/bin/env python
"""Daily annotation dashboard: progress, blockers, and a live linking preview.

The one command to run after an annotation session. Reads the working
draft directly — no publish, no API, no Neo4j — and prints:

1. progress (verified / total, per split and stratum);
2. blockers (rows marked verified that still hold an UNDECIDED homonym —
   the publisher will reject these);
3. a **deterministic linking preview**: the linker's exact/loose output
   scored against the verified-and-clean rows, with micro P/R/F1 and
   bootstrap CIs per stratum.

The linking preview excludes the LLM disambiguation stage (that costs
API and runs from the extractor), so single-word homonyms the annotator
resolved to a card show up as recall the LLM stage must recover. Numbers
are a dev-time compass, never a portfolio result — N is small and the
intervals are wide on purpose.

Usage:
    python scripts/annotation_progress.py
    python scripts/annotation_progress.py --split annotation
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.evaluation.metrics import evaluate_by_stratum
from graphrag_mtg.extraction.linker import Lexicon, scan_ruling

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
CARDS_PATH = bulk_path(ORACLE_CARDS_STEM)
UNDECIDED = "UNDECIDED"


def is_clean(row: dict) -> bool:
    """Verified and free of leftover UNDECIDED homonyms."""
    return bool(row.get("verified")) and not any(
        m["target_oracle_id"] == UNDECIDED for m in row["mentions"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--cards", type=Path, default=CARDS_PATH)
    parser.add_argument("--split", choices=("dev", "annotation"), default=None)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.draft.open(encoding="utf-8")]
    if args.split:
        rows = [r for r in rows if r["split"] == args.split]

    verified = [r for r in rows if r.get("verified")]
    print(f"Progress: {len(verified)}/{len(rows)} verified.")
    print(f"  by split:   {dict(Counter(r['split'] for r in verified))}")
    print(f"  by stratum: {dict(Counter(r['stratum'] for r in verified))}")

    blockers = [r for r in verified if not is_clean(r)]
    if blockers:
        print(f"\n{len(blockers)} verified row(s) still hold UNDECIDED — the publisher rejects these:")
        for r in blockers:
            todo = [m["surface"] for m in r["mentions"] if m["target_oracle_id"] == UNDECIDED]
            print(f"  {r['ruling_id']}: {todo}")

    clean = [r for r in verified if is_clean(r)]

    # Citation pass — the second read-through, tracked separately from
    # linking's `verified` because it runs over already-verified rows.
    reviewed = [r for r in rows if r.get("citations_reviewed")]
    citations = sum(len(r["cited_rules"]) for r in rows)
    print(
        f"\nCitation pass: {len(reviewed)}/{len(rows)} rulings citation-reviewed, "
        f"{citations} rules cited so far."
    )
    if len(reviewed) < len(rows):
        print(
            "  Next batch:  python scripts/annotation_worksheet.py "
            "--citation-pass --needs-citations --out data/interim/cite.txt"
        )

    print(f"\nClean rows ready to score: {len(clean)}")
    if not clean:
        print("Annotate and clear UNDECIDED to see the linking preview.")
        return 0

    lexicon = Lexicon.build(
        (c["name"], c["oracle_id"]) for c in iter_bulk(args.cards)
    )

    gold: dict[str, frozenset] = {}
    predicted: dict[str, frozenset] = {}
    strata: dict[str, str] = {}
    for r in clean:
        rid = r["ruling_id"]
        strata[rid] = r["stratum"]
        gold[rid] = frozenset(
            (rid, m["start"], m["target_oracle_id"])
            for m in r["mentions"]
            if m["target_oracle_id"]
        )
        resolved, _ = scan_ruling(rid, r["text"], lexicon, host_oracle_id=r.get("oracle_id"))
        predicted[rid] = frozenset((rid, m.span.start, m.oracle_id) for m in resolved)

    print("\nDeterministic linking preview (exact/loose only — no LLM stage):")
    print(f"  {'stratum':<12} {'F1':<22} P      R      counts")
    for report in evaluate_by_stratum(predicted, gold, stratum_by_doc=strata):
        c = report.counts
        print(
            f"  {report.stratum:<12} {report.f1!s:<22} "
            f"{report.precision.point:.2f}   {report.recall.point:.2f}   "
            f"tp={c.tp} fp={c.fp} fn={c.fn}"
        )
    print(
        "\n(Preview only: dev-time compass, wide CIs, LLM stage excluded. "
        "Homonym recall is what the LLM disambiguation step will recover.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
