#!/usr/bin/env python
"""Simulate a quarterly CR release and prove the graph converges (Phase 2 DoD).

The Comprehensive Rules are republished every few months, and a release does
not only add: it **rewrites** rule text and **withdraws** rules whose content
moved or was renumbered. A MERGE-only load handles the first two cases and
silently fails the third, since MERGE never deletes — a withdrawn rule would
survive forever as a ghost node while ``--stats`` reported a healthy graph.

This script builds a synthetic "previous version" from the current document
(one rule reworded, one rule that the current CR does not contain), loads it,
loads the current document on top, and asserts the graph ends up describing
exactly the current document.

A synthetic previous version is used deliberately: WotC does not keep old CR
URLs stable, and synthesising the diff lets the test state precisely which
change it is checking.

Usage:
    docker compose up -d --wait
    python -m graphrag_mtg.graph.loader     # backbone must be loaded first
    python scripts/simulate_cr_update.py
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, parse_cr
from graphrag_mtg.graph.connection import driver_session
from graphrag_mtg.graph.loader import load_rules

# The rule whose wording we pretend changed between releases.
REWORDED_RULE = "613.4b"
_REWORDED_ANCHOR = "613.4b Layer 7b: Effects that set power"
_REWORDED_OLD = "613.4b Layer 7b: PREVIOUS WORDING - effects that set power"

# A rule the "previous" CR had and the current one withdrew. 702.2 runs a-f, so
# 702.2g is free; it must be a single letter, which is what the parser accepts.
WITHDRAWN_RULE = "702.2g"
_WITHDRAWN_ANCHOR = "702.2f Multiple instances of deathtouch"
_WITHDRAWN_LINE = "702.2g A rule that the current CR no longer contains."

COUNT_RULES = "MATCH (r:Rule) RETURN count(r) AS n"
GET_RULE_TEXT = "MATCH (r:Rule {number: $number}) RETURN r.text AS text"
COUNT_RULE = "MATCH (r:Rule {number: $number}) RETURN count(r) AS n"


def build_previous_version(current: Path, destination: Path) -> Path:
    """Write a synthetic earlier CR: one rule reworded, one rule extra."""
    text = current.read_text(encoding="utf-8-sig")
    if _REWORDED_ANCHOR not in text or _WITHDRAWN_ANCHOR not in text:
        msg = "The CR text no longer contains the anchors this simulation edits."
        raise ValueError(msg)

    text = text.replace(_REWORDED_ANCHOR, _REWORDED_OLD)
    text = text.replace(_WITHDRAWN_ANCHOR, f"{_WITHDRAWN_LINE}\n\n{_WITHDRAWN_ANCHOR}")
    destination.write_text("﻿" + text, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        previous_path = build_previous_version(args.cr, Path(tmp) / "cr_previous.txt")
        previous = parse_cr(previous_path)
        current = parse_cr(args.cr)

        withdrawn = sorted(set(previous.by_number) - set(current.by_number))
        print(f"previous version : {len(previous.rules):,} rules")
        print(f"current version  : {len(current.rules):,} rules")
        print(f"withdrawn by the release: {withdrawn}\n")

        failures = []
        with driver_session() as session:
            print("-- loading the previous version --")
            load_rules(session, previous, "sha-previous", size=1_000)
            before = session.run(COUNT_RULES).single()["n"]
            old_text = session.run(GET_RULE_TEXT, number=REWORDED_RULE).single()["text"]
            print(f"   Rule nodes: {before:,}")
            print(f"   {REWORDED_RULE}: {old_text[:64]}")

            print("\n-- loading the current version on top (no manual rebuild) --")
            counts = load_rules(session, current, "sha-current", size=1_000)
            after = session.run(COUNT_RULES).single()["n"]
            new_text = session.run(GET_RULE_TEXT, number=REWORDED_RULE).single()["text"]
            ghost = session.run(COUNT_RULE, number=WITHDRAWN_RULE).single()["n"]
            print(f"   Rule nodes: {after:,}")
            print(f"   {REWORDED_RULE}: {new_text[:64]}")
            print(f"   pruned: {counts['pruned']}")

            # 1. Reworded text must be the current one.
            if "PREVIOUS WORDING" in new_text:
                failures.append(f"{REWORDED_RULE} kept its old wording")
            # 2. The withdrawn rule must be gone, not a ghost.
            if ghost:
                failures.append(f"{WITHDRAWN_RULE} survived the update as a ghost node")
            # 3. The graph must describe exactly the current document.
            if after != len(current.rules):
                failures.append(f"graph has {after:,} rules, document has {len(current.rules):,}")

        print()
        if failures:
            print("FAILED — the graph does not match the current document:")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print("PASS — the graph converged on the current document without a rebuild:")
        print(f"  reworded rule updated, {WITHDRAWN_RULE} withdrawn, {after:,} rules exactly")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
