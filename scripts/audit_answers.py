#!/usr/bin/env python
"""E-007's audit harness: sufficiency first, segmentation second, score last.

The order is the measurement. Each command refuses to run before the one
it depends on has finished, because every shortcut here is a way to let
the result decide the method:

    sufficiency init    worksheet of retrieved subgraphs, before generating
    sufficiency freeze  labels locked with a hash — generation may now run
    segment             citation-stripped sentences, frozen with a hash
    claims show/set     each sentence beside the evidence it cites
    control build       the same claims, citations permuted — judged blind
    report              coverage, support, refusals, with their guards

`segment` refuses while sufficiency is unfrozen, mirroring how
`adjudicate.py` refuses to show a disagreement before the ceiling exists.
Reading a generated answer before the sufficiency labels are frozen voids
the run, and nothing downstream can detect that afterwards — so the tool
makes the ordering awkward to break rather than trusting memory.

Usage:
    python scripts/audit_answers.py sufficiency init --retrieval runs/e007_retrieval.jsonl
    python scripts/audit_answers.py sufficiency freeze
    python scripts/audit_answers.py segment --answers runs/e007_answers_audit.jsonl
    python scripts/audit_answers.py claims show --next
    python scripts/audit_answers.py claims set rg-2848 3 factual --support supported
    python scripts/audit_answers.py report
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap
from dataclasses import asdict
from pathlib import Path

from graphrag_mtg.evaluation.claims import (
    EXCLUSION_VOID,
    ClaimRow,
    Failure,
    Label,
    Sufficiency,
    Support,
    classify_refusals,
    coverage,
    failure_counts,
    segment_answer,
    segment_with_handles,
    support_clusters,
    worksheet_hash,
)
from graphrag_mtg.evaluation.metrics import cluster_proportion_ci, rule_of_three_upper
from graphrag_mtg.generation.citations import index
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph

# Question and answer text carry characters a default Windows console cannot
# encode; force UTF-8 so the worksheet is readable rather than mojibake.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SUFFICIENCY_PATH = Path("data/golden/e007_sufficiency.json")
WORKSHEET_PATH = Path("data/golden/e007_claims_audit.jsonl")
ANSWERS_PATH = Path("runs/e007_answers_audit.jsonl")
CONTROL_PATH = Path("data/golden/e007_control.jsonl")
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
    out: Path = SUFFICIENCY_PATH,
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
        # The path is carried into the hint because it is not always the
        # default: a blind second pass writes to its own file, and a hint
        # that omits it sends the judgement at the frozen first pass.
        f"  -> python scripts/audit_answers.py sufficiency set {question_id} <label>"
        + ("" if out == SUFFICIENCY_PATH else f" --out {out}"),
    ]
    return "\n".join(lines)


def sufficiency_reopen(args: argparse.Namespace) -> int:
    """Clear one side's labels after the evidence they described changed.

    A frozen label is meant to be immovable, so reopening needs a reason
    that is written down rather than implied. The reason here is the only
    one that qualifies: the subgraphs were re-retrieved after a defect fix,
    so the labels no longer describe what a reader would see.

    **Only a side whose answers have never been generated may be reopened.**
    Re-labelling a question whose answer the annotator has already read is
    not a fresh pass — it is a pass contaminated by exactly what E-007's
    ordering exists to prevent. The other side's labels are kept and marked
    stale, because a stale label used for prompt iteration is honest and a
    silently re-labelled one is not.
    """
    meta = load_sufficiency(args.out)
    dev = set(json.loads(args.split.read_text(encoding="utf-8"))["dev_ids"])
    reopening = [q for q in meta["labels"] if (q in dev) == (args.side == "dev")]

    kept = meta.get("stale_labels", {})
    for question_id in meta["labels"]:
        if question_id in reopening:
            meta["labels"][question_id]["label"] = ""
        else:
            kept[question_id] = meta["labels"][question_id].get("label", "")
    meta["stale_labels"] = kept
    meta["frozen"] = False
    meta.setdefault("history", []).append(
        {
            "reopened": args.side,
            "n": len(reopening),
            "previous_hash": meta.get("hash", ""),
            "reason": args.reason,
        }
    )
    meta["hash"] = ""
    args.out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Reopened {len(reopening)} {args.side} label(s); {len(kept)} kept and marked stale.")
    print(f"reason: {args.reason}")
    print("Label the reopened side against the new subgraphs, then freeze again.")
    return 0


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
                out=args.out,
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

    write_rows(args.out, rows)

    digest = worksheet_hash(rows)
    print(f"Segmented {len(answers)} answer(s) into {len(rows)} row(s) -> {args.out}")
    print(f"hash {digest}")
    print("Record that hash in the run log NOW, before labelling anything.")
    print("Next: python scripts/audit_answers.py claims show --next")
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


def write_rows(path: Path, rows: list[ClaimRow]) -> None:
    """Rewrite the worksheet. The segmentation is untouched; only labels move."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = asdict(row)
            payload["label"] = row.label.value
            payload["support"] = row.support.value
            payload["failure"] = row.failure.value if row.failure else None
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Claims — one sentence at a time, next to the evidence it cites
# ─────────────────────────────────────────────────────────────────────────────

#: The two judgements, in the order they are made. Kept in step with
#: `docs/claim-annotation-guide.md`, which is the binding version.
CLAIM_CRIB = """\
  1. IS THIS A FACTUAL CLAIM?

  factual       it asserts something about a card, a rule, a ruling, or what
                happens in a game — including reasoning steps ("so it is
                still a 1/1") and restatements of the question's premise
  non_factual   only these four: pure discourse ("Let's look at the rules"),
                a heading with no assertion, a direct quotation of the
                question, or a sentence about the answer itself ("I cannot
                answer this from the evidence")

  Excluding a row is the only way to shrink the denominator, so `non_factual`
  is the narrow list above and nothing else. Above 20% exclusions the
  coverage figure is void.

  2. DOES THE CITED EVIDENCE CARRY IT?   (cited factual rows only)

  supported     the evidence shown below states the claim
  unsupported   it does not — and the failure code says how:
                  wrong_leaf                     right rule, wrong subrule
                  right_evidence_wrong_reading   right item, misread
                  unrelated_evidence             cites something else entirely
                  evidence_absent                handle not in the subgraph
                  claim_not_in_evidence          nothing here says this

  Judge against the evidence printed here, not against what you know about
  Magic. A claim that is true but unsupported by its citation is
  `unsupported`."""


def answers_index(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"No answers at {path}. Run `run_e007.py generate` first.")
    return {
        json.loads(line)["question_id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def handle_table(record: dict) -> dict[str, Evidence]:
    """Handle -> evidence, exactly as the answer's context showed it."""
    subgraph = Subgraph(
        question="",
        evidence=[Evidence(**item) for item in record.get("evidence", [])],
    )
    return index(subgraph)


def cited_by_row(answer: str) -> dict[int, list[str]]:
    """Row index -> handles, aligned with the frozen segmentation."""
    return {i: cited for i, (_, _, cited) in enumerate(segment_with_handles(answer))}


def render_claim(
    row: ClaimRow,
    payload: dict,
    handles_cited: list[str],
    table: dict[str, Evidence],
    *,
    position: str = "",
    header: str = "",
    command: str = "",
    crib: str = "",
) -> str:
    """One sentence, its citation resolved, and the standard it is judged by.

    ``header`` and ``command`` are overridable because the shuffled-citation
    control shows the same view with the row's identity withheld — printing
    the question id and claim index there would let the annotator pair a
    control row with the real one and stop judging it on its own evidence.
    """
    lines = [
        RULE,
        f"{header or f'{row.question_id}  claim {row.index}'}  {position}".rstrip(),
        "",
        "  QUESTION",
        wrap(payload.get("questionSimple") or payload.get("question", "")),
        "",
        "  SENTENCE",
        wrap(row.sentence),
        "",
    ]
    if not handles_cited:
        lines += [
            "  CITED: no marker on this sentence.",
            "  If this row is factual it is an uncited claim — a coverage miss, and",
            "  there is no support judgement to make.",
        ]
    else:
        lines.append(f"  CITED: {', '.join(handles_cited)}")
        for handle in handles_cited:
            item = table.get(handle)
            if item is None:
                lines.append(f"    [{handle}] NOT IN THE SUBGRAPH — this is evidence_absent.")
                continue
            lines.append(f"    [{handle}] {item.kind} {item.key}")
            lines.append(wrap(item.text)[:1200])
            if item.path:
                lines.append(f"      path: {item.path}")
    decided = row.label.value if row.label is not Label.UNLABELLED else "—"
    support = row.support.value if row.support is not Support.NOT_APPLICABLE else "—"
    lines += [
        "",
        crib or CLAIM_CRIB,
        "",
        f"  decided: {decided}   support: {support}",
        command
        or (
            f"  -> python scripts/audit_answers.py claims set {row.question_id} {row.index} "
            "<factual|non_factual> [--support supported|unsupported --failure <code>]"
        ),
    ]
    return "\n".join(lines)


def claims_show(args: argparse.Namespace) -> int:
    """Print claims to judge, with their evidence. Reads only; `set` writes."""
    require_frozen(args.sufficiency)
    rows = load_rows(args.worksheet)
    answers = answers_index(args.answers)
    records = retrieval_index(args.retrieval)

    if args.id:
        chosen = [row for row in rows if row.question_id == args.id]
        if not chosen:
            raise SystemExit(f"No rows for {args.id} in {args.worksheet}.")
    elif args.all:
        chosen = rows
    else:
        # Two kinds of unfinished row, and the second is invisible if you only
        # look at `label`: a factual cited row whose support has not been
        # judged is labelled, and still owes the judgement the metric needs.
        chosen = [row for row in rows if row.label is Label.UNLABELLED]
        if not chosen:
            chosen = [
                row for row in rows
                if row.label is Label.FACTUAL
                and row.cited
                and row.support is Support.NOT_APPLICABLE
            ]
        if not chosen:
            print("Every claim is labelled and every cited one judged.")
            print("Next: `audit_answers.py control build --seed <n> --per-answer 2`.")
            return 0
        chosen = chosen[: args.count]

    if args.brief:
        # The step-1 survey: every sentence of an answer in reading order, so
        # `factual` / `non_factual` is decided on the answer as a whole. No
        # evidence and no citation shown — step 1 judges the sentence alone.
        current = ""
        for row in chosen:
            if row.question_id != current:
                current = row.question_id
                payload = cached_question(current, args.cache_dir)
                print(f"\n{RULE}\n{current}")
                print(wrap(payload.get("questionSimple") or payload.get("question", "")))
                print()
            state = row.label.value if row.label is not Label.UNLABELLED else "·"
            print(f"  [{row.index:>3}] {state:<12} {row.sentence[:96]}")
        print(f"\n{RULE}")
        return 0

    done = sum(1 for row in rows if row.label is not Label.UNLABELLED)
    tables: dict[str, dict[str, Evidence]] = {}
    marks: dict[str, dict[int, list[str]]] = {}
    for i, row in enumerate(chosen, start=1):
        if row.question_id not in tables:
            tables[row.question_id] = handle_table(records[row.question_id])
            marks[row.question_id] = cited_by_row(answers[row.question_id]["text"])
        print(
            render_claim(
                row,
                cached_question(row.question_id, args.cache_dir),
                marks[row.question_id].get(row.index, []),
                tables[row.question_id],
                position=f"[{i} of {len(chosen)} shown; {done}/{len(rows)} done]",
            )
        )
    print(RULE)
    return 0


def parse_indices(raw: str) -> list[int]:
    """``"3"``, ``"0,2,5"`` or ``"0-4"`` — the rows one command applies to."""
    chosen: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part.lstrip("-"):
            start, _, end = part.partition("-")
            chosen.extend(range(int(start), int(end) + 1))
        elif part:
            chosen.append(int(part))
    return chosen


def claims_set(args: argparse.Namespace) -> int:
    """Record claim judgements, validated, without hand-editing the worksheet.

    Several rows may take one label at once — ``0,2,5`` or ``0-4`` — because
    step 1 of the guide is a decision about a sentence's *kind* and reading
    thirty of them one shell command at a time invites the fastest label
    rather than the right one. A **support** judgement is different: it
    requires reading that row's evidence, so it stays one row per command.
    """
    require_frozen(args.sufficiency)
    rows = load_rows(args.worksheet)
    before = worksheet_hash(rows)

    indices = parse_indices(args.index)
    if args.support and len(indices) != 1:
        raise SystemExit(
            "--support judges one row against its own evidence; pass a single index. "
            "Batching support is how a citation nobody read gets scored as supported."
        )
    by_index = {r.index: r for r in rows if r.question_id == args.question_id}
    missing = [i for i in indices if i not in by_index]
    if missing:
        raise SystemExit(
            f"No row {args.question_id}[{missing[0]}] in {args.worksheet}."
            + (f" ({len(missing)} of {len(indices)} not found)" if len(missing) > 1 else "")
        )

    support = Support(args.support) if args.support else Support.NOT_APPLICABLE
    failure = Failure(args.failure) if args.failure else None
    label = Label(args.label)

    # The rules the guide states, enforced here so a worksheet can never
    # hold a combination the report would have to interpret.
    if label is Label.NON_FACTUAL and (args.support or args.failure):
        raise SystemExit("A non_factual row is not judged for support — it is out of the denominator.")
    if support is Support.UNSUPPORTED and failure is None:
        raise SystemExit(
            "An unsupported row needs --failure. Without it E-007's prediction about "
            "which failure dominates cannot be scored, and an unfalsifiable prediction "
            "is not a prediction."
        )
    if failure is not None and support is not Support.UNSUPPORTED:
        raise SystemExit("--failure describes an unsupported row; pass --support unsupported.")
    if args.support and not by_index[indices[0]].cited:
        raise SystemExit(
            f"{args.question_id}[{indices[0]}] carries no citation marker, so there is "
            "nothing to judge for support. A factual row with no citation is a coverage "
            "miss, which the report counts on its own."
        )

    for i in indices:
        row = by_index[i]
        row.label = label
        row.support = support
        row.failure = failure
        if args.comment:
            row.comment = args.comment
    write_rows(args.worksheet, rows)

    if worksheet_hash(rows) != before:
        raise SystemExit(
            "The worksheet hash moved while writing a label. The segmentation must not "
            "change after freezing — investigate before labelling anything else."
        )

    done = sum(1 for r in rows if r.label is not Label.UNLABELLED)
    tail = f"   support: {support.value}" if support is not Support.NOT_APPLICABLE else ""
    written = ",".join(str(i) for i in indices)
    print(f"{args.question_id}[{written}]: {label.value}{tail}   [{done}/{len(rows)} done]")
    owed = [i for i in indices if by_index[i].cited and support is Support.NOT_APPLICABLE]
    if label is Label.FACTUAL and owed:
        preview = ", ".join(f"{args.question_id}[{i}]" for i in owed[:8])
        print(f"  still needs --support (factual and cited): {preview}")
    return 0


def claims_status(args: argparse.Namespace) -> int:
    """What is labelled, what is still owed, and the exclusion rate so far."""
    rows = load_rows(args.worksheet)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.label.value] = counts.get(row.label.value, 0) + 1
    owed = [
        r for r in rows
        if r.label is Label.FACTUAL and r.cited and r.support is Support.NOT_APPLICABLE
    ]
    left = [r for r in rows if r.label is Label.UNLABELLED]

    print(f"{len(rows) - len(left)}/{len(rows)} row(s) labelled")
    print(f"  mix: {dict(sorted(counts.items()))}")
    print(f"  worksheet hash {worksheet_hash(rows)[:12]}")
    if left:
        preview = ", ".join(f"{r.question_id}[{r.index}]" for r in left[:8])
        print(f"  left: {preview}{' ...' if len(left) > 8 else ''}")
    if owed:
        preview = ", ".join(f"{r.question_id}[{r.index}]" for r in owed[:8])
        print(f"  awaiting --support: {preview}{' ...' if len(owed) > 8 else ''}")
    excluded = counts.get(Label.NON_FACTUAL.value, 0)
    judged = len(rows) - len(left)
    if judged:
        share = excluded / judged
        verdict = "VOID above 0.20" if share > EXCLUSION_VOID else "within the registered limit"
        print(f"  exclusions {excluded}/{judged} = {share:.3f} — {verdict}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Shuffled-citation control — the only pre-committed reading support has
# ─────────────────────────────────────────────────────────────────────────────

#: Support judged with the citations permuted. Registered in E-007 before any
#: answer existed: the second DoD clause holds only if the real arm's lower
#: bound clears this arm's upper bound.
CONTROL_CRIB = """\
  DOES THE EVIDENCE SHOWN CARRY THIS SENTENCE?

  supported     it states the claim, or the sentence restates it
  unsupported   it does not — with the code saying how:
                  wrong_leaf | right_evidence_wrong_reading |
                  unrelated_evidence | evidence_absent | claim_not_in_evidence

  Judge only what is printed above. Do not reconstruct what the answer
  "meant" to cite, and do not consult your own Magic knowledge — a true
  sentence whose evidence does not carry it is `unsupported`."""


def derange(n: int, rng: random.Random) -> list[int]:
    """A permutation of ``range(n)`` with no fixed point.

    A fixed point would hand a control row its own true citation and score
    it as if the pairing were random, which biases the control arm toward
    the real one — the direction that makes the DoD easier to pass.
    """
    if n < 2:
        raise ValueError("a derangement needs at least two elements")
    order = list(range(n))
    while any(i == j for i, j in enumerate(order)):
        rng.shuffle(order)
    return order


def control_build(args: argparse.Namespace) -> int:
    """Pair every cited factual claim with another claim's citation.

    Permuted **within an answer**, as registered: across answers the
    evidence would come from a different subgraph entirely and every row
    would be trivially unsupported, which measures nothing. An answer
    holding a single cited factual claim cannot be deranged against itself
    and is excluded — counted and printed, never silently dropped.
    """
    require_frozen(args.sufficiency)
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to rebuild over judgements.")

    rows = load_rows(args.worksheet)
    unlabelled = [r for r in rows if r.label is Label.UNLABELLED]
    if unlabelled:
        raise SystemExit(
            f"{len(unlabelled)} row(s) still unlabelled. The control covers cited factual "
            "claims, so which rows those are must be settled first."
        )
    answers = answers_index(args.answers)

    if args.per_answer and args.per_answer < 2:
        raise SystemExit("--per-answer must be at least 2; one claim cannot be deranged.")

    rng = random.Random(args.seed)
    entries: list[dict] = []
    excluded: list[str] = []
    sampled = 0
    for question_id in sorted({r.question_id for r in rows}):
        marks = cited_by_row(answers[question_id]["text"])
        eligible = [
            r for r in rows
            if r.question_id == question_id
            and r.label is Label.FACTUAL
            and r.cited
            and marks.get(r.index)
        ]
        if len(eligible) < 2:
            excluded += [f"{question_id}[{r.index}]" for r in eligible]
            continue
        if args.per_answer and len(eligible) > args.per_answer:
            # Sampled per answer rather than over the pool, because the
            # bootstrap resamples questions: keeping every cluster present
            # is what the interval depends on, not claims per cluster.
            sampled += len(eligible) - args.per_answer
            eligible = sorted(rng.sample(eligible, args.per_answer), key=lambda r: r.index)
        order = derange(len(eligible), rng)
        for position, row in enumerate(eligible):
            entries.append(
                {
                    "question_id": question_id,
                    "index": row.index,
                    "sentence": row.sentence,
                    "handles": marks[row.index],
                    "arm": "real",
                    "support": "",
                    "failure": None,
                    "comment": "",
                }
            )
            entries.append(
                {
                    "question_id": question_id,
                    "index": row.index,
                    "sentence": row.sentence,
                    "handles": marks[eligible[order[position]].index],
                    "arm": "shuffled",
                    "support": "",
                    "failure": None,
                    "comment": "",
                }
            )

    # Presentation order is randomised over the whole file so a row and its
    # twin are far apart. This weakens recognition; it does not eliminate it,
    # and the registry amendment says so.
    rng.shuffle(entries)
    for slot, entry in enumerate(entries):
        entry["slot"] = slot

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    real = sum(1 for e in entries if e["arm"] == "real")
    print(f"Wrote {len(entries)} row(s) -> {args.out}   ({real} real + {real} shuffled)")
    print(f"seed {args.seed} — record it in the run log; the pairing is not reproducible without it.")
    if sampled:
        print(
            f"  {sampled} cited claim(s) left out by --per-answer {args.per_answer}: every "
            "answer keeps a pair, so the cluster count is untouched."
        )
    if excluded:
        print(f"  excluded, one cited claim in the answer: {', '.join(excluded)}")
    print("Judge every row by slot. The arm is in the file and is never printed.")
    return 0


def load_control(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"No control at {path}. Run `control build` first.")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def control_show(args: argparse.Namespace) -> int:
    """Print control rows by slot, with the arm withheld."""
    entries = load_control(args.control)
    records = retrieval_index(args.retrieval)

    if args.slot is not None:
        chosen = [e for e in entries if e["slot"] == args.slot]
        if not chosen:
            raise SystemExit(f"No slot {args.slot} in {args.control}.")
    else:
        chosen = [e for e in entries if not e["support"]][: args.count]
        if not chosen:
            print("Every control row is judged. Next: `control compare`.")
            return 0

    done = sum(1 for e in entries if e["support"])
    for i, entry in enumerate(chosen, start=1):
        row = ClaimRow(
            entry["question_id"],
            entry["index"],
            entry["sentence"],
            cited=True,
            label=Label.FACTUAL,
            support=Support(entry["support"]) if entry["support"] else Support.NOT_APPLICABLE,
        )
        print(
            render_claim(
                row,
                cached_question(entry["question_id"], args.cache_dir),
                entry["handles"],
                handle_table(records[entry["question_id"]]),
                position=f"[{i} of {len(chosen)} shown; {done}/{len(entries)} done]",
                header=f"slot {entry['slot']}",
                command=f"  -> python scripts/audit_answers.py control set {entry['slot']} "
                "<supported|unsupported> [--failure <code>]",
                crib=CONTROL_CRIB,
            )
        )
    print(RULE)
    return 0


def control_set(args: argparse.Namespace) -> int:
    """Record one control judgement. One slot at a time, like support itself."""
    entries = load_control(args.control)
    matches = [e for e in entries if e["slot"] == args.slot]
    if not matches:
        raise SystemExit(f"No slot {args.slot} in {args.control}.")
    if args.support == Support.UNSUPPORTED.value and not args.failure:
        raise SystemExit("An unsupported row needs --failure, here as everywhere.")
    if args.failure and args.support != Support.UNSUPPORTED.value:
        raise SystemExit("--failure describes an unsupported row.")

    entry = matches[0]
    entry["support"] = args.support
    entry["failure"] = args.failure
    if args.comment:
        entry["comment"] = args.comment
    with args.control.open("w", encoding="utf-8") as handle:
        for row in entries:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    done = sum(1 for e in entries if e["support"])
    print(f"slot {args.slot}: {args.support}   [{done}/{len(entries)} done]")
    return 0


def control_status(args: argparse.Namespace) -> int:
    """Progress only. Per-arm counts stay hidden until every row is judged."""
    entries = load_control(args.control)
    done = sum(1 for e in entries if e["support"])
    print(f"{done}/{len(entries)} control row(s) judged")
    if done < len(entries):
        left = [str(e["slot"]) for e in entries if not e["support"]]
        print(f"  next slots: {', '.join(left[:10])}{' ...' if len(left) > 10 else ''}")
        print("  per-arm results are withheld until the last row is judged.")
    else:
        print("  complete — run `control compare`.")
    return 0


def control_compare(args: argparse.Namespace) -> int:
    """Apply the registered reading of the second DoD clause. No new rule here."""
    entries = load_control(args.control)
    pending = [e for e in entries if not e["support"]]
    if pending:
        raise SystemExit(
            f"{len(pending)} control row(s) unjudged. Comparing now would let the "
            "remaining judgements be made against a visible gap."
        )

    intervals = {}
    for arm in ("real", "shuffled"):
        clusters: dict[str, list[bool]] = {}
        for entry in entries:
            if entry["arm"] == arm:
                clusters.setdefault(entry["question_id"], []).append(
                    entry["support"] == Support.SUPPORTED.value
                )
        intervals[arm] = cluster_proportion_ci(list(clusters.values()))

    real, shuffled = intervals["real"], intervals["shuffled"]
    print(f"real      {real.point:.3f} [{real.low:.3f}, {real.high:.3f}]  {real.n_docs} cluster(s)")
    print(f"shuffled  {shuffled.point:.3f} [{shuffled.low:.3f}, {shuffled.high:.3f}]")
    print()
    if real.low > shuffled.high:
        print("Second DoD clause MET: the real arm's lower bound clears the control's upper bound.")
    else:
        print(
            "Second DoD clause NOT MET: the intervals overlap. Whatever coverage reads, "
            "this run cannot claim its citations support their sentences rather than "
            "merely looking plausible to this judge."
        )
    print("Registered before any answer existed; nothing here is decided now.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Blind re-audit (M2) — the ceiling every hand-made label is reported against
# ─────────────────────────────────────────────────────────────────────────────


def reaudit_sufficiency(args: argparse.Namespace) -> int:
    """A blank second pass over a sample of subgraphs, originals hidden.

    E-003a measured this annotator at 0.815 against themself. A label with
    no ceiling is reported against a 1.0 that does not exist, so E-007c
    re-labels a sample and scores exact agreement. The originals are not
    copied into the new file — a worksheet that carries the answer is not a
    blind pass.
    """
    original = require_frozen(args.source)
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to overwrite a pass in progress.")

    rng = random.Random(args.seed)
    chosen = sorted(rng.sample(sorted(original["labels"]), args.n))
    payload = {
        "frozen": False,
        "pass": "m2",
        "source": str(args.source),
        "source_hash": original.get("hash", ""),
        "seed": args.seed,
        "labels": {question: {"label": ""} for question in chosen},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(chosen)} blank row(s) -> {args.out}   seed {args.seed}")
    print(f"source hash {original.get('hash', '')[:12]} — recorded, not copied.")
    print(f"Label them with:  sufficiency show --out {args.out} --next")
    print("Do not open the original file until every row here is labelled.")
    return 0


def reaudit_claims(args: argparse.Namespace) -> int:
    """A blank second claim pass over a sample of answers.

    The segmentation is **regenerated** from the citation-stripped text
    rather than copied, which is both what the guide specifies and a check
    in itself: if the same answers segment differently, the worksheet the
    first pass was frozen against was not reproducible.
    """
    require_frozen(args.sufficiency)
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to overwrite a pass in progress.")
    first = load_rows(args.source)
    answers = answers_index(args.answers)

    rng = random.Random(args.seed)
    questions = sorted({row.question_id for row in first})
    chosen = set(rng.sample(questions, min(args.n, len(questions))))

    rebuilt: list[ClaimRow] = []
    for question_id in sorted(chosen):
        for i, (sentence, cited) in enumerate(segment_answer(answers[question_id]["text"])):
            rebuilt.append(ClaimRow(question_id=question_id, index=i, sentence=sentence, cited=cited))

    original = {(r.question_id, r.index): r for r in first if r.question_id in chosen}
    drifted = [
        f"{row.question_id}[{row.index}]"
        for row in rebuilt
        if (row.question_id, row.index) not in original
        or original[(row.question_id, row.index)].sentence != row.sentence
    ]
    if drifted:
        raise SystemExit(
            f"{len(drifted)} row(s) segment differently than the frozen worksheet: "
            f"{', '.join(drifted[:5])}. The first pass is not reproducible, which has to be "
            "understood before an agreement number means anything."
        )

    write_rows(args.out, rebuilt)
    print(f"Wrote {len(rebuilt)} blank row(s) over {len(chosen)} answer(s) -> {args.out}")
    print(f"seed {args.seed}   source hash {worksheet_hash(first)[:12]}")
    print("Segmentation reproduced the frozen worksheet exactly.")
    print(f"Label them with:  claims show --worksheet {args.out} --next")
    print("Do not open the first pass until every row here is judged.")
    return 0


def reaudit_claims_score(args: argparse.Namespace) -> int:
    """Exact agreement on the claim labels, and on support where both judged."""
    second = load_rows(args.out)
    pending = [r for r in second if r.label is Label.UNLABELLED]
    if pending:
        raise SystemExit(f"{len(pending)} row(s) still unlabelled.")
    first = {(r.question_id, r.index): r for r in load_rows(args.source)}

    label_hits = [first[(r.question_id, r.index)].label is r.label for r in second]
    both_support = [
        (first[(r.question_id, r.index)], r)
        for r in second
        if r.support is not Support.NOT_APPLICABLE
        and first[(r.question_id, r.index)].support is not Support.NOT_APPLICABLE
    ]
    labels = cluster_proportion_ci([[hit] for hit in label_hits])
    print(f"label agreement   {sum(label_hits)}/{len(label_hits)} = {labels.point:.3f} "
          f"[{labels.low:.3f}, {labels.high:.3f}]")
    if both_support:
        hits = [a.support is b.support for a, b in both_support]
        support = cluster_proportion_ci([[hit] for hit in hits])
        print(f"support agreement {sum(hits)}/{len(hits)} = {support.point:.3f} "
              f"[{support.low:.3f}, {support.high:.3f}]")
    else:
        print("support agreement: no row was judged for support in both passes.")
    print("\nThe ceiling coverage and support are read against — E-003a put this")
    print("annotator at 0.815, so a figure reported against 1.0 is reported against nothing.")
    return 0


def reaudit_score(args: argparse.Namespace) -> int:
    """Exact agreement between the two passes, with an interval."""
    second = load_sufficiency(args.out)
    pending = [q for q, row in second["labels"].items() if not (row.get("label") or "").strip()]
    if pending:
        raise SystemExit(
            f"{len(pending)} row(s) still unlabelled. Scoring now would let the rest be "
            "labelled against a visible agreement rate."
        )
    first = load_sufficiency(Path(second["source"]))
    if second.get("source_hash") and second["source_hash"] != first.get("hash"):
        raise SystemExit(
            "The source file's hash has changed since this pass was built. The first pass "
            "moved, so an agreement number would compare against something that no longer "
            "exists."
        )

    pairs = [
        (first["labels"][q]["label"], second["labels"][q]["label"]) for q in second["labels"]
    ]
    agreed = [a == b for a, b in pairs]
    interval = cluster_proportion_ci([[hit] for hit in agreed])
    print(f"exact agreement {sum(agreed)}/{len(agreed)} = {interval.point:.3f} "
          f"[{interval.low:.3f}, {interval.high:.3f}]")
    disagreements = [(q, a, b) for (q, (a, b)) in zip(second["labels"], pairs, strict=True) if a != b]
    if disagreements:
        print("\ndisagreements (pass 1 -> pass 2):")
        for question, before, after in disagreements:
            print(f"  {question}: {before} -> {after}")
    print("\nThis is the ceiling the sufficiency-dependent figures are read against,")
    print("not a score for the system. E-003a put this annotator at 0.815.")
    return 0


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

    reopen = suff_sub.add_parser("reopen", help="clear one side's labels after a re-retrieval")
    reopen.add_argument("--side", choices=("dev", "audit"), required=True)
    reopen.add_argument("--reason", required=True, help="why the evidence changed")
    reopen.add_argument("--out", type=Path, default=SUFFICIENCY_PATH)
    reopen.add_argument("--split", type=Path, default=SPLIT_PATH)
    reopen.set_defaults(func=sufficiency_reopen)

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

    claims = sub.add_parser("claims", help="label the segmented claims, one at a time")
    claims_sub = claims.add_subparsers(dest="stage", required=True)

    claim_show = claims_sub.add_parser("show", help="one claim with the evidence it cites")
    claim_show.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    claim_show.add_argument("--answers", type=Path, default=ANSWERS_PATH)
    claim_show.add_argument("--retrieval", type=Path, default=RETRIEVAL_PATH)
    claim_show.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    claim_show.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    claim_show.add_argument("--id", help="every row of one answer")
    claim_show.add_argument("--all", action="store_true")
    claim_show.add_argument("--next", action="store_true", help="the next unlabelled (default)")
    claim_show.add_argument("--count", type=int, default=1)
    claim_show.add_argument(
        "--brief", action="store_true", help="one line per sentence, no evidence — for step 1"
    )
    claim_show.set_defaults(func=claims_show)

    claim_set = claims_sub.add_parser("set", help="record one claim judgement")
    claim_set.add_argument("question_id")
    claim_set.add_argument("index", help="one row, or several: 3 | 0,2,5 | 0-4")
    claim_set.add_argument("label", choices=[Label.FACTUAL.value, Label.NON_FACTUAL.value])
    claim_set.add_argument("--support", choices=[Support.SUPPORTED.value, Support.UNSUPPORTED.value])
    claim_set.add_argument("--failure", choices=[f.value for f in Failure])
    claim_set.add_argument("--comment", default="", help="where a bad split is noted, not fixed")
    claim_set.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    claim_set.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    claim_set.set_defaults(func=claims_set)

    claim_status = claims_sub.add_parser("status", help="what is labelled and what is owed")
    claim_status.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    claim_status.set_defaults(func=claims_status)

    ctl = sub.add_parser("control", help="the shuffled-citation control")
    ctl_sub = ctl.add_subparsers(dest="stage", required=True)

    ctl_build = ctl_sub.add_parser("build", help="pair each cited claim with another's citation")
    ctl_build.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    ctl_build.add_argument("--answers", type=Path, default=ANSWERS_PATH)
    ctl_build.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    ctl_build.add_argument("--out", type=Path, default=CONTROL_PATH)
    ctl_build.add_argument("--seed", type=int, required=True, help="recorded in the run log")
    ctl_build.add_argument(
        "--per-answer", type=int, default=None, help="cap cited claims per answer (min 2)"
    )
    ctl_build.add_argument("--force", action="store_true")
    ctl_build.set_defaults(func=control_build)

    ctl_show = ctl_sub.add_parser("show", help="one slot, with the arm withheld")
    ctl_show.add_argument("--control", type=Path, default=CONTROL_PATH)
    ctl_show.add_argument("--retrieval", type=Path, default=RETRIEVAL_PATH)
    ctl_show.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    ctl_show.add_argument("--slot", type=int)
    ctl_show.add_argument("--next", action="store_true", help="the next unjudged (default)")
    ctl_show.add_argument("--count", type=int, default=1)
    ctl_show.set_defaults(func=control_show)

    ctl_set = ctl_sub.add_parser("set", help="record one control judgement")
    ctl_set.add_argument("slot", type=int)
    ctl_set.add_argument("support", choices=[Support.SUPPORTED.value, Support.UNSUPPORTED.value])
    ctl_set.add_argument("--failure", choices=[f.value for f in Failure])
    ctl_set.add_argument("--comment", default="")
    ctl_set.add_argument("--control", type=Path, default=CONTROL_PATH)
    ctl_set.set_defaults(func=control_set)

    ctl_status = ctl_sub.add_parser("status", help="progress, without per-arm counts")
    ctl_status.add_argument("--control", type=Path, default=CONTROL_PATH)
    ctl_status.set_defaults(func=control_status)

    ctl_compare = ctl_sub.add_parser("compare", help="apply the registered reading")
    ctl_compare.add_argument("--control", type=Path, default=CONTROL_PATH)
    ctl_compare.set_defaults(func=control_compare)

    re_ = sub.add_parser("reaudit", help="the blind second pass (M2 / E-007c)")
    re_sub = re_.add_subparsers(dest="stage", required=True)

    re_build = re_sub.add_parser("build", help="blank worksheet over a sample, originals hidden")
    re_build.add_argument("--source", type=Path, default=SUFFICIENCY_PATH)
    re_build.add_argument("--out", type=Path, default=Path("data/golden/e007_sufficiency_m2.json"))
    re_build.add_argument("--n", type=int, default=10)
    re_build.add_argument("--seed", type=int, required=True)
    re_build.add_argument("--force", action="store_true")
    re_build.set_defaults(func=reaudit_sufficiency)

    re_score = re_sub.add_parser("score", help="exact agreement between the two passes")
    re_score.add_argument("--out", type=Path, default=Path("data/golden/e007_sufficiency_m2.json"))
    re_score.set_defaults(func=reaudit_score)

    re_claims = re_sub.add_parser("claims-build", help="blank claim worksheet over sampled answers")
    re_claims.add_argument("--source", type=Path, default=WORKSHEET_PATH)
    re_claims.add_argument("--answers", type=Path, default=ANSWERS_PATH)
    re_claims.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    re_claims.add_argument("--out", type=Path, default=Path("data/golden/e007_claims_m2.jsonl"))
    re_claims.add_argument("--n", type=int, default=8)
    re_claims.add_argument("--seed", type=int, required=True)
    re_claims.add_argument("--force", action="store_true")
    re_claims.set_defaults(func=reaudit_claims)

    re_cscore = re_sub.add_parser("claims-score", help="agreement on labels and support")
    re_cscore.add_argument("--source", type=Path, default=WORKSHEET_PATH)
    re_cscore.add_argument("--out", type=Path, default=Path("data/golden/e007_claims_m2.jsonl"))
    re_cscore.set_defaults(func=reaudit_claims_score)

    rep = sub.add_parser("report", help="coverage, support and refusals")
    rep.add_argument("--worksheet", type=Path, default=WORKSHEET_PATH)
    rep.add_argument("--sufficiency", type=Path, default=SUFFICIENCY_PATH)
    rep.add_argument("--answers", type=Path, default=ANSWERS_PATH)
    rep.set_defaults(func=report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
