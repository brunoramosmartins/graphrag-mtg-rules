#!/usr/bin/env python
"""Answer six golden-set questions with hand-written Cypher (Phase 2 acceptance).

This is the backbone's acceptance test: before any retrieval layer or LLM
exists, plain Cypher must already answer the structural strata of the golden
set. Each check names the golden-set id it satisfies and verifies the result
against that question's own answer key where one exists, so a passing run is
evidence, not a demo.

Nothing here is the eventual pipeline — Phase 4 replaces these with
parameterized templates. What it proves is that the graph *contains* the
answers.

Usage:
    docker compose up -d --wait
    python -m graphrag_mtg.graph.loader
    python scripts/sanity_cypher.py
    python scripts/sanity_cypher.py --verbose   # print the rows returned
"""

from __future__ import annotations

import argparse

from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.evaluation.golden import load_golden_dir
from graphrag_mtg.graph.connection import driver_session

GOLDEN_DIR = "data/golden"

# ─── Cypher (named constants; never built by interpolation) ──────────────────

Q_LEGALITY = """
MATCH (c:Card {name: $card})-[e:HAS_LEGALITY]->(f:Format {name: $format})
RETURN c.name AS card, f.name AS format, e.status AS status
"""

Q_KEYWORD_TO_RULE = """
MATCH (k:Keyword {name: $keyword})-[:DEFINED_BY]->(parent:Rule)
OPTIONAL MATCH (parent)-[:HAS_SUBRULE]->(sub:Rule)
RETURN parent.number AS parent, collect(sub.number) AS subrules
"""

Q_RULE_REFERENCES = """
MATCH (a:Rule {number: $number})-[:REFERENCES]->(b:Rule)
RETURN collect(b.number) AS targets
"""

Q_RULE_SUBTREE = """
MATCH (p:Rule {number: $number})-[:HAS_SUBRULE]->(c:Rule)
RETURN collect(c.number) AS subrules
"""

Q_CARD_RULINGS = """
MATCH (c:Card {name: $card})-[:HAS_RULING]->(r:Ruling)
RETURN count(r) AS rulings, collect(r.text)[0..2] AS sample
"""

Q_CARD_KEYWORD_RULE = """
MATCH (c:Card {name: $card})-[:HAS_KEYWORD]->(k:Keyword)-[:DEFINED_BY]->(r:Rule)
RETURN c.name AS card, collect(DISTINCT k.display_name) AS keywords,
       collect(DISTINCT r.number) AS rules
"""


def _golden(questions, question_id: str):
    """Return the golden question with ``question_id``, or None."""
    return next((q for q in questions if q.id == question_id), None)


def check_legality(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """legality_1hop — Card -[:HAS_LEGALITY]-> Format, verified against the key."""
    question = next(q for q in questions if q.stratum.value == "legality_1hop")
    card = question.gold_entities[0]
    fmt = next(f for f in question.gold_entities[1:] if f) if len(question.gold_entities) > 1 else None
    fmt = fmt or question.id.rsplit("-", 1)[-1]

    record = session.run(Q_LEGALITY, card=card, format=fmt).single()
    if record is None:
        return question.id, False, f"no legality edge for {card!r} in {fmt!r}"
    # The answer key is the question's own answer text.
    ok = record["status"].replace("_", " ") in question.answer.lower() or (
        record["status"] == "legal" and "is legal" in question.answer.lower()
    )
    detail = f"{card} in {fmt}: {record['status']}"
    if verbose:
        detail += f"   | key: {question.answer}"
    return question.id, ok, detail


def check_keyword_to_rule(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """keyword_rule_2hop — Keyword -[:DEFINED_BY]-> Rule -[:HAS_SUBRULE]-> Rule."""
    question = _golden(questions, "hand-protection-from-red-debt")
    keyword = normalize_name(question.gold_entities[0])
    expected = question.gold_cr_rules[0]  # 702.16e

    record = session.run(Q_KEYWORD_TO_RULE, keyword=keyword).single()
    if record is None:
        return question.id, False, f"keyword {keyword!r} has no defining rule"
    reachable = [record["parent"], *record["subrules"]]
    ok = expected in reachable
    detail = f"{keyword} -> {record['parent']} -> {len(record['subrules'])} subrules"
    if verbose:
        detail += f"   | need {expected}: {'found' if ok else 'MISSING'}"
    return question.id, ok, detail


def check_rule_references(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """REFERENCES — 510.4 (first-strike damage step) points at 702.7 (first strike)."""
    question = _golden(questions, "hand-first-strike-deathtouch")
    record = session.run(Q_RULE_REFERENCES, number="510.4").single()
    targets = record["targets"] if record else []
    ok = "702.7" in targets
    detail = f"510.4 REFERENCES {targets}"
    if verbose:
        detail += f"   | question cites {question.gold_cr_rules}"
    return question.id, ok, detail


def check_layer_sublayers(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """The layer system — 613.4's sublayers must contain 7b and 7c."""
    question = _golden(questions, "hand-humility-plus-counter")
    record = session.run(Q_RULE_SUBTREE, number="613.4").single()
    subrules = record["subrules"] if record else []
    ok = set(question.gold_cr_rules) <= set(subrules)
    detail = f"613.4 -> {sorted(subrules)}"
    if verbose:
        detail += f"   | question needs {question.gold_cr_rules}"
    return question.id, ok, detail


def check_card_rulings(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """Card -[:HAS_RULING]-> Ruling, for the interaction the thesis is named after."""
    question = _golden(questions, "hand-humility-opalescence")
    record = session.run(Q_CARD_RULINGS, card="Humility").single()
    count = record["rulings"] if record else 0
    ok = count > 0
    detail = f"Humility has {count} official rulings"
    if verbose and record and record["sample"]:
        detail += f"\n        e.g. {record['sample'][0][:96]}"
    return question.id, ok, detail


def check_card_keyword_rule(session, questions, verbose: bool) -> tuple[str, bool, str]:
    """The full 2-hop chain on a real card: Card -> Keyword -> Rule."""
    question = _golden(questions, "hand-deathtouch-trample")
    record = session.run(Q_CARD_KEYWORD_RULE, card="Vampire Nighthawk").single()
    if record is None:
        return question.id, False, "Vampire Nighthawk not reachable"
    ok = "702.2" in record["rules"]
    detail = f"Vampire Nighthawk -> {record['keywords']} -> {sorted(record['rules'])}"
    return question.id, ok, detail


CHECKS = (
    ("legality_1hop", check_legality),
    ("keyword_rule_2hop", check_keyword_to_rule),
    ("rule cross-reference", check_rule_references),
    ("layer-system subtree", check_layer_sublayers),
    ("card -> rulings", check_card_rulings),
    ("card -> keyword -> rule", check_card_keyword_rule),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="show answer keys and samples")
    args = parser.parse_args()

    questions = load_golden_dir(GOLDEN_DIR)
    failures = 0

    print(f"Six sanity questions against the loaded backbone ({len(questions)} golden rows)\n")
    with driver_session() as session:
        for label, check in CHECKS:
            question_id, ok, detail = check(session, questions, args.verbose)
            status = "PASS" if ok else "FAIL"
            failures += not ok
            print(f"  [{status}] {label:<24} {question_id}")
            print(f"         {detail}")

    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
