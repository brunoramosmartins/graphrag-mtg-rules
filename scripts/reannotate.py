#!/usr/bin/env python
"""Intra-annotator agreement: re-annotate a blind subsample, then compare.

E-003 measures the extractor against a gold written by one annotator. That
number has no meaning without a ceiling: if the same person, re-reading the
same rulings, cites different rules, the task itself is ambiguous and no
system could have scored higher. This script measures that ceiling.

Two steps, deliberately separated in time:

    # 1. draw the sample and write a blinded copy (once)
    python scripts/reannotate.py draw --n 20

    # 2. after re-citing every row in the blind file, compare
    python scripts/reannotate.py compare

Between them, the annotator re-cites the blind file with the *same* tools as
the original pass -- nothing new is introduced, or the two passes would not
be comparable:

    python scripts/annotation_worksheet.py --draft data/interim/reannotation_draft.jsonl \
        --citation-pass --needs-citations
    python scripts/cite_search.py --ruling <id>
    python scripts/cite.py <id> 603.7 --draft data/interim/reannotation_draft.jsonl

The blind file carries the ruling text and the mentions but **no**
``cited_rules`` -- pass 1 is not visible while pass 2 is written.

Agreement is reported with the same metric as E-003 (micro P/R/F1 with
per-document bootstrap CIs, on ``(ruling_id, rule_number)``), so the two
numbers sit on the same scale. Micro F1 is symmetric under swapping the two
sets, so which pass is called "gold" does not change the figure; pass 1 is
passed as gold only so precision and recall read in the familiar direction.

Ordering matters: this must run **before** the annotator inspects any
disagreement between the gold and the system. Re-reading rulings that were
just re-litigated against the model's output is not a blind second pass.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Hashable, Mapping
from datetime import date, datetime
from pathlib import Path

from graphrag_mtg.evaluation.metrics import StratumReport, by_family, evaluate_by_stratum

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_PATH = Path("data/interim/extraction_annotations_draft.jsonl")
BLIND_PATH = Path("data/interim/reannotation_draft.jsonl")
SAMPLE_PATH = Path("data/golden/reannotation_sample_ids.json")

DEFAULT_N = 20
DEFAULT_SEED = 20260809


def read_rows(path: Path) -> list[dict]:
    """Read a JSONL annotation file into a list of rows."""
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_rows(path: Path, rows: list[dict]) -> None:
    """Write annotation rows back as JSONL, one object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def allocate(counts: Mapping[str, int], n: int) -> dict[str, int]:
    """Split ``n`` draws across strata proportionally (largest remainder).

    Proportional rather than equal so the subsample has the same
    composition as the split it measures. At n=20 the per-stratum cells
    are far too thin to report separately -- they exist to keep the
    *overall* figure representative, not to be read stratum by stratum.
    """
    total = sum(counts.values())
    if total == 0:
        return {}
    if n >= total:
        return dict(counts)
    exact = {s: c * n / total for s, c in counts.items()}
    base = {s: int(v) for s, v in exact.items()}
    order = sorted(counts, key=lambda s: (-(exact[s] - base[s]), s))
    for stratum in order[: n - sum(base.values())]:
        base[stratum] += 1
    return base


def draw_sample(rows: list[dict], n: int, seed: int, split: str) -> list[str]:
    """Pick ``n`` reviewed ruling ids from ``split``, stratified and seeded.

    Only rows whose citation pass is finished are eligible: an unreviewed
    row has no pass 1 to disagree with.
    """
    eligible: dict[str, list[str]] = {}
    for row in rows:
        if row["split"] != split or not row.get("citations_reviewed"):
            continue
        eligible.setdefault(row["stratum"], []).append(row["ruling_id"])

    rng = random.Random(seed)
    quota = allocate({s: len(ids) for s, ids in eligible.items()}, n)
    drawn: list[str] = []
    for stratum in sorted(quota):
        drawn.extend(rng.sample(sorted(eligible[stratum]), quota[stratum]))
    return sorted(drawn)


def blind_row(row: dict) -> dict:
    """Copy one row with pass 1's citation decision removed.

    Keeps the ruling text and the mentions -- the linking pass is not
    under measurement here, and the worksheet needs the text to be
    readable. Everything that records what was cited, or that it was
    cited at all, is reset to the pre-annotation state.
    """
    blinded = dict(row)
    blinded["cited_rules"] = []
    blinded["citations_reviewed"] = False
    blinded["notes"] = ""
    return blinded


def cited(row: dict) -> set[str]:
    """The set of rule numbers a row cites, tolerating the older key."""
    return {c.get("rule_number") or c.get("rule") for c in row.get("cited_rules", [])}


def as_items(rows: Mapping[str, dict]) -> dict[str, frozenset[Hashable]]:
    """Key citations the way E-003 does: ``(ruling_id, rule_number)``."""
    return {rid: frozenset((rid, n) for n in cited(row)) for rid, row in rows.items()}


def print_report(title: str, reports: list[StratumReport]) -> None:
    """Print one stratified table, overall row first (same shape as the scorer)."""
    print(f"\n{title}")
    print(f"  {'stratum':<14} {'P':<22} {'R':<22} {'F1':<22} counts")
    for report in reports:
        counts = report.counts
        print(
            f"  {report.stratum:<14} {report.precision!s:<22} {report.recall!s:<22} "
            f"{report.f1!s:<22} tp={counts.tp} fp={counts.fp} fn={counts.fn}"
        )


def cmd_draw(args: argparse.Namespace) -> int:
    """Freeze a subsample and write the blinded copy for pass 2."""
    if args.blind.exists() and not args.force:
        print(f"error: {args.blind} already exists -- pass 2 may be in progress.")
        print("Delete it deliberately, or pass --force, to draw a new sample.")
        return 1

    rows = read_rows(args.draft)
    ids = draw_sample(rows, args.n, args.seed, args.split)
    if not ids:
        print(f"No citation-reviewed rows in split {args.split!r} of {args.draft}.")
        return 1

    by_id = {row["ruling_id"]: row for row in rows}
    write_rows(args.blind, [blind_row(by_id[rid]) for rid in ids])

    counts: dict[str, int] = {}
    for rid in ids:
        counts[by_id[rid]["stratum"]] = counts.get(by_id[rid]["stratum"], 0) + 1
    args.sample.parent.mkdir(parents=True, exist_ok=True)
    args.sample.write_text(
        json.dumps(
            {
                "purpose": "intra-annotator agreement on CITES_RULE (E-003 ceiling)",
                "source": str(args.draft),
                "split": args.split,
                "seed": args.seed,
                "n": len(ids),
                "drawn_at": date.today().isoformat(),
                "strata": counts,
                "ruling_ids": ids,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Drew {len(ids)} rulings (seed {args.seed}), strata {counts}.")
    print(f"  frozen sample: {args.sample}")
    print(f"  blind draft:   {args.blind}  (cited_rules cleared)")
    print("\nRe-cite every row WITHOUT looking at the original draft:")
    print(
        f"  python scripts/annotation_worksheet.py --draft {args.blind} "
        "--citation-pass --needs-citations"
    )
    print(f"  python scripts/cite.py <ruling_id> <rules...> --draft {args.blind}")
    print("\nThen: python scripts/reannotate.py compare")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Score pass 2 against pass 1 with the E-003 citation metric."""
    if not args.blind.exists():
        print(f"No blind draft at {args.blind}. Run `reannotate.py draw` first.")
        return 1

    pass2_rows = {r["ruling_id"]: r for r in read_rows(args.blind)}
    pass1_rows = {r["ruling_id"]: r for r in read_rows(args.draft) if r["ruling_id"] in pass2_rows}

    pending = [rid for rid, row in pass2_rows.items() if not row.get("citations_reviewed")]
    if pending:
        print(f"{len(pending)} of {len(pass2_rows)} rows are not re-cited yet:")
        for rid in pending[:10]:
            print(f"  {rid}")
        print("Finish pass 2 before comparing -- a partial pass biases the figure.")
        return 1

    missing = sorted(set(pass2_rows) - set(pass1_rows))
    if missing:
        print(f"error: {len(missing)} blind rows have no pass 1 in {args.draft}: {missing[:3]}")
        return 1

    if args.sample.exists():
        meta = json.loads(args.sample.read_text(encoding="utf-8"))
        drawn = datetime.fromisoformat(meta["drawn_at"]).date()
        gap = (date.today() - drawn).days
        print(f"Sample drawn {meta['drawn_at']} (seed {meta['seed']}), compared {gap} day(s) later.")
        if gap < 1:
            print(
                "  Caveat: same-day re-annotation is recall, not independent judgement.\n"
                "  The agreement below is an OPTIMISTIC bound on the ceiling."
            )

    strata = {rid: row["stratum"] for rid, row in pass1_rows.items()}
    p1, p2 = as_items(pass1_rows), as_items(pass2_rows)

    print(f"\nIntra-annotator agreement on {len(p1)} rulings, pass 1 as reference.")
    print_report("Citations, PRIMARY (ruling, rule_number)", evaluate_by_stratum(p2, p1, stratum_by_doc=strata))
    print_report(
        "Citations, SECONDARY -- family only (rule without subrule letter)",
        evaluate_by_stratum(by_family(p2), by_family(p1), stratum_by_doc=strata),
    )

    identical = sum(1 for rid in p1 if p1[rid] == p2[rid])
    print(f"\nRulings cited identically in both passes: {identical}/{len(p1)}")

    print("\nPer-ruling differences (pass 1 -> pass 2):")
    for rid in sorted(p1):
        first, second = cited(pass1_rows[rid]), cited(pass2_rows[rid])
        if first == second:
            continue
        print(f"  {rid}  {strata[rid]}")
        print(f"    only pass 1: {sorted(first - second) or '-'}")
        print(f"    only pass 2: {sorted(second - first) or '-'}")
        print(f"    both:        {sorted(first & second) or '-'}")
        if args.show_text:
            print(f"    {pass1_rows[rid]['text'][:300]}")

    print(
        "\nThis F1 is the ceiling the E-003 citation score is measured against\n"
        "(annotation-split figure in experiments/registry.md). A system cannot\n"
        "be expected to agree with the gold more than the gold agrees with\n"
        "itself. Record the figure in docs/evaluation.md beside the results;\n"
        "it replaces the 'agreement unmeasured' limitation, and it does NOT\n"
        "license changing any gold label -- that is the adjudication rule's job."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DRAFT_PATH)
    parser.add_argument("--blind", type=Path, default=BLIND_PATH)
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    draw = sub.add_parser("draw", help="freeze a subsample and blind it")
    draw.add_argument("--n", type=int, default=DEFAULT_N)
    draw.add_argument("--seed", type=int, default=DEFAULT_SEED)
    draw.add_argument("--split", choices=("dev", "annotation"), default="annotation")
    draw.add_argument("--force", action="store_true", help="overwrite an existing blind draft")
    draw.set_defaults(func=cmd_draw)

    compare = sub.add_parser("compare", help="score pass 2 against pass 1")
    compare.add_argument("--show-text", action="store_true", help="print the ruling on a diff")
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
