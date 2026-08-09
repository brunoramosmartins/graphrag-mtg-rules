#!/usr/bin/env python
"""E-003b: what the citation F1 gap is made of, estimated on a sample.

Exact match scores a *wrong* rule and a *differently defensible* rule
identically, so a citation F1 of 0.125 is consistent with several different
worlds and by itself names none of them. This script samples the E-003
disagreements and asks the annotator to sort each into one bucket:

    gold_right       the gold is right, the prediction is wrong  -> model error
    both_defensible  the predicted rule also governs             -> metric artifact
    gold_wrong       the gold is wrong under the annotation guide-> adjudicable
    unclear          parked, and counted, not forced

The output is four proportions with confidence intervals — not an F1, and
not a correction to one.

**This is measurement, not repair.** It changes no gold label. A sample
cannot patch a gold: a half-patched gold makes the pre- and
post-adjudication figures equally meaningless. The adjudication rule
pre-registered on 2026-08-08 still governs any actual change, including
its 10% cap, above which the registered response is to void the run and
re-annotate rather than patch.

    python scripts/adjudicate.py sample --n 40
    python scripts/adjudicate.py worksheet          # read the cases
    python scripts/adjudicate.py judge 7 both_defensible --note "704.5 also applies"
    python scripts/adjudicate.py report

`worksheet` and `judge` refuse to run until the E-003a blind second pass is
finished. That ordering is registered and binding: re-reading rulings that
were just re-litigated against the model's output is recall, not an
independent second pass, and would inflate the measured ceiling.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap
from datetime import date
from pathlib import Path

from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.evaluation.metrics import cluster_proportion_ci

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
GATED_PATH = Path("data/interim/gated_triples.annotation.jsonl")
BLIND_PATH = Path("data/interim/reannotation_draft.jsonl")
SAMPLE_PATH = Path("data/golden/disagreement_sample.json")
VERDICTS_PATH = Path("data/golden/disagreement_verdicts.jsonl")

VERDICTS = ("gold_right", "both_defensible", "gold_wrong", "unclear")
DEFAULT_N = 40
DEFAULT_SEED = 20260810

RULE = "-" * 78


def read_rows(path: Path) -> list[dict]:
    """Read a JSONL file into a list of rows."""
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def gold_citations(rows: list[dict], split: str) -> dict[str, set[str]]:
    """Reviewed citation gold per ruling. Unreviewed rows have no gold at all."""
    return {
        row["ruling_id"]: {c.get("rule_number") or c.get("rule") for c in row["cited_rules"]}
        for row in rows
        if row["split"] == split and row.get("citations_reviewed")
    }


def predicted_citations(path: Path, docs: set[str]) -> dict[str, set[str]]:
    """Gate-passing ``CITES_RULE`` edges per ruling — what reached the graph."""
    predicted: dict[str, set[str]] = {rid: set() for rid in docs}
    for triple in read_rows(path):
        if triple["edge_type"] == "CITES_RULE" and triple["source_key"] in docs:
            predicted[triple["source_key"]].add(triple["target_key"])
    return predicted


def disagreements(gold: dict[str, set[str]], predicted: dict[str, set[str]]) -> list[dict]:
    """Every false positive and false negative, one case per rule number."""
    cases: list[dict] = []
    for rid in sorted(gold):
        for number in sorted(predicted.get(rid, set()) - gold[rid]):
            cases.append({"ruling_id": rid, "kind": "fp", "rule_number": number})
        for number in sorted(gold[rid] - predicted.get(rid, set())):
            cases.append({"ruling_id": rid, "kind": "fn", "rule_number": number})
    return cases


def ceiling_is_measured(blind: Path) -> tuple[bool, str]:
    """Whether the E-003a second pass is finished, and why not if it is not."""
    if not blind.exists():
        return False, f"no blind second pass at {blind}"
    rows = read_rows(blind)
    pending = [r for r in rows if not r.get("citations_reviewed")]
    if pending:
        return False, f"{len(pending)} of {len(rows)} rulings are not re-cited yet"
    return True, ""


def require_ceiling(args: argparse.Namespace) -> bool:
    """Print the registered ordering constraint and refuse, or allow."""
    ok, why = ceiling_is_measured(args.blind)
    if ok:
        return True
    print(f"Refusing: {why}.")
    print(
        "\nE-003a (intra-annotator agreement) must be finished FIRST — the order\n"
        "is registered in experiments/registry.md. Reading these disagreements\n"
        "now would contaminate the blind second pass: re-citing a ruling you\n"
        "just re-argued against the model's output measures memory, not\n"
        "judgement, and the ceiling would come out too high.\n"
    )
    print("  python scripts/reannotate.py draw --n 20")
    print(f"  python scripts/annotation_worksheet.py --draft {args.blind} "
          "--citation-pass --needs-citations")
    print("  python scripts/reannotate.py compare")
    return False


def load_verdicts(path: Path) -> dict[int, dict]:
    """Recorded verdicts by case index; a later line supersedes an earlier one."""
    if not path.exists():
        return {}
    return {row["case"]: row for row in read_rows(path)}


def cmd_sample(args: argparse.Namespace) -> int:
    """Freeze a seeded sample of the disagreements. Reveals nothing on its own."""
    if args.sample.exists() and not args.force:
        print(f"error: {args.sample} already exists — judging may be in progress.")
        print("Pass --force to draw a new sample (this discards the frozen one).")
        return 1

    rows = read_rows(args.draft)
    gold = gold_citations(rows, args.split)
    predicted = predicted_citations(args.gated, set(gold))
    cases = disagreements(gold, predicted)
    if not cases:
        print("No disagreements — nothing to decompose.")
        return 1

    rng = random.Random(args.seed)
    drawn = sorted(
        rng.sample(cases, min(args.n, len(cases))),
        key=lambda c: (c["ruling_id"], c["kind"], c["rule_number"]),
    )
    for i, case in enumerate(drawn, start=1):
        case["case"] = i

    args.sample.parent.mkdir(parents=True, exist_ok=True)
    args.sample.write_text(
        json.dumps(
            {
                "purpose": "E-003b — composition of the citation disagreements",
                "gold": str(args.draft),
                "predictions": str(args.gated),
                "split": args.split,
                "seed": args.seed,
                "population": len(cases),
                "n": len(drawn),
                "drawn_at": date.today().isoformat(),
                "verdicts": list(VERDICTS),
                "cases": drawn,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    fp = sum(1 for c in cases if c["kind"] == "fp")
    print(f"Population: {len(cases)} disagreements ({fp} fp, {len(cases) - fp} fn).")
    print(f"Drew {len(drawn)} (seed {args.seed}) into {args.sample}.")
    ok, why = ceiling_is_measured(args.blind)
    print(
        "\nNext: `worksheet` — available once E-003a is finished."
        if ok
        else f"\nDo NOT read these yet: {why}. Finish E-003a first (registry: ordering)."
    )
    return 0


def cmd_worksheet(args: argparse.Namespace) -> int:
    """Print the unjudged cases with everything a verdict needs."""
    if not require_ceiling(args):
        return 1
    if not args.sample.exists():
        print(f"No frozen sample at {args.sample}. Run `adjudicate.py sample` first.")
        return 1

    meta = json.loads(args.sample.read_text(encoding="utf-8"))
    rows = {r["ruling_id"]: r for r in read_rows(args.draft)}
    gold = gold_citations(list(rows.values()), meta["split"])
    predicted = predicted_citations(args.gated, set(gold))
    bodies = {rule.number: rule.text for rule in parse_cr(args.cr).rules}
    judged = load_verdicts(args.verdicts)

    def body(number: str, width: int) -> str:
        return textwrap.shorten(bodies.get(number, "(not in the CR)"), width=width)

    shown = 0
    for case in meta["cases"]:
        if case["case"] in judged and not args.all:
            continue
        shown += 1
        rid = case["ruling_id"]
        side = "the SYSTEM cited it, the gold did not" if case["kind"] == "fp" else (
            "the GOLD cites it, the system did not"
        )
        print(f"\n{RULE}")
        print(f"case {case['case']}  {rid}  [{case['kind']}] rule {case['rule_number']}")
        print(f"  {side}")
        print()
        print(textwrap.fill(rows[rid]["text"], width=78))
        print()
        print(f"  gold cites:   {sorted(gold[rid]) or '[]'}")
        print(f"  system cited: {sorted(predicted.get(rid, set())) or '[]'}")
        print(f"\n  {case['rule_number']}: {body(case['rule_number'], 600)}")
        for number in sorted((gold[rid] | predicted.get(rid, set())) - {case["rule_number"]}):
            print(f"  {number}: {body(number, 400)}")
        print(
            f"\n  python scripts/adjudicate.py judge {case['case']} "
            f"<{'|'.join(VERDICTS)}> --note \"...\""
        )

    print(f"\n{RULE}")
    print(f"{shown} case(s) shown, {len(judged)} of {meta['n']} already judged.")
    print(
        "Reminder: `gold_wrong` means wrong on its own terms under\n"
        "docs/extraction-annotation-guide.md — the rule does not govern the\n"
        "question the ruling answers. 'The model disagrees' is not a reason,\n"
        "and 'both rules support it' is `both_defensible`, not `gold_wrong`."
    )
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    """Record one verdict, appended so the history is never overwritten."""
    if not require_ceiling(args):
        return 1
    if not args.sample.exists():
        print(f"No frozen sample at {args.sample}. Run `adjudicate.py sample` first.")
        return 1

    meta = json.loads(args.sample.read_text(encoding="utf-8"))
    case = next((c for c in meta["cases"] if c["case"] == args.case), None)
    if case is None:
        print(f"error: case {args.case} is not in the frozen sample (1..{meta['n']}).")
        return 1

    args.verdicts.parent.mkdir(parents=True, exist_ok=True)
    with args.verdicts.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "case": args.case,
                    "ruling_id": case["ruling_id"],
                    "kind": case["kind"],
                    "rule_number": case["rule_number"],
                    "verdict": args.verdict,
                    "note": args.note,
                    "judged_at": date.today().isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    judged = load_verdicts(args.verdicts)
    print(f"case {args.case}: {args.verdict}  ({len(judged)}/{meta['n']} judged)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Four proportions with intervals, clustered by ruling."""
    if not args.sample.exists():
        print(f"No frozen sample at {args.sample}. Run `adjudicate.py sample` first.")
        return 1
    meta = json.loads(args.sample.read_text(encoding="utf-8"))
    judged = load_verdicts(args.verdicts)

    missing = [c["case"] for c in meta["cases"] if c["case"] not in judged]
    if missing and not args.partial:
        print(f"{len(missing)} of {meta['n']} cases unjudged: {missing[:10]}")
        print("Finish them, or pass --partial to report on what is judged so far.")
        return 1

    by_ruling: dict[str, list[dict]] = {}
    for row in judged.values():
        by_ruling.setdefault(row["ruling_id"], []).append(row)
    clusters = list(by_ruling.values())
    total = sum(len(c) for c in clusters)

    print(f"E-003b — composition of {total} sampled disagreements "
          f"(of {meta['population']}), clustered over {len(clusters)} rulings.")
    print(f"  {'bucket':<18} {'n':>4}  proportion")
    for verdict in VERDICTS:
        flags = [[row["verdict"] == verdict for row in cluster] for cluster in clusters]
        interval = cluster_proportion_ci(flags)
        count = sum(1 for row in judged.values() if row["verdict"] == verdict)
        print(f"  {verdict:<18} {count:>4}  {interval}")

    for kind, label in (("fp", "false positives"), ("fn", "false negatives")):
        subset = [row for row in judged.values() if row["kind"] == kind]
        if subset:
            print(f"\n  among {len(subset)} {label}:")
            for verdict in VERDICTS:
                n = sum(1 for row in subset if row["verdict"] == verdict)
                print(f"    {verdict:<18} {n:>4}")

    wrong = sum(1 for row in judged.values() if row["verdict"] == "gold_wrong")
    print(
        f"\n`gold_wrong` is {wrong}/{total} of the sampled disagreements. This is an\n"
        "estimate of how often the gold is wrong WHERE IT DISAGREES, not of how\n"
        "much of the gold is wrong — and it licenses no edit. Any change to a\n"
        "label goes through the adjudication rule registered 2026-08-08."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--gated", type=Path, default=GATED_PATH)
    parser.add_argument("--blind", type=Path, default=BLIND_PATH)
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--verdicts", type=Path, default=VERDICTS_PATH)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    draw = sub.add_parser("sample", help="freeze a seeded sample of the disagreements")
    draw.add_argument("--n", type=int, default=DEFAULT_N)
    draw.add_argument("--seed", type=int, default=DEFAULT_SEED)
    draw.add_argument("--split", choices=("dev", "annotation"), default="annotation")
    draw.add_argument("--force", action="store_true")
    draw.set_defaults(func=cmd_sample)

    sheet = sub.add_parser("worksheet", help="read the sampled cases")
    sheet.add_argument("--all", action="store_true", help="include already-judged cases")
    sheet.set_defaults(func=cmd_worksheet)

    verdict = sub.add_parser("judge", help="record one verdict")
    verdict.add_argument("case", type=int)
    verdict.add_argument("verdict", choices=VERDICTS)
    verdict.add_argument("--note", type=str, default="")
    verdict.set_defaults(func=cmd_judge)

    out = sub.add_parser("report", help="proportions with intervals")
    out.add_argument("--partial", action="store_true", help="report before every case is judged")
    out.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
