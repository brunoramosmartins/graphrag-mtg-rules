#!/usr/bin/env python
"""Project the full-corpus extraction cost from a representative sample.

Phase 3 DoD: report cost per 1000 rulings and average tokens per document,
before any full run. The extraction of one ruling is up to two LLM calls:

- **disambiguation** — one call, only when the ruling has single-word
  homonyms the deterministic linker left pending;
- **citation** — one call per ruling (open or grounded mode; grounded
  carries the CR chapter map + keyword directory in the system prompt,
  which dominates input tokens).

The script samples rulings, builds the real prompts each stage would send,
estimates their tokens with the same chars/4 heuristic the runner prints,
and scales the totals to the whole corpus. Numbers are budgeting ceilings,
not invoices — verify current pricing before spending.

Usage:
    python scripts/extraction_cost_report.py --sample 2000
    python scripts/extraction_cost_report.py --sample 2000 --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag_mtg.extraction import disambiguate, extractor
from graphrag_mtg.extraction.linker import Lexicon, scan_ruling
from graphrag_mtg.extraction.llm import estimate_tokens, price_for_model

SEED = 20260720
OUTPUT_TOKENS_PER_CALL = 300  # both stages return a short JSON array


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulings", type=Path, default=Path("data/raw/scryfall_rulings.json"))
    parser.add_argument(
        "--cards", type=Path, default=Path("data/raw/scryfall_oracle_cards.json")
    )
    parser.add_argument("--cr", type=Path, default=Path("data/raw/comprehensive_rules.txt"))
    parser.add_argument("--sample", type=int, default=2000, help="rulings to sample")
    parser.add_argument("--model", type=str, default=None, help="override LLM_MODEL")
    args = parser.parse_args()

    from graphrag_mtg.config import get_settings

    model = args.model or get_settings().llm_model
    price_in, price_out = price_for_model(model)

    with args.cards.open(encoding="utf-8") as fh:
        cards = json.load(fh)
    lexicon = Lexicon.build((c["name"], c["oracle_id"]) for c in cards)

    with args.rulings.open(encoding="utf-8") as fh:
        rulings = json.load(fh)
    corpus_n = len(rulings)
    sample = random.Random(SEED).sample(rulings, min(args.sample, corpus_n))

    # Grounded system prompt + per-keyword candidates, parsed once.
    from graphrag_mtg.etl.cr_parser import parse_cr
    from graphrag_mtg.extraction.grounding import (
        candidate_rules_for_keywords,
        grounding_block,
    )

    doc = parse_cr(args.cr)
    grounded_system = extractor.SYSTEM_PROMPT + "\n\n" + grounding_block(doc)
    keywords_by_oracle = {c["oracle_id"]: c.get("keywords", []) for c in cards}

    stats = {
        "rulings": 0,
        "with_homonyms": 0,
        "disambig_input": 0,
        "open_input": 0,
        "grounded_input": 0,
    }
    for raw in sample:
        text = raw.get("comment", "")
        stats["rulings"] += 1
        _, pending = scan_ruling("x", text, lexicon, host_oracle_id=raw.get("oracle_id"))
        if pending:
            stats["with_homonyms"] += 1
            prompt = disambiguate.build_prompt(pending, text)
            stats["disambig_input"] += estimate_tokens(prompt) + estimate_tokens(
                disambiguate.SYSTEM_PROMPT
            )
        stats["open_input"] += estimate_tokens(extractor.build_prompt(text)) + estimate_tokens(
            extractor.SYSTEM_PROMPT
        )
        cand = candidate_rules_for_keywords(keywords_by_oracle.get(raw.get("oracle_id", ""), []), doc)
        stats["grounded_input"] += estimate_tokens(
            extractor.build_prompt(text, cand)
        ) + estimate_tokens(grounded_system)

    n = stats["rulings"]
    homonym_rate = stats["with_homonyms"] / n

    def project(input_tokens_sample: int, calls_sample: int) -> tuple[float, float, float]:
        """Return (avg_input_per_call, usd_per_1000_rulings, usd_full_corpus)."""
        scale = corpus_n / n
        in_tokens = input_tokens_sample * scale
        out_tokens = calls_sample * scale * OUTPUT_TOKENS_PER_CALL
        usd = (in_tokens * price_in + out_tokens * price_out) / 1_000_000
        avg_in = input_tokens_sample / calls_sample if calls_sample else 0.0
        return avg_in, usd / corpus_n * 1000, usd

    print(f"Model: {model}   (${price_in}/${price_out} per Mtok in/out)")
    print(f"Sample: {n} of {corpus_n:,} rulings   seed={SEED}")
    print(f"Rulings with homonyms (disambiguation call): {homonym_rate:.1%}\n")

    print(f"{'stage / mode':<28} {'avg in tok/call':>16} {'$/1000 rulings':>16} {'$ full corpus':>16}")
    for label, in_toks, calls in (
        ("disambiguation", stats["disambig_input"], stats["with_homonyms"]),
        ("citation (open)", stats["open_input"], n),
        ("citation (grounded)", stats["grounded_input"], n),
    ):
        avg_in, per_k, full = project(in_toks, calls)
        print(f"{label:<28} {avg_in:>16,.0f} {per_k:>16,.4f} {full:>16,.2f}")

    _, dis_k, dis_full = project(stats["disambig_input"], stats["with_homonyms"])
    _, open_k, open_full = project(stats["open_input"], n)
    _, gr_k, gr_full = project(stats["grounded_input"], n)
    print(
        f"\nFull pipeline, open mode:     ${dis_k + open_k:,.4f}/1000  "
        f"= ${dis_full + open_full:,.2f} for the whole corpus"
    )
    print(
        f"Full pipeline, grounded mode: ${dis_k + gr_k:,.4f}/1000  "
        f"= ${dis_full + gr_full:,.2f} for the whole corpus"
    )
    print(
        "\n(chars/4 token heuristic, output assumed "
        f"{OUTPUT_TOKENS_PER_CALL} tok/call; ceilings for budgeting, verify pricing.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
