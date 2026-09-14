#!/usr/bin/env python
"""Render what each E-018 condition was sent, and what it answered.

Registered as a deliverable in the 2026-09-13 amendment, under standing rule 8:
no comparative evaluation is published without a manual sample of every outcome
category, read with the **final prompt as sent** in front of the reader. This
entry's whole result rests on two discordant pairs. Two cases are not a summary
statistic — they are two cases, and they can be read in full.

**The rebuild is verified, not assumed.** The run recorded `prompt_sha256` over
the system prompt and the user prompt together. This rebuilds the three
conditions from the same frozen inputs at the same seed and checks each digest;
a case whose digest disagrees is **refused, not shown with a caveat**, because
a prompt that differs from the one sent makes every reading of it fiction.

`--flips` is the sample the entry needs: every question where a condition's
label differs from control's, which on this run is four questions across three
conditions, plus the ceiling's three `false` cases on request.

Usage:
    python scripts/e018_inspect.py --qid rg-271
    python scripts/e018_inspect.py --flips
    python scripts/e018_inspect.py --qid rg-271 --condition treatment --full
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graphrag_mtg.evaluation.rubric import render_for_judgement
from graphrag_mtg.generation.answerer import SYSTEM, prompt_digest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import load_jsonl
from e018_analysis import by_condition
from run_e018 import CONDITIONS, RUN_PATH, prepare
from run_eval import CACHE_DIR, GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78


def flipped(labels: dict[str, dict[str, str]]) -> list[str]:
    """Questions where any condition's label differs from control's.

    The sample standing rule 8 asks for. On a run resting on two discordant
    pairs, "every case that moved" is four questions — small enough to read in
    full, which is what the rule requires of a category with five or fewer.
    """
    return sorted(
        qid
        for qid, pair in labels.items()
        if "control" in pair and any(pair.get(name) != pair["control"] for name in CONDITIONS)
    )


def show(
    row: dict, scored: dict[str, dict], conditions: tuple[str, ...], full: bool
) -> int:
    """One question, every requested condition, prompt and answer. Returns unverified count."""
    qid = row["question_id"]
    print(f"\n{RULE}")
    print(f"{qid}   gold rules: {', '.join(row['gold_cr_rules'])}")
    labels = "   ".join(f"{name}={scored[name]['label']}" for name in CONDITIONS if name in scored)
    print(f"labels: {labels}")
    print(f"\n{THIN}\nQUESTION\n{THIN}\n{row['question']}")
    print(f"\n{THIN}\nKEY — the only authority the judge has\n{THIN}\n{row['key']}")

    unverified = 0
    for name in conditions:
        if name not in scored:
            continue
        prompt = row["prompts"][name]
        digest = prompt_digest(SYSTEM, prompt)
        recorded = scored[name].get("prompt_sha256")
        print(f"\n{RULE}\nCONDITION: {name.upper()}   label {scored[name]['label']}")
        if recorded is None:
            unverified += 1
            print("RECONSTRUCTION, UNVERIFIED — the run recorded no prompt hash.")
        elif recorded != digest:
            print(f"** MISMATCH — recorded {recorded[:12]}, rebuilt {digest[:12]}. Skipped.")
            print("   The inputs have changed since the run. Nothing below would be real.")
            continue
        else:
            print(f"VERIFIED against the recorded prompt hash ({digest[:12]}).")

        injected = scored[name].get("injected") or []
        if injected:
            cited = scored[name].get("cited_injected") or []
            print(f"INJECTED ({len(injected)}): {', '.join(injected)}")
            print(f"CITED BY THE ANSWER: {', '.join(cited) if cited else 'none'}")
        print(f"TOKENS: {scored[name]['tokens']}")

        if full:
            print(f"\n{THIN}\nSYSTEM PROMPT\n{THIN}\n{SYSTEM}")
        print(f"\n{THIN}\nUSER PROMPT — AS SENT\n{THIN}\n{prompt}")
        print(f"{THIN}\nWHAT THE MODEL RETURNED\n{THIN}\n{scored[name]['text']}")
        if scored[name].get("unknown_handles"):
            print(f"\n** FABRICATED CITATIONS: {scored[name]['unknown_handles']}")
        print(f"\n{THIN}\nWHAT THE JUDGE SAW, AND SAID\n{THIN}")
        print(render_for_judgement(scored[name]["text"]))
        print(f"\nVERDICT: {scored[name]['label']}")
        print(f"RATIONALE: {scored[name].get('rationale')}")
    return unverified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN_PATH)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--caches", type=Path, nargs="+", default=None)
    parser.add_argument("--qid", default=None)
    parser.add_argument(
        "--flips", action="store_true", help="every question where a condition moved"
    )
    parser.add_argument("--condition", choices=(*CONDITIONS, "all"), default="all")
    parser.add_argument(
        "--full", action="store_true", help="print the system prompt too, once per condition"
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if args.caches is None:
        from audit_correctness import CACHE_DIR as E007_CACHE_DIR

        args.caches = [CACHE_DIR, E007_CACHE_DIR]

    rows = load_jsonl(args.run, what="E-018 run")
    labels = by_condition(rows)
    scored: dict[str, dict[str, dict]] = {}
    for row in rows:
        scored.setdefault(row["question_id"], {})[row["condition"]] = row

    if args.flips:
        wanted = flipped(labels)
    elif args.qid:
        wanted = [args.qid]
    else:
        raise SystemExit("Name a question with --qid, or pass --flips.")

    # `prepare` rebuilds every condition at the recorded seed. The placebo is
    # drawn there, so rebuilding one question in isolation would draw from a
    # different point in the sequence and produce a prompt that was never sent
    # — which the hash check would catch, but only after printing nothing.
    prepared, _ = prepare(args)
    by_qid = {row["question_id"]: row for row in prepared}
    missing = [qid for qid in wanted if qid not in by_qid]
    if missing:
        raise SystemExit(f"Not in the frozen population: {', '.join(missing)}")
    if args.limit:
        wanted = wanted[: args.limit]

    conditions = CONDITIONS if args.condition == "all" else (args.condition,)
    unverified = sum(show(by_qid[qid], scored[qid], conditions, args.full) for qid in wanted)
    print(f"\n{RULE}")
    print(f"{len(wanted)} question(s) shown.")
    if unverified:
        print(f"{unverified} condition(s) shown as unverified reconstructions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
