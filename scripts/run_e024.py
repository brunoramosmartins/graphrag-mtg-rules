#!/usr/bin/env python
"""E-024: can the governing rule be named from the question alone?

Phase 9 measured that the governing CR rule does not reach the context on
`interaction_multihop` — 2 of 22 for the graph arm, 2 of 22 for the vector arm,
3 of 22 for the hybrid — and closed every repair it had registered. Then
counting turned up the thing nobody had written down.

`docs/annotation-guide.md`, step 4: *"Cite the most specific rule that carries
the answer"*, with the annotator holding the question **and the key**.
**`gold_cr_rules` is a function of the answer.** "Retrieval does not reach the
target" and "the target is not determinable from the question" are different
claims, and Phase 9 measured the first while assuming the second was false.

This entry tests the second, for under US$ 0.05.

    question_only      the question text, nothing else
    question_and_key   the question and the answer key

The control is the design. The annotator did the key-given task by hand, so
that arm should be near-perfect; without it a null on `question_only` cannot
be told apart from a task that is impossible as posed. If the control fails
too, the entry reports **that** and does not report the other number.

**Chapter, not the lettered leaf.** The leaf is what an annotator chose knowing
the answer. A chapter is what a router would need, and retrieving a chapter's
subtree is something this graph already does.

**No result is read against zero.** Counted before the run: 17 distinct gold
chapters over 22 questions, majority baseline **6/22 = 0.273**. The run refuses
if the data no longer produces those figures.

Usage:
    python scripts/run_e024.py run --dry-run
    python scripts/run_e024.py run
    python scripts/run_e024.py score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_correctness import CACHE_DIR as E007_CACHE_DIR
from audit_correctness import question_and_key
from e001_inspect import artefacts, gold_rules, load_jsonl
from run_eval import CACHE_DIR, GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

ARM = "B"
SPLIT = "eval"
STRATUM = "interaction_multihop"
RUN_PATH = Path("runs/e024.jsonl")

CONDITIONS = ("question_only", "question_and_key")

#: Three per condition, because E-020 measured that one sample is not a
#: reading. At temperature 0 this is a decoding-noise measurement and it is
#: reported as one.
SAMPLES = 3

#: Recorded so the run is reproducible; it names nothing else.
RANDOM_SEED = 20260914

#: Counted 2026-09-14 and frozen here. A first draft of the entry said nine
#: chapters from memory. If the golden set moves, these stop matching and the
#: run refuses rather than quietly measuring a different population.
EXPECTED_QUESTIONS = 22
EXPECTED_CHAPTERS = 17
EXPECTED_BASELINE = (6, 22)

PROMPT_VERSION = "e024-c1"

SYSTEM = """You identify which part of the Magic: The Gathering Comprehensive
Rules governs a rules question.

Reply with EXACTLY one line, in this form and nothing else:

CHAPTER: 613

The number is the three-digit rule chapter — 613 for layers, 603 for triggered
abilities, 400 for zones, and so on. Do not give a subrule, do not explain, do
not add any other line.

If you are unsure, still name the single chapter you consider most likely. An
empty or hedged reply is scored the same as a wrong one, so guessing costs you
nothing and silence costs the measurement.
"""

_CHAPTER = re.compile(r"CHAPTER:\s*(\d{3})", re.IGNORECASE)


def chapter_of(rule: str) -> str:
    """The three-digit chapter a rule number belongs to."""
    return rule.split(".")[0]


def parse_chapter(text: str) -> str | None:
    """The chapter the model named, or None when the reply had no marker.

    `None` is kept distinct from a wrong chapter all the way to the report.
    E-014 measured what happens otherwise: a missing marker scores as a wrong
    answer and a format failure is reported as a reasoning failure.
    """
    match = _CHAPTER.search(text)
    return match.group(1) if match else None


def build_prompt(question: str, key: str | None) -> str:
    """The question, and the key only in the control condition."""
    if key is None:
        return f"## QUESTION\n{question}\n"
    return f"## QUESTION\n{question}\n\n## ANSWER\n{key}\n"


def population(args: argparse.Namespace) -> list[dict]:
    """The 22 questions, their keys, and their gold chapters.

    Raises:
        SystemExit: if the counts no longer match what the entry registered.
            A population that drifted is a different experiment under the same
            id, and this is the check that makes that loud.
    """
    retrieval_path, _, _ = artefacts(ARM, SPLIT)
    records = [
        row
        for row in load_jsonl(retrieval_path, what="retrieval")
        if row["stratum"] == STRATUM
    ]
    wanted = gold_rules(args.golden)
    rows = []
    for record in records:
        qid = record["question_id"]
        if qid not in wanted:
            continue
        question, key = question_and_key(qid, args.caches, args.golden)
        rows.append(
            {
                "question_id": qid,
                "question": question,
                "key": key,
                "gold_chapters": sorted({chapter_of(rule) for rule in wanted[qid]}),
            }
        )

    chapters = Counter(ch for row in rows for ch in row["gold_chapters"])
    top, hits = chapters.most_common(1)[0]
    if (len(rows), len(chapters)) != (EXPECTED_QUESTIONS, EXPECTED_CHAPTERS):
        raise SystemExit(
            f"The population no longer matches what E-024 registered: "
            f"{len(rows)} question(s) over {len(chapters)} chapter(s), "
            f"registered {EXPECTED_QUESTIONS} over {EXPECTED_CHAPTERS}.\n"
            f"Something moved in the golden set. Find out what before running."
        )
    if (hits, len(rows)) != EXPECTED_BASELINE:
        raise SystemExit(
            f"The majority baseline is now {hits}/{len(rows)} on chapter {top}, "
            f"registered {EXPECTED_BASELINE[0]}/{EXPECTED_BASELINE[1]}.\n"
            f"The comparator this entry reads against was fixed before the run."
        )
    return rows[: args.limit] if args.limit else rows


def baseline(rows: list[dict]) -> tuple[str, float]:
    """The modal gold chapter and the rate a model naming it always would get."""
    chapters = Counter(ch for row in rows for ch in row["gold_chapters"])
    top, hits = chapters.most_common(1)[0]
    return top, hits / len(rows)


def run(args: argparse.Namespace) -> int:
    """Both conditions, three samples each, interleaved by question."""
    rows = population(args)
    top, rate = baseline(rows)
    print(f"E-024   arm {ARM}   split {SPLIT}   stratum {STRATUM}")
    print(f"{len(rows)} question(s), {len(CONDITIONS)} conditions, {SAMPLES} samples each")
    print(f"prompt {PROMPT_VERSION}   seed {RANDOM_SEED}")
    print(f"\nMAJORITY BASELINE, fixed before the run: chapter {top} on every "
          f"question scores {rate:.3f}")
    print("No number from this run is read against zero.")

    client = LlmClient(model=args.model, max_tokens=16, temperature=0.0)
    prompts = [
        build_prompt(row["question"], row["key"] if name == "question_and_key" else None)
        for row in rows
        for name in CONDITIONS
        for _ in range(SAMPLES)
    ]
    cost = estimate_cost(prompts, model=client.model, output_tokens_per_call=16, system=SYSTEM)
    print(f"\nestimate: {cost.n_calls} call(s), no judge, about US$ {cost.usd:.3f}")
    if args.dry_run:
        print("\nDry run: nothing was sent. Population and baseline both check out.")
        return 0
    if RUN_PATH.exists():
        raise SystemExit(f"{RUN_PATH} already exists. Move it aside to re-run.")

    written = []
    for row in rows:
        for name in CONDITIONS:
            key = row["key"] if name == "question_and_key" else None
            prompt = build_prompt(row["question"], key)
            for index in range(SAMPLES):
                text = client.complete_text(prompt, system=SYSTEM).strip()
                named = parse_chapter(text)
                written.append(
                    {
                        "question_id": row["question_id"],
                        "condition": name,
                        "sample": index,
                        "named": named,
                        "raw": text,
                        "gold_chapters": row["gold_chapters"],
                        "hit": named in row["gold_chapters"] if named else False,
                        "model": client.model,
                        "prompt_version": PROMPT_VERSION,
                        "arm": ARM,
                        "split": SPLIT,
                    }
                )
            got = [r["named"] for r in written[-SAMPLES:]]
            print(f"  {row['question_id']:<30}{name:<18}{got} gold {row['gold_chapters']}")

    RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_PATH.open("w", encoding="utf-8") as handle:
        for record in written:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(written)} row(s) -> {RUN_PATH}")
    print("Next: python scripts/run_e024.py score")
    return 0


def score(args: argparse.Namespace) -> int:
    """The two conditions against the registered baseline, and the branches."""
    rows = load_jsonl(args.run, what="E-024 run")
    by_condition: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        by_condition.setdefault(row["condition"], {}).setdefault(
            row["question_id"], []
        ).append(row)

    # Recomputed from the run's own rows rather than from the golden set, so
    # scoring a saved run does not silently read it against a baseline the
    # data has moved to since.
    chapters = Counter(
        ch
        for samples in by_condition[CONDITIONS[0]].values()
        for ch in samples[0]["gold_chapters"]
    )
    top, hits = chapters.most_common(1)[0]
    n = len(by_condition[CONDITIONS[0]])
    rate = hits / n

    print(f"E-024 — {n} question(s), {SAMPLES} samples per condition\n")
    print(f"{THIN}\nMAJORITY BASELINE: chapter {top} every time = {rate:.3f} ({hits}/{n})")

    print(f"\n{THIN}\nACCURACY — a question counts as a hit when the MAJORITY of its")
    print("samples name a gold chapter. The per-sample rate is printed beside it.")
    results = {}
    for name in CONDITIONS:
        per_question = []
        unparsed = 0
        per_sample = 0
        total = 0
        for qid, samples in sorted(by_condition.get(name, {}).items()):
            hits_here = sum(1 for s in samples if s["hit"])
            unparsed += sum(1 for s in samples if s["named"] is None)
            per_sample += hits_here
            total += len(samples)
            per_question.append(hits_here * 2 > len(samples))
        wins = sum(per_question)
        interval = wilson_interval(wins, len(per_question))
        results[name] = (wins, len(per_question))
        print(
            f"  {name:<20}{wins:>3}/{len(per_question)}   {wins / len(per_question):.3f}  "
            f"[{interval.low:.3f}, {interval.high:.3f}]   per-sample "
            f"{per_sample / total:.3f}   unparseable {unparsed}"
        )

    control_wins, control_n = results[CONDITIONS[1]]
    only_wins, only_n = results[CONDITIONS[0]]
    print(f"\n{RULE}\nVERDICT — the branches as registered")
    if control_wins / control_n < 0.80:
        print("\nBRANCH 3 — the control failed.")
        print(f"The key-given arm reached {control_wins}/{control_n}, under the 0.80 the")
        print("entry predicted for a task the annotator did by hand. The task is")
        print("ill-posed as operationalised - most likely the chapter is the wrong")
        print("granularity - and the question-only number IS NOT REPORTED.")
        return 0
    if only_wins / only_n > rate:
        print("\nBRANCH 1 — question-only clears the majority baseline.")
        print(f"{only_wins}/{only_n} against {hits}/{n}. A bridge may exist and it costs one")
        print("call. Consequence: a question-to-chapter router is registered as a front,")
        print("docs/evaluation.md's scope statement gains a premature notice, and Phase")
        print("10's design is reconsidered before any curation.")
        print("\nCheck prediction 3 before acting: if the hits are the questions whose")
        print("text names the mechanism, the bridge works where it is not needed.")
        return 0
    print("\nBRANCH 2 — question-only is at or below the baseline, control is not.")
    print("The governing rule is determinable FROM THE ANSWER and not from the")
    print("question. The scope statement in docs/evaluation.md stands, an extraction")
    print("programme over the CR is the only remaining path, and this is the sharpest")
    print("sentence Phase 9 produced.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    common.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    common.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    common.add_argument("--limit", type=int, default=0)
    common.add_argument("--dry-run", action="store_true", help="check and price, send nothing")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[common], help="both conditions, three samples each")
    scorer = sub.add_parser("score", parents=[common], help="the branches, against the baseline")
    scorer.add_argument("--run", type=Path, default=RUN_PATH)
    args = parser.parse_args()
    return {"run": run, "score": score}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
