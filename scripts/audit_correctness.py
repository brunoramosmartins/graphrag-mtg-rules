#!/usr/bin/env python
"""The correctness ceiling: two blind human passes, days apart.

E-011 fixes the judge's pass mark as the lower bound of a human
self-agreement interval and forbids any other mapping. That threshold is
therefore an instrument reading, and this is the instrument. Nothing here
scores the system: every number it prints describes the annotator.

    build              pass 1 worksheet over dress-rehearsal answers
    show / set         label one answer at a time, key beside it
    freeze             lock pass 1 and start the clock
    reaudit build      pass 2, blank, refused before the clock has run
    reaudit score      exact agreement, the interval, the threshold

The pool is E-007's 42 RulesGuru questions, which `build` verifies are
disjoint from E-001's evaluation split before it writes anything. That
guard is the point of the command: a ceiling measured on questions the
head-to-head will later be scored on would leak the evaluation set into
the instrument that grades it, and no downstream check could see it.

Usage:
    python scripts/audit_correctness.py build
    python scripts/audit_correctness.py show --next
    python scripts/audit_correctness.py set rg-1049 correct
    python scripts/audit_correctness.py status
    python scripts/audit_correctness.py freeze
    ... at least 5 days later ...
    python scripts/audit_correctness.py reaudit build
    python scripts/audit_correctness.py reaudit score
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import textwrap
from datetime import date
from pathlib import Path

from graphrag_mtg.evaluation.metrics import wilson_interval
from graphrag_mtg.evaluation.rubric import (
    JUDGED,
    RUBRIC,
    RUBRIC_VERSION,
    Correctness,
    render_for_judgement,
    rubric_hash,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_golden import QUESTION_FILES, load_questions  # sibling script; path set above

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "─" * 78

#: The dress-rehearsal answers. Both E-007 sides, same model and prompt —
#: `build` refuses if that stops being true.
ANSWER_FILES = (
    Path("runs/e007_answers_audit.jsonl"),
    Path("runs/e007_answers_dev.jsonl"),
)
CACHE_DIR = Path("data/interim/e007_cache")
GOLDEN_DIR = Path("data/golden")
PHASE4_SPLIT = Path("data/golden/phase4_dev_ids.json")

PASS1_PATH = Path("data/golden/p6_correctness_m1.json")
PASS2_PATH = Path("data/golden/p6_correctness_m2.json")

#: Registered in E-011: the second pass is a second *judgement*, not a
#: recollection of the first. Days, not hours.
MIN_DAYS = 5

#: Registered in E-011: below 30 judged answers the ceiling is reported
#: descriptively and gates nothing.
CEILING_FLOOR = 30

#: Registered in E-011: a ceiling whose lower bound falls below this leaves
#: correctness ungated, following the `sufficiency` precedent.
GATE_FLOOR = 0.70

LABELS = tuple(label.value for label in Correctness)


def wrap(text: str, indent: str = "  ") -> str:
    out = []
    for block in text.split("\n"):
        out.append(textwrap.fill(block, width=76, initial_indent=indent, subsequent_indent=indent))
    return "\n".join(out)


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"No answers at {path}. Generate the dress-rehearsal side first.")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cached(question_id: str, cache: Path) -> dict:
    """Question and answer key, from the gitignored cache.

    The committed pool carries ids and our own annotations only — the
    licence posture the golden set already uses — so RulesGuru's text and
    its answer key live here and never in the repo.
    """
    path = cache / f"{question_id}.json"
    if not path.exists():
        raise SystemExit(f"No cached text for {question_id} at {path}. Re-run the draw.")
    return json.loads(path.read_text(encoding="utf-8"))


def answers_fingerprint(answers: dict[str, dict]) -> str:
    """Hash the judged rendering, not the file.

    A label describes the prose the annotator read. Hashing the raw file
    would fire on a re-generation that produced identical text, and hashing
    the model's output before blinding would miss a change to the blinding
    itself — which is the one thing that alters what was read without
    altering what was written.
    """
    payload = "\n".join(
        f"{qid}|{render_for_judgement(answers[qid]['text'])}" for qid in sorted(answers)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_worksheet(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"No worksheet at {path}. Run `build` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_worksheet(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def gather_answers(paths: tuple[Path, ...] | list[Path]) -> tuple[dict[str, dict], dict]:
    """Every dress-rehearsal answer, keyed by question, with its provenance.

    Raises:
        SystemExit: if the files disagree on model or prompt version. Two
            generators pooled into one ceiling would measure the annotator
            on a mixture, and the mixture is not what Phase 6 will judge.
    """
    answers: dict[str, dict] = {}
    provenance: set[tuple[str, str]] = set()
    for path in paths:
        for row in jsonl(path):
            if row["question_id"] in answers:
                raise SystemExit(
                    f"{row['question_id']} appears in two answer files. One answer per "
                    "question, or the worksheet does not know which prose was labelled."
                )
            answers[row["question_id"]] = row
            provenance.add((row.get("model", ""), row.get("prompt_version", "")))
    if len(provenance) > 1:
        listed = ", ".join(f"{m} / {p}" for m, p in sorted(provenance))
        raise SystemExit(
            f"The answer files mix generators: {listed}. A ceiling pooled across two "
            "of them describes neither."
        )
    model, prompt_version = next(iter(provenance))
    return answers, {"model": model, "prompt_version": prompt_version}


def evaluation_ids(golden_dir: Path, split: Path) -> set[str]:
    """E-001's evaluation split: the golden set minus its development draw."""
    rows = load_questions(golden_dir, QUESTION_FILES)
    everything = {row["id"] for row in rows}
    dev = set(json.loads(split.read_text(encoding="utf-8"))["dev_ids"])
    return everything - dev


def build(args: argparse.Namespace) -> int:
    """Write the blank pass-1 worksheet, after the contamination guard."""
    if args.out.exists() and not args.force:
        raise SystemExit(
            f"{args.out} already exists — refusing to overwrite a pass in progress. "
            "Rebuilding after labelling has started would let the sample follow the labels."
        )

    answers, provenance = gather_answers(args.answers)

    # The guard this command exists for. An id on both sides would make the
    # ceiling a function of the questions it is later used to grade.
    forbidden = sorted(set(answers) & evaluation_ids(args.golden, args.split))
    if forbidden:
        raise SystemExit(
            f"{len(forbidden)} answer(s) are in E-001's evaluation split: "
            f"{', '.join(forbidden[:5])}. The ceiling cannot be measured on questions the "
            "head-to-head will be scored on."
        )

    refused = sorted(qid for qid, row in answers.items() if row.get("refused"))
    eligible = sorted(set(answers) - set(refused))
    if args.n:
        rng = random.Random(args.seed)
        eligible = sorted(rng.sample(eligible, min(args.n, len(eligible))))

    order = list(eligible)
    random.Random(args.seed).shuffle(order)

    meta = {
        "pass": "m1",
        "frozen": False,
        "rubric_version": RUBRIC_VERSION,
        "rubric_hash": rubric_hash(),
        "seed": args.seed,
        "drawn_at": date.today().isoformat(),
        "frozen_at": None,
        "sources": [str(p) for p in args.answers],
        "answers_sha256": answers_fingerprint({q: answers[q] for q in eligible}),
        "model": provenance["model"],
        "prompt_version": provenance["prompt_version"],
        "pool": {"total": len(answers), "refused": len(refused), "eligible": len(eligible)},
        "refused_ids": refused,
        "order": order,
        "labels": {qid: {"label": "", "note": ""} for qid in eligible},
    }
    save_worksheet(args.out, meta)

    print(f"Wrote {len(eligible)} blank row(s) -> {args.out}")
    print(f"rubric {RUBRIC_VERSION} @ {rubric_hash()[:12]}   seed {args.seed}")
    print(f"answers {provenance['model']} / {provenance['prompt_version']}")
    print(f"pool {len(answers)} answer(s): {len(eligible)} judged, {len(refused)} refused")
    print("Refusals are excluded: both passes agree on them without judging anything,")
    print("which would inflate the very number that becomes the judge's pass mark.")
    print(f"Disjoint from E-001's evaluation split ({len(evaluation_ids(args.golden, args.split))} ids) — verified.")
    if len(eligible) < CEILING_FLOOR:
        print(f"\nWARNING: {len(eligible)} < {CEILING_FLOOR}. Below the registered floor this")
        print("ceiling is reported descriptively and gates nothing.")
    print(f"\nLabel them with:  show --next    then    set <id> <{'|'.join(LABELS)}>")
    return 0


def render(question_id: str, entry: dict, answer: dict, position: str) -> str:
    payload = cached(question_id, CACHE_DIR)
    question = payload.get("questionSimple") or payload.get("question") or ""
    key = payload.get("answerSimple") or payload.get("answer") or ""
    out = [
        RULE,
        f"{question_id}   {position}",
        RULE,
        "QUESTION",
        wrap(question),
        "",
        "ANSWER (citation handles stripped)",
        wrap(render_for_judgement(answer["text"])),
        "",
        "KEY — the only authority",
        wrap(key),
        "",
        f"current label: {entry.get('label') or '(none)'}",
        f"  set {question_id} <{'|'.join(LABELS)}>",
    ]
    return "\n".join(out)


def show(args: argparse.Namespace) -> int:
    """Print answers to judge. Reads only; `set` is what writes."""
    meta = load_worksheet(args.out)
    guard_blindness(args.out, meta)
    answers, _ = gather_answers([Path(p) for p in meta["sources"]])
    labels = meta["labels"]

    if args.rubric:
        print(RULE)
        print(RUBRIC)
        print(RULE)

    if args.id:
        if args.id not in labels:
            raise SystemExit(f"{args.id} is not in {args.out}.")
        chosen = [args.id]
    else:
        chosen = [q for q in meta["order"] if not (labels[q].get("label") or "").strip()]
        if not chosen:
            print(f"Every answer is labelled. Next: `freeze --out {args.out}`.")
            return 0
        chosen = chosen[: args.count]

    done = sum(1 for row in labels.values() if (row.get("label") or "").strip())
    for i, question_id in enumerate(chosen, start=1):
        print(
            render(
                question_id,
                labels[question_id],
                answers[question_id],
                f"[{i} of {len(chosen)} shown; {done}/{len(labels)} done]",
            )
        )
    print(RULE)
    return 0


def require_same_prose(first: dict) -> None:
    """Refuse if the judged rendering has moved since pass 1 was built.

    Recomputed from the live answer files rather than compared against the
    copy pass 2 carries — comparing a copy to its own source is a check
    that cannot fail. What can move underneath the two passes is the
    answers being regenerated, or `render_for_judgement` changing what a
    reader sees, and both show up here.

    Raises:
        SystemExit: if the current rendering does not hash to what pass 1
            recorded.
    """
    answers, _ = gather_answers([Path(p) for p in first["sources"]])
    live = answers_fingerprint({q: answers[q] for q in first["labels"]})
    if live != first["answers_sha256"]:
        raise SystemExit(
            "The prose has moved since pass 1 was built — the answers were regenerated, "
            "or the blinding changed what a reader sees. An agreement number would "
            "compare labels assigned to two different texts."
        )


def open_second_pass(source: Path) -> Path | None:
    """A second pass over ``source`` that still has unlabelled rows, if any.

    Found by reading each worksheet's own `source` field rather than by
    testing one hard-coded path. Tying the guard to `PASS2_PATH` meant any
    pair addressed through `--out` slipped past it, which is the same
    mistake one layer up: the guard named a file instead of the
    relationship it was protecting.
    """
    resolved = source.resolve()
    for candidate in sorted(source.parent.glob("*.json")):
        if candidate.resolve() == resolved:
            continue
        try:
            meta = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(meta, dict) or "source" not in meta or "labels" not in meta:
            continue
        if Path(meta["source"]).resolve() != resolved:
            continue
        if any(not (row.get("label") or "").strip() for row in meta["labels"].values()):
            return candidate
    return None


def withhold_marginals(path: Path, meta: dict) -> bool:
    """Whether `status` must hide pass 1's label mix.

    `show` was guarded and `status` was not, which left the aggregate
    reachable by a command nobody thinks of as revealing. Knowing that the
    first pass said `correct` nine times pulls the second toward saying it
    nine times — a weaker leak than per-row labels and the same kind. The
    guard that named one command rather than the property it protected is
    the guard that misses the second command.
    """
    return meta.get("pass") == "m1" and open_second_pass(path) is not None


def guard_blindness(path: Path, meta: dict) -> None:
    """Refuse to reveal pass 1 while pass 2 is still being labelled.

    Blindness is not a promise the annotator makes to themself; it is a
    property of what the tool will display. Reading the first pass's
    labels halfway through the second turns the remaining rows into
    recall, and the agreement number would no longer describe the
    instrument.
    """
    if meta.get("pass") != "m1":
        return
    second = open_second_pass(path)
    if second is not None:
        raise SystemExit(
            f"{second} still has unlabelled rows. Showing {path} now would put the "
            "first pass's labels in front of the second's remaining rows."
        )


def set_label(args: argparse.Namespace) -> int:
    """Record one correctness label, validated, without hand-editing JSON."""
    meta = load_worksheet(args.out)
    if meta.get("frozen"):
        raise SystemExit(
            f"{args.out} is frozen. Labels cannot move after freezing — that is what "
            "makes the second pass a second pass. If the freeze was a mistake, say so in "
            "the decision journal and re-run the whole pass."
        )
    if args.question_id not in meta["labels"]:
        raise SystemExit(f"{args.question_id} is not in {args.out}.")
    entry = meta["labels"][args.question_id]
    previous = entry.get("label") or ""
    entry["label"] = args.label
    if args.note:
        entry["note"] = args.note
    save_worksheet(args.out, meta)
    done = sum(1 for row in meta["labels"].values() if (row.get("label") or "").strip())
    note = f" (was {previous})" if previous and previous != args.label else ""
    print(f"{args.question_id}: {args.label}{note}   [{done}/{len(meta['labels'])} done]")
    return 0


def flag_exposed(args: argparse.Namespace) -> int:
    """Record that a row's content was discussed outside the worksheet.

    Allowed on a frozen pass, because it changes no label — it changes what
    the score is permitted to claim. `reaudit score` then reports the
    ceiling twice, once over every row and once with these excluded, and
    both figures are pre-committed here rather than picked after the
    disagreements are visible.
    """
    meta = load_worksheet(args.out)
    if args.question_id not in meta["labels"]:
        raise SystemExit(f"{args.question_id} is not in {args.out}.")
    exposed = dict(meta.get("exposed", {}))
    exposed[args.question_id] = {"reason": args.reason, "recorded_at": date.today().isoformat()}
    meta["exposed"] = exposed
    save_worksheet(args.out, meta)
    print(f"{args.question_id}: flagged as exposed   [{len(exposed)} of {len(meta['labels'])}]")
    return 0


def status(args: argparse.Namespace) -> int:
    """What is labelled, the mix, and whether the floor is met."""
    meta = load_worksheet(args.out)
    labels = meta["labels"]
    hide = withhold_marginals(args.out, meta)
    counts: dict[str, int] = {}
    pending: list[str] = []
    # Walk the worksheet's own order, so the ids named here are the ones
    # `show --next` will actually put in front of the annotator.
    for question_id in meta["order"]:
        value = (labels[question_id].get("label") or "").strip()
        if not value:
            pending.append(question_id)
        else:
            counts[value] = counts.get(value, 0) + 1

    print(f"{args.out}   pass {meta['pass']}   rubric {meta['rubric_version']}")
    print(f"drawn {meta['drawn_at']}   frozen {meta.get('frozen_at') or 'no'}")
    print(RULE)
    if hide:
        print("  label mix withheld: a second pass is open, and knowing the first pass's")
        print("  marginals biases the second toward reproducing them.")
    else:
        for label in LABELS:
            print(f"  {label:<12} {counts.get(label, 0)}")
    print(f"  {'unlabelled':<12} {len(pending)}")
    print(RULE)
    judged = sum(counts.get(label.value, 0) for label in JUDGED)
    if not hide:
        print(f"judged {judged}   void {counts.get(Correctness.VOID.value, 0)}   "
              f"refused (excluded at build) {meta['pool']['refused']}")
        if judged and judged < CEILING_FLOOR:
            print(f"Below the registered floor of {CEILING_FLOOR} — descriptive only, gates nothing.")
    if meta.get("exposed"):
        print(f"exposed rows recorded: {len(meta['exposed'])} — the score reports with and without.")
    if pending:
        print(f"\nnext: {', '.join(pending[:5])}")
    return 0


def freeze(args: argparse.Namespace) -> int:
    """Lock pass 1 and start the clock."""
    meta = load_worksheet(args.out)
    if meta.get("frozen"):
        print(f"{args.out} is already frozen ({meta.get('frozen_at')}).")
        return 0
    pending = [q for q, row in meta["labels"].items() if not (row.get("label") or "").strip()]
    if pending:
        raise SystemExit(f"{len(pending)} row(s) still unlabelled. Freezing now would lock a gap.")
    meta["frozen"] = True
    meta["frozen_at"] = date.today().isoformat()
    save_worksheet(args.out, meta)
    print(f"Frozen {args.out} on {meta['frozen_at']}.")
    print(f"The second pass may be built on or after "
          f"{date.fromordinal(date.today().toordinal() + MIN_DAYS).isoformat()} "
          f"({MIN_DAYS} days).")
    return 0


def reaudit_build(args: argparse.Namespace) -> int:
    """A blank second pass over the same rows, originals hidden."""
    first = load_worksheet(args.source)
    if not first.get("frozen"):
        raise SystemExit(f"{args.source} is not frozen. Freeze pass 1 before pass 2 exists.")
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} already exists — refusing to overwrite a pass in progress.")

    elapsed = date.today().toordinal() - date.fromisoformat(first["frozen_at"]).toordinal()
    if elapsed < args.min_days and not args.force:
        raise SystemExit(
            f"{elapsed} day(s) since pass 1 was frozen; {args.min_days} are registered. "
            "A second pass taken too soon measures recall, not judgement, and it inflates "
            "the ceiling that becomes the judge's pass mark."
        )
    if rubric_hash() != first["rubric_hash"]:
        raise SystemExit(
            "The rubric has changed since pass 1. Two passes under two rubrics are two "
            "instruments, and their agreement is not a ceiling."
        )
    require_same_prose(first)

    order = sorted(first["labels"])
    random.Random(args.seed).shuffle(order)
    meta = {
        "pass": "m2",
        "frozen": False,
        "rubric_version": first["rubric_version"],
        "rubric_hash": first["rubric_hash"],
        "seed": args.seed,
        "drawn_at": date.today().isoformat(),
        "frozen_at": None,
        "source": str(args.source),
        "source_frozen_at": first["frozen_at"],
        "elapsed_days": elapsed,
        "sources": first["sources"],
        "answers_sha256": first["answers_sha256"],
        "model": first["model"],
        "prompt_version": first["prompt_version"],
        "pool": first["pool"],
        "refused_ids": first["refused_ids"],
        "order": order,
        "labels": {qid: {"label": "", "note": ""} for qid in order},
    }
    save_worksheet(args.out, meta)
    print(f"Wrote {len(order)} blank row(s) -> {args.out}")
    print(f"{elapsed} day(s) since pass 1 was frozen ({first['frozen_at']}).")
    print("Pass 1's labels are recorded, not copied — a worksheet carrying the answer")
    print("is not a blind pass. Presentation order is reshuffled at a new seed.")
    print(f"Label them with:  show --out {args.out} --next")
    return 0


def reaudit_score(args: argparse.Namespace) -> int:
    """Exact agreement between the two passes, and the threshold it fixes."""
    second = load_worksheet(args.out)
    pending = [q for q, row in second["labels"].items() if not (row.get("label") or "").strip()]
    if pending:
        raise SystemExit(
            f"{len(pending)} row(s) still unlabelled. Scoring now would let the rest be "
            "labelled against a visible agreement rate."
        )
    first = load_worksheet(Path(second["source"]))
    require_same_prose(first)

    pairs = [
        (q, first["labels"][q]["label"], second["labels"][q]["label"]) for q in second["order"]
    ]
    # Void is not a judgement about the answer, and E-011 excludes it from
    # every denominator. Declared here rather than discovered later.
    scored = [(q, a, b) for q, a, b in pairs if Correctness.VOID.value not in (a, b)]
    voided = len(pairs) - len(scored)

    agreed = [a == b for _, a, b in scored]
    interval = wilson_interval(sum(agreed), len(agreed))
    print(f"rubric {second['rubric_version']} @ {second['rubric_hash'][:12]}")
    print(f"{second['elapsed_days']} day(s) between passes   "
          f"{second['model']} / {second['prompt_version']}")
    print(RULE)
    print(f"exact agreement {sum(agreed)}/{len(agreed)} = {interval.point:.3f} "
          f"[{interval.low:.3f}, {interval.high:.3f}]")
    if voided:
        print(f"{voided} row(s) excluded: one or both passes called the key void.")
    print(f"refused and excluded at build: {second['pool']['refused']}")

    # Pre-committed at flag time, not chosen here: a row whose content was
    # argued about outside the worksheet may agree for a reason that is not
    # the annotator's consistency. Both figures print; neither is "the"
    # number until the registry's rule picks one.
    exposed = set(first.get("exposed", {}))
    if exposed:
        clean = [a == b for q, a, b in scored if q not in exposed]
        clean_interval = wilson_interval(sum(clean), len(clean))
        print(f"excluding {len(exposed)} exposed row(s): {sum(clean)}/{len(clean)} = "
              f"{clean_interval.point:.3f} [{clean_interval.low:.3f}, {clean_interval.high:.3f}]")
        interval, agreed = clean_interval, clean

    # Void-involving pairs are listed apart from the scored disagreements.
    # Printing them together reads as a contradiction beside a 7/7, and it
    # conflates two different events: changing one's mind about the answer,
    # and changing one's mind about whether the key answers its question.
    disagreements = [(q, a, b) for q, a, b in scored if a != b]
    if disagreements:
        print("\ndisagreements (pass 1 -> pass 2):")
        for question, before, after in disagreements:
            mark = "  [exposed]" if question in exposed else ""
            print(f"  {question}: {before} -> {after}{mark}")
    void_moves = [
        (q, a, b)
        for q, a, b in pairs
        if a != b and Correctness.VOID.value in (a, b)
    ]
    if void_moves:
        print("\nvoid reassessments, excluded from the denominator:")
        for question, before, after in void_moves:
            print(f"  {question}: {before} -> {after}")

    print(RULE)
    if len(agreed) < CEILING_FLOOR:
        print(f"{len(agreed)} judged rows < the registered floor of {CEILING_FLOOR}.")
        print("Reported descriptively; correctness is NOT gated by this ceiling.")
    elif interval.low < GATE_FLOOR:
        print(f"lower bound {interval.low:.3f} < {GATE_FLOOR:.2f}: per E-011 correctness is")
        print("NOT gated, and the head-to-head is published with this ceiling beside it.")
    else:
        print(f"judge threshold = {interval.low:.3f}")
        print("The judge passes only if the lower bound of its agreement interval reaches")
        print("this. No other mapping is permitted — E-011 fixed that before the number.")
    print("\nThis describes the annotator, not the system.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    builder = sub.add_parser("build", help="pass 1 worksheet over dress-rehearsal answers")
    builder.add_argument("--answers", type=Path, nargs="+", default=list(ANSWER_FILES))
    builder.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    builder.add_argument("--split", type=Path, default=PHASE4_SPLIT)
    builder.add_argument("--out", type=Path, default=PASS1_PATH)
    builder.add_argument("--n", type=int, default=0, help="0 = every eligible answer")
    builder.add_argument("--seed", type=int, default=20260904)
    builder.add_argument("--force", action="store_true")
    builder.set_defaults(func=build)

    shower = sub.add_parser("show", help="one answer beside its key")
    shower.add_argument("--out", type=Path, default=PASS1_PATH)
    shower.add_argument("--id")
    shower.add_argument("--next", dest="next_", action="store_true")
    shower.add_argument("--count", type=int, default=1)
    shower.add_argument("--rubric", action="store_true", help="print the rubric first")
    shower.set_defaults(func=show)

    setter = sub.add_parser("set", help="record one correctness label")
    setter.add_argument("question_id")
    setter.add_argument("label", choices=LABELS)
    setter.add_argument("--note", default="")
    setter.add_argument("--out", type=Path, default=PASS1_PATH)
    setter.set_defaults(func=set_label)

    flg = sub.add_parser("flag", help="record that a row was discussed outside the worksheet")
    flg.add_argument("question_id")
    flg.add_argument("--reason", required=True)
    flg.add_argument("--out", type=Path, default=PASS1_PATH)
    flg.set_defaults(func=flag_exposed)

    stat = sub.add_parser("status", help="progress, the mix, and the floor")
    stat.add_argument("--out", type=Path, default=PASS1_PATH)
    stat.set_defaults(func=status)

    frz = sub.add_parser("freeze", help="lock a pass and start the clock")
    frz.add_argument("--out", type=Path, default=PASS1_PATH)
    frz.set_defaults(func=freeze)

    re_ = sub.add_parser("reaudit", help="the blind second pass")
    re_sub = re_.add_subparsers(dest="reaudit_command", required=True)

    rb = re_sub.add_parser("build", help="blank second worksheet, originals hidden")
    rb.add_argument("--source", type=Path, default=PASS1_PATH)
    rb.add_argument("--out", type=Path, default=PASS2_PATH)
    rb.add_argument("--min-days", type=int, default=MIN_DAYS)
    rb.add_argument("--seed", type=int, default=20260909)
    rb.add_argument("--force", action="store_true")
    rb.set_defaults(func=reaudit_build)

    rs = re_sub.add_parser("score", help="exact agreement and the threshold it fixes")
    rs.add_argument("--out", type=Path, default=PASS2_PATH)
    rs.set_defaults(func=reaudit_score)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
