#!/usr/bin/env python
"""E-007's audit harness: sufficiency first, segmentation second, score last.

The order is the measurement. Each command refuses to run before the one
it depends on has finished, because every shortcut here is a way to let
the result decide the method:

    sufficiency init    worksheet of retrieved subgraphs, before generating
    sufficiency freeze  labels locked with a hash — generation may now run
    segment             citation-stripped sentences, frozen with a hash
    report              coverage, support, refusals, with their guards

`segment` refuses while sufficiency is unfrozen, mirroring how
`adjudicate.py` refuses to show a disagreement before the ceiling exists.
Reading a generated answer before the sufficiency labels are frozen voids
the run, and nothing downstream can detect that afterwards — so the tool
makes the ordering awkward to break rather than trusting memory.

Usage:
    python scripts/audit_answers.py sufficiency init --retrieval runs/e007_retrieval.jsonl
    python scripts/audit_answers.py sufficiency freeze
    python scripts/audit_answers.py segment --answers runs/e007_answers.jsonl
    python scripts/audit_answers.py report
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import asdict
from pathlib import Path

from graphrag_mtg.evaluation.claims import (
    ClaimRow,
    Failure,
    Label,
    Sufficiency,
    Support,
    classify_refusals,
    coverage,
    failure_counts,
    segment_answer,
    support_clusters,
    worksheet_hash,
)
from graphrag_mtg.evaluation.metrics import cluster_proportion_ci, rule_of_three_upper

# Question and answer text carry characters a default Windows console cannot
# encode; force UTF-8 so the worksheet is readable rather than mojibake.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SUFFICIENCY_PATH = Path("data/golden/e007_sufficiency.json")
WORKSHEET_PATH = Path("data/golden/e007_claims.jsonl")
RETRIEVAL_PATH = Path("runs/e007_retrieval.jsonl")
CACHE_DIR = Path("data/interim/e007_cache")
SPLIT_PATH = Path("data/golden/e007_split.json")

#: E-007's pre-registered floor: below this many answerable audit questions
#: there is no coverage figure worth reporting, so the pool is topped up
#: before anything is generated. Registered before the labels existed.
CONTINGENCY_FLOOR = 12


def wrap(text: str) -> str:
    return textwrap.fill(text, width=76, initial_indent="  ", subsequent_indent="  ")


# ─────────────────────────────────────────────────────────────────────────────
# Sufficiency — labelled before any answer is read, then frozen
# ─────────────────────────────────────────────────────────────────────────────


def load_sufficiency(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"No sufficiency file at {path}. Run `sufficiency init` on the retrieval "
            "output first — it must exist before any answer is generated."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def require_frozen(path: Path) -> dict:
    """Refuse to proceed while sufficiency labels can still move.

    An unfrozen label is a label that can follow the result. This is the
    same guard `adjudicate.require_ceiling()` applies for E-003a, and for
    the same reason: the ordering is the only thing making the refusal
    rule non-circular.
    """
    meta = load_sufficiency(path)
    if not meta.get("frozen"):
        raise SystemExit(
            f"{path} is not frozen. Label every question, then run "
            "`sufficiency freeze`. Generating answers before that voids the run."
        )
    return meta


def sufficiency_init(args: argparse.Namespace) -> int:
    """Write one row per retrieved subgraph, unlabelled, for the author to fill."""
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to overwrite labels.")
    rows = [json.loads(line) for line in args.retrieval.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = {
        row["question_id"]: {
            "outcome": row.get("outcome", ""),
            "evidence": len(row.get("citations", [])),
            "label": "",
        }
        for row in rows
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"frozen": False, "labels": labels}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(labels)} unlabelled row(s) to {args.out}.")
    print("Label each with sufficient | partial | insufficient against the RulesGuru key,")
    print("then run `sufficiency freeze`. Do not generate an answer before that.")
    return 0


RULE = "-" * 78

#: What the sufficiency label means. Printed with every question so the
#: judgement is made against a written standard rather than a remembered one.
SUFFICIENCY_CRIB = """\
  Could a human derive the RulesGuru answer from THIS EVIDENCE ALONE?

  sufficient    yes — everything the answer turns on is here
  partial       some of it is here; an honest answer would have to say what
                is missing
  insufficient  no — the evidence cannot support the answer

  Judge the evidence against the answer, not against your own knowledge of
  Magic. "I know the rule, so it is fine" is the failure this label exists
  to prevent.

  The `cited rules present` line is an aid, not the rule: the subgraph may
  carry a different rule that still supports the answer, and it may carry
  the cited rule in a form that does not."""


def cached_question(question_id: str, cache: Path) -> dict:
    path = cache / f"{question_id}.json"
    if not path.exists():
        raise SystemExit(f"No cached text for {question_id} at {path}. Re-run the draw.")
    return json.loads(path.read_text(encoding="utf-8"))


def retrieval_index(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"No retrieval dump at {path}. Run `run_e007.py retrieve` first.")
    return {
        json.loads(line)["question_id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def render_sufficiency(
    question_id: str,
    row: dict,
    payload: dict,
    record: dict,
    *,
    context_lines: int,
    position: str = "",
) -> str:
    """One question, its judge-curated answer, and what retrieval actually got."""
    cites = [str(r) for r in payload.get("citedRules", [])]
    keys = {item["key"] for item in record.get("evidence", [])}
    present = [rule for rule in cites if rule in keys]
    context = record.get("context", "").splitlines()
    shown = context[:context_lines]

    lines = [
        RULE,
        f"{question_id}  {position}".rstrip(),
        f"  outcome: {record.get('outcome')}   evidence: {len(record.get('evidence', []))} items"
        f"   tokens: {record.get('tokens')}",
        "",
        "  QUESTION",
        wrap(payload.get("questionSimple") or payload.get("question", "")),
        "",
        "  ANSWER (RulesGuru, judge-curated)",
        wrap(payload.get("answerSimple", "") or "—"),
        f"  cited rules: {', '.join(cites) or 'none'}",
        f"  cited rules present in the subgraph: {', '.join(present) or 'NONE'}",
        "",
        f"  RETRIEVED CONTEXT ({len(context)} lines"
        + (f", showing {len(shown)} — pass --full for all)" if len(shown) < len(context) else ")"),
    ]
    lines += [f"  {line}" for line in shown] or ["  (empty)"]
    lines += [
        "",
        SUFFICIENCY_CRIB,
        "",
        f"  decided: {row.get('label') or '—'}",
        f"  -> python scripts/audit_answers.py sufficiency set {question_id} <label>",
    ]
    return "\n".join(lines)


def sufficiency_show(args: argparse.Namespace) -> int:
    """Print subgraphs to judge. Reads only; `set` is what writes."""
    meta = load_sufficiency(args.out)
    if meta.get("frozen") and not args.force:
        print(f"{args.out} is frozen — showing read-only, nothing here can change a label.")
    records = retrieval_index(args.retrieval)
    labels = meta["labels"]

    if args.id:
        chosen = [args.id] if args.id in labels else []
        if not chosen:
            raise SystemExit(f"{args.id} is not in {args.out}.")
    elif args.all:
        chosen = list(labels)
    else:
        chosen = [q for q, row in labels.items() if not (row.get("label") or "").strip()]
        if not chosen:
            print("Every subgraph is labelled. Next: `sufficiency freeze`.")
            return 0
        chosen = chosen[: args.count]

    done = sum(1 for row in labels.values() if (row.get("label") or "").strip())
    for i, question_id in enumerate(chosen, start=1):
        print(
            render_sufficiency(
                question_id,
                labels[question_id],
                cached_question(question_id, args.cache_dir),
                records[question_id],
                context_lines=10_000 if args.full else args.context_lines,
                position=f"[{i} of {len(chosen)} shown; {done}/{len(labels)} done]",
            )
        )
    print(RULE)
    return 0


def sufficiency_set(args: argparse.Namespace) -> int:
    """Record one sufficiency label, validated, without hand-editing JSON."""
    meta = load_sufficiency(args.out)
    if meta.get("frozen"):
        raise SystemExit(
            f"{args.out} is frozen. Labels cannot move after freezing — that is the "
            "guarantee the refusal rule rests on. If the freeze was a mistake, say so "
            "in the decision journal and re-run the whole labelling pass."
        )
    if args.question_id not in meta["labels"]:
        raise SystemExit(f"{args.question_id} is not in {args.out}.")
    previous = meta["labels"][args.question_id].get("label") or ""
    meta["labels"][args.question_id]["label"] = args.label
    args.out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    done = sum(1 for row in meta["labels"].values() if (row.get("label") or "").strip())
    note = f" (was {previous})" if previous and previous != args.label else ""
    print(f"{args.question_id}: {args.label}{note}   [{done}/{len(meta['labels'])} done]")
    return 0


def sufficiency_status(args: argparse.Namespace) -> int:
    """How many are labelled, the mix, and whether the contingency fires."""
    meta = load_sufficiency(args.out)
    labels = meta["labels"]
    dev: set[str] = set()
    if args.split.exists():
        dev = set(json.loads(args.split.read_text(encoding="utf-8"))["dev_ids"])

    counts: dict[str, int] = {}
    audit_answerable = 0
    undecided: list[str] = []
    for question_id, row in labels.items():
        value = (row.get("label") or "").strip()
        if not value:
            undecided.append(question_id)
            continue
        counts[value] = counts.get(value, 0) + 1
        if question_id not in dev and value in (
            Sufficiency.SUFFICIENT.value,
            Sufficiency.PARTIAL.value,
        ):
            audit_answerable += 1

    print(f"{len(labels) - len(undecided)}/{len(labels)} labelled   frozen: {meta.get('frozen')}")
    print(f"  mix: {dict(sorted(counts.items()))}")
    if undecided:
        print(f"  left: {', '.join(undecided[:12])}{' ...' if len(undecided) > 12 else ''}")
        return 0

    # E-007's pre-registered contingency, checked by the tool rather than
    # recalled: below 12 answerable audit questions there is no coverage
    # figure worth reporting, and finding that out after generating would
    # leave only bad options.
    print(f"\n  audit questions labelled sufficient or partial: {audit_answerable}")
    if audit_answerable < CONTINGENCY_FLOOR:
        print(
            f"  BELOW THE REGISTERED FLOOR OF {CONTINGENCY_FLOOR}. E-007 says to top up the "
            "pool under the same filters and exclusions, label the new questions, and "
            "only then generate."
        )
    else:
        print(f"  at or above the registered floor of {CONTINGENCY_FLOOR} — generation may proceed.")
    return 0


def sufficiency_freeze(args: argparse.Namespace) -> int:
    meta = load_sufficiency(args.out)
    if meta.get("frozen"):
        print(f"Already frozen: {meta.get('hash', '')[:12]}")
        return 0
    valid = {s.value for s in Sufficiency}
    missing = [q for q, row in meta["labels"].items() if row.get("label") not in valid]
    if missing:
        print(f"{len(missing)} question(s) still unlabelled or invalid:")
        for question in missing[:10]:
            print(f"  {question}")
        raise SystemExit("Every question needs a label before the file can be frozen.")
    payload = "\n".join(f"{q}|{row['label']}" for q, row in sorted(meta["labels"].items()))
    meta["frozen"] = True
    meta["hash"] = worksheet_hash([ClaimRow("sufficiency", 0, payload)])
    args.out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in meta["labels"].values():
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    print(f"Frozen {len(meta['labels'])} label(s): {counts}")
    print(f"hash {meta['hash']}")
    print("Record that hash in the run log. Generation may now run.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Segmentation — mechanical, on citation-stripped text, hashed
# ─────────────────────────────────────────────────────────────────────────────


def segment(args: argparse.Namespace) -> int:
    require_frozen(args.sufficiency)
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to re-segment over labels.")

    answers = [
        json.loads(line)
        for line in args.answers.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows: list[ClaimRow] = []
    for answer in answers:
        # Boundaries fall where they fall in the citation-free text; the
        # `cited` flag comes from the same chunk, so the two can never
        # misalign. See `claims.segment_answer`.
        for i, (sentence, cited) in enumerate(segment_answer(answer.get("text", ""))):
            rows.append(
                ClaimRow(
                    question_id=answer["question_id"],
                    index=i,
                    sentence=sentence,
                    cited=cited,
                )
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = asdict(row)
            payload["label"] = row.label.value
            payload["support"] = row.support.value
            payload["failure"] = row.failure.value if row.failure else None
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    digest = worksheet_hash(rows)
    print(f"Segmented {len(answers)} answer(s) into {len(rows)} row(s) -> {args.out}")
    print(f"hash {digest}")
    print("Record that hash in the run log NOW, before labelling anything.")
    print("Label every row factual | non_factual under docs/claim-annotation-guide.md.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Report — the guards are the point
# ─────────────────────────────────────────────────────────────────────────────


def load_rows(path: Path) -> list[ClaimRow]:
    if not path.exists():
        raise SystemExit(f"No worksheet at {path}. Run `segment` first.")
    rows: list[ClaimRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        rows.append(
            ClaimRow(
                question_id=raw["question_id"],
                index=raw["index"],
                sentence=raw["sentence"],
                cited=raw.get("cited", False),
                label=Label(raw.get("label") or Label.UNLABELLED.value),
                support=Support(raw.get("support") or Support.NOT_APPLICABLE.value),
                failure=Failure(raw["failure"]) if raw.get("failure") else None,
                comment=raw.get("comment", ""),
            )
        )
    return rows


def report(args: argparse.Namespace) -> int:
    meta = require_frozen(args.sufficiency)
    rows = load_rows(args.worksheet)

    unlabelled = [row for row in rows if row.label is Label.UNLABELLED]
    if unlabelled:
        print(f"{len(unlabelled)} of {len(rows)} row(s) still unlabelled — partial report.\n")

    print(f"worksheet hash {worksheet_hash(rows)}")
    print(f"sufficiency hash {meta.get('hash', '')}\n")

    result = coverage(rows)
    print(str(result))
    if result.voided:
        print(
            f"  VOID: exclusions above {int(100 * 0.20)}% mean this figure is measuring the "
            "segmentation, not the answers."
        )
    elif result.rate == 1.0 and result.clusters:
        # The E-003b trap: a bootstrap over a unanimous sample resamples to
        # itself and prints [1.000, 1.000], which reads as certainty.
        bound = rule_of_three_upper(result.clusters)
        print(
            f"  unanimous — report the rule-of-three bound, not an interval: the "
            f"per-question uncited-claim rate is at most {bound:.3f} (95%) over "
            f"{result.clusters} cluster(s)."
        )

    clusters = support_clusters(rows)
    if clusters:
        interval = cluster_proportion_ci(clusters)
        print(
            f"\nsupport {interval.point:.3f} [{interval.low:.3f}, {interval.high:.3f}] "
            f"over {interval.n_docs} cluster(s), {sum(len(c) for c in clusters)} cited claim(s)"
        )
        if interval.n_docs < 10:
            print("  fewer than 10 clusters — a description, not an estimate.")
        print("  no pass threshold: the pre-committed reading is the shuffled-citation control.")
        counts = failure_counts(rows)
        if counts:
            print(f"  failures: {counts}")
    else:
        print("\nsupport: no cited factual claims judged yet.")

    if args.answers and args.answers.exists():
        refused = {
            json.loads(line)["question_id"]: json.loads(line).get("refused", False)
            for line in args.answers.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        sufficiency = {q: Sufficiency(row["label"]) for q, row in meta["labels"].items()}
        refusals = classify_refusals(refused, sufficiency)
        print(f"\n{refusals}")
        if refusals.blocks_dod:
            print("  Phase 5 DoD BLOCKED: refusing where the evidence was present.")
            for question in refusals.over_refusal:
                print(f"    {question}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    suff = sub.add_parser("sufficiency", help="label subgraphs before generating")
    suff_sub = suff.add_subparsers(dest="stage", required=True)
    init = suff_sub.add_parser("init")
    init.add_argument("--retrieval", type=Path, required=True)
    init.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=sufficiency_init)
    freeze = suff_sub.add_parser("freeze")
    freeze.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    freeze.set_defaults(func=sufficiency_freeze)

    shower = suff_sub.add_parser("show", help="question, judge answer, retrieved context")
    shower.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    shower.add_argument("--retrieval", type=Path, default=RETRIEVAL_PATH)
    shower.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    shower.add_argument("--id", help="one question by id")
    shower.add_argument("--all", action="store_true")
    shower.add_argument("--next", action="store_true", help="the next unlabelled (default)")
    shower.add_argument("--count", type=int, default=1)
    shower.add_argument("--context-lines", type=int, default=40)
    shower.add_argument("--full", action="store_true", help="print the whole context")
    shower.add_argument("--force", action="store_true")
    shower.set_defaults(func=sufficiency_show)

    setter = suff_sub.add_parser("set", help="record one sufficiency label")
    setter.add_argument("question_id")
    setter.add_argument("label", choices=[s.value for s in Sufficiency])
    setter.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    setter.set_defaults(func=sufficiency_set)

    status = suff_sub.add_parser("status", help="mix so far, and the contingency check")
    status.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    status.add_argument("--split", type=Path, default=SPLIT_PATH)
    status.set_defaults(func=sufficiency_status)

    seg = sub.add_parser("segment", help="split answers into claim rows")
    seg.add_argument("--answers", type=Path, required=True)
    seg.add_argument("--out", type=Path, default=WORKSHEET_PATH)
    seg.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    seg.add_argument("--force", action="store_true")
    seg.set_defaults(func=segment)

    rep = sub.add_parser("report", help="coverage, support and refusals")
    rep.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    rep.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    rep.add_argument("--answers", type=Path, default=Path("runs/e007_answers.jsonl"))
    rep.set_defaults(func=report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
