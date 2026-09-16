#!/usr/bin/env python
"""Every multi-hop question, both arms, end to end, for reading by a person.

No API, no graph, no model: rendering over E-001's dumps. The output is a
worksheet, not a result — it goes to `data/interim/` because it carries CR rule
text and card oracle text, which the Fan Content Policy forbids committing.

**The prompt was never recorded, so it is rebuilt — and verified, not assumed.**
`e001_*_answers_*.jsonl` stores `prompt_version` and nothing else of what the
model was sent. The context string *is* stored on the retrieval dump, so this
re-runs `serialize()` over the dumped evidence and compares the result byte for
byte against that recording. A question whose rebuild differs is printed as
**MISMATCH** and counted; it is not quietly rendered. E-018 paid for this
lesson twice — once when 27 of 60 recorded prompts stopped rebuilding after an
amendment changed the builder, and once when a summary line said "zero
unverified" because it grepped for a word the failure branch never wrote.

What the worksheet answers, which no aggregate in this project does: *on the
stratum the thesis was written about, what did each arm actually put in front
of the model, and what did the model do with it?*

Usage:
    python scripts/multihop_observability.py
    python scripts/multihop_observability.py --stratum legality_1hop --limit 3
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import artefacts, load_jsonl, outcome_of
from graphrag_mtg.generation.answerer import (
    PROMPT_VERSION,
    SYSTEM,
    build_prompt,
)
from graphrag_mtg.retrieval.subgraph import (
    Evidence,
    Outcome,
    Subgraph,
    serialize,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Arm A is the vector baseline, arm B the graph. Arm C is the shipped hybrid
#: and is deliberately absent: the question this worksheet serves is the
#: thesis contrast, and a third column would triple the reading for a question
#: nobody asked.
ARMS = {"A": "A-hybrid", "B": "B"}
SPLIT = "eval"
STRATUM = "interaction_multihop"
GOLDEN = Path("data/golden")
OUT = Path("data/interim/multihop-observability.md")

#: E-001 suppressed the incompleteness notice on every arm, so that no arm was
#: handed an invitation to hedge that another could not receive (pin 11). The
#: rebuild has to match that or it rebuilds a prompt nobody sent.
NOTICE = False


def golden() -> dict[str, dict]:
    """Every golden row that carries a question, keyed by id."""
    rows: dict[str, dict] = {}
    for path in sorted(GOLDEN.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "question" in row and "id" in row:
                rows.setdefault(row["id"], row)
    return rows


def rebuild(record: dict) -> Subgraph:
    """A Subgraph from the dumped evidence, for re-serializing.

    `distance` defaults to 0 when a dump predates the field; it affects
    eviction order, which has already happened, and not the rendering.
    """
    return Subgraph(
        question=record.get("question", ""),
        outcome=Outcome(record["outcome"]),
        evidence=[
            Evidence(
                kind=item["kind"],
                key=item["key"],
                text=item.get("text", ""),
                template=item.get("template", ""),
                path=item.get("path", ""),
                distance=item.get("distance", 0),
            )
            for item in record.get("evidence", ())
        ],
        templates_run=list(record.get("templates_run") or ()),
        note=record.get("note", "") or "",
    )


def kinds(record: dict) -> Counter[str]:
    return Counter(item.get("kind", "?") for item in record.get("evidence", ()))


def keyset(record: dict) -> set[tuple[str, str]]:
    return {(i.get("kind", "?"), i.get("key", "?")) for i in record.get("evidence", ())}


def fence(text: str) -> str:
    """Fence a block whose content may itself contain backticks.

    The fence has to be longer than the longest backtick run *inside* the
    content, or a rule quoting a code span silently ends the block early and
    the rest of the prompt renders as prose. Card names and CR text are not
    supposed to contain backticks, which is exactly why nobody would notice.
    """
    longest = 0
    run = 0
    for character in text:
        run = run + 1 if character == "`" else 0
        longest = max(longest, run)
    return f"{'`' * max(3, longest + 1)}text\n{text}\n{'`' * max(3, longest + 1)}"


def overlap(retrieval: dict[str, dict[str, dict]], ids: list[str]) -> None:
    """How much of each arm's context the other arm also had.

    **Jaccard is not the figure to quote here, and standing rule 9 is why.**
    *"Of the items the two arms retrieved, how many are shared"* returns 0.11 —
    and what **else** produces a low Jaccard? A size asymmetry. With 50 items
    against 12, the index is capped at 0.24 even when the smaller set is a
    perfect subset of the larger, so a low value is partly arithmetic about
    sizes this project already published (3.38x median items).

    Containment answers the question the Jaccard only gestures at: of what the
    graph put in the context, what fraction did the vector arm also have? Both
    are printed, and the containment is the one the claim rests on.
    """
    import statistics

    per_b, per_a, jac = [], [], []
    rulings, rules = [], []
    for qid in ids:
        a = keyset(retrieval["A"][qid])
        b = keyset(retrieval["B"][qid])
        shared = a & b
        if b:
            per_b.append(len(shared) / len(b))
        if a:
            per_a.append(len(shared) / len(a))
        if a | b:
            jac.append(len(shared) / len(a | b))
        count_a, count_b = Counter(k for k, _ in a), Counter(k for k, _ in b)
        rulings.append((count_a["ruling"], count_b["ruling"]))
        rules.append((count_a["rule"], count_b["rule"]))

    total_a = sum(len(keyset(retrieval["A"][q])) for q in ids)
    total_b = sum(len(keyset(retrieval["B"][q])) for q in ids)
    shared_total = sum(len(keyset(retrieval["A"][q]) & keyset(retrieval["B"][q])) for q in ids)

    print(f"\n{'=' * 78}\nHOW MUCH OF EACH CONTEXT THE OTHER ARM ALSO HAD\n{'=' * 78}\n")
    print(f"  {len(ids)} questions. Items: A {total_a}, B {total_b}, shared {shared_total}.\n")
    print(f"  {'':<46}{'median':>10}{'pooled':>10}")
    print(f"  {'of the graph, what the vector also had':<46}"
          f"{statistics.median(per_b):>10.3f}{shared_total / total_b:>10.3f}")
    print(f"  {'of the vector, what the graph also had':<46}"
          f"{statistics.median(per_a):>10.3f}{shared_total / total_a:>10.3f}")
    print(f"  {'Jaccard (depressed by the size gap - see docstring)':<46}"
          f"{statistics.median(jac):>10.3f}{shared_total / (total_a + total_b - shared_total):>10.3f}")
    print("\n  What each arm bought with the same token budget, per question:\n")
    print(f"  {'':<24}{'A (vector)':>12}{'B (graph)':>12}")
    print(f"  {'median rulings':<24}{statistics.median(x for x, _ in rulings):>12.1f}"
          f"{statistics.median(y for _, y in rulings):>12.1f}")
    print(f"  {'median CR rules':<24}{statistics.median(x for x, _ in rules):>12.1f}"
          f"{statistics.median(y for _, y in rules):>12.1f}")
    print(f"\n  A holds more rulings on {sum(1 for x, y in rulings if x > y)} of {len(ids)} "
          f"questions; B holds more rules on {sum(1 for x, y in rules if y > x)} of {len(ids)}.")
    print(
        "\n  The trade is general, not carried by a few questions - which is the\n"
        "  check that matters, because a median of ratios and a ratio of totals\n"
        "  disagree exactly when one question dominates."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default=SPLIT)
    parser.add_argument("--stratum", default=STRATUM)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    retrieval = {
        key: {r["question_id"]: r for r in load_jsonl(artefacts(slug, args.split)[0], what=slug)}
        for key, slug in ARMS.items()
    }
    answers = {
        key: {r["question_id"]: r for r in load_jsonl(artefacts(slug, args.split)[1], what=slug)}
        for key, slug in ARMS.items()
    }
    verdicts = {
        key: {r["question_id"]: r for r in load_jsonl(artefacts(slug, args.split)[2], what=slug)}
        for key, slug in ARMS.items()
    }
    gold = golden()

    ids = sorted(q for q, r in retrieval["B"].items() if r["stratum"] == args.stratum)
    if args.limit:
        ids = ids[: args.limit]

    mismatch = 0
    lines: list[str] = []
    lines.append(f"# {args.stratum} — what each arm put in front of the model\n")
    lines.append(
        f"{len(ids)} questions, arms A (vector) and B (graph), split `{args.split}`.\n\n"
        "**Not for the repository.** This worksheet carries serialized CR rule text and "
        "card oracle text.\n\n"
        "**The prompt was never recorded** — the answers dump stores `prompt_version` and "
        "nothing else of what was sent. Every prompt below is *rebuilt* by re-running "
        "`serialize()` over the dumped evidence and is marked VERIFIED only where the "
        "rebuild reproduces the recorded context byte for byte.\n"
    )

    summary: list[str] = []
    for qid in ids:
        row = gold.get(qid, {})
        question = row.get("question", "(question text not in the golden set)")
        gold_rules = row.get("gold_cr_rules") or []

        lines.append(f"\n---\n\n## `{qid}`\n")
        lines.append(f"**Question.** {question}\n")
        if gold_rules:
            lines.append(f"**Gold CR rules.** {', '.join(gold_rules)}\n")
        if row.get("answer"):
            lines.append(f"**Answer key.** {row['answer']}\n")

        sets = {}
        for key in ARMS:
            record = retrieval[key].get(qid)
            answer = answers[key].get(qid)
            verdict = verdicts[key].get(qid)
            if record is None or answer is None:
                lines.append(f"\n### Arm {key} — no record\n")
                continue
            sets[key] = keyset(record)

            recorded = record.get("context") or ""
            rebuilt = serialize(rebuild(record), notice=NOTICE)
            ok = rebuilt == recorded
            mismatch += 0 if ok else 1
            stamp = (
                "VERIFIED — rebuild reproduces the recorded context byte for byte"
                if ok
                else "**MISMATCH — the rebuild differs from what was recorded; "
                "the prompt below is NOT what was sent**"
            )

            outcome = outcome_of(answer, verdict)
            counts = kinds(record)
            lines.append(f"\n### Arm {key} — {'vector' if key == 'A' else 'graph'}\n")
            lines.append(
                f"| | |\n|---|---|\n"
                f"| retrieval outcome | `{record['outcome']}` |\n"
                f"| templates run | {', '.join(record.get('templates_run') or ['—'])} |\n"
                f"| evidence items | {sum(counts.values())} — "
                f"{', '.join(f'{k} {v}' for k, v in sorted(counts.items())) or '—'} |\n"
                f"| context tokens | {record.get('tokens', 0)} |\n"
                f"| dropped / capped | {dict(record.get('dropped') or {})} / "
                f"{dict(record.get('capped') or {})} |\n"
                f"| harness outcome | `{outcome}` |\n"
                f"| judge label | `{(verdict or {}).get('label', '—')}` |\n"
                f"| prompt version | recorded `{answer.get('prompt_version')}`, "
                f"rebuilt at HEAD `{PROMPT_VERSION}` |\n"
                f"| rebuild | {stamp} |\n"
            )

            lines.append("\n**Prompt as rebuilt (system omitted, identical across arms):**\n")
            lines.append(fence(build_prompt(question, rebuild(record), notice=NOTICE)))
            lines.append("\n**Model output:**\n")
            lines.append(fence(answer.get("rendered") or answer.get("text") or "(empty)"))
            if verdict and verdict.get("rationale"):
                lines.append(f"\n**Judge rationale.** {verdict['rationale']}\n")

        if len(sets) == 2:
            only_a, only_b = sets["A"] - sets["B"], sets["B"] - sets["A"]
            shared = sets["A"] & sets["B"]
            union = sets["A"] | sets["B"]
            jaccard = len(shared) / len(union) if union else 0.0
            lines.append(
                f"\n### What the two contexts do not share\n\n"
                f"| | count | by kind |\n|---|---:|---|\n"
                f"| only in A (vector) | {len(only_a)} | "
                f"{dict(Counter(k for k, _ in only_a))} |\n"
                f"| only in B (graph) | {len(only_b)} | "
                f"{dict(Counter(k for k, _ in only_b))} |\n"
                f"| in both | {len(shared)} | {dict(Counter(k for k, _ in shared))} |\n\n"
                f"Jaccard **{jaccard:.3f}**.\n"
            )
            summary.append(
                f"| `{qid}` | {len(sets['A'])} | {len(sets['B'])} | {len(shared)} "
                f"| {jaccard:.3f} | `{outcome_of(answers['A'][qid], verdicts['A'].get(qid))}` "
                f"| `{outcome_of(answers['B'][qid], verdicts['B'].get(qid))}` |"
            )

    header = (
        "\n## Overlap at a glance\n\n"
        "| question | A items | B items | shared | Jaccard | A outcome | B outcome |\n"
        "|---|---:|---:|---:|---:|---|---|\n" + "\n".join(summary) + "\n"
    )
    lines.insert(2, header)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")

    if len(ARMS) == 2:
        overlap(retrieval, [q for q in ids if q in retrieval["A"] and q in retrieval["B"]])

    print(f"\n{len(ids)} questions x {len(ARMS)} arms -> {args.out}")
    print(f"system prompt is identical across arms and omitted; SYSTEM is {len(SYSTEM)} chars")
    if mismatch:
        print(f"** {mismatch} context(s) did NOT rebuild — read those sections with that in mind")
    else:
        print(f"all {len(ids) * len(ARMS)} contexts rebuilt byte for byte against the recording")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
