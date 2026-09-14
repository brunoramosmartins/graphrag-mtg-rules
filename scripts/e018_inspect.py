#!/usr/bin/env python
"""Render what each E-018 condition was sent, and what it answered.

Registered as a deliverable in the 2026-09-13 amendment, under standing rule 8:
no comparative evaluation is published without a manual sample of every outcome
category, read with the **final prompt as sent** in front of the reader. This
entry's whole result rests on two discordant pairs. Two cases are not a summary
statistic — they are two cases, and they can be read in full.

**The rebuild is verified, not assumed.** The run recorded `prompt_sha256` over
the system prompt and the user prompt together. This rebuilds the three
conditions from the same frozen inputs at the same seed and checks each digest;
a case whose digest disagrees is **refused, not shown with a caveat**, because
a prompt that differs from the one sent makes every reading of it fiction.

**The builder is chosen against those digests, not assumed.** The amendment
written for the secondary subset changed how the conditions are built, so the
working tree reproduces only 33 of this run's 60 prompts. `--builder auto`
rebuilds at `RUN_BUILDER_REV` when the working tree disagrees, and says which
builder rendered what. A run's prompts belong to the code that sent them.

`--flips` is the sample the entry needs: every question where a condition's
label differs from control's, which on this run is four questions across three
conditions, plus the ceiling's three `false` cases on request.

Usage:
    python scripts/e018_inspect.py --qid rg-271
    python scripts/e018_inspect.py --flips
    python scripts/e018_inspect.py --qid rg-271 --condition treatment --full
    python scripts/e018_inspect.py --qid rg-271 --builder head
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from graphrag_mtg.evaluation.rubric import render_for_judgement
from graphrag_mtg.generation.answerer import SYSTEM, prompt_digest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import load_jsonl
from e018_analysis import by_condition
from run_e018 import CONDITIONS, POPULATIONS, outputs
from run_eval import CACHE_DIR, GOLDEN_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

#: The revision whose `conditions_for` produced `runs/e018.jsonl`, measured
#: rather than remembered: at this revision all 60 condition-rows rebuild to
#: their recorded digest, and at HEAD 27 of them do not.
#:
#: The de-duplication amendment (726c651, written for the secondary subset)
#: changed `injectable`, the placebo pool, and whether `draw_placebo` is called
#: at all. Those change how much of the shared random stream each question
#: consumes, and `conditions_for` shuffles the merged evidence from that stream
#: in **every** condition — so a change meant for the secondary moved the
#: primary's control and treatment prompts too.
#:
#: This is not a version to migrate off. A rendering of E-018 is a rendering of
#: what was sent, and what was sent was built here. Later runs record their own
#: builder; this one predates the field.
RUN_BUILDER_REV = "598f200"
BUILDER_PATH = "scripts/run_e018.py"


def flipped(labels: dict[str, dict[str, str]]) -> list[str]:
    """Questions where any condition's label differs from control's.

    The sample standing rule 8 asks for. On a run resting on two discordant
    pairs, "every case that moved" is four questions — small enough to read in
    full, which is what the rule requires of a category with five or fewer.
    """
    return sorted(
        qid
        for qid, pair in labels.items()
        if "control" in pair and any(pair.get(name) != pair["control"] for name in CONDITIONS)
    )


def builder(revision: str | None):
    """The module that builds the three conditions, at HEAD or at a revision.

    Args:
        revision: a git revision to load `scripts/run_e018.py` from, or None
            for the working tree.

    Returns:
        The imported module, whose `prepare` rebuilds every condition.

    Raises:
        SystemExit: when the revision cannot be read, rather than silently
            falling back to a builder that produces different prompts.
    """
    if revision is None:
        import run_e018

        return run_e018
    try:
        source = subprocess.run(  # noqa: S603
            ["git", "show", f"{revision}:{BUILDER_PATH}"],  # noqa: S607
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(
            f"Cannot read {BUILDER_PATH} at {revision}: {error}.\n"
            "The prompts this run sent were built there and cannot be "
            "reconstructed without it."
        ) from error
    path = Path(tempfile.gettempdir()) / f"e018_builder_{revision}.py"
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location(f"run_e018_at_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def rebuild_at(revision: str | None, args: argparse.Namespace) -> dict[str, dict]:
    """Every question's three prompts, built by one builder, keyed by question.

    `--limit` here means "show at most N", never "rebuild the first N": the
    run's `--limit` truncates the frozen population, and reusing it would
    silently drop the question being asked for out of the rebuild.
    """
    namespace = argparse.Namespace(
        population=args.population, limit=0, golden=args.golden, caches=args.caches
    )
    prepared, _ = builder(revision).prepare(namespace)
    return {row["question_id"]: row for row in prepared}


def mismatches(
    built: dict[str, dict],
    scored: dict[str, dict[str, dict]],
    wanted: list[str],
    conditions: tuple[str, ...],
) -> int:
    """How many requested condition-rows rebuild to a digest the run did not record.

    Counted before anything is printed. A rendering that disagrees with the
    prompt hash is fiction, and finding that out one case at a time — with the
    first two already read — is finding it out too late.
    """
    bad = 0
    for qid in wanted:
        for name in conditions:
            row = scored.get(qid, {}).get(name)
            recorded = (row or {}).get("prompt_sha256")
            if recorded and qid in built:
                bad += prompt_digest(SYSTEM, built[qid]["prompts"][name]) != recorded
    return bad


def show(
    row: dict, scored: dict[str, dict], conditions: tuple[str, ...], full: bool
) -> int:
    """One question, every requested condition, prompt and answer.

    Returns:
        The number of conditions that did not render — a missing hash shown as
        an unverified reconstruction, or a digest mismatch shown as nothing at
        all. Both are counted, because a summary that reports "9 questions
        shown" while three of them printed no prompt is how a mismatch goes
        unnoticed. It did.
    """
    qid = row["question_id"]
    print(f"\n{RULE}")
    print(f"{qid}   gold rules: {', '.join(row['gold_cr_rules'])}")
    labels = "   ".join(f"{name}={scored[name]['label']}" for name in CONDITIONS if name in scored)
    print(f"labels: {labels}")
    print(f"\n{THIN}\nQUESTION\n{THIN}\n{row['question']}")
    print(f"\n{THIN}\nKEY — the only authority the judge has\n{THIN}\n{row['key']}")

    unverified = 0
    for name in conditions:
        if name not in scored:
            continue
        prompt = row["prompts"][name]
        digest = prompt_digest(SYSTEM, prompt)
        recorded = scored[name].get("prompt_sha256")
        print(f"\n{RULE}\nCONDITION: {name.upper()}   label {scored[name]['label']}")
        if recorded is None:
            unverified += 1
            print("RECONSTRUCTION, UNVERIFIED — the run recorded no prompt hash.")
        elif recorded != digest:
            unverified += 1
            print(f"** MISMATCH — recorded {recorded[:12]}, rebuilt {digest[:12]}. Skipped.")
            print("   The builder does not reproduce what was sent. Nothing below would be real.")
            continue
        else:
            print(f"VERIFIED against the recorded prompt hash ({digest[:12]}).")

        injected = scored[name].get("injected") or []
        if injected:
            cited = scored[name].get("cited_injected") or []
            print(f"INJECTED ({len(injected)}): {', '.join(injected)}")
            print(f"CITED BY THE ANSWER: {', '.join(cited) if cited else 'none'}")
        print(f"TOKENS: {scored[name]['tokens']}")

        if full:
            print(f"\n{THIN}\nSYSTEM PROMPT\n{THIN}\n{SYSTEM}")
        print(f"\n{THIN}\nUSER PROMPT — AS SENT\n{THIN}\n{prompt}")
        print(f"{THIN}\nWHAT THE MODEL RETURNED\n{THIN}\n{scored[name]['text']}")
        if scored[name].get("unknown_handles"):
            print(f"\n** FABRICATED CITATIONS: {scored[name]['unknown_handles']}")
        print(f"\n{THIN}\nWHAT THE JUDGE SAW, AND SAID\n{THIN}")
        print(render_for_judgement(scored[name]["text"]))
        print(f"\nVERDICT: {scored[name]['label']}")
        print(f"RATIONALE: {scored[name].get('rationale')}")
    return unverified


def build_parser() -> argparse.ArgumentParser:
    """The CLI, separated so the wiring to `prepare` can be tested.

    `prepare` reads `population`, `limit`, `golden` and `caches` off the
    namespace it is handed. This parser is the only thing that guarantees the
    first of those exists; when it did not, every invocation died on an
    `AttributeError` after the imports and before a single prompt was rendered.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--caches", type=Path, nargs="+", default=None)
    parser.add_argument(
        "--population",
        choices=sorted(POPULATIONS),
        default="primary",
        help="which frozen population to rebuild; must match the run being read",
    )
    parser.add_argument("--qid", default=None)
    parser.add_argument(
        "--flips", action="store_true", help="every question where a condition moved"
    )
    parser.add_argument("--condition", choices=(*CONDITIONS, "all"), default="all")
    parser.add_argument(
        "--full", action="store_true", help="print the system prompt too, once per condition"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="show at most N of the selected questions"
    )
    parser.add_argument(
        "--builder",
        default="auto",
        help=(
            "which revision of scripts/run_e018.py rebuilds the prompts: "
            f"'auto' tries the working tree and falls back to {RUN_BUILDER_REV}, "
            "'head' refuses to fall back, or name a revision"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.caches is None:
        from audit_correctness import CACHE_DIR as E007_CACHE_DIR

        args.caches = [CACHE_DIR, E007_CACHE_DIR]

    # The run file belongs to a population; reading one against the other's
    # rebuild would fail the digest check, which is the right outcome but a
    # confusing one. Derive it instead of defaulting to the primary path.
    if args.run is None:
        args.run = outputs(args.population)[1]

    rows = load_jsonl(args.run, what="E-018 run")
    labels = by_condition(rows)
    scored: dict[str, dict[str, dict]] = {}
    for row in rows:
        scored.setdefault(row["question_id"], {})[row["condition"]] = row

    if args.flips:
        wanted = flipped(labels)
    elif args.qid:
        wanted = [args.qid]
    else:
        raise SystemExit("Name a question with --qid, or pass --flips.")

    # `prepare` rebuilds every condition at the recorded seed. The placebo is
    # drawn there, so rebuilding one question in isolation would draw from a
    # different point in the sequence and produce a prompt that was never sent.
    revision = None if args.builder in {"auto", "head"} else args.builder
    by_qid = rebuild_at(revision, args)
    missing = [qid for qid in wanted if qid not in by_qid]
    if missing:
        raise SystemExit(f"Not in the frozen population: {', '.join(missing)}")
    if args.limit:
        wanted = wanted[: args.limit]

    # The builder is chosen against the recorded digests, before anything is
    # printed. The working tree is not authoritative here: the amendment that
    # followed this run changed how the conditions are built, so HEAD renders
    # prompts for 27 of the 60 rows that the run never sent.
    conditions = CONDITIONS if args.condition == "all" else (args.condition,)
    bad = mismatches(by_qid, scored, wanted, conditions)
    used = revision or "working tree"
    if bad and args.builder == "auto":
        print(
            f"{bad} row(s) do not match the recorded prompt hash under the "
            f"working tree. Falling back to {RUN_BUILDER_REV}, the revision "
            "that produced this run.\n"
        )
        fallback = rebuild_at(RUN_BUILDER_REV, args)
        if mismatches(fallback, scored, wanted, conditions) < bad:
            by_qid, used = fallback, RUN_BUILDER_REV
            bad = mismatches(by_qid, scored, wanted, conditions)
    if bad:
        print(
            f"** {bad} row(s) still do not match under {used}. Those will "
            "print nothing. Do not read around them.\n"
        )

    unrendered = sum(show(by_qid[qid], scored[qid], conditions, args.full) for qid in wanted)
    print(f"\n{RULE}")
    print(f"{len(wanted)} question(s) shown, built by {used}.")
    if unrendered:
        print(f"** {unrendered} condition(s) did NOT render — unverified or mismatched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
