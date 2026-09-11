#!/usr/bin/env python
"""E-009 — does the model refuse when the evidence is absent?

Registered 2026-08-15, amended twice. E-007 measured **8 of 9** subgraphs
labelled `insufficient` answered rather than refused; E-008 measured 12 of 12
probes following the graph over parametric memory. Those are compatible and
they are not the same question: **overriding fiction that is present is not
what happens when evidence is absent.**

Three arms, and the registered design turns on the differences between them:

    control       the question with its gold rule present
    ablated       the same question with that rule removed **before
                  serialization**, everything else identical
    natural_thin  E-007's `insufficient` subgraphs, replayed unchanged

**The ablation must be invisible to the prompt** (amendment 2026-08-15b, item
1). `subgraph.py` appends a NOTICE whenever `dropped` or `capped` is non-empty,
telling the model to say so if the answer depends on what is missing. An
ablated arm carrying that string and a control arm not carrying it would
measure obedience to a sentence rather than detection of absent evidence. So
the rule is removed by rebuilding the evidence list, `dropped` and `capped` are
asserted identical, and `build` **refuses to admit a probe whose two
serializations differ anywhere except the removed item**.

**Ablation is not absence** (threat, registered). A rule removed from the
evidence may still be reconstructible from a ruling or an oracle text that
stayed. Every probe is checked for the rule number appearing anywhere in the
ablated context; one that fails is admitted as `retrieval_artefact` rather than
silently leaking.

**Nine probes exist, and six are definitions** (amendment 2026-09-11). The 0.80
floor is on the point estimate so a verdict is produced, and one probe flips
it. The report prints the interval and the stratum composition beside every
figure, and refuses to describe the number as establishing anything.

**The coding is a person's.** `generate` writes answers; it does not label
them. The five outcome codes were registered before any answer existed and
`code` records one per probe, from the evidence rather than from knowing Magic.

Usage:
    python scripts/run_e009.py build      # construct and verify probes
    python scripts/run_e009.py generate   # ~27 calls
    python scripts/run_e009.py show       # one answer beside its context
    python scripts/run_e009.py code <id> <arm> <outcome> --why '...'
    python scripts/run_e009.py report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.generation.answerer import PROMPT_VERSION, SYSTEM, answer
from graphrag_mtg.retrieval.subgraph import Evidence, Outcome, Subgraph, serialize

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

PROBES = Path("data/interim/e009_probes.jsonl")
ANSWERS = Path("runs/e009_answers.jsonl")
CODES = Path("data/interim/e009_codes.jsonl")

#: The retrieval record probes are built from. Named, not globbed: a probe
#: built from arm A's retrieval and one from arm C's are different constructs,
#: and the 2026-09-11 amendment refuses to widen the pool by mixing them.
SOURCE = Path("runs/e001_C-vector-hybrid-routed_retrieval_dev.jsonl")

ARMS = ("control", "ablated", "natural_thin")

#: Registered 2026-08-15, before any answer existed.
OUTCOMES = (
    "refused",
    "answered_from_memory",
    "answered_wrong",
    "hedged",
    "retrieval_artefact",
    # Added 2026-09-11c, after answers existed, and admissible only because
    # of the firewall in that amendment: `answered_grounded` is a **control
    # arm** code, the control arm carries no floor, and the gated quantity —
    # the ablated arm's refusal rate — cannot be touched by it. The five
    # codes above were all written for the ablated arm and left the control's
    # normal behaviour, answering correctly from evidence that was present,
    # with nowhere to go.
    "answered_grounded",
)

#: Amendment 2026-08-15b item 3: `hedged` is **not** in the numerator, and
#: `refused + hedged` is reported beside it under its own name.
IN_DENOMINATOR = ("refused", "answered_from_memory", "answered_wrong", "hedged")

#: Control-arm only, and refused there by `code` on any other arm. A grounded
#: answer is not a possible outcome of a probe whose evidence was ablated.
CONTROL_ONLY = ("answered_grounded",)

FLOOR = 0.80


def gold_rules() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(Path("data/golden").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("id") and row.get("gold_cr_rules"):
                found.setdefault(row["id"], [str(r) for r in row["gold_cr_rules"]])
    return found


def strata() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(Path("data/golden").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") and row.get("stratum"):
                    found.setdefault(row["id"], row["stratum"])
    return found


def covers(want: str, key: str) -> bool:
    """Retrieval-side coverage: a parent satisfies a subrule and vice versa."""
    return key == want or key.startswith(want) or want.startswith(key)


def ablatable(want: str, keys: set[str]) -> bool:
    """Whether the gold rule can be removed **without removing more**.

    Coverage and ablation are not the same relation, and conflating them was
    the first defect this harness caught. Retrieval counts `702.140` as
    reaching `702.140a`, because the parent's text carries the child. But
    removing the parent removes its whole subtree, and the registry reserves
    `retrieval_artefact` for exactly "the ablation removed more or less than
    intended". So a probe is admissible only when the gold rule is present as
    its **own key**; coverage-by-parent is not enough.
    """
    return want in keys


def rebuild(row: dict, *, drop: str | None = None) -> Subgraph:
    """A Subgraph from a stored retrieval record, optionally minus one rule.

    The removal happens here, on the evidence list, **before** anything is
    serialized — which is what keeps `dropped` and `capped` untouched and the
    NOTICE in the same state on both arms.
    """
    subgraph = Subgraph(
        question=row.get("question", ""),
        outcome=Outcome.RESOLVED,
        note=row.get("note", ""),
    )
    for item in row["evidence"]:
        # Exact key only — see `ablatable`. Dropping by `covers` would take
        # the parent and its whole subtree with it.
        if drop and item["kind"] == "rule" and item["key"] == drop:
            continue
        subgraph.evidence.append(
            Evidence(
                kind=item["kind"],
                key=item["key"],
                text=item["text"],
                template=item["template"],
                path=item["path"],
                distance=item["distance"],
            )
        )
    subgraph.templates_run = list(row.get("templates_run") or [])
    subgraph.dropped.update(row.get("dropped") or {})
    subgraph.capped.update(row.get("capped") or {})
    return subgraph


def question_text(qid: str, row: dict) -> str:
    if row.get("question"):
        return row["question"]
    for cache in (Path("data/interim/e007_cache"), Path("data/interim/golden_cache")):
        path = cache / f"{qid}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = payload.get("questionSimple") or payload.get("question") or ""
            if text:
                return text
    # Authored questions carry their text inline in the versioned golden set;
    # only the RulesGuru rows keep it in the gitignored cache.
    for name in sorted(Path("data/golden").glob("*.jsonl")):
        for line in name.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("id") == qid and row.get("question"):
                    return row["question"]
    return ""


def differs_only_by(control: str, ablated: str, rule: str) -> str | None:
    """Why the two serializations differ, beyond the removed item.

    Reconstruction, not pattern matching. Two earlier attempts failed here
    and both failures were the verifier's, not the construct's: filtering
    every control line containing the rule number also deleted lines that
    survive into the ablated arm, and matching the `via` line by pattern
    missed that a subrule's path names its **parent**, not itself.

    So the expected ablated text is built by walking the control and dropping
    exactly the removed item's two lines — its handle line and the `via` line
    that follows it — plus any section header left with nothing under it.
    Anything else is a difference the experiment did not manipulate.
    """
    control_lines = control.splitlines()
    expected: list[str] = []
    skip_next = False
    for index, line in enumerate(control_lines):
        if skip_next:
            skip_next = False
            continue
        if line.startswith(f"[rule:{rule}]"):
            skip_next = True  # the `via` line belongs to this item
            continue
        expected.append(line)

    # A header whose section emptied goes with it.
    pruned: list[str] = []
    for index, line in enumerate(expected):
        if line.startswith("## "):
            following = expected[index + 1 : index + 2]
            if not following or following[0].startswith("## "):
                continue
        pruned.append(line)

    if ("NOTICE" in control) != ("NOTICE" in ablated):
        return "the NOTICE appears in one arm and not the other"
    if pruned == ablated.splitlines():
        return None
    if len(control_lines) == len(ablated.splitlines()):
        return "the two serializations are the same length — the rule was never removed"
    return "the serializations differ beyond the removed item's own lines"


def build(args: argparse.Namespace) -> int:
    gold, stratum = gold_rules(), strata()
    rows = {
        json.loads(line)["question_id"]: json.loads(line)
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    probes: list[dict] = []
    for qid, row in rows.items():
        if qid not in gold:
            continue
        keys = {e["key"] for e in row["evidence"] if e["kind"] == "rule"}
        reached = [w for w in gold[qid] if any(covers(w, k) for k in keys)]
        exact = [w for w in reached if ablatable(w, keys)]
        if not exact:
            if reached:
                print(f"  {qid}: gold {reached} reached only through a parent rule; "
                      "not ablatable without removing more")
            continue
        target = exact[0]
        question = question_text(qid, row)
        if not question:
            print(f"  {qid}: no question text; skipped")
            continue

        control = rebuild(row)
        ablated = rebuild(row, drop=target)
        control_text = serialize(control, notice=True)
        ablated_text = serialize(ablated, notice=True)

        reason = differs_only_by(control_text, ablated_text, target)
        # Ablation is not absence: the rule number may survive inside a
        # ruling or an oracle text that stayed. That is not a leak to hide,
        # it is an outcome code the registry already reserved.
        # Two different signals, reported apart. A bare cross-reference
        # ("See rule 702.19") leaves the number without the content, and is
        # a far weaker cue than the rule's own sentence surviving inside a
        # ruling. Only the second is reconstructibility; the coder decides.
        rule_text = next(
            (e["text"] for e in row["evidence"] if e["kind"] == "rule" and e["key"] == target),
            "",
        )
        probe_text = " ".join(rule_text.split())[:60]
        artefact = bool(probe_text) and probe_text in " ".join(ablated_text.split())
        number_only = (target in ablated_text) and not artefact
        probes.append(
            {
                "question_id": qid,
                "question": question,
                "stratum": stratum.get(qid),
                "ablated_rule": target,
                "gold_rules": gold[qid],
                "admitted": reason is None,
                "refused_because": reason,
                "rule_text_survives_in_context": artefact,
                "rule_number_only_survives": number_only,
                "notice_present": "NOTICE" in control_text,
                "evidence_n_control": len(control.evidence),
                "evidence_n_ablated": len(ablated.evidence),
                "dropped": dict(control.dropped),
                "capped": dict(control.capped),
                "context_control": control_text,
                "context_ablated": ablated_text,
            }
        )

    # The third arm: replayed unchanged, carrying no ablation cue. By the
    # 2026-08-15b amendment the 0.80 floor does not apply to it, and by the
    # 2026-09-11 amendment it is the more informative half.
    natural = json.loads(Path("data/golden/e007_sufficiency.json").read_text(encoding="utf-8"))
    labels = natural.get("labels", {})
    thin = [q for q, v in labels.items() if (v.get("label") if isinstance(v, dict) else v) == "insufficient"]
    e007 = {
        json.loads(line)["question_id"]: json.loads(line)
        for line in Path("runs/e007_retrieval.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    for qid in thin:
        row = e007.get(qid)
        if row is None:
            continue
        subgraph = rebuild(row)
        probes.append(
            {
                "question_id": qid,
                "question": question_text(qid, row),
                "stratum": stratum.get(qid),
                "ablated_rule": None,
                "gold_rules": gold.get(qid, []),
                "admitted": True,
                "refused_because": None,
                "rule_text_survives_in_context": False,
                "rule_number_only_survives": False,
                "notice_present": "NOTICE" in serialize(subgraph, notice=True),
                "evidence_n_control": len(subgraph.evidence),
                "evidence_n_ablated": len(subgraph.evidence),
                "dropped": dict(subgraph.dropped),
                "capped": dict(subgraph.capped),
                "context_control": None,
                "context_ablated": serialize(subgraph, notice=True),
                "natural_thin": True,
            }
        )

    PROBES.parent.mkdir(parents=True, exist_ok=True)
    with PROBES.open("w", encoding="utf-8") as handle:
        for probe in probes:
            handle.write(json.dumps(probe, ensure_ascii=False) + "\n")

    ablation = [p for p in probes if not p.get("natural_thin")]
    admitted = [p for p in ablation if p["admitted"]]
    print(f"{PROBES}: {len(ablation)} ablation probe(s), {len(admitted)} admitted; "
          f"{len(probes) - len(ablation)} natural_thin.")
    for probe in ablation:
        if not probe["admitted"]:
            print(f"  refused {probe['question_id']}: {probe['refused_because']}")
        elif probe["rule_text_survives_in_context"]:
            print(f"  {probe['question_id']}: the TEXT of {probe['ablated_rule']} survives "
                  "elsewhere in the context — code it `retrieval_artefact`")
        elif probe["rule_number_only_survives"]:
            print(f"  {probe['question_id']}: only the NUMBER {probe['ablated_rule']} survives "
                  "(a bare cross-reference, no content) — admitted, noted on the probe")
    print(f"\nstrata: {dict(Counter(p['stratum'] or '?' for p in admitted))}")
    print("Six of nine being definitions is registered in the 2026-09-11 amendment,")
    print("not a surprise to discover at report time.")
    return 0


def generate(args: argparse.Namespace) -> int:
    probes = [
        json.loads(line)
        for line in PROBES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    work = [(p, arm) for p in probes if p["admitted"]
            for arm in (("natural_thin",) if p.get("natural_thin") else ("control", "ablated"))]
    print(f"{len(work)} generation(s), prompt {PROMPT_VERSION} — the object under test, not a variable.")
    if args.dry_run:
        print("Dry run: nothing sent.")
        return 0

    from graphrag_mtg.extraction.llm import LlmClient

    client = LlmClient(model=args.model, max_tokens=args.max_tokens, temperature=0.0)
    ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with ANSWERS.open("w", encoding="utf-8") as handle:
        for probe, arm in work:
            key = "context_control" if arm == "control" else "context_ablated"
            context = probe[key]
            subgraph = Subgraph(question=probe["question"], outcome=Outcome.RESOLVED)
            subgraph.evidence.append(
                Evidence(kind="rule", key="prebuilt", text=context,
                         template="e009", path="e009", distance=0)
            )
            result = answer(
                probe["question"],
                subgraph,
                lambda system, prompt: client.complete_text(prompt, system=system),
                system=SYSTEM,
                notice=False,
                model=client.model,
            )
            handle.write(
                json.dumps(
                    {
                        "question_id": probe["question_id"],
                        "arm": arm,
                        "stratum": probe["stratum"],
                        "ablated_rule": probe["ablated_rule"],
                        "notice_present": probe["notice_present"],
                        "text": result.text,
                        "refused_by_rule": result.refused,
                        "model": client.model,
                        "prompt_version": PROMPT_VERSION,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"wrote {ANSWERS}")
    print("\nNothing is labelled. Run `show`, then `code` — the outcome codes are")
    print("assigned by a person, from the evidence rather than from knowing Magic.")
    return 0


def _codes() -> dict[tuple[str, str], dict]:
    if not CODES.exists():
        return {}
    out = {}
    for line in CODES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[(row["question_id"], row["arm"])] = row
    return out


def show(args: argparse.Namespace) -> int:
    answers = [json.loads(l) for l in ANSWERS.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = _codes()
    pending = [a for a in answers if (a["question_id"], a["arm"]) not in done]
    if args.question_id:
        pending = [a for a in answers if a["question_id"] == args.question_id]
    if not pending:
        print("Every answer is coded. Run `report`.")
        return 0
    for row in pending[: args.limit]:
        print(RULE)
        print(f"{row['question_id']}   arm {row['arm']}   stratum {row['stratum']}")
        print(f"  ablated rule: {row['ablated_rule']}   NOTICE in context: {row['notice_present']}")
        print(f"\nANSWER\n  {' '.join(row['text'].split())[:1200]}")
    print(RULE)
    print(f"{len([a for a in answers if (a['question_id'], a['arm']) not in done])} left.")
    print(f"  code <id> <arm> <{'|'.join(OUTCOMES)}> --why '...'")
    return 0


def code(args: argparse.Namespace) -> int:
    if args.outcome not in OUTCOMES:
        raise SystemExit(f"{args.outcome} is not one of {', '.join(OUTCOMES)}")
    if args.outcome in CONTROL_ONLY and args.arm != "control":
        raise SystemExit(
            f"`{args.outcome}` is a control-arm code. On `{args.arm}` the evidence was "
            "ablated or naturally thin, so an answer grounded in the missing rule is "
            "not a possible outcome — and allowing it there would let a code added "
            "after the answers existed reach the gated quantity."
        )
    CODES.parent.mkdir(parents=True, exist_ok=True)
    rows = _codes()
    rows[(args.question_id, args.arm)] = {
        "question_id": args.question_id,
        "arm": args.arm,
        "outcome": args.outcome,
        "why": args.why,
    }
    with CODES.open("w", encoding="utf-8") as handle:
        for row in rows.values():
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{args.question_id}/{args.arm} -> {args.outcome}")
    return 0


def report(args: argparse.Namespace) -> int:
    coded = list(_codes().values())
    if not coded:
        raise SystemExit("Nothing coded yet.")
    answers = {
        (json.loads(l)["question_id"], json.loads(l)["arm"]): json.loads(l)
        for l in ANSWERS.read_text(encoding="utf-8").splitlines() if l.strip()
    }
    print(f"prompt {PROMPT_VERSION}   floor {FLOOR:.2f} on the point estimate, ablated arm only")
    print(RULE)
    for arm in ARMS:
        rows = [c for c in coded if c["arm"] == arm]
        if not rows:
            continue
        counts = Counter(c["outcome"] for c in rows)
        denominator = sum(counts[o] for o in IN_DENOMINATOR)
        refused = counts["refused"]
        print(f"  {arm}   n={len(rows)}   {dict(counts)}")
        if denominator:
            interval = wilson_interval(refused, denominator)
            plus = wilson_interval(refused + counts["hedged"], denominator)
            print(f"    refusal rate {refused}/{denominator} = {refused/denominator:.3f} "
                  f"[{interval.low:.3f}, {interval.high:.3f}]"
                  + (f"   {'PASSES' if refused/denominator >= FLOOR else 'BELOW'} the floor"
                     if arm == "ablated" else "   (no floor applies)"))
            print(f"    refused+hedged {refused + counts['hedged']}/{denominator} = "
                  f"{(refused + counts['hedged'])/denominator:.3f} "
                  f"[{plus.low:.3f}, {plus.high:.3f}]")
        strata_here = Counter(answers[(c["question_id"], c["arm"])]["stratum"] or "?" for c in rows)
        print(f"    strata: {dict(strata_here)}")
    print(RULE)
    print("Condition (2): the control arm must answer. A system that refuses")
    print("everything passes condition (1) and is worthless.")
    print("\nNine probes, six of them definitions. The interval is printed because")
    print("one probe flips the verdict; no sentence may call this an established rate.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="construct and verify probes")
    b.set_defaults(func=build)

    g = sub.add_parser("generate", help="run the shipped prompt over every admitted probe")
    g.add_argument("--model", default=None)
    g.add_argument("--max-tokens", type=int, default=700)
    g.add_argument("--dry-run", action="store_true")
    g.set_defaults(func=generate)

    s = sub.add_parser("show", help="one uncoded answer")
    s.add_argument("question_id", nargs="?", default=None)
    s.add_argument("--limit", type=int, default=1)
    s.set_defaults(func=show)

    c = sub.add_parser("code", help="record one outcome")
    c.add_argument("question_id")
    c.add_argument("arm", choices=ARMS)
    c.add_argument("outcome", choices=OUTCOMES)
    c.add_argument("--why", default="")
    c.set_defaults(func=code)

    r = sub.add_parser("report", help="refusal rate per arm, with intervals")
    r.set_defaults(func=report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
