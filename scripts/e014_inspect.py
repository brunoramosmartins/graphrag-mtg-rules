#!/usr/bin/env python
"""Render what the generator actually saw, and what it actually said.

E-012 concluded that the bottleneck is depth, and every figure supporting that
is an aggregate. The claim underneath it — *the model was handed a clean chain
and still failed* — had never been rendered for a single question, because the
run records the outcome and not the input: no prompt, no evidence list, no raw
completion. A claim nobody has looked at is a claim nobody has checked.

This script rebuilds the exact context for a scored cell and prints it beside
the answer key, the chain that was guaranteed present, and what the model
returned. It spends nothing: the split is frozen, the graph is loaded, and the
reduction rule is deterministic, so the prompt is reproducible from the row.

**The reconstruction is verified, not assumed.** A rebuilt prompt that happens
to differ from the one sent would make every reading here fiction, and it would
look identical to a correct one. When the row carries `prompt_sha256` this
script checks it and refuses the case on a mismatch; when it does not — runs
written before that field existed, E-012's among them — it says so in the
header rather than letting a reconstruction pass as a record.

Outcomes are separated because "incorrect" hides three different failures:

    refused   the model declined, with the chain in front of it
    format    it answered without the ANSWER: marker, so nothing parsed
    wrong     it committed to an entity and the entity was wrong

Only the third is a reasoning error. At three hops the first outnumbers it
three to one, which is not what "cannot chain three facts" describes.

Usage:
    python scripts/e014_inspect.py --hops 3 --outcome refused --limit 3
    python scripts/e014_inspect.py --qid <id> --k 16
    python scripts/e014_inspect.py --counts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from graphrag_mtg.evaluation import metaqa
from graphrag_mtg.evaluation.metaqa import HOPS
from graphrag_mtg.generation.answerer import build_prompt
from graphrag_mtg.graph.connection import driver_session, metaqa_target
from graphrag_mtg.retrieval.subgraph import DEFAULT_TOKEN_BUDGET, Subgraph

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e002 import (  # sibling script; the sys.path line above enables it
    DEFAULT_FRONTIER_CAP,
    E002_KIND_CAP,
    PROMPTS,
    _require_bolt,
    collect,
)
from run_e012 import METAQA_DIR, PROMPT_KEY, SPLITS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

OUTCOMES = ("correct", "refused", "format", "wrong")


def outcome_of(row: dict) -> str:
    """Which of the four things happened, from the fields a run already writes.

    `parse_prediction` returns None on a reply that skipped the ANSWER: marker,
    and `hits_at_1(None, ...)` is False — so a format failure lands in the same
    `correct: false` bucket as a wrong entity and a refusal. The three are
    different findings and are separated here rather than pooled.
    """
    if row.get("correct"):
        return "correct"
    if row.get("refused"):
        return "refused"
    if not row.get("predicted"):
        return "format"
    return "wrong"


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"No answers at {path}.")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise SystemExit(f"{path} is empty.")
    return rows


def counts(rows: list[dict]) -> int:
    """The four-way split per cell. Exploratory: it re-cuts a finished run."""
    print("EXPLORATORY — a re-cut of a completed run, not the registered contrast.")
    print("Conditioning on 'the model committed' is post-selection: it may be")
    print("declining the hard questions, so the committed subset is easier.\n")
    sizes = sorted({row["k"] for row in rows}, key=lambda k: (k == 0, k))
    header = "".join(f"{name:>12}" for name in OUTCOMES)
    print(f"{'k':<8}{'hop':<7}{'n':>6}{header}{'refuse rate':>14}")
    print(THIN)
    for k in sizes:
        for hops in HOPS:
            cell = [row for row in rows if row["hops"] == hops and row["k"] == k]
            if not cell:
                continue
            tally = {name: 0 for name in OUTCOMES}
            for row in cell:
                tally[outcome_of(row)] += 1
            label = "untrimmed" if k == 0 else str(k)
            line = "".join(f"{tally[name]:>12}" for name in OUTCOMES)
            rate = tally["refused"] / len(cell)
            print(f"{label:<8}{f'{hops}-hop':<7}{len(cell):>6}{line}{rate:>13.1%}")
    print(THIN)
    return 0


def show(args: argparse.Namespace) -> int:
    rows = load_rows(args.answers)
    wanted = [
        row
        for row in rows
        if (not args.qid or row["qid"] == args.qid)
        and (not args.hops or row["hops"] == args.hops)
        and row["k"] == args.k
        and (args.outcome == "any" or outcome_of(row) == args.outcome)
    ]
    if not wanted:
        raise SystemExit(
            f"No row matches hops={args.hops or 'any'} k={args.k} "
            f"outcome={args.outcome} in {args.answers}."
        )
    wanted = wanted[: args.limit]
    by_qid = {row["qid"]: row for row in wanted}

    _, _, split_path = SPLITS[args.split]
    questions = [q for q in metaqa.load_frozen(split_path, args.metaqa_dir) if q.qid in by_qid]
    if len(questions) != len(by_qid):
        missing = sorted(set(by_qid) - {q.qid for q in questions})
        raise SystemExit(f"{len(missing)} scored qid(s) are not in the {args.split} split: {missing[:3]}")

    system, version = PROMPTS[PROMPT_KEY]
    unverified = 0

    with driver_session(_require_bolt(metaqa_target())) as session:
        for question in questions:
            row = by_qid[question.qid]
            subgraph, _ = collect(
                session,
                question,
                frontier_cap=DEFAULT_FRONTIER_CAP,
                kind_cap=E002_KIND_CAP,
                token_budget=DEFAULT_TOKEN_BUDGET,
            )
            chain = metaqa.answer_path(subgraph.evidence, question.seed, question.answers)
            if chain is None:
                print(f"\n{RULE}\n{question.qid} — the answer is not reachable now.")
                print("This question was excluded from the run, or the KB changed.")
                continue
            kept = subgraph.evidence if row["k"] == 0 else metaqa.reduce_to_k(
                subgraph.evidence, chain, row["k"]
            )
            cell = Subgraph(question=question.text, evidence=list(kept))
            prompt = build_prompt(question.text, cell)
            digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            recorded = row.get("prompt_sha256")

            print(f"\n{RULE}")
            print(f"{question.qid}  |  {row['hops']}-hop  k={row['k']}  "
                  f"{outcome_of(row).upper()}  |  {row.get('model', '?')}  prompt {version}")
            if recorded is None:
                unverified += 1
                print("RECONSTRUCTION, UNVERIFIED — this run predates `prompt_sha256`.")
                print("What follows is what the same inputs produce today, which is not")
                print("proof it is what was sent. Treat it as strong evidence, not a record.")
            elif recorded != digest:
                print(f"** MISMATCH — recorded {recorded[:12]}, rebuilt {digest[:12]}.")
                print("   The context has changed since the run. Case skipped.")
                continue
            else:
                print(f"VERIFIED against the recorded prompt hash ({digest[:12]}).")

            print(f"\n{THIN}\nGOLD ANSWER(S): {', '.join(question.answers)}")
            print(f"SEED: {question.seed}")
            print(f"CHAIN GUARANTEED PRESENT IN THE CONTEXT BELOW ({len(chain)} step(s)):")
            for step in chain:
                print(f"  [{step.key}] {step.text}")
                print(f"      {step.path}")
            print(f"\n{THIN}\nSYSTEM PROMPT\n{THIN}\n{system}")
            print(f"\n{THIN}\nUSER PROMPT ({len(cell.evidence)} evidence items)\n{THIN}")
            print(prompt)
            print(f"{THIN}\nWHAT THE MODEL RETURNED\n{THIN}")
            raw = row.get("raw")
            if raw is None:
                print("(not recorded — this run predates the `raw` field)")
                print(f"parsed prediction: {row['predicted']!r}")
                print(f"refused: {row.get('refused')}   correct: {row['correct']}")
            else:
                print(raw)
                print(f"\nparsed prediction: {row['predicted']!r}   correct: {row['correct']}")

    if unverified:
        print(f"\n{RULE}")
        print(f"{unverified} case(s) shown as unverified reconstructions. Runs written")
        print("from now on record `prompt_sha256` and `raw`, and this script checks them.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, default=Path("runs/e012_conf.jsonl"))
    parser.add_argument("--split", choices=sorted(SPLITS), default="conf")
    parser.add_argument("--metaqa-dir", type=Path, default=METAQA_DIR)
    parser.add_argument("--counts", action="store_true", help="the four-way split per cell")
    parser.add_argument("--qid", default=None)
    parser.add_argument("--hops", type=int, choices=HOPS, default=0)
    parser.add_argument("--k", type=int, default=16)
    parser.add_argument("--outcome", choices=(*OUTCOMES, "any"), default="refused")
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()

    if args.counts:
        return counts(load_rows(args.answers))
    return show(args)


if __name__ == "__main__":
    raise SystemExit(main())
