#!/usr/bin/env python
"""Check that every CR rule cited by the golden set exists in the real CR.

A cheap, mechanical guard against invented or stale rule numbers. It proves
existence only — whether a rule *says* what a question claims still needs a
judge. Run it after editing the golden set or after a CR release.

Needs ``data/raw/comprehensive_rules.txt`` (gitignored), so this is a script
rather than a test: the unit suite must not depend on downloaded data.

Usage:
    python scripts/check_cr_citations.py          # exits 1 if any citation is unknown
    python scripts/check_cr_citations.py --list   # also list every cited rule
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from graphrag_mtg.evaluation.golden import load_golden_dir

CR_TXT = Path("data/raw/comprehensive_rules.txt")
GOLDEN_DIR = Path("data/golden")

# Rule lines look like "613.4b Layer 7b: ..." or "510.4. If at least one ...".
# The CR ships as UTF-8 *with a BOM*, hence utf-8-sig.
_CR_RULE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s", re.MULTILINE)


def known_rules(path: Path = CR_TXT) -> set[str]:
    """Return every rule number defined in the Comprehensive Rules text."""
    text = path.read_text(encoding="utf-8-sig")
    return {match.group(1) for match in _CR_RULE.finditer(text)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list every cited rule")
    parser.add_argument("--cr", type=Path, default=CR_TXT)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    args = parser.parse_args()

    if not args.cr.exists():
        print(f"Missing {args.cr}. Fetch it first:")
        print("  CR_TXT_URL=... python -m graphrag_mtg.etl.download --source comprehensive-rules")
        return 1

    rules = known_rules(args.cr)
    questions = load_golden_dir(args.golden)
    cited = [(q.id, rule) for q in questions for rule in q.gold_cr_rules]
    unknown = [(qid, rule) for qid, rule in cited if rule not in rules]

    print(f"CR rules defined:     {len(rules):,}")
    print(f"golden questions:     {len(questions):,}")
    print(f"citations checked:    {len(cited):,}")
    print(f"unknown citations:    {len(unknown)}")

    if args.list:
        for qid, rule in sorted(cited):
            print(f"  {'??' if rule not in rules else 'ok'}  {qid:<38} {rule}")

    if unknown:
        print("\nThese cited rules do not exist in the current CR:")
        for qid, rule in unknown:
            print(f"  {qid:<38} {rule}")
        return 1

    print("\nAll cited rules exist in the current Comprehensive Rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
