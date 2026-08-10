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

SUFFICIENCY_PATH = Path("data/golden/e007_sufficiency.json")
WORKSHEET_PATH = Path("data/golden/e007_claims.jsonl")


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
