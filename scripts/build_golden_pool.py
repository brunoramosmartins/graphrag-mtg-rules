#!/usr/bin/env python
"""Seed the golden-set candidate pool from RulesGuru (Gate G2).

Pulls a stratified pool of judge questions and writes an annotation
skeleton to ``data/golden/ids_v0.jsonl`` — **IDs and our annotations only,
never the question text** (license: eval-only, IDs + fetch; see
docs/data-sources.md). Full text is cached to ``data/interim/golden_cache/``
(gitignored) so a human can annotate hops / gold-entities offline.

Existing rows are preserved (human annotations are never clobbered); only
unseen ids are appended. The suggested stratum is a heuristic from
RulesGuru complexity — the human confirms it during annotation.

Usage:
    python scripts/build_golden_pool.py --per-stratum 12
    python scripts/build_golden_pool.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from graphrag_mtg.etl import rulesguru
from graphrag_mtg.evaluation.golden import (
    GoldenQuestion,
    Source,
    Stratum,
    VectorExpectation,
    content_sha256,
    dump_golden,
    load_golden,
    resolved_content,
)

OUT_PATH = Path("data/golden/ids_v0.jsonl")
CACHE_DIR = Path("data/interim/golden_cache")

# (stratum, RulesGuru complexity filter, default hops, a-priori vector prediction).
# Complexity is only a hint; the human confirms the stratum during annotation.
STRATUM_PLAN = [
    (Stratum.keyword_rule_2hop, ["Simple"], 2, VectorExpectation.lose),
    (Stratum.rulings_2hop, ["Intermediate"], 2, VectorExpectation.lose),
    (Stratum.interaction_multihop, ["Complicated"], 3, VectorExpectation.fail),
]


def _included_card_names(question: dict) -> list[str]:
    return [c["name"] for c in question.get("includedCards", []) if c.get("name")]


def _cited_rule_numbers(question: dict) -> list[str]:
    out: list[str] = []
    for rule in question.get("citedRules", []):
        if isinstance(rule, str):
            out.append(rule)
        elif isinstance(rule, dict):
            num = rule.get("ruleNumber") or rule.get("number") or rule.get("id")
            if num:
                out.append(str(num))
    return out


def _fetch_stratum(http: httpx.Client, settings: dict, count: int) -> list[dict]:
    """Fetch a stratum, backing off ``count`` on a 404 ("not enough questions")."""
    while count >= 1:
        try:
            return rulesguru.fetch({**settings, "count": count}, http=http)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and count > 1:
                count = max(1, count // 2)
                print(f"  (404 not enough; retrying with count={count})")
                continue
            raise
    return []


def _skeleton(question: dict, stratum: Stratum, hops: int, vector: VectorExpectation) -> GoldenQuestion:
    """Build an unverified annotation skeleton from a fetched question."""
    return GoldenQuestion(
        id=f"rg-{question['id']}",
        source=Source.rulesguru,
        stratum=stratum,
        hops=hops,
        gold_entities=_included_card_names(question),
        gold_cr_rules=_cited_rule_numbers(question),
        vector_should=vector,
        rulesguru_url=question.get("url"),
        snapshot_sha256=content_sha256(resolved_content(question)),
        verified=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-stratum", type=int, default=12, help="candidates to pull per stratum")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    args = parser.parse_args()

    existing = load_golden(args.out) if args.out.exists() else []
    known_ids = {q.id for q in existing}
    print(f"Loaded {len(existing)} existing row(s) from {args.out}")

    added: list[GoldenQuestion] = []
    with rulesguru.client() as http:
        for stratum, complexity, hops, vector in STRATUM_PLAN:
            settings = {
                "level": ["0", "1", "2"],
                "complexity": complexity,
                "tags": [],
                "tagsConjunc": "OR",
                "rules": [],
                "rulesConjunc": "OR",
                "cards": [],
                "cardsConjunc": "OR",
            }
            try:
                questions = _fetch_stratum(http, settings, args.per_stratum)
            except Exception as exc:  # one stratum failing must not sink the run
                print(f"[{stratum.value}] fetch failed: {exc}")
                continue
            new_here = 0
            for q in questions:
                qid = f"rg-{q['id']}"
                if qid in known_ids:
                    continue
                known_ids.add(qid)
                added.append(_skeleton(q, stratum, hops, vector))
                new_here += 1
                if not args.dry_run:
                    args.cache_dir.mkdir(parents=True, exist_ok=True)
                    (args.cache_dir / f"{qid}.json").write_text(
                        json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
            print(f"[{stratum.value}] fetched {len(questions)}, {new_here} new")

    if args.dry_run:
        print(f"\nDry run: would add {len(added)} new row(s); wrote nothing.")
        return 0

    dump_golden(existing + added, args.out)
    print(f"\nWrote {len(existing) + len(added)} row(s) to {args.out} "
          f"(+{len(added)} new); full text cached under {args.cache_dir} (gitignored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
