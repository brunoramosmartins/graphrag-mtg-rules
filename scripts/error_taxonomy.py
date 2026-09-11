#!/usr/bin/env python
"""Where did the chain break, on the answers a human said were wrong?

The judge audit produced, in passing, the number that decides whether this
system is worth showing anyone: a human read 55 answers and called 18 of
them correct. Working on the judge does not move that. Working on the
pipeline does, and this is the instrument for deciding *which part* of the
pipeline.

**It spends nothing and invents nothing.** Every input already exists — the
frozen human labels, the retrieval row with its outcome, note, templates,
evidence and token accounting, and the generated answer with the handles it
cited. `build` assembles them per question and leaves `stage` blank; the
reading is done by a person, and `report` counts what they wrote.

The stages are the pipeline's own, in the order a question passes through
them, so a count here names a component rather than a mood:

    linking      the question's entities were not resolved, or the wrong
                 ones were — nothing downstream can recover from this
    routing      entities resolved, but the plan sent the question to the
                 wrong half: traversals that cannot reach the rule, or the
                 text retriever where a walk existed
    evidence     the plan was right and the graph did not hold the edge —
                 the `CITES_RULE` withdrawal lives here
    budget       the evidence was retrieved and the token ceiling dropped
                 or capped the part the answer needed
    generation   everything needed was in the context and the model still
                 wrote the wrong answer
    key          the answer is defensible and the answer key is wrong or
                 answers a different question

`key` is not a pipeline stage and is there on purpose: a taxonomy with no
way to say "the instrument was wrong" pushes those cases into whichever
stage is nearest, and the count that gets acted on is then wrong twice.

Usage:
    python scripts/error_taxonomy.py build     # the worksheet
    python scripts/error_taxonomy.py show      # one case, with its evidence
    python scripts/error_taxonomy.py set rg-1049 evidence --why "..."
    python scripts/error_taxonomy.py report    # counts, by stage and stratum
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: Gitignored: it carries answer and key text derived from licensed sources.
WORKSHEET = Path("data/interim/error_taxonomy.jsonl")

#: The human passes whose `partial` and `incorrect` rows are the population.
WORKSHEETS = (
    Path("data/golden/p6_correctness_m1.json"),
    Path("data/golden/p6_correctness_b2_m1.json"),
)

RETRIEVAL = (
    Path("runs/e007_retrieval.jsonl"),
    Path("runs/e001_C-tfidf-routed_retrieval_dev.jsonl"),
)

STAGES = ("linking", "routing", "evidence", "budget", "generation", "key")

FAILED = ("partial", "incorrect")


def _rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        json.loads(line)["question_id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def human_labels() -> dict[str, tuple[str, Path]]:
    """Every `partial` or `incorrect` row, with the answers file it came from."""
    found: dict[str, tuple[str, Path]] = {}
    for path in WORKSHEETS:
        sheet = json.loads(path.read_text(encoding="utf-8"))
        sources = [Path(str(s).replace("\\", "/")) for s in sheet["sources"]]
        for qid, entry in sheet["labels"].items():
            label = entry.get("label") if isinstance(entry, dict) else entry
            if label in FAILED:
                for source in sources:
                    if qid in _rows(source):
                        found[qid] = (label, source)
                        break
    return found


def load_worksheet() -> dict[str, dict]:
    if not WORKSHEET.exists():
        raise SystemExit(f"No worksheet at {WORKSHEET}. Run `build` first.")
    return _rows(WORKSHEET)


def save(rows: dict[str, dict]) -> None:
    order = sorted(rows, key=lambda q: (rows[q]["stratum"] or "", q))
    with WORKSHEET.open("w", encoding="utf-8") as handle:
        for qid in order:
            handle.write(json.dumps(rows[qid], ensure_ascii=False) + "\n")


def build(args: argparse.Namespace) -> int:
    existing = _rows(WORKSHEET)
    retrieval: dict[str, dict] = {}
    for path in RETRIEVAL:
        retrieval.update(_rows(path))

    rows: dict[str, dict] = {}
    missing = []
    for qid, (label, source) in human_labels().items():
        answer = _rows(source)[qid]
        got = retrieval.get(qid)
        if got is None:
            missing.append(qid)
            continue
        prior = existing.get(qid, {})
        rows[qid] = {
            "question_id": qid,
            "human_label": label,
            "stratum": got.get("stratum") or answer.get("stratum"),
            "outcome": got.get("outcome"),
            "note": got.get("note"),
            "templates_run": got.get("templates_run"),
            "evidence_kinds": sorted({e["kind"] for e in got.get("evidence", [])}),
            "evidence_n": len(got.get("evidence", [])),
            "capped": got.get("capped"),
            "dropped": got.get("dropped"),
            "tokens": got.get("tokens"),
            "cited": answer.get("unknown_handles") is not None
            and got.get("citations"),
            "answer": answer.get("text") or answer.get("rendered") or "",
            "context": got.get("context", ""),
            # Filled by a person.
            "stage": prior.get("stage", ""),
            "why": prior.get("why", ""),
        }

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    save(rows)
    done = sum(1 for r in rows.values() if r["stage"])
    print(f"{WORKSHEET}: {len(rows)} failed answer(s), {done} already classified.")
    print("The file is gitignored: it carries answer and key text.")
    if missing:
        print(f"\n{len(missing)} labelled answer(s) have no retrieval row and are not "
              f"in the worksheet: {', '.join(sorted(missing)[:6])}")
        print("A case whose retrieval was never recorded cannot be attributed to a")
        print("stage, and guessing would put a count behind a guess.")
    return 0


def show(args: argparse.Namespace) -> int:
    rows = load_worksheet()
    pending = [q for q in rows if not rows[q]["stage"]]
    if args.question_id:
        pending = [args.question_id]
    if not pending:
        print("Every case is classified. Run `report`.")
        return 0

    for qid in pending[: args.limit]:
        row = rows[qid]
        print(RULE)
        print(f"{qid}   human said {row['human_label']}   stratum {row['stratum']}")
        print(f"  outcome     {row['outcome']}")
        print(f"  note        {row['note']}")
        print(f"  templates   {row['templates_run']}")
        print(f"  evidence    {row['evidence_n']} item(s), kinds {row['evidence_kinds']}")
        print(f"  budget      {row['tokens']} tokens, capped {row['capped']}, "
              f"dropped {row['dropped']}")
        print(f"\nANSWER\n  {' '.join(row['answer'].split())[:900]}")
    print(RULE)
    print(f"{len([q for q in rows if not rows[q]['stage']])} case(s) left.")
    print(f"  set <id> <{'|'.join(STAGES)}> --why '...'")
    return 0


def record(args: argparse.Namespace) -> int:
    rows = load_worksheet()
    if args.question_id not in rows:
        raise SystemExit(f"{args.question_id} is not in the worksheet.")
    if args.stage not in STAGES:
        raise SystemExit(f"{args.stage} is not one of {', '.join(STAGES)}.")
    rows[args.question_id]["stage"] = args.stage
    rows[args.question_id]["why"] = args.why
    save(rows)
    left = sum(1 for r in rows.values() if not r["stage"])
    print(f"{args.question_id} -> {args.stage}. {left} case(s) left.")
    return 0


def report(args: argparse.Namespace) -> int:
    from collections import Counter

    rows = load_worksheet()
    classified = {q: r for q, r in rows.items() if r["stage"]}
    if not classified:
        raise SystemExit("Nothing classified yet.")

    print(f"{len(classified)} of {len(rows)} failed answer(s) classified.")
    print(RULE)
    by_stage = Counter(r["stage"] for r in classified.values())
    for stage in STAGES:
        n = by_stage.get(stage, 0)
        if n:
            share = n / len(classified)
            print(f"  {stage:<12} {n:3d}   {share:.1%}")
    print(RULE)
    print("by stratum:")
    # The e007 retrieval rows predate the `stratum` field, so most of this
    # population has none. An absent stratum is printed as one rather than
    # dropped: a breakdown that silently omits rows is a breakdown that
    # reads as covering everything.
    strata = Counter(r["stratum"] or "(not recorded)" for r in classified.values())
    for stratum, count in strata.most_common():
        stages = Counter(
            r["stage"]
            for r in classified.values()
            if (r["stratum"] or "(not recorded)") == stratum
        )
        detail = ", ".join(f"{s} {c}" for s, c in stages.most_common())
        print(f"  {stratum:<24} {count:3d}   {detail}")
    print(RULE)
    print("A count here names a component to repair. It does not say the repair is")
    print("cheap, and a stage carrying one case is not a finding.")
    if len(classified) < len(rows):
        print(f"\n{len(rows) - len(classified)} case(s) unclassified — the shares above")
        print("are over what has been read, not over the failures.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    builder = sub.add_parser("build", help="assemble the worksheet from existing runs")
    builder.set_defaults(func=build)

    shower = sub.add_parser("show", help="one unclassified case with its retrieval record")
    shower.add_argument("question_id", nargs="?", default=None)
    shower.add_argument("--limit", type=int, default=1)
    shower.set_defaults(func=show)

    setter = sub.add_parser("set", help="record which stage broke")
    setter.add_argument("question_id")
    setter.add_argument("stage", choices=STAGES)
    setter.add_argument("--why", default="", help="one line; what the record shows")
    setter.set_defaults(func=record)

    reporter = sub.add_parser("report", help="counts by stage and stratum")
    reporter.set_defaults(func=report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
