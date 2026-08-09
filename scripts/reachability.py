#!/usr/bin/env python
"""Can the deterministic graph reach each question's gold rules from its cards?

The measurement that decides Phase 4's architecture. Phase 3 reduced
`CITES_RULE` to explicit citations (ADR-006), removing the intended
ruling→rule bridge. The open question was whether the *remaining*
deterministic structure — `Keyword-[:DEFINED_BY]->Rule`, the CR tree, and
the parser-validated `REFERENCES` cross-references — already reaches the
rules the golden set needs, over several hops.

Method: seed from each question's ``gold_entities`` (a card's keywords, or
a keyword named directly), expand k hops through the undirected union of
`REFERENCES` and the CR tree, and ask what fraction of ``gold_cr_rules``
falls inside the ball.

**Both numbers matter.** Coverage without a size bound is meaningless: a
ball containing half the Comprehensive Rules "reaches" almost anything and
discriminates nothing. The median ball size is printed beside the coverage
for exactly that reason, and it is what turns this from an encouraging
number into an honest one.

The third column is the one that ended the argument: questions whose
entities produce **no seed at all**. A card with no keyword abilities
(*Humility*, *Opalescence*) has no deterministic edge into the rule graph,
so no amount of traversal depth helps — what connects such a card to the
layer system is the meaning of its text, which is inference, not
structure.

    python scripts/reachability.py
    python scripts/reachability.py --hops 2 4 6 --stratum interaction_multihop

No Neo4j: the CR comes from the parser and the cards from the local bulk
file, so this runs offline like the rest of the phase's measurements.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.cr_parser import CR_TXT_PATH, CRDocument, parse_cr
from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.graph.loader import keyword_definition_rows

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOLDEN_DIR = Path("data/golden")
DEFAULT_HOPS = (2, 4, 6)


def rule_graph(doc: CRDocument) -> dict[str, set[str]]:
    """Undirected adjacency over `REFERENCES` plus the CR parent/child tree.

    Undirected on purpose: a traversal looking for the rule that governs a
    situation has no reason to respect the direction in which the document
    happens to cross-reference. Treating it as directed would understate
    what the graph can reach, and this measurement exists to give the
    architecture its *best* case.
    """
    adjacency: dict[str, set[str]] = {number: set() for number in doc.by_number}
    for rule in doc.rules:
        for target in rule.references:
            if target in adjacency:
                adjacency[rule.number].add(target)
                adjacency[target].add(rule.number)
        if rule.parent and rule.parent in adjacency:
            adjacency[rule.number].add(rule.parent)
            adjacency[rule.parent].add(rule.number)
    return adjacency


def keyword_rules(doc: CRDocument) -> dict[str, set[str]]:
    """Normalized keyword name -> the rules the glossary defines it by."""
    rules: dict[str, set[str]] = {}
    for row in keyword_definition_rows(doc):
        rules.setdefault(row["keyword"], set()).add(row["rule"])
    return rules


def seeds_for(
    entities: Iterable[str] | None,
    *,
    cards: Mapping[str, dict],
    kw_rules: Mapping[str, set[str]],
) -> tuple[set[str], dict[str, int]]:
    """Rules a question's entities land on, plus how each entity resolved.

    ``gold_entities`` mixes card names with keyword names, so both are
    tried — keyword first, since a keyword name is unambiguous here while
    a card may coincidentally share it.

    Returns:
        ``(seed_rules, counts)`` where ``counts`` breaks the entities into
        ``keyword`` / ``card_with_kw`` / ``card_no_kw`` / ``unknown``. The
        ``card_no_kw`` count is the finding, not bookkeeping: those cards
        have no deterministic edge into the rule graph at all.
    """
    seeds: set[str] = set()
    counts = {"keyword": 0, "card_with_kw": 0, "card_no_kw": 0, "unknown": 0}
    for name in entities or []:
        normalized = normalize_name(name)
        if normalized in kw_rules:
            seeds |= kw_rules[normalized]
            counts["keyword"] += 1
            continue
        card = cards.get(name)
        if card is None:
            counts["unknown"] += 1
            continue
        keywords = card.get("keywords", [])
        for keyword in keywords:
            seeds |= kw_rules.get(normalize_name(keyword), set())
        counts["card_with_kw" if keywords else "card_no_kw"] += 1
    return seeds, counts


def ball(seeds: set[str], adjacency: Mapping[str, set[str]], hops: int) -> set[str]:
    """Every rule within ``hops`` steps of ``seeds``, seeds included."""
    seen = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        nxt: set[str] = set()
        for node in frontier:
            nxt |= adjacency.get(node, set())
        nxt -= seen
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
    return seen


def load_questions(directory: Path) -> list[dict]:
    """Golden-set rows that name gold CR rules (the ones this can score)."""
    rows = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("gold_cr_rules"):
                    rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR)
    parser.add_argument("--cr", type=Path, default=CR_TXT_PATH)
    parser.add_argument("--cards", type=Path, default=None)
    parser.add_argument("--hops", type=int, nargs="+", default=list(DEFAULT_HOPS))
    parser.add_argument("--stratum", type=str, default=None)
    args = parser.parse_args()

    doc = parse_cr(args.cr)
    adjacency = rule_graph(doc)
    kw_rules = keyword_rules(doc)
    cards = {c["name"]: c for c in iter_bulk(args.cards or bulk_path(ORACLE_CARDS_STEM))}

    rows = load_questions(args.golden)
    if args.stratum:
        rows = [r for r in rows if r["stratum"] == args.stratum]
    if not rows:
        print(f"No golden rows with gold_cr_rules in {args.golden}.")
        return 1

    edges = sum(len(v) for v in adjacency.values()) // 2
    totals = {"keyword": 0, "card_with_kw": 0, "card_no_kw": 0, "unknown": 0}
    for row in rows:
        _, counts = seeds_for(row.get("gold_entities"), cards=cards, kw_rules=kw_rules)
        for key in totals:
            totals[key] += counts[key]

    print(
        f"{len(rows)} golden questions with gold CR rules; {len(adjacency)} rules and "
        f"{edges} deterministic edges (REFERENCES + tree)."
    )
    print(f"gold_entities resolved as: {totals}\n")

    strata = sorted({r["stratum"] for r in rows})
    for hops in args.hops:
        print(f"k={hops} hops:")
        print(f"  {'stratum':<22} {'gold reached':<16} {'median ball':<12} no seed")
        for stratum in strata:
            subset = [r for r in rows if r["stratum"] == stratum]
            hit = total = no_seed = 0
            sizes = []
            for row in subset:
                seeds, _ = seeds_for(row.get("gold_entities"), cards=cards, kw_rules=kw_rules)
                if not seeds:
                    no_seed += 1
                reached = ball(seeds, adjacency, hops) if seeds else set()
                gold = set(row["gold_cr_rules"])
                hit += len(gold & reached)
                total += len(gold)
                sizes.append(len(reached))
            median = sorted(sizes)[len(sizes) // 2]
            print(
                f"  {stratum:<22} {hit:>3}/{total:<3} ({hit / total:>4.0%})    "
                f"{median:>6}       {no_seed}/{len(subset)}"
            )
        print()

    print(
        "Read the three columns together. Coverage alone is not a result: a ball\n"
        "holding half the Comprehensive Rules reaches almost anything and\n"
        "discriminates nothing. And a question with no seed cannot be helped by\n"
        "more hops — its cards have no keyword, so nothing deterministic connects\n"
        "them to the rule graph at all."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
