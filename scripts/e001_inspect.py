#!/usr/bin/env python
"""Render what a Magic-side arm was sent, and what it actually said.

`e014_inspect.py` does this for MetaQA, and building it is what withdrew the
project's most-quoted number: the first scored case anyone rendered showed a
context that did not answer its question and a model refusing correctly, and
92% of that cell was the same. The Magic side had no equivalent, so every
figure E-001 published rests on rows nobody has opened.

Standing rule 8, adopted 2026-09-13, requires the **final prompt as sent** in
front of the reader before any comparative number is quoted. `--each` is that
rule in one command: one case per outcome category the harness distinguishes.

**Outcome categories, because `incorrect` hides four different things:**

    correct / partial / incorrect   the judge's label under the frozen rubric
    refused_by_model                the model declined with a context in hand
    refused_by_pipeline             the model was never called
    void                            the key does not answer the question asked
    unjudged                        an answer with no verdict row

`refused_by_pipeline` is tested first and deliberately. `answerer.answer`
short-circuits on any outcome that is not `RESOLVED`, and `judge.score` labels
a refusal `incorrect` without a model call — so those rows sit in the
`incorrect` bucket looking like reasoning failures. On the 42 evaluation
questions carrying gold rules, five of them are exactly that, and they carried
12, 9, 7, 5 and 28 pieces of evidence apiece. The refusal text they received
says "retrieval returned no usable evidence", which is false on all five.

**This script spends nothing and needs no graph.** `runs/e001_*_retrieval_*`
records the serialized context contemporaneously, so the prompt is rebuilt from
the record rather than re-queried — the graph cannot move underneath it.

**The rebuild is checked, not assumed.** A rebuilt prompt that quietly differs
from the one sent looks identical to a correct one, which is the failure this
project keeps paying for. Three states, and the header always says which:

    VERIFIED              the answer row carries `prompt_sha256` and it matches
    CONTEXT VERIFIED      the context matches the recorded serialization
                          byte for byte; the system prompt is named by version
                          and cannot be hashed, because E-001 predates the field
    UNVERIFIED            neither is available, and this is a reconstruction

Usage:
    python scripts/e001_inspect.py --counts
    python scripts/e001_inspect.py --arm B --each
    python scripts/e001_inspect.py --arm B --outcome refused_by_pipeline
    python scripts/e001_inspect.py --qid rg-1469
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION, render_for_judgement
from graphrag_mtg.generation.answerer import (
    PROMPT_VERSION,
    SYSTEM,
    build_prompt,
    prompt_digest,
)
from graphrag_mtg.retrieval.subgraph import serialize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_correctness import CACHE_DIR as E007_CACHE_DIR  # noqa: E402
from audit_correctness import question_and_key  # noqa: E402
from run_e007 import rebuild  # noqa: E402  sibling script; sys.path above enables it
from run_eval import CACHE_DIR, GOLDEN_DIR, NOTICE  # noqa: E402
from split_golden import QUESTION_FILES, load_questions  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

RUNS = Path("runs")

#: Ordered so a reader of `--counts` meets the judged labels first and the
#: two refusals next to each other, which is the comparison that matters.
OUTCOMES = (
    "correct",
    "partial",
    "incorrect",
    "refused_by_model",
    "refused_by_pipeline",
    "void",
    "unjudged",
)

#: `runs/e001_<slug>_answers_<split>.jsonl`, and the slug is what names an
#: arm's exact configuration — `B`, `A-hybrid`, `C-vector-hybrid-routed`.
_SLUG = re.compile(r"^e001_(?P<slug>.+)_answers_(?P<split>[a-z]+)\.jsonl$")


def outcome_of(answer: dict, verdict: dict | None) -> str:
    """Which of the seven things happened, from fields the run already writes.

    Order is load-bearing. A pipeline refusal is both `refused` and labelled
    `incorrect`, and a model refusal is labelled `incorrect` too, so testing
    the judge's label first would pool three findings into one bucket — which
    is how six of arm B's seven "refusals" read as generation failures for
    weeks.

    Args:
        answer: One row of an `e001_*_answers_*.jsonl` dump.
        verdict: The matching verdict row, or None when the answer was never
            judged.

    Returns:
        One of :data:`OUTCOMES`.
    """
    if not answer.get("generated", True):
        return "refused_by_pipeline"
    if answer.get("refused"):
        return "refused_by_model"
    if verdict is None:
        return "unjudged"
    label = verdict.get("label")
    return label if label in OUTCOMES else "unjudged"


def load_jsonl(path: Path, *, what: str) -> list[dict]:
    """Rows of a JSONL artefact, or a refusal naming what to run to get it."""
    if not path.exists():
        raise SystemExit(
            f"No {what} at {path}.\n"
            f"  `runs/` is gitignored, so this file exists only where the run "
            f"happened.\n"
            f"  Produce it with:  python scripts/run_eval.py --help"
        )
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise SystemExit(f"{path} is empty.")
    return rows


def artefacts(slug: str, split: str) -> tuple[Path, Path, Path]:
    """The three dumps one arm writes, in the order the pipeline writes them."""
    return (
        RUNS / f"e001_{slug}_retrieval_{split}.jsonl",
        RUNS / f"e001_{slug}_answers_{split}.jsonl",
        RUNS / f"e001_{slug}_verdicts_{split}.jsonl",
    )


def available(split: str) -> list[str]:
    """Arm slugs with an answers dump for this split, in filename order."""
    found = []
    for path in sorted(RUNS.glob(f"e001_*_answers_{split}.jsonl")):
        match = _SLUG.match(path.name)
        if match:
            found.append(match["slug"])
    return found


def gold_rules(golden: Path) -> dict[str, list[str]]:
    """Question id to the CR rules its key needs, from the golden set.

    The keys were written before any retriever existed, which is what makes
    them usable as a target. They are a human annotation of *which rule
    governs*, not of what it takes to answer — see E-018's fourth threat.
    """
    wanted: dict[str, list[str]] = {}
    for row in load_questions(golden, QUESTION_FILES):
        rules = row.get("gold_cr_rules") or []
        if rules:
            wanted[row["id"]] = [str(rule) for rule in rules]
    return wanted


def retrieved_rules(record: dict) -> set[str]:
    """The CR rule numbers that reached the context, from the evidence itself.

    Read off the `rule` evidence rather than regexed out of the serialized
    text: a ruling quoting `613.4b` in prose would count under a regex, and a
    figure that counts it is measuring something else. E-010 was re-derived
    this way after the first pass did exactly that.
    """
    return {item["key"] for item in record.get("evidence", ()) if item.get("kind") == "rule"}


def verification(answer: dict, record: dict, prompt: str, context: str) -> tuple[str, list[str]]:
    """How much of this prompt is a record, and how much is a reconstruction.

    Returns:
        A one-word state — ``verified``, ``context``, ``mismatch`` or
        ``unverified`` — and the lines to print under the case header.
    """
    lines: list[str] = []
    recorded_digest = answer.get("prompt_sha256")
    if recorded_digest:
        digest = prompt_digest(SYSTEM, prompt)
        if digest == recorded_digest:
            return "verified", [f"VERIFIED against the recorded prompt hash ({digest[:12]})."]
        return "mismatch", [
            f"** MISMATCH — recorded {recorded_digest[:12]}, rebuilt {digest[:12]}.",
            "   The inputs have changed since the run. Case skipped.",
        ]

    dumped = record.get("context")
    if dumped is None:
        return "unverified", [
            "RECONSTRUCTION, UNVERIFIED — this run recorded neither the prompt hash",
            "nor the serialized context. What follows is what the same inputs produce",
            "today, which is not proof it is what was sent.",
        ]
    if dumped != context:
        return "mismatch", [
            "** MISMATCH — the rebuilt context differs from the one the run dumped.",
            "   Case skipped. The evidence or the serializer has moved since the run.",
        ]

    lines.append("CONTEXT VERIFIED — byte for byte against the serialization the run")
    lines.append("dumped. The system prompt cannot be checked: this run predates")
    lines.append(f"`prompt_sha256`, and records only its version ({answer.get('prompt_version')}).")
    if answer.get("prompt_version") != PROMPT_VERSION:
        lines.append(
            f"** The module is now at {PROMPT_VERSION}. The system prompt printed below "
            "is NOT the one this answer was generated under."
        )
    return "context", lines


def counts(split: str, golden: Path, slugs: list[str]) -> int:
    """The outcome split per arm, plus the two numbers that hide inside it."""
    wanted = gold_rules(golden)
    header = "".join(f"{name.replace('refused_by_', 'ref:'):>13}" for name in OUTCOMES)
    print(f"split {split}   rubric {RUBRIC_VERSION}   prompt {PROMPT_VERSION}\n")
    print(f"{'arm':<24}{'n':>4}{header}")
    print(THIN)
    for slug in slugs:
        retrieval_path, answers_path, verdicts_path = artefacts(slug, split)
        answers = load_jsonl(answers_path, what="answers")
        verdicts = {row["question_id"]: row for row in load_jsonl(verdicts_path, what="verdicts")}
        tally = dict.fromkeys(OUTCOMES, 0)
        for row in answers:
            tally[outcome_of(row, verdicts.get(row["question_id"]))] += 1
        line = "".join(f"{tally[name]:>13}" for name in OUTCOMES)
        print(f"{slug:<24}{len(answers):>4}{line}")

        records = {row["question_id"]: row for row in load_jsonl(retrieval_path, what="retrieval")}
        carrying = [qid for qid in records if qid in wanted]
        present = [qid for qid in carrying if retrieved_rules(records[qid]) & set(wanted[qid])]
        never = [qid for qid in carrying if not _generated(answers, qid)]
        print(
            f"{'':<28}of {len(carrying)} carrying gold rules: "
            f"{len(present)} had one retrieved, {len(never)} never called the model"
        )
    print(THIN)
    print("A category with five cases or fewer is read in full (standing rule 8).")
    print("`--each` prints one case per category, with the prompt as sent.")
    return 0


def _generated(answers: list[dict], qid: str) -> bool:
    """Whether the model was called for this question. Absent rows count as no."""
    for row in answers:
        if row["question_id"] == qid:
            return bool(row.get("generated", True))
    return False


def select(
    answers: list[dict],
    verdicts: dict[str, dict],
    args: argparse.Namespace,
) -> list[dict]:
    """The rows to render, in the order the run wrote them."""
    rows = [
        row
        for row in answers
        if (not args.qid or row["question_id"] == args.qid)
        and (not args.stratum or row.get("stratum") == args.stratum)
        and (not args.fabricated or row.get("unknown_handles"))
    ]
    if args.each:
        seen: dict[str, dict] = {}
        for row in rows:
            seen.setdefault(outcome_of(row, verdicts.get(row["question_id"])), row)
        return [seen[name] for name in OUTCOMES if name in seen]
    if args.outcome != "any":
        rows = [
            row for row in rows if outcome_of(row, verdicts.get(row["question_id"])) == args.outcome
        ]
    return rows[: args.limit] if args.limit else rows


def render(args: argparse.Namespace) -> int:
    """Print each selected case: the prompt as sent, the answer, the verdict."""
    retrieval_path, answers_path, verdicts_path = artefacts(args.arm, args.split)
    records = {row["question_id"]: row for row in load_jsonl(retrieval_path, what="retrieval")}
    answers = load_jsonl(answers_path, what="answers")
    verdicts = {row["question_id"]: row for row in load_jsonl(verdicts_path, what="verdicts")}
    wanted = gold_rules(args.golden)

    chosen = select(answers, verdicts, args)
    if not chosen:
        raise SystemExit(
            f"No row matches arm={args.arm} outcome={args.outcome} "
            f"qid={args.qid or 'any'} in {answers_path}."
        )

    unverified = 0
    for row in chosen:
        qid = row["question_id"]
        record = records.get(qid)
        if record is None:
            print(f"\n{RULE}\n{qid} — answered but absent from the retrieval dump. Skipped.")
            continue
        verdict = verdicts.get(qid)
        question, key = question_and_key(qid, args.caches, args.golden)
        subgraph = rebuild(record, question)
        context = serialize(subgraph, notice=NOTICE)
        prompt = build_prompt(question, subgraph, notice=NOTICE)
        state, notes = verification(row, record, prompt, context)

        print(f"\n{RULE}")
        print(
            f"{qid}  |  arm {row.get('arm')}  {row.get('stratum')}  "
            f"{outcome_of(row, verdict).upper()}  |  {row.get('model', '?')}"
        )
        for note in notes:
            print(note)
        if state == "mismatch":
            continue
        if state == "unverified":
            unverified += 1

        needed = wanted.get(qid, [])
        if needed:
            arrived = retrieved_rules(record) & set(needed)
            print(
                f"\nGOLD CR RULES: {', '.join(needed)}  |  retrieved: "
                f"{', '.join(sorted(arrived)) or 'none'}"
            )
        print(f"RETRIEVAL: {record['outcome']}  {len(record.get('evidence', ()))} item(s)  "
              f"{record.get('tokens')} tokens  dropped {record.get('dropped')}  "
              f"capped {record.get('capped')}")
        if record.get("note"):
            print(f"NOTE: {record['note']}")

        # "As sent" is false when the model was never called, and a header
        # that says it anyway is how a reader concludes the model saw this
        # and failed. The whole script exists against that reading.
        sent = row.get("generated", True)
        banner = (
            "USER PROMPT — THE CONTEXT AS SENT"
            if sent
            else "USER PROMPT — NEVER SENT. This is what the model would have been"
            "\ngiven; the pipeline refused on the retrieval outcome above first."
        )
        print(f"\n{THIN}\nSYSTEM PROMPT ({row.get('prompt_version')})\n{THIN}\n{SYSTEM}")
        print(f"{THIN}\n{banner}\n{THIN}")
        print(prompt)

        print(f"{THIN}\nWHAT THE MODEL RETURNED\n{THIN}")
        if not sent:
            print("(nothing — the model was never called. The line below is the")
            print(" pipeline's own refusal string, not a completion.)\n")
        print(row.get("text", ""))
        if row.get("unknown_handles"):
            print(f"\n** FABRICATED CITATIONS: {row['unknown_handles']}")
            print("   Handles cited that the subgraph does not contain.")

        print(f"\n{THIN}\nWHAT THE JUDGE SAW, AND SAID\n{THIN}")
        print(f"## QUESTION\n{question}\n")
        print(f"## ANSWER (handles stripped)\n{render_for_judgement(row.get('text', ''))}\n")
        print(f"## KEY\n{key}\n")
        if verdict is None:
            print("VERDICT: none — this answer was never judged.")
        else:
            print(f"VERDICT: {verdict['label']}   rubric {verdict.get('rubric_version')} "
                  f"@ {str(verdict.get('rubric_hash'))[:12]}   prompt {verdict.get('prompt_version')}")
            print(f"RATIONALE: {verdict.get('rationale')}")

    if unverified:
        print(f"\n{RULE}")
        print(f"{unverified} case(s) shown as unverified reconstructions.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="eval", help="eval or dev")
    parser.add_argument("--arm", default="B", help="the slug in the filename, e.g. B, A-hybrid")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    parser.add_argument("--counts", action="store_true", help="the outcome split per arm")
    parser.add_argument(
        "--each",
        action="store_true",
        help="one case per outcome category — standing rule 8 in one command",
    )
    parser.add_argument("--qid", default=None)
    parser.add_argument("--stratum", default=None)
    parser.add_argument("--outcome", choices=(*OUTCOMES, "any"), default="any")
    parser.add_argument(
        "--fabricated", action="store_true", help="only answers citing a handle that is not there"
    )
    parser.add_argument("--limit", type=int, default=2, help="0 for every match")
    args = parser.parse_args()

    if args.counts:
        slugs = available(args.split)
        if not slugs:
            raise SystemExit(f"No e001 answers dump for split {args.split} under {RUNS}/.")
        return counts(args.split, args.golden, slugs)
    return render(args)


if __name__ == "__main__":
    raise SystemExit(main())
