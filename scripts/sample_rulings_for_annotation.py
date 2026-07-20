#!/usr/bin/env python
"""Draw the frozen Phase 3 samples: 30-ruling dev set + 120-ruling annotation set.

Freezing happens HERE, before any annotation or extraction run — the id
lists are committed, E-003 registers against them, and neither list
changes afterwards. The draw is stratified by what the deterministic
linker already knows, deliberately overweighting the tail that decides
the phase (single-word homonym candidates like "Opt"):

- ``homonym``   — ≥1 single-word candidate pending LLM disambiguation
- ``multiword`` — ≥1 deterministic mention, no homonym candidates
- ``explicit``  — text states a CR rule number (measured: 25 in 77,999, 3 cards)
- ``plain``     — none of the above (the negatives that keep precision honest)

Outputs:
- ``data/golden/extraction_sample_ids.json`` — ids + strata + seed
  (committed; ids and offsets only, no ruling text, per licensing rules)
- ``data/interim/extraction_annotation_todo.jsonl`` — full text for the
  annotator (gitignored)

Usage:
    python scripts/sample_rulings_for_annotation.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from graphrag_mtg.extraction.linker import Lexicon, scan_ruling
from graphrag_mtg.graph.loader import ruling_id as make_ruling_id

SEED = 20260720  # date of the draw; never reseeded

DEV_QUOTA = {"homonym": 10, "multiword": 10, "plain": 10}
ANNOTATION_QUOTA = {"homonym": 50, "multiword": 40, "plain": 30}
EXPLICIT_CAP = 5  # every explicit-rule ruling is precious; take up to this many extra

SAMPLE_IDS_PATH = Path("data/golden/extraction_sample_ids.json")
TODO_PATH = Path("data/interim/extraction_annotation_todo.jsonl")

_RULE_NUMBER = re.compile(r"\b\d{3}\.\d+[a-z]?\b")


def classify(ruling: dict, lexicon: Lexicon) -> str:
    """Assign one ruling to its sampling stratum."""
    text = ruling.get("comment", "")
    if _RULE_NUMBER.search(text):
        return "explicit"
    rid = make_ruling_id(ruling)
    resolved, pending = scan_ruling(rid, text, lexicon, host_oracle_id=ruling.get("oracle_id"))
    if pending:
        return "homonym"
    if resolved:
        return "multiword"
    return "plain"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulings", type=Path, default=Path("data/raw/scryfall_rulings.json"))
    parser.add_argument(
        "--cards", type=Path, default=Path("data/raw/scryfall_oracle_cards.json")
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="classify at most N rulings and stop — dry run, writes nothing "
        "(a frozen draw must always see the full corpus)",
    )
    args = parser.parse_args()

    if SAMPLE_IDS_PATH.exists():
        print(f"{SAMPLE_IDS_PATH} already exists — the sample is frozen. Refusing to redraw.")
        return 1

    with args.cards.open(encoding="utf-8") as fh:
        cards = json.load(fh)
    lexicon = Lexicon.build((c["name"], c["oracle_id"]) for c in cards)
    with args.rulings.open(encoding="utf-8") as fh:
        rulings = json.load(fh)
    if args.limit is not None:
        rulings = rulings[: args.limit]

    by_stratum: dict[str, list[dict]] = {"homonym": [], "multiword": [], "explicit": [], "plain": []}
    stratum_by_id: dict[str, str] = {}
    for n, ruling in enumerate(rulings, 1):
        stratum = classify(ruling, lexicon)
        by_stratum[stratum].append(ruling)
        stratum_by_id[make_ruling_id(ruling)] = stratum
        if n % 10_000 == 0:
            print(f"  classified {n:,}/{len(rulings):,} rulings...", flush=True)

    if args.limit is not None:
        counts = {k: len(v) for k, v in by_stratum.items()}
        print(f"Dry run over {len(rulings):,} rulings — strata: {counts}. Nothing written.")
        return 0

    rng = random.Random(SEED)
    for pool in by_stratum.values():
        rng.shuffle(pool)

    picked: dict[str, list[dict]] = {"dev": [], "annotation": []}
    for split, quota in (("dev", DEV_QUOTA), ("annotation", ANNOTATION_QUOTA)):
        for stratum, want in quota.items():
            pool = by_stratum[stratum]
            take, by_stratum[stratum] = pool[:want], pool[want:]
            if len(take) < want:
                print(f"warning: stratum {stratum!r} short for {split} ({len(take)}/{want})")
            picked[split].extend(take)
    picked["annotation"].extend(by_stratum["explicit"][:EXPLICIT_CAP])

    strata = {
        make_ruling_id(r): stratum_by_id[make_ruling_id(r)]
        for split in picked.values()
        for r in split
    }
    manifest = {
        "seed": SEED,
        "counts_in_corpus": {k: len(v) for k, v in by_stratum.items()},
        "dev": [make_ruling_id(r) for r in picked["dev"]],
        "annotation": [make_ruling_id(r) for r in picked["annotation"]],
        "strata": strata,
    }
    SAMPLE_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_IDS_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    TODO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TODO_PATH.open("w", encoding="utf-8") as out:
        for split in ("dev", "annotation"):
            for ruling in picked[split]:
                row = {
                    "split": split,
                    "ruling_id": make_ruling_id(ruling),
                    "stratum": strata[make_ruling_id(ruling)],
                    "oracle_id": ruling.get("oracle_id"),
                    "published_at": ruling.get("published_at"),
                    "text": ruling.get("comment", ""),
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"Frozen: {len(manifest['dev'])} dev + {len(manifest['annotation'])} annotation "
        f"rulings -> {SAMPLE_IDS_PATH} (ids, committed) and {TODO_PATH} (text, gitignored)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
