#!/usr/bin/env python
"""Does the judge score against the key it was given, or against Magic?

E-011 point 6, registered 2026-08-15 and amended 2026-09-10c: a judge told
to score only against the supplied key either does so or does not, and
**agreement figures cannot tell you which**. A judge and a human who share
the same Magic knowledge agree beautifully, and a judge quietly correcting
from memory systematically favours whichever arm's answers resemble what it
already believes. The only way to find out is to hand it a key a
knowledgeable reader would want to overrule.

So: a registered subset of already-judged answers is re-scored against a
**perturbed** key, and the judge passes domain blindness only if it follows
the supplied key on at least 0.90 of them.

Two directions, because one direction cannot fail a constant judge:

    A   the answer is wrong, and the key is rewritten to endorse it
        -> a key-blind judge says `correct`

    B   the answer is right, and the key is rewritten to contradict it
        -> a key-blind judge says `incorrect`

A judge that always answers `correct` passes A and fails B, and one that
always answers `incorrect` does the reverse. Only a key-following judge
passes both.

**Nothing here enters a correctness denominator.** Every perturbed item is
marked, written to its own file, and read by nothing that reports on the
arms. `build` refuses to write a perturbation identical to its real key,
because a control that changes nothing measures nothing while looking like
evidence.

**The registered subset is versioned; the perturbed text is not.** A
perturbed key is derived from a RulesGuru answer key, which this repo keeps
out of git. So the ids, directions and expected labels live in
`data/golden/key_fidelity_ids.json`, where anyone can check what was
registered, and the key text lives in `data/interim/`, which is gitignored.

Usage:
    python scripts/audit_key_fidelity.py build   # the worksheet, from the subset
    # ... the author writes each perturbed key and verifies it is wrong ...
    python scripts/audit_key_fidelity.py score   # one call per item
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from graphrag_mtg.evaluation.judge import (
    PERTURBED,
    Verdict,
    follows_key,
    perturbed_key,
)
from graphrag_mtg.evaluation.judge import (
    score as judge_score,
)
from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION, Correctness, rubric_hash

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: The registered subset — ids, direction and expected label. Versioned.
SUBSET_PATH = Path("data/golden/key_fidelity_ids.json")

#: The perturbed key text. Gitignored: it is derived from licensed keys.
FIXTURE_PATH = Path("data/interim/key_fidelity.jsonl")

#: Where a run's verdicts land. `runs/` is gitignored.
VERDICTS_PATH = Path("runs/key_fidelity_verdicts.jsonl")

#: Registered in E-011 point 6. Read as a point estimate, as written, with
#: the interval printed beside it — see the 2026-09-10c amendment, which
#: records that the entry never said point or bound and does not repair it
#: after the fact.
PASS_MARK = 0.90

#: Registered in the 2026-09-10c amendment: 15 per direction.
PER_DIRECTION = 15

DIRECTIONS = {
    "A": (Correctness.INCORRECT, Correctness.CORRECT),
    "B": (Correctness.CORRECT, Correctness.INCORRECT),
}


@dataclass(frozen=True)
class Item:
    """One fixture row: a real answer, a perturbed key, and what it implies."""

    question_id: str
    direction: str
    expected: Correctness
    real_key: str
    perturbed: str
    question: str
    answer: str


def load_subset() -> list[dict]:
    if not SUBSET_PATH.exists():
        raise SystemExit(
            f"No registered subset at {SUBSET_PATH}. The subset is registered before "
            "any perturbation is written — see E-011 amendment 2026-09-10c."
        )
    return json.loads(SUBSET_PATH.read_text(encoding="utf-8"))["items"]


def load_fixture() -> dict[str, dict]:
    if not FIXTURE_PATH.exists():
        raise SystemExit(
            f"No fixture at {FIXTURE_PATH}. Run `build`, then verify every "
            "perturbation is genuinely wrong about Magic before scoring."
        )
    rows = {}
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["question_id"]] = row
    return rows


def verify(items: list[Item]) -> None:
    """Refuse a fixture that cannot measure what it claims to.

    Two checks, and the second is the one that matters. A perturbation
    identical to the real key is caught by `perturbed_key`. A perturbation
    that is *accidentally right about Magic* is not catchable here at all —
    it inverts the item's meaning while looking like a passing row — which
    is why the amendment registers author verification as part of the
    build and why `verified` must be true on every row.
    """
    for item in items:
        perturbed_key(item.real_key, item.perturbed)
        if item.expected is not DIRECTIONS[item.direction][1]:
            raise SystemExit(
                f"{item.question_id}: direction {item.direction} implies "
                f"{DIRECTIONS[item.direction][1]}, fixture says {item.expected}."
            )


def report(verdicts: list[tuple[Item, Verdict]]) -> int:
    print(f"rubric  {RUBRIC_VERSION} @ {rubric_hash()[:12]}")
    print(RULE)
    followed = [(i, v) for i, v in verdicts if follows_key(v, i.expected)]
    rate = len(followed) / len(verdicts) if verdicts else 0.0
    interval = wilson_interval(len(followed), len(verdicts))

    for direction in sorted(DIRECTIONS):
        rows = [(i, v) for i, v in verdicts if i.direction == direction]
        if not rows:
            continue
        ok = [1 for i, v in rows if follows_key(v, i.expected)]
        d_interval = wilson_interval(len(ok), len(rows))
        source, expected = DIRECTIONS[direction]
        print(
            f"  direction {direction}  (answer was {source.value}, key rewritten to imply "
            f"{expected.value})"
        )
        print(
            f"    followed the key {len(ok)}/{len(rows)} = {len(ok)/len(rows):.3f}   "
            f"[{d_interval.low:.3f}, {d_interval.high:.3f}]"
        )
        for item, verdict in rows:
            if not follows_key(verdict, item.expected):
                print(
                    f"      {item.question_id}: expected {item.expected.value}, "
                    f"judged {verdict.label.value} — {verdict.rationale[:90]}"
                )

    print(RULE)
    print(f"key fidelity {len(followed)}/{len(verdicts)} = {rate:.3f}   "
          f"[{interval.low:.3f}, {interval.high:.3f}]")
    print(f"registered pass mark {PASS_MARK:.2f}, read as the point estimate — the entry")
    print("never said point or bound, and it is not repaired after seeing the rate.")

    if rate >= PASS_MARK:
        print("\nPASSES domain blindness as registered.")
        print("The interval's lower bound is printed above; it is what a reader")
        print("should weigh, and on a 30-item fixture it is well below the mark.")
        return 0
    print("\nFAILS domain blindness. The judge scored against its own knowledge of")
    print("Magic on the items above, which no agreement figure can detect and which")
    print("systematically favours whichever arm resembles what it already believes.")
    print("Every correctness figure produced by this judge inherits that.")
    return 1


def question_and_key(question_id: str) -> tuple[str, str]:
    """The question and its real key, from the gitignored fetch caches."""
    for cache in (Path("data/interim/e007_cache"), Path("data/interim/golden_cache")):
        path = cache / f"{question_id}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            question = payload.get("questionSimple") or payload.get("question") or ""
            key = payload.get("answerSimple") or payload.get("answer") or ""
            if question and key:
                return question, key
    for name in ("ids_v0.jsonl", "authored_v0.jsonl", "definitions_v0.jsonl"):
        for line in (Path("data/golden") / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") == question_id and row.get("question") and row.get("answer"):
                    return row["question"], row["answer"]
    raise SystemExit(f"No question and key found for {question_id}.")


#: The human worksheets this subset was drawn from, and the answers each one
#: was labelled over. Named rather than globbed: a question can appear in
#: four arms' answer files, and picking the wrong one would perturb a key
#: against prose no human ever labelled — an item that looks identical and
#: measures a different thing.
WORKSHEETS = (
    Path("data/golden/p6_correctness_m1.json"),
    Path("data/golden/p6_correctness_b2_m1.json"),
)


def answer_sources() -> dict[str, Path]:
    """Which answers file each labelled question was judged from."""
    mapping: dict[str, Path] = {}
    for worksheet in WORKSHEETS:
        sheet = json.loads(worksheet.read_text(encoding="utf-8"))
        paths = [Path(str(source).replace("\\", "/")) for source in sheet["sources"]]
        for qid in sheet["labels"]:
            for path in paths:
                if path.exists() and qid in _ids_in(path):
                    mapping[qid] = path
                    break
    return mapping


def _ids_in(path: Path) -> set[str]:
    return {
        json.loads(line)["question_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def answer_text(question_id: str, sources: dict[str, Path]) -> str:
    """The generated answer this item perturbs the key against."""
    path = sources.get(question_id)
    if path is None:
        raise SystemExit(
            f"{question_id} is in the registered subset but in none of the worksheets' "
            "answer sources. The subset is drawn from labelled answers only."
        )
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("question_id") == question_id:
                return row.get("text") or row.get("rendered") or ""
    raise SystemExit(f"No generated answer found for {question_id} in {path}.")


def build(args: argparse.Namespace) -> int:
    """Write the worksheet the perturbations are authored into.

    The row carries everything needed to write one and nothing that
    decides it: the question, the real key, the answer, the direction and
    the label a key-following judge must produce. `perturbed` is empty and
    `verified` is false, and `score` refuses on either — because the
    property that makes this control work, *the perturbed key is genuinely
    wrong about Magic*, is not mechanically checkable and must be asserted
    by someone who knows the rule.
    """
    subset = load_subset()
    sources = answer_sources()
    existing = {}
    if FIXTURE_PATH.exists():
        existing = load_fixture()

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = kept = 0
    with FIXTURE_PATH.open("w", encoding="utf-8") as handle:
        for entry in subset:
            qid = entry["question_id"]
            prior = existing.get(qid, {})
            if prior.get(PERTURBED) and not args.reset:
                handle.write(json.dumps(prior, ensure_ascii=False) + "\n")
                kept += 1
                continue
            question, key = question_and_key(qid)
            row = {
                "question_id": qid,
                "direction": entry["direction"],
                "expected": entry["expected"],
                "question": question,
                "real_key": key,
                "answer": answer_text(qid, sources),
                PERTURBED: "",
                "verified": False,
                "instruction": (
                    "Rewrite real_key so it ENDORSES what the answer claims"
                    if entry["direction"] == "A"
                    else "Rewrite real_key so it CONTRADICTS what the answer claims"
                )
                + ". The rewritten key must be wrong about Magic — that is the whole "
                "control — and must still read as an answer key.",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(f"{FIXTURE_PATH}: {written} row(s) to author, {kept} kept.")
    print("The file is gitignored: it holds licensed key text.")
    print("\nFill `perturbed` on every row, then set `verified` to true only on rows")
    print("you have checked are genuinely wrong about Magic. `score` refuses otherwise.")
    return 0


def score(args: argparse.Namespace) -> int:
    subset = load_subset()
    fixture = load_fixture()
    items = []
    for entry in subset:
        row = fixture.get(entry["question_id"])
        if row is None:
            raise SystemExit(f"{entry['question_id']} is registered but not in the fixture.")
        if not row.get("verified"):
            raise SystemExit(
                f"{entry['question_id']} is unverified. A perturbation that is "
                "accidentally right about Magic measures the opposite of what the "
                "item intends and looks like a passing row."
            )
        items.append(
            Item(
                question_id=entry["question_id"],
                direction=entry["direction"],
                expected=Correctness(entry["expected"]),
                real_key=row["real_key"],
                perturbed=row[PERTURBED],
                question=row["question"],
                answer=row["answer"],
            )
        )
    verify(items)

    from graphrag_mtg.extraction.llm import LlmClient

    client = LlmClient(model=args.model, max_tokens=args.max_tokens, temperature=0.0)
    print(f"{len(items)} perturbed item(s), one call each, model {client.model}.")
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    verdicts = []
    VERDICTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with VERDICTS_PATH.open("w", encoding="utf-8") as handle:
        for item in items:
            verdict = judge_score(
                item.question_id,
                item.question,
                item.answer,
                item.perturbed,
                lambda system, prompt: client.complete_text(prompt, system=system),
                model=client.model,
            )
            verdicts.append((item, verdict))
            handle.write(
                json.dumps(
                    {
                        "question_id": item.question_id,
                        "direction": item.direction,
                        "expected": item.expected.value,
                        "label": verdict.label.value,
                        "rationale": verdict.rationale,
                        "model": verdict.model,
                        "rubric_version": verdict.rubric_version,
                        "rubric_hash": verdict.rubric_hash,
                        PERTURBED: True,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"wrote {VERDICTS_PATH}\n")
    return report(verdicts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    builder = sub.add_parser("build", help="write the worksheet perturbations are authored into")
    builder.add_argument(
        "--reset",
        action="store_true",
        help="discard perturbations already written; without it they are kept",
    )
    builder.set_defaults(func=build)

    scorer = sub.add_parser("score", help="judge the fixture and report key fidelity")
    scorer.add_argument("--model", default=None, help="defaults to LLM_MODEL")
    scorer.add_argument("--max-tokens", type=int, default=400)
    scorer.add_argument("--dry-run", action="store_true", help="count the calls, send none")
    scorer.set_defaults(func=score)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
