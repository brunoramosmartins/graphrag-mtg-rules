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

    # E-007's audit pool: a separate file, disjoint from the golden set by id
    # *and* reported for card overlap. --exclude is not optional here — dedup
    # otherwise sees only --out, and a fresh pool would re-draw the 77.
    python scripts/build_golden_pool.py --per-stratum 14 \
        --out data/golden/e007_audit_pool.jsonl \
        --exclude data/golden/ids_v0.jsonl \
        --cache-dir data/interim/e007_cache
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
    parser.add_argument(
        "--stratum",
        action="append",
        default=[],
        choices=[row[0].value for row in STRATUM_PLAN],
        help="only draw for these strata; repeatable. Default: all three.",
    )
    parser.add_argument(
        "--complexity",
        action="append",
        default=[],
        help=(
            "override the stratum's RulesGuru complexity filter; repeatable. "
            "Complexity is a hint the human confirms during annotation, so "
            "widening it is legitimate — but it changes what the sample "
            "represents and belongs in the registry before the draw is frozen."
        ),
    )
    parser.add_argument(
        "--level",
        action="append",
        default=[],
        help="RulesGuru judge levels to include; repeatable. Default: 0, 1, 2.",
    )
    parser.add_argument(
        "--exclude",
        type=Path,
        action="append",
        default=[],
        help=(
            "another pool whose ids and cards are off-limits. Required when --out "
            "is not the golden set: dedup otherwise only sees the output file, so a "
            "fresh pool would happily re-draw questions the golden set already holds."
        ),
    )
    args = parser.parse_args()
    args.level = args.level or ["0", "1", "2"]

    existing = load_golden(args.out) if args.out.exists() else []
    known_ids = {q.id for q in existing}
    print(f"Loaded {len(existing)} existing row(s) from {args.out}")

    # Disjointness has two levels and only the first is free. Ids keep the
    # same question out; card names are how a *near-duplicate* gets caught —
    # RulesGuru carries several questions about one interaction, and a pool
    # that shares its cards with the evaluation split is not the independent
    # sample it claims to be. Overlap is reported, not silently dropped: a
    # question about Humility is not automatically the same question.
    excluded_cards: set[str] = set()
    for path in args.exclude:
        rows = load_golden(path)
        known_ids.update(q.id for q in rows)
        excluded_cards.update(name.casefold() for q in rows for name in q.gold_entities)
        print(f"Excluding {len(rows)} row(s) from {path}")

    plan = [row for row in STRATUM_PLAN if not args.stratum or row[0].value in args.stratum]
    added: list[GoldenQuestion] = []
    with rulesguru.client() as http:
        for stratum, complexity, hops, vector in plan:
            # The filter is an argument, not a constant, because a bucket
            # can be exhausted. The golden set already took 22 of its
            # `interaction_multihop` questions from RulesGuru, and a later
            # draw against `complexity: Complicated` matched three, all of
            # them already taken. Widening the filter changes what the
            # sample represents, so it is stated on the command line and
            # printed with the result rather than edited into a constant.
            settings = {
                "level": args.level,
                "complexity": args.complexity or complexity,
                "tags": [],
                "tagsConjunc": "OR",
                "rules": [],
                "rulesConjunc": "OR",
                "cards": [],
                "cardsConjunc": "OR",
            }
            print(
                f"[{stratum.value}] filter: complexity={settings['complexity']} "
                f"level={settings['level']} count={args.per_stratum}"
            )
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

    if excluded_cards:
        shared = sorted(
            {
                name
                for q in added
                for name in q.gold_entities
                if name.casefold() in excluded_cards
            }
        )
        touching = sum(
            1
            for q in added
            if any(name.casefold() in excluded_cards for name in q.gold_entities)
        )
        print(
            f"\nCard overlap with the excluded pool(s): {touching} of {len(added)} "
            f"question(s) touch {len(shared)} shared card name(s)."
        )
        if shared:
            print(f"  {', '.join(shared[:12])}{' ...' if len(shared) > 12 else ''}")
        print("  Report this figure with the sample; disjoint by id is not disjoint by content.")

    if args.dry_run:
        print(f"\nDry run: would add {len(added)} new row(s); wrote nothing.")
        return 0

    dump_golden(existing + added, args.out)
    print(f"\nWrote {len(existing) + len(added)} row(s) to {args.out} "
          f"(+{len(added)} new); full text cached under {args.cache_dir} (gitignored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
