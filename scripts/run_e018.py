#!/usr/bin/env python
"""E-018: does the governing rule *cause* the answer, or do easy questions get it?

E-001's null has a candidate explanation: on the questions carrying gold CR
rules, every arm sits near 0.80 when retrieval brought one and near 0.38 when
it did not, and every arm brings one on about 40% of them. That reading is
**post-selection** — the questions where the rule arrives may be the easy ones
— which is the confound that inverted E-012a. So this entry assigns instead of
observing, on arm B only, paired within question.

    control     exactly what E-001's retrieval produced
    placebo     control plus one random rule subtree per gold rule, drawn at
                the same depth in the CR tree, token-matched to the treatment
    treatment   control plus the question's gold rules, each with its subtree

**The placebo is the registered falsifier.** Without it, a lift under treatment
is equally explained by "more context" and by "rule-shaped text in the prompt".

**The ceiling was read before this file was written: 17 of 20 (0.850).** No arm
here can exceed 17 flips; anything above it is a defect in the measurement, not
a finding. And no figure here is a system score — injecting the gold rule is an
oracle intervention that measures the generator's use of evidence, never any
retriever's ability to find it.

**The noise floor runs first, and `run` refuses without it.** E-011's amendment
item 9 made this binding for paired comparisons over these rows: a model at
temperature 0 is not deterministic, and with a threshold of six or seven
discordant pairs, generator and judge stochasticity could manufacture several
from nothing. `floor` generates control twice and publishes the
control-vs-control discordance. `run` then reuses the first replicate as the
comparison's control, so the pairing is exact rather than approximate.

**Checks that can fail**, each hard, each registered before the run:

    every control context carries exactly E-001's evidence
    nothing is dropped or capped in any condition
    every injected rule number appears in the prompt as sent, on every question
    the placebo's token count is within +/-20% of the treatment's, per question

All of them run before a single token is spent: a run that would fail its
manipulation check on question seventeen should fail before it has paid for
sixteen. The realized per-question deltas are printed whether they pass or not.

Usage:
    python scripts/run_e018.py floor --dry-run
    python scripts/run_e018.py floor
    python scripts/run_e018.py run --dry-run
    python scripts/run_e018.py run --limit 3
    python scripts/run_e018.py run
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.evaluation.judge import CORRECTNESS_SYSTEM, JUDGE_PROMPT_VERSION, score
from graphrag_mtg.evaluation.judge import correctness_prompt as judge_prompt
from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION, rubric_hash
from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.generation.answerer import (
    PROMPT_VERSION,
    SYSTEM,
    answer,
    build_prompt,
    prompt_digest,
)
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph, enforce_budget

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_correctness import CACHE_DIR as E007_CACHE_DIR
from audit_correctness import question_and_key
from e001_inspect import artefacts, gold_rules, load_jsonl
from e018_ceiling import ABSENT_IDS, ARM, SPLIT
from run_e007 import MAX_ANSWER_TOKENS, rebuild
from run_eval import CACHE_DIR, GOLDEN_DIR, NOTICE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THIN = "-" * 78

FLOOR_PATH = Path("runs/e018_floor.jsonl")
RUN_PATH = Path("runs/e018.jsonl")

#: Raised for every condition alike so nothing is evicted and the comparison
#: is not silently measuring `enforce_budget`. E-013 measured `dropped` empty
#: at 6,000 on this corpus and the treatment adds roughly 300 tokens; this is
#: four times the shipped budget and the run hard-fails if anything is dropped
#: anyway, because a budget that is merely *probably* slack is a guard that
#: passes for two reasons.
TOKEN_BUDGET = 24_000

#: The placebo draw and the shuffle. Recorded so the arms are reproducible;
#: it is the registration date and carries no other meaning.
RANDOM_SEED = 20260913

#: The placebo must land within this fraction of the treatment's token count,
#: per question. Beyond it the placebo has stopped controlling volume, which
#: is the only thing it controls, and the run refuses rather than reporting.
TOKEN_TOLERANCE = 0.20

#: Attempts before the run gives up on matching one question's placebo. A
#: silent fallback to "closest available" would let a question with no
#: matchable draw pass as a matched one.
MAX_DRAWS = 400

#: Read 2026-09-13 from the 20 frozen primary questions, before this file
#: existed. The maximum number of flips this design can produce.
CEILING = 17

CONDITIONS = ("control", "placebo", "treatment")

#: Injected evidence says how it arrived. It is not a traversal and a path
#: claiming one would be a fabricated provenance in a file that exists to
#: measure honesty about provenance. The node is real, so the path names the
#: node and nothing else.
INJECTION_TEMPLATE = "e018_injection"


def injected(number: str, text: str) -> Evidence:
    """One CR rule as evidence, shaped exactly like retrieved evidence.

    Same dataclass, same handle contract, so `serialize`, `cited_handles` and
    `expand`'s fabricated-citation detector cannot tell it apart — which is
    what makes a citation of an injected rule count as a citation rather than
    as a fabrication.

    `distance` is 0: the oracle named this node, the way a question naming a
    card gives that card distance 0. It also puts injected items last in
    `enforce_budget`'s eviction order, which is moot here because the run
    refuses if anything is evicted at all.
    """
    return Evidence(
        kind="rule",
        key=number,
        text=text,
        template=INJECTION_TEMPLATE,
        path=f"(:Rule {{{number}}})",
        distance=0,
    )


def subtree_evidence(number: str, cr: object) -> list[Evidence]:
    """A gold rule and every rule beneath it.

    The subtree and not the bare rule, per amendment 2026-09-13b: ten of the
    thirty gold rules in this population have subrules, `613.7` has thirteen,
    and injecting the parent alone injects a preamble while omitting the
    subrules where the cases live. On `701.15` it would have injected the
    single word "Goad".
    """
    return [injected(rule.number, rule.text) for rule in cr.subtree(number)]  # type: ignore[attr-defined]


def rule_pools(cr: object, excluded: set[str]) -> dict[int, list[str]]:
    """Placebo candidates, indexed by depth in the CR tree.

    Drawn **at the same level as the gold rule each one replaces**, because
    the placebo controls two things and level carries both. Volume: a level-2
    rule's subtree runs to a median 342 characters and a level-3 subrule's to
    200, so drawing across levels makes the token match a lottery. Shape: a
    numbered rule with lettered subrules under it reads differently from a
    lone subrule, and a treatment that is always the first and a placebo that
    is sometimes the second differ by more than goldness.

    The first version of this drew level-1 chapters — the treatment never
    injects one, the pool was 147 instead of 3,161, and no draw for a
    two-rule question landed inside the registered tolerance. The check
    refused, which is what it is for.
    """
    pools: dict[int, list[str]] = {}
    for rule in cr.rules:  # type: ignore[attr-defined]
        if rule.number not in excluded:
            pools.setdefault(rule.level, []).append(rule.number)
    return pools


def tokens_of(items: list[Evidence]) -> int:
    """What these items cost once serialized. The placebo matches on this."""
    return sum(item.tokens for item in items)


def draw_placebo(
    rng: random.Random,
    pools: dict[int, list[str]],
    cr: object,
    levels: list[int],
    target: int,
    items_target: int,
) -> list[Evidence]:
    """One random subtree per gold rule, at its level, matching its size.

    `levels` is the multiset of the gold rules' levels, so the placebo has
    the same number of rules at the same depths as the treatment it replaces.
    Drawn and redrawn rather than assembled toward a size: assembling would
    let the rule *count* drift, and the entry matched count and tokens both.
    The loop is bounded and its failure is loud.

    Raises:
        SystemExit: when no draw inside `MAX_DRAWS` lands within tolerance.
            A question whose placebo cannot be matched is a question the
            design cannot measure, and reporting it as matched would put a
            volume effect where a rule effect is claimed.
    """
    best_gap = float("inf")
    accepted: list[tuple[int, list[Evidence]]] = []
    for _ in range(MAX_DRAWS):
        chosen = [rng.choice(pools[level]) for level in levels]
        if len(set(chosen)) != len(chosen):
            continue
        items = [item for number in chosen for item in subtree_evidence(number, cr)]
        gap = abs(tokens_of(items) - target)
        best_gap = min(best_gap, gap)
        if target and gap / target <= TOKEN_TOLERANCE:
            accepted.append((abs(len(items) - items_target), items))
    if accepted:
        # Tokens are the registered criterion and every candidate here already
        # meets it. Item count is the tiebreak, not a second gate: at equal
        # volume, nine long rules and twenty-three short ones are differently
        # shaped contexts, and picking the closest costs a comparison over
        # draws already made. The realized counts are published either way.
        return min(accepted, key=lambda pair: pair[0])[1]
    raise SystemExit(
        f"No placebo of {len(levels)} subtree(s) at level(s) {levels} landed within "
        f"{TOKEN_TOLERANCE:.0%} of {target} tokens in {MAX_DRAWS} draws "
        f"(closest was off by {best_gap:.0f}).\n"
        f"The placebo controls volume and shape and nothing else. A question it "
        f"cannot match is one this design cannot measure — report it, do not "
        f"widen the tolerance after seeing it."
    )


def conditions_for(
    qid: str,
    question: str,
    record: dict,
    wanted: list[str],
    cr: object,
    rng: random.Random,
) -> dict[str, Subgraph]:
    """The three paired contexts for one question, from the same control.

    Built once and shared, so no condition can win by having been handed a
    different retrieval. The merged evidence is shuffled at the recorded seed
    in **every** condition — including control, which has nothing injected —
    so that injected items are never a contiguous block at one end and the
    shuffle itself is not a difference between conditions.
    """
    control = rebuild(record, question)
    treatment_items = [item for number in wanted for item in subtree_evidence(number, cr)]
    by_number = cr.by_number  # type: ignore[attr-defined]
    # Excluded by subtree, not by the gold numbers alone: a placebo drawn as a
    # subrule of a gold rule would be gold text wearing a random label.
    pools = rule_pools(cr, {item.key for item in treatment_items})
    levels = [by_number[number].level for number in wanted]
    placebo_items = draw_placebo(
        rng, pools, cr, levels, tokens_of(treatment_items), len(treatment_items)
    )

    built = {}
    for name, extra in (
        ("control", []),
        ("placebo", placebo_items),
        ("treatment", treatment_items),
    ):
        evidence = list(control.evidence) + list(extra)
        rng.shuffle(evidence)
        built[name] = Subgraph(
            question=question,
            outcome=control.outcome,
            evidence=evidence,
            templates_run=list(control.templates_run),
            note=control.note,
        )
    return built


def check_control(qid: str, control: Subgraph, record: dict) -> None:
    """The control must be what E-001 produced, not merely something like it.

    Raises:
        SystemExit: on any difference. The control is the baseline every
            contrast is measured against; if it is not E-001's context then
            "control" names something this entry never registered.
    """
    rebuilt = {(item.kind, item.key) for item in control.evidence}
    original = {(item["kind"], item["key"]) for item in record.get("evidence", ())}
    if rebuilt != original:
        missing = sorted(original - rebuilt)
        added = sorted(rebuilt - original)
        raise SystemExit(
            f"{qid}: the control context is not E-001's.\n"
            f"  missing: {missing[:5]}\n  added:   {added[:5]}"
        )


def check_budget(qid: str, name: str, subgraph: Subgraph) -> None:
    """Nothing may be evicted, in any condition.

    Raises:
        SystemExit: if anything was dropped or capped. An evicted item makes
            the contrast a measurement of `enforce_budget`, which E-015
            already measured and which is not what this entry claims.
    """
    if subgraph.dropped or subgraph.capped:
        raise SystemExit(
            f"{qid} ({name}): the budget evicted evidence — dropped "
            f"{dict(subgraph.dropped)}, capped {dict(subgraph.capped)}.\n"
            f"Raise TOKEN_BUDGET (currently {TOKEN_BUDGET:,}) and record the "
            f"change; do not analyse a run in which a condition was trimmed."
        )


def check_injection(qid: str, name: str, prompt: str, items: list[Evidence]) -> None:
    """Every injected rule must be in the prompt as sent.

    The manipulation check registered in amendment 2026-09-13. A null under an
    injection that silently failed is indistinguishable from a null under one
    that worked, and this project has already shipped a cell that was handing
    the model the wrong evidence for months without a trace showing it.

    Raises:
        SystemExit: if any injected rule is absent from the prompt.
    """
    absent = [item.key for item in items if f"[rule:{item.key}]" not in prompt]
    if absent:
        raise SystemExit(
            f"{qid} ({name}): {len(absent)} injected rule(s) are not in the prompt "
            f"as sent: {absent[:5]}.\nThe manipulation did not happen. Nothing "
            f"downstream of this is interpretable."
        )


def generators(args: argparse.Namespace) -> tuple[object, object, str]:
    """The answer generator, the judge generator, and the model name."""
    client = LlmClient(model=args.model, max_tokens=MAX_ANSWER_TOKENS, temperature=0.0)
    generate = lambda system, prompt: client.complete_text(prompt, system=system)  # noqa: E731
    return generate, generate, client.model


def population(args: argparse.Namespace) -> list[str]:
    """The frozen primary ids, in file order, honouring `--limit`."""
    if not ABSENT_IDS.exists():
        raise SystemExit(
            f"No frozen population at {ABSENT_IDS}.\n"
            f"  python scripts/e018_ceiling.py freeze"
        )
    ids = json.loads(ABSENT_IDS.read_text(encoding="utf-8"))["ids"]
    return ids[: args.limit] if args.limit else ids


def prepare(args: argparse.Namespace) -> tuple[list[dict], object]:
    """Every question's three contexts, built before a single token is spent.

    All construction and all four checks run first. A run that would fail its
    manipulation check on question 17 should fail before it has paid for
    sixteen, and a check that fires after the spend is a postmortem.
    """
    ids = population(args)
    retrieval_path, _, _ = artefacts(ARM, SPLIT)
    records = {row["question_id"]: row for row in load_jsonl(retrieval_path, what="retrieval")}
    wanted = gold_rules(args.golden)
    cr = parse_cr()
    rng = random.Random(RANDOM_SEED)

    prepared = []
    for qid in ids:
        question, key = question_and_key(qid, args.caches, args.golden)
        built = conditions_for(qid, question, records[qid], wanted[qid], cr, rng)
        check_control(qid, built["control"], records[qid])
        row: dict = {"question_id": qid, "question": question, "key": key, "prompts": {}}
        for name in CONDITIONS:
            subgraph = built[name]
            enforce_budget(subgraph, TOKEN_BUDGET)
            check_budget(qid, name, subgraph)
            prompt = build_prompt(question, subgraph, notice=NOTICE)
            row["prompts"][name] = prompt
            row.setdefault("tokens", {})[name] = subgraph.tokens
            row.setdefault("subgraphs", {})[name] = subgraph
        injected_treatment = [
            item for item in built["treatment"].evidence if item.template == INJECTION_TEMPLATE
        ]
        injected_placebo = [
            item for item in built["placebo"].evidence if item.template == INJECTION_TEMPLATE
        ]
        check_injection(qid, "treatment", row["prompts"]["treatment"], injected_treatment)
        check_injection(qid, "placebo", row["prompts"]["placebo"], injected_placebo)
        row["injected"] = {
            "treatment": [item.key for item in injected_treatment],
            "placebo": [item.key for item in injected_placebo],
        }
        row["gold_cr_rules"] = wanted[qid]
        prepared.append(row)
    return prepared, cr


def report_match(prepared: list[dict]) -> None:
    """The realized placebo-vs-treatment token deltas, published not hoped."""
    print(f"\n{THIN}\nPLACEBO TOKEN MATCH (registered tolerance +/-{TOKEN_TOLERANCE:.0%})")
    worst = 0.0
    for row in prepared:
        treat = row["tokens"]["treatment"] - row["tokens"]["control"]
        plac = row["tokens"]["placebo"] - row["tokens"]["control"]
        delta = abs(plac - treat) / treat if treat else 0.0
        worst = max(worst, delta)
        print(
            f"  {row['question_id']:<34} treatment +{treat:>5}  placebo +{plac:>5}  "
            f"{delta:>6.1%}  ({len(row['injected']['treatment'])} vs "
            f"{len(row['injected']['placebo'])} rules)"
        )
    print(f"  worst realized delta: {worst:.1%}")


def estimate(prepared: list[dict], names: tuple[str, ...], model: str) -> None:
    """What this would cost, printed before anything is sent."""
    prompts = [row["prompts"][name] for row in prepared for name in names]
    generation = estimate_cost(
        prompts, model=model, output_tokens_per_call=MAX_ANSWER_TOKENS, system=SYSTEM
    )
    judged = estimate_cost(
        [judge_prompt(row["question"], "x" * 800, row["key"]) for row in prepared for _ in names],
        model=model,
        output_tokens_per_call=300,
        system=CORRECTNESS_SYSTEM,
    )
    total = generation.usd + judged.usd
    print(
        f"\nestimate: {generation.n_calls} generation(s) + {judged.n_calls} judge call(s), "
        f"about US$ {total:.2f}"
    )


def generate_and_judge(
    row: dict, name: str, generate, judge, model: str
) -> dict:
    """One condition on one question: answer it, then score it."""
    subgraph = row["subgraphs"][name]
    result = answer(row["question"], subgraph, generate, notice=NOTICE, model=model)
    verdict = score(
        row["question_id"],
        row["question"],
        result.text,
        row["key"],
        judge,
        model=model,
        refused=result.refused,
    )
    return {
        "question_id": row["question_id"],
        "condition": name,
        "text": result.text,
        "refused": result.refused,
        "generated": result.generated,
        "handles": result.handles,
        "unknown_handles": result.unknown,
        "injected": row["injected"].get(name, []),
        # Which of the injected rules the answer actually cited. Below 0.50
        # across treatment, branch 3 does not fire: a null under a treatment
        # the generator never used is a null about the harness.
        "cited_injected": sorted(
            set(row["injected"].get(name, [])) & {h.split(":", 1)[1] for h in result.handles}
        ),
        "label": str(verdict.label),
        "rationale": verdict.rationale,
        "by_rule": verdict.by_rule,
        "tokens": row["tokens"][name],
        "prompt_sha256": prompt_digest(SYSTEM, row["prompts"][name]),
        "prompt_version": PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "rubric_hash": rubric_hash(),
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "model": model,
        "arm": ARM,
        "split": SPLIT,
    }


def write(path: Path, rows: list[dict]) -> None:
    """Write a run, refusing to destroy one that already exists."""
    if path.exists():
        raise SystemExit(
            f"{path} already exists. `runs/` is gitignored and generated answers "
            f"are the only copy of what a label describes — move it aside if you "
            f"mean to re-run."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(rows)} row(s) -> {path}")


def floor(args: argparse.Namespace) -> int:
    """Control against control: what this comparison's noise looks like.

    Binding since E-011's amendment item 9. It runs before `run` and `run`
    refuses without it, because a threshold of six or seven discordant pairs
    means nothing until the number stochasticity produces on its own is known.
    """
    prepared, _ = prepare(args)
    print(f"E-018 noise floor   arm {ARM}   split {SPLIT}   {len(prepared)} question(s)")
    print(f"budget {TOKEN_BUDGET:,}   seed {RANDOM_SEED}   ceiling {CEILING}")
    report_match(prepared)
    generate, judge, model = generators(args)
    estimate(prepared, ("control", "control"), model)
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    rows = []
    for row in prepared:
        for replicate in ("control_a", "control_b"):
            scored = generate_and_judge(row, "control", generate, judge, model)
            scored["condition"] = replicate
            rows.append(scored)
            print(f"  {row['question_id']:<34} {replicate}: {scored['label']}")
    write(FLOOR_PATH, rows)

    by_qid: dict[str, dict[str, str]] = {}
    for scored in rows:
        by_qid.setdefault(scored["question_id"], {})[scored["condition"]] = scored["label"]
    discordant = [q for q, pair in by_qid.items() if pair["control_a"] != pair["control_b"]]
    print(f"\n{THIN}\nNOISE FLOOR: {len(discordant)} of {len(by_qid)} pairs discordant")
    for qid in discordant:
        print(f"  {qid}: {by_qid[qid]['control_a']} vs {by_qid[qid]['control_b']}")
    if len(discordant) >= 4:
        print(
            "\n** At or above four. The thresholds in the decision rule are recomputed\n"
            "   against this floor before any branch fires — registered in the entry,\n"
            "   not decided now."
        )
    return 0


def run(args: argparse.Namespace) -> int:
    """The three conditions, interleaved by question."""
    if not FLOOR_PATH.exists() and not args.dry_run:
        raise SystemExit(
            f"No noise floor at {FLOOR_PATH}. It runs first, and this refuses without it:\n"
            f"  python scripts/run_e018.py floor\n"
            f"A threshold of six or seven discordant pairs means nothing until the "
            f"number two identical runs produce on their own is known."
        )
    prepared, _ = prepare(args)
    print(f"E-018   arm {ARM}   split {SPLIT}   {len(prepared)} question(s), 3 conditions")
    print(f"budget {TOKEN_BUDGET:,}   seed {RANDOM_SEED}   prompt {PROMPT_VERSION}")
    print(f"ceiling {CEILING} of {len(prepared)} — read before this ran; nothing may exceed it")
    report_match(prepared)
    generate, judge, model = generators(args)
    estimate(prepared, CONDITIONS, model)
    if args.dry_run:
        print("\nDry run: nothing was sent. Every check above passed.")
        return 0

    control = {}
    if FLOOR_PATH.exists():
        for scored in load_jsonl(FLOOR_PATH, what="noise floor"):
            if scored["condition"] == "control_a":
                control[scored["question_id"]] = scored

    rows = []
    # Interleaved by question, not batched by condition, so a silent model
    # change cannot be confounded with the manipulation.
    for row in prepared:
        for name in CONDITIONS:
            if name == "control" and row["question_id"] in control:
                scored = dict(control[row["question_id"]])
                scored["condition"] = "control"
                scored["replicated_from"] = "floor"
            else:
                scored = generate_and_judge(row, name, generate, judge, model)
            rows.append(scored)
            print(f"  {row['question_id']:<34} {name:<10} {scored['label']}")
    write(RUN_PATH, rows)

    uptake = [r for r in rows if r["condition"] == "treatment"]
    used = [r for r in uptake if r["cited_injected"]]
    rate = len(used) / len(uptake) if uptake else 0.0
    print(f"\n{THIN}\nGOLD-RULE CITATION UPTAKE: {len(used)} of {len(uptake)} ({rate:.1%})")
    if rate < 0.50:
        print(
            "** Below 0.50. Branch 3 does not fire on this run: a null under a\n"
            "   treatment the generator never used is a null about the harness.\n"
            "   Registered in amendment 2026-09-13, before the run."
        )
    print(f"\nNext: python scripts/e018_analysis.py --run {RUN_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Shared through `parents=` rather than on the top-level parser, so the
    # flags read after the subcommand where a reader expects them: `run
    # --dry-run`, not `--dry-run run`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    common.add_argument("--caches", type=Path, nargs="+", default=[CACHE_DIR, E007_CACHE_DIR])
    common.add_argument("--model", default=None, help="defaults to LLM_MODEL in .env")
    common.add_argument("--limit", type=int, default=0, help="run at most N questions")
    common.add_argument("--dry-run", action="store_true", help="build and check, send nothing")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("floor", parents=[common], help="control against control — runs first")
    sub.add_parser("run", parents=[common], help="the three conditions, paired within question")
    args = parser.parse_args()
    return {"floor": floor, "run": run}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
