#!/usr/bin/env python
"""E-014 — is the depth effect a property of the task, or of the generator?

E-012 measured, on `gpt-4o-mini` and at a matched 16-item context with a clean
chain guaranteed present, that Hits@1 falls 0.890 -> 0.672 -> 0.511 across one,
two and three hops, and that context size does nothing. It never varied the
model. So the project does not know whether "the generator cannot chain three
facts" is a statement about the task or about that one small model.

This script applies the rule registered on 2026-09-13, before either arm ran:

    D = Hits@1(1-hop, k=16) - Hits@1(3-hop, k=16) under the new model.
    Under gpt-4o-mini, D = 0.379.

    branch 1  D <= 0.15 AND the 3-hop paired contrast clears its Holm step
    branch 2  D >= 0.25
    branch 3  anything else, including a narrowed D that rests on noise

The primary contrast is **paired across models within question** — the same
question scored by both generators at k=16, exact McNemar, Holm over the three
hops. Pairing across hops is impossible; they are different questions.

Two things this script will refuse to do, both registered:

- **Interpret the 3-hop cells when 1-hop moved more than 5 points.** At k=16
  with a clean chain present there is no chaining at all at one hop, so a large
  movement there is answer-matching or prompt sensitivity, not reasoning. The
  instrument is contaminated and the depth cells are not readable.
- **Print a verdict from an incomplete run.** Every cell is paid and written
  before any is read; `--interim` prints the cells and withholds the branch.

No figure here is an end-to-end system score. The reduction rule is an oracle
filter that uses the gold answer, so this measures the generator's ceiling
given good retrieval, and E-012's threat carries over verbatim.

Usage:
    python scripts/e014_analysis.py
    python scripts/e014_analysis.py --interim     # cells only, no branch
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from graphrag_mtg.evaluation.metaqa import HOPS
from graphrag_mtg.evaluation.metrics import mcnemar, wilson_interval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78

BASELINE = Path("runs/e012_conf.jsonl")
TREATMENT = Path("runs/e014_conf.jsonl")

#: The generator E-012 measured. A baseline file written by anything else is
#: not the arm this experiment pairs against.
BASELINE_MODEL = "gpt-4o-mini"

#: The size the registered primary contrast reads. E-014 drops E-012's sweep
#: because E-012 measured it null; `SIZE_NULL_K` is the single replication.
PRIMARY_K = 16
SIZE_NULL_K = 256

#: The registered branch boundaries on D, and the instrument check.
BRANCH_1_MAX_D = 0.15
BRANCH_2_MIN_D = 0.25
INSTRUMENT_MAX_1HOP_GAIN = 0.05

ALPHA = 0.05

#: E-012b's published k=16 cells, quoted so the report can state the prior it
#: is moving against. These are never recomputed from the treatment file.
E012_K16 = {1: 0.890, 2: 0.672, 3: 0.511}


def die(message: str) -> None:
    raise SystemExit(f"VALIDITY GUARD FAILED — no numbers printed.\n  {message}")


def load(path: Path) -> list[dict]:
    if not path.exists():
        die(f"missing {path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        die(f"{path} is empty")
    return rows


def one_model(rows: list[dict], path: Path) -> str:
    """The model that wrote every row, or a hard failure.

    A file holding two models is a resumed run that changed generator
    mid-flight. There is no defensible way to read it, so it is not read.
    """
    models = {row.get("model") for row in rows}
    if len(models) != 1:
        die(f"{path} holds {len(models)} model(s): {sorted(map(str, models))}")
    model = models.pop()
    if not model:
        die(f"{path} has rows with no model recorded")
    return str(model)


def one_prompt(rows: list[dict], path: Path) -> str:
    versions = {row.get("prompt_version") for row in rows}
    if len(versions) != 1:
        die(f"{path} holds {len(versions)} prompt version(s): {sorted(map(str, versions))}")
    version = versions.pop()
    if not version:
        die(f"{path} has rows with no prompt_version recorded")
    return str(version)


def cell(rows: list[dict], hops: int, k: int) -> dict[str, bool]:
    """`{qid: correct}` for one (hops, k) cell, refusing a duplicated qid."""
    scored: dict[str, bool] = {}
    for row in rows:
        if row["hops"] != hops or row["k"] != k:
            continue
        qid = row["qid"]
        if qid in scored:
            die(f"qid {qid} appears twice in cell ({hops}-hop, k={k})")
        scored[qid] = bool(row["correct"])
    return scored


def holm(pvalues: dict[str, float], alpha: float = ALPHA) -> dict[str, tuple[float, bool]]:
    """Holm-Bonferroni, returning the adjusted p and the reject flag per key.

    Step-down: sort ascending, test p_(i) against alpha/(m-i), and once a
    hypothesis fails to reject every later one fails too. The adjusted p is the
    running maximum of (m-i) * p_(i), clipped at 1.
    """
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, tuple[float, bool]] = {}
    running = 0.0
    still_rejecting = True
    for index, (key, p) in enumerate(ordered):
        value = min(1.0, max(running, (m - index) * p))
        running = value
        if still_rejecting and p > alpha / (m - index):
            still_rejecting = False
        adjusted[key] = (value, still_rejecting)
    return adjusted


def guards(
    base: list[dict], treat: list[dict], base_path: Path, treat_path: Path
) -> tuple[str, str]:
    """Every check that must hold before a number is printed.

    Registered prediction 4 lives here: the excluded questions are chosen by
    retrieval, before any model call, so the two runs must cover **identical**
    question sets at k=16. A difference means the harness changed and not the
    model, and nothing in the file is readable until that is explained.
    """
    base_model = one_model(base, base_path)
    treat_model = one_model(treat, treat_path)
    if base_model != BASELINE_MODEL:
        die(f"{base_path} was written by {base_model!r}, not the registered {BASELINE_MODEL!r}")
    if treat_model == base_model:
        die(f"both files were written by {base_model!r} — there is no contrast to read")

    base_prompt = one_prompt(base, base_path)
    treat_prompt = one_prompt(treat, treat_path)
    if base_prompt != treat_prompt:
        die(
            f"prompt differs: {base_path} is {base_prompt!r}, {treat_path} is "
            f"{treat_prompt!r}. E-014 is not a prompt experiment and an edit "
            f"voids the comparison."
        )

    for hops in HOPS:
        left = set(cell(base, hops, PRIMARY_K))
        right = set(cell(treat, hops, PRIMARY_K))
        if not right:
            die(f"{treat_path} has no {hops}-hop cell at k={PRIMARY_K}")
        if left != right:
            die(
                f"{hops}-hop at k={PRIMARY_K}: the runs cover different questions "
                f"({len(left)} vs {len(right)}, {len(left ^ right)} not shared). "
                f"Exclusion is decided by retrieval before any model call, so this "
                f"is a harness change, not a model effect."
            )
    return base_model, treat_model


def report_cells(base: list[dict], treat: list[dict], treat_model: str) -> dict[int, float]:
    """Hits@1 at k=16 by hop, both models side by side."""
    print(f"CELLS at k={PRIMARY_K} — Hits@1, answer guaranteed present.\n")
    print(f"{'hop':<8}{BASELINE_MODEL:<30}{treat_model:<30}{'delta':<10}")
    print(RULE)
    points: dict[int, float] = {}
    for hops in HOPS:
        before = cell(base, hops, PRIMARY_K)
        after = cell(treat, hops, PRIMARY_K)
        ids = sorted(after)
        left = wilson_interval(sum(before[i] for i in ids), len(ids))
        right = wilson_interval(sum(after[i] for i in ids), len(ids))
        points[hops] = right.point
        print(
            f"{f'{hops}-hop':<8}"
            f"{f'{left.point:.3f} [{left.low:.3f},{left.high:.3f}] n={len(ids)}':<30}"
            f"{f'{right.point:.3f} [{right.low:.3f},{right.high:.3f}] n={len(ids)}':<30}"
            f"{right.point - left.point:+.3f}"
        )
    print(RULE)
    quoted = "  ".join(f"{h}-hop {E012_K16[h]:.3f}" for h in sorted(E012_K16))
    print(f"\nE-012b published, for reference: {quoted}")
    print("Those numbers stand. E-014's may not be substituted into E-012's tables.")
    return points


def instrument_ok(base: list[dict], treat: list[dict]) -> tuple[bool, float]:
    """The registered check that can return negative.

    One hop at k=16 involves no chaining, so it should barely move. A large
    gain there means the change is in answer-matching, formatting or prompt
    sensitivity — and the depth cells are then not readable as reasoning.
    """
    before = cell(base, 1, PRIMARY_K)
    after = cell(treat, 1, PRIMARY_K)
    ids = sorted(after)
    if not ids:
        die(f"no 1-hop cell at k={PRIMARY_K} — the instrument check cannot run")
    gain = sum(after[i] for i in ids) / len(ids) - sum(before[i] for i in ids) / len(ids)
    return gain <= INSTRUMENT_MAX_1HOP_GAIN, gain


def paired(base: list[dict], treat: list[dict]) -> dict[int, tuple[float, int, int, int]]:
    """Exact McNemar per hop at k=16, paired within question across models."""
    results: dict[int, tuple[float, int, int, int]] = {}
    for hops in HOPS:
        before = cell(base, hops, PRIMARY_K)
        after = cell(treat, hops, PRIMARY_K)
        ids = sorted(after)
        outcome = mcnemar([before[i] for i in ids], [after[i] for i in ids])
        results[hops] = (outcome.p_value, outcome.improved, outcome.regressed, len(ids))
    return results


def size_null(treat: list[dict]) -> None:
    """Did E-012's size-null survive the model change? A check, not a contrast."""
    small = cell(treat, 3, PRIMARY_K)
    large = cell(treat, 3, SIZE_NULL_K)
    if not large:
        print(f"\nSIZE-NULL REPLICATION — not run (no 3-hop cell at k={SIZE_NULL_K}).")
        print("Registered as droppable if the printed estimate exceeded US$ 40.")
        return
    ids = sorted(set(small) & set(large))
    if not ids:
        die(f"3-hop k={PRIMARY_K} and k={SIZE_NULL_K} share no question")
    left = wilson_interval(sum(small[i] for i in ids), len(ids))
    right = wilson_interval(sum(large[i] for i in ids), len(ids))
    overlap = left.low <= right.high and right.low <= left.high
    print(f"\nSIZE-NULL REPLICATION — 3-hop, k={PRIMARY_K} against k={SIZE_NULL_K}.")
    print(f"  k={PRIMARY_K:<5} {left.point:.3f} [{left.low:.3f},{left.high:.3f}]")
    print(f"  k={SIZE_NULL_K:<5} {right.point:.3f} [{right.low:.3f},{right.high:.3f}]  n={len(ids)}")
    print(
        "  intervals overlap: E-012's size-null replicates."
        if overlap
        else "  ** intervals separate: size now matters, which E-012 said it did not. **"
    )


def branch(spread: float, rejected: bool) -> str:
    """The registered rule as a pure function, so it can be tested without a run.

    Branch 1 needs both halves: a narrowed D **and** a 3-hop paired contrast
    that clears its Holm step. A D that narrows on noise is branch 3, which is
    the case this ordering exists to prevent being read as branch 1.
    """
    if spread <= BRANCH_1_MAX_D and rejected:
        return "1"
    if spread >= BRANCH_2_MIN_D:
        return "2"
    return "3"


def verdict(spread: float, tests: dict[str, tuple[float, bool]], hop3_key: str) -> None:
    """Apply the registered rule. The branch is read off, never chosen."""
    _, rejected = tests[hop3_key]
    print(f"\nD = Hits@1(1-hop) - Hits@1(3-hop) = {spread:.3f}")
    print(f"Under {BASELINE_MODEL}, D = {E012_K16[1] - E012_K16[3]:.3f}")
    print(RULE)
    if branch(spread, rejected) == "1":
        print("BRANCH 1 — the depth effect is largely a property of that generator.")
        print("  - E-012's verdict is annotated model-conditional; its numbers stand.")
        print("  - E-001's inconclusive result gains a live, registered explanation.")
        print("  - This earns ONE second opening of the MTG evaluation split, as its")
        print("    own entry with its own decision rule, both openings dated in print.")
        print("  - P3's decomposition hypothesis is WEAKENED.")
        print("\n  It does not conclude anything about E-001. MetaQA is templated;")
        print("  a gap that closes here proves nothing about judge-level questions.")
    elif branch(spread, rejected) == "2":
        print("BRANCH 2 — the depth effect survives a generator change in-family.")
        print("  - No second opening of the MTG evaluation split on a model swap.")
        print("  - E-001's multi-hop reading stands as published.")
        print("  - P3 inherits this as its registered prior; decomposition STRENGTHENED.")
    else:
        reason = (
            "D narrowed but the paired contrast did not clear its Holm step"
            if spread <= BRANCH_1_MAX_D
            else f"D sits between {BRANCH_1_MAX_D} and {BRANCH_2_MIN_D}"
        )
        print(f"BRANCH 3 — {reason}.")
        print("  - Reported and not acted on. No second opening.")
        print("  - The decision passes to P3.")
        print("\n  Registered so a middling result is not read as whichever half is")
        print("  more convenient, and so a narrowing on noise is not read as branch 1.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--treatment", type=Path, default=TREATMENT)
    parser.add_argument(
        "--interim",
        action="store_true",
        help="print the cells and withhold the branch (a run read before it completes)",
    )
    args = parser.parse_args()

    base, treat = load(args.baseline), load(args.treatment)
    _, treat_model = guards(base, treat, args.baseline, args.treatment)

    print(f"E-014 — {BASELINE_MODEL} -> {treat_model}, registered 2026-09-13.")
    print("Oracle filter: the answer is present by construction. Not a system score.\n")

    points = report_cells(base, treat, treat_model)
    size_null(treat)

    ok, gain = instrument_ok(base, treat)
    print(f"\nINSTRUMENT CHECK — 1-hop moved {gain:+.3f} (limit {INSTRUMENT_MAX_1HOP_GAIN:+.3f}).")
    if not ok:
        print("  ** CONTAMINATED. At k=16 one hop involves no chaining, so a gain this")
        print("     large is answer-matching, formatting or prompt sensitivity.")
        print("     The depth cells are NOT interpreted. No branch is printed.")
        return 1
    print("  passed — the depth cells are readable as reasoning.")

    print("\nPAIRED ACROSS MODELS, within question — exact McNemar, Holm over 3 hops.\n")
    tests = paired(base, treat)
    adjusted = holm({f"{hops}-hop": result[0] for hops, result in tests.items()})
    for hops in HOPS:
        p, up, down, n = tests[hops]
        key = f"{hops}-hop"
        value, rejected = adjusted[key]
        flag = "significant" if rejected else "not significant"
        print(f"  {key:<8} +{up}/-{down}  n={n:<5} p={p:.5f}  adj={value:.4f}  {flag}")

    if args.interim:
        print("\nINTERIM — cells printed, branch withheld. Every cell is paid and")
        print("written before any is read; this run is exploratory until it completes.")
        return 0

    verdict(points[1] - points[3], adjusted, "3-hop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
