#!/usr/bin/env python
"""E-010 — what else came with it: the precision side of retrieval.

Entity recall is `|gold ∩ retrieved| / |gold|`, so a spurious entity **cannot
lower it**. E-006 read 1.000 with three linking defects present and 1.000 with
them fixed. The headline metric of Phase 4 is structurally incapable of seeing
noise, and E-001 compares a graph arm against a retriever whose failure mode is
*bringing too much* — so without a precision measure the head-to-head turns on
which system retrieves **more**, not which retrieves **better**.

Two instruments, because 20 development questions cannot do this job alone
(amendment 2026-08-15b item 6):

    proxy    (b) deterministic, no annotator, no blinding problem: retrieved
             rule-number count, context tokens, and the share of retrieved
             rule numbers present in `gold_cr_rules`, per question per arm.
    build/   (a) the human relevance pass, pooled across arms and blinded —
    label        and the blinding is **measured**, not asserted.

**Precision is computed at rule-number granularity** (item 1). A window
containing the gold rule and four irrelevant ones scores 1 relevant item while
the graph returning those same five as five items scores 1/5 — the same
unit-size defect E-001 already fixed for recall. A retrieved unit is decomposed
into the CR rule numbers it contains, and relevance is judged per number.

**A budget-normalised figure is reported alongside** (item 2): relevant tokens
over total context tokens, which is what survives E-001's token parity.

**Blinding is normalised and then measured** (item 4). Arm A names cards by
oracle UUID and the graph arms by name; `glossary` appears only in A, and
`keyword` and `legality` only in the graph arms; every graph item carries
`via {template}: {path}`. All of that is stripped or mapped to a common form.
Residual tells are expected to remain, which is exactly why a seeded 20%
subsample asks the annotator to **guess the arm before labelling relevance**.
Above 0.70 accuracy the blind claim is withdrawn and the comparison is
reported as unblinded.

Usage:
    python scripts/run_e010.py proxy            # free, runs now
    python scripts/run_e010.py build --per-question 4
    python scripts/run_e010.py show
    python scripts/run_e010.py guess <slot> <A|graph>
    python scripts/run_e010.py label <slot> <relevant|irrelevant>
    python scripts/run_e010.py report
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from graphrag_mtg.evaluation.metrics import wilson_interval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: Versioned: the seeded draw is the registered sample. Gitignored sibling
#: carries the item text, which is derived from licensed sources.
SAMPLE = Path("data/golden/e010_sample.json")
ITEMS = Path("data/interim/e010_items.jsonl")
LABELS = Path("data/interim/e010_labels.jsonl")

ARMS = {
    "A": Path("runs/e001_A-hybrid_retrieval_dev.jsonl"),
    "B": Path("runs/e001_B_retrieval_dev.jsonl"),
    "C": Path("runs/e001_C-vector-hybrid-routed_retrieval_dev.jsonl"),
}

#: The annotator guesses between these, not between the three arms: B and C
#: share a retrieval core and telling them apart is not what blinding is for.
GUESSES = ("A", "graph")

RULE_NUMBER = re.compile(r"\b(\d{3}\.\d+[a-z]?)\b")

#: Kinds mapped to a shared vocabulary. `glossary` is arm A's name for a
#: definitional entry and `keyword` is the graph arms' name for the same
#: thing; leaving them apart hands the annotator the arm for free.
KIND_MAP = {"glossary": "term", "keyword": "term"}


def gold_rules() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(Path("data/golden").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") and row.get("gold_cr_rules"):
                    found.setdefault(row["id"], [str(r) for r in row["gold_cr_rules"]])
    return found


def covers(want: str, key: str) -> bool:
    return key == want or key.startswith(want) or want.startswith(key)


def rows_for(arm: str) -> dict[str, dict]:
    return {
        json.loads(line)["question_id"]: json.loads(line)
        for line in ARMS[arm].read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def rule_numbers(item: dict) -> list[str]:
    """The CR rule numbers a retrieved unit contains.

    Amendment item 1: the unit of precision is the rule number, not the
    retrieved passage, or the two arms are graded on different denominators
    for identical content.
    """
    if item["kind"] == "rule":
        found = {item["key"], *RULE_NUMBER.findall(item.get("text") or "")}
        return sorted(n for n in found if RULE_NUMBER.fullmatch(n))
    return sorted(set(RULE_NUMBER.findall(item.get("text") or "")))


def proxy(args: argparse.Namespace) -> int:
    """Part (b): deterministic, no annotator, no blinding problem."""
    gold = gold_rules()
    print("E-010 (b) — deterministic proxy. No annotator, no model call.")
    print("Registered to run on the E-001 evaluation run; on the dev split it is")
    print("a dress-rehearsal figure and is labelled one.")
    print(RULE)
    for arm in ARMS:
        rows = rows_for(arm)
        hits = total = tokens = items = 0
        per_question = []
        for qid, row in rows.items():
            if qid not in gold:
                continue
            numbers = {n for item in row["evidence"] for n in rule_numbers(item)}
            relevant = {n for n in numbers if any(covers(w, n) for w in gold[qid])}
            hits += len(relevant)
            total += len(numbers)
            tokens += row.get("tokens") or 0
            items += len(row["evidence"])
            if numbers:
                per_question.append(len(relevant) / len(numbers))
        # Amendment item 2, and it is not a footnote: the rule-number figure
        # alone flatters whichever arm retrieves few rules. Arm A's payload is
        # 90% cards and rulings, so a denominator of rule numbers only asks
        # "of the few rules it did bring, how many were gold" and ignores
        # everything else it charged the budget for.
        relevant_tokens = total_tokens = 0
        for qid, row in rows.items():
            if qid not in gold:
                continue
            for item in row["evidence"]:
                size = len(" ".join((item.get("text") or "").split()).split())
                total_tokens += size
                numbers = rule_numbers(item)
                if numbers and any(covers(w, n) for n in numbers for w in gold[qid]):
                    relevant_tokens += size
        interval = wilson_interval(hits, total) if total else None
        print(f"  arm {arm}")
        print(f"    retrieved rule numbers {total}, of which in gold: {hits}")
        if interval:
            print(f"    rule-number precision {hits}/{total} = {hits/total:.3f} "
                  f"[{interval.low:.3f}, {interval.high:.3f}]")
        print(f"    mean per-question precision {sum(per_question)/len(per_question):.3f} "
              f"over {len(per_question)} question(s)")
        print(f"    evidence items {items}, context tokens {tokens}")
        print(f"    **token-normalised** {relevant_tokens}/{total_tokens} = "
              f"{(relevant_tokens/total_tokens if total_tokens else 0):.3f}"
              "   <- the figure invariant to unit size")
    print(RULE)
    print("`gold_cr_rules` is a lower bound on relevance: a rule can be useful")
    print("without being in the key. This proxy therefore **understates** precision")
    print("for every arm, and is comparable across arms rather than absolute.")
    return 0


def render(item: dict) -> str:
    """The item as the annotator sees it: text, and nothing that names the arm.

    Stripped: `template`, `path`, handle syntax, and the kind vocabulary that
    only one arm uses. Card identifiers are normalised to the name both arms
    can be made to share — arm A carries it at the head of its text, the graph
    arms carry it as the key.
    """
    text = " ".join((item.get("text") or "").split())
    kind = KIND_MAP.get(item["kind"], item["kind"])
    if kind == "rule":
        return f"[rule {item['key']}] {text}"
    if kind == "card":
        return f"[card] {text}"
    if kind == "ruling":
        return f"[ruling] {text}"
    if kind == "term":
        return f"[term] {text}"
    return f"[{kind}] {text}"


def build(args: argparse.Namespace) -> int:
    gold = gold_rules()
    rng = random.Random(args.seed)
    pool: list[dict] = []
    for arm in ARMS:
        for qid, row in rows_for(arm).items():
            if qid not in gold:
                continue
            evidence = list(row["evidence"])
            rng.shuffle(evidence)
            for item in evidence[: args.per_question]:
                pool.append(
                    {
                        "question_id": qid,
                        "arm": arm,
                        "kind": KIND_MAP.get(item["kind"], item["kind"]),
                        "rule_numbers": rule_numbers(item),
                        "tokens": len(" ".join((item.get("text") or "").split()).split()),
                        "rendered": render(item),
                    }
                )
    rng.shuffle(pool)
    for index, entry in enumerate(pool):
        entry["slot"] = f"s{index:04d}"

    # The blinding subsample: seeded, 20%, and drawn before any label exists.
    guess_slots = sorted(rng.sample([e["slot"] for e in pool], max(1, len(pool) // 5)))

    SAMPLE.write_text(
        json.dumps(
            {
                "purpose": "E-010 (a): the registered seeded sample, ids only.",
                "seed": args.seed,
                "per_question_per_arm": args.per_question,
                "n": len(pool),
                "arms": sorted(ARMS),
                "blinding_subsample": guess_slots,
                "blind_claim_withdrawn_above": 0.70,
                "slots": [
                    {"slot": e["slot"], "question_id": e["question_id"], "arm": e["arm"]}
                    for e in pool
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    ITEMS.parent.mkdir(parents=True, exist_ok=True)
    with ITEMS.open("w", encoding="utf-8") as handle:
        for entry in pool:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"{SAMPLE}: {len(pool)} slot(s) — versioned, ids and arms only.")
    print(f"{ITEMS}: the rendered text — gitignored, it is derived from licensed sources.")
    print(f"blinding subsample: {len(guess_slots)} slot(s), drawn at seed {args.seed}")
    print(f"\nper arm: {dict(Counter(e['arm'] for e in pool))}")
    print(f"per kind: {dict(Counter(e['kind'] for e in pool))}")
    return 0


def _labels() -> dict[str, dict]:
    if not LABELS.exists():
        return {}
    return {
        json.loads(line)["slot"]: json.loads(line)
        for line in LABELS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _save(rows: dict[str, dict]) -> None:
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with LABELS.open("w", encoding="utf-8") as handle:
        for slot in sorted(rows):
            handle.write(json.dumps(rows[slot], ensure_ascii=False) + "\n")


def question_and_key(qid: str) -> tuple[str, str]:
    """The question and its answer key.

    The key is shown because the registered metric is relevance "judged
    against the question **and its answer key**". Without it the annotator is
    judging relevance to a question whose answer they are reconstructing, and
    two readers would reconstruct differently — which is the instrument
    instability E-011a already measured on a different label.
    """
    for cache in (Path("data/interim/e007_cache"), Path("data/interim/golden_cache")):
        path = cache / f"{qid}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            question = payload.get("questionSimple") or payload.get("question") or ""
            key = payload.get("answerSimple") or payload.get("answer") or ""
            if question and key:
                return question, key
    for name in sorted(Path("data/golden").glob("*.jsonl")):
        for line in name.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") == qid and row.get("question"):
                    return row["question"], row.get("answer") or ""
    return "", ""


def question_text(qid: str) -> str:
    for cache in (Path("data/interim/e007_cache"), Path("data/interim/golden_cache")):
        path = cache / f"{qid}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = payload.get("questionSimple") or payload.get("question") or ""
            if text:
                return text
    for name in sorted(Path("data/golden").glob("*.jsonl")):
        for line in name.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") == qid and row.get("question"):
                    return row["question"]
    return ""


def show(args: argparse.Namespace) -> int:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    items = {
        json.loads(line)["slot"]: json.loads(line)
        for line in ITEMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    done = _labels()
    pending = [s["slot"] for s in sample["slots"] if s["slot"] not in done]
    if args.slot:
        pending = [args.slot]
    if not pending:
        print("Every slot is labelled. Run `report`.")
        return 0

    needs_guess = set(sample["blinding_subsample"])
    for slot in pending[: args.limit]:
        item = items[slot]
        print(RULE)
        print(f"{slot}   question {item['question_id']}")
        question, key = question_and_key(item["question_id"])
        print(f"\nQUESTION\n  {question}")
        print(f"\nANSWER KEY\n  {' '.join(key.split())[:700] or '(none recorded)'}")
        if slot in needs_guess and not done.get(slot, {}).get("guess"):
            print(f"\n  ** blinding subsample — `guess {slot} <A|graph>` BEFORE labelling **")
        print(f"\nITEM\n  {item['rendered'][:900]}")
    print(RULE)
    print(f"{len([s for s in sample['slots'] if s['slot'] not in done])} slot(s) left.")
    print("  label <slot> <relevant|irrelevant>   — does this help answer the question?")
    return 0


def guess(args: argparse.Namespace) -> int:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if args.slot not in set(sample["blinding_subsample"]):
        raise SystemExit(f"{args.slot} is not in the blinding subsample; nothing to guess.")
    rows = _labels()
    row = rows.setdefault(args.slot, {"slot": args.slot})
    if row.get("relevance"):
        raise SystemExit(
            f"{args.slot} is already labelled. The guess is recorded **before** the "
            "relevance judgement or it measures nothing."
        )
    row["guess"] = args.arm
    _save(rows)
    print(f"{args.slot} guess -> {args.arm}")
    return 0


def label(args: argparse.Namespace) -> int:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    rows = _labels()
    if args.slot in set(sample["blinding_subsample"]) and not rows.get(args.slot, {}).get("guess"):
        raise SystemExit(
            f"{args.slot} is in the blinding subsample and has no arm guess. "
            "Guess first — afterwards the guess is contaminated by having read the item "
            "for relevance."
        )
    row = rows.setdefault(args.slot, {"slot": args.slot})
    row["relevance"] = args.relevance
    _save(rows)
    print(f"{args.slot} -> {args.relevance}   ({len(sample['slots']) - len(rows)} left)")
    return 0


def report(args: argparse.Namespace) -> int:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    items = {
        json.loads(line)["slot"]: json.loads(line)
        for line in ITEMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = _labels()
    labelled = {s: r for s, r in rows.items() if r.get("relevance")}
    if not labelled:
        raise SystemExit("Nothing labelled yet.")

    print(f"E-010 (a) — {len(labelled)} of {len(sample['slots'])} slot(s) labelled")
    print(RULE)

    # Blinding first: a comparison read before its own blinding check is a
    # comparison the reader cannot weigh.
    guessed = [
        (r["guess"], "A" if items[s]["arm"] == "A" else "graph")
        for s, r in rows.items()
        if r.get("guess")
    ]
    if guessed:
        right = sum(1 for g, truth in guessed if g == truth)
        interval = wilson_interval(right, len(guessed))
        print(f"  blinding: {right}/{len(guessed)} = {right/len(guessed):.3f} "
              f"[{interval.low:.3f}, {interval.high:.3f}]")
        if right / len(guessed) > sample["blind_claim_withdrawn_above"]:
            print("  ABOVE 0.70 — the blind claim is withdrawn and everything below is")
            print("  reported as an unblinded comparison, per the registered rule.")
        else:
            print("  at or below 0.70 — the blind claim stands.")
    else:
        print("  blinding: no guesses recorded yet.")
    print(RULE)

    by_arm: dict[str, list[int]] = defaultdict(list)
    tokens: dict[str, list[int]] = defaultdict(list)
    for slot, row in labelled.items():
        arm = items[slot]["arm"]
        hit = 1 if row["relevance"] == "relevant" else 0
        by_arm[arm].append(hit)
        tokens[arm].append(items[slot]["tokens"] * hit)
    for arm in sorted(by_arm):
        hits, n = sum(by_arm[arm]), len(by_arm[arm])
        interval = wilson_interval(hits, n)
        total_tokens = sum(items[s]["tokens"] for s in labelled if items[s]["arm"] == arm)
        print(f"  arm {arm}   precision {hits}/{n} = {hits/n:.3f} "
              f"[{interval.low:.3f}, {interval.high:.3f}]")
        print(f"    token-normalised {sum(tokens[arm])}/{total_tokens} = "
              f"{(sum(tokens[arm])/total_tokens if total_tokens else 0):.3f}")
    print(RULE)
    print("Independent intervals are not the comparison. The design is paired —")
    print("the same questions in every arm — and the registered analysis is a")
    print("cluster bootstrap over questions. Per-stratum figures are unpowered")
    print("by construction and labelled so.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("proxy", help="(b) deterministic precision proxy")
    p.set_defaults(func=proxy)

    b = sub.add_parser("build", help="(a) draw and blind the seeded sample")
    b.add_argument("--per-question", type=int, default=4, help="items per arm per question")
    b.add_argument("--seed", type=int, default=20260911)
    b.set_defaults(func=build)

    s = sub.add_parser("show", help="one unlabelled slot")
    s.add_argument("slot", nargs="?", default=None)
    s.add_argument("--limit", type=int, default=1)
    s.set_defaults(func=show)

    g = sub.add_parser("guess", help="record the arm guess, before labelling")
    g.add_argument("slot")
    g.add_argument("arm", choices=GUESSES)
    g.set_defaults(func=guess)

    la = sub.add_parser("label", help="record relevance")
    la.add_argument("slot")
    la.add_argument("relevance", choices=("relevant", "irrelevant"))
    la.set_defaults(func=label)

    r = sub.add_parser("report", help="precision per arm, blinding first")
    r.set_defaults(func=report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
