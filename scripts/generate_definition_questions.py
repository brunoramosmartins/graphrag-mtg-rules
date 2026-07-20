#!/usr/bin/env python
"""Generate the ``definition_1hop`` golden questions from the CR glossary.

This stratum restores the **tie** prediction. The evaluation needs strata where
the vector baseline should draw: if every stratum predicts a graph win, a
reported win cannot be falsified and the comparison is worthless. A keyword's
effect is written in one self-contained CR passage, so both retrievers should
find it — that is exactly the honest draw.

Each keyword is validated against the real parsed document before a row is
emitted: the glossary must contain the term, and the cited rule must exist in
the tree. The answer prose is **ours** — copying glossary text into a committed
file would redistribute CR text, which the project's IP rules forbid.

Usage:
    python -m graphrag_mtg.etl.download --source comprehensive-rules
    python scripts/generate_definition_questions.py
    python scripts/generate_definition_questions.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from graphrag_mtg.etl.cr_parser import parse_cr
from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.evaluation.generators import build_definition_question
from graphrag_mtg.evaluation.golden import dump_golden

OUT_PATH = Path("data/golden/definitions_v0.jsonl")

# (display keyword, defining CR rule, our paraphrase of what it does).
#
# Twelve keyword abilities (702.x) and three keyword actions (701.x). Every
# paraphrase was written against the rule's own text and says what the keyword
# *does*, not what category it belongs to — "Flying is an evasion ability" is
# true and useless as an answer key.
_DEFINITIONS: list[tuple[str, str, str]] = [
    (
        "Flying",
        "702.9",
        "A creature with flying can't be blocked except by creatures that have "
        "flying and/or reach. It can itself block any creature, flying or not.",
    ),
    (
        "Trample",
        "702.19",
        "An attacking creature with trample assigns lethal damage to its blockers "
        "first; any excess may be assigned to the player, planeswalker, or battle "
        "it is attacking. Its controller may assign less than lethal to the "
        "blockers, but then no damage may go through to the defender.",
    ),
    (
        "Vigilance",
        "702.20",
        "Attacking does not cause a creature with vigilance to tap, so it can "
        "attack and still be untapped to block.",
    ),
    (
        "Haste",
        "702.10",
        "A creature with haste ignores the summoning-sickness restriction: it can "
        "attack, and use abilities with {T} or {Q} in their cost, even if it has "
        "not been under its controller's control since their turn began.",
    ),
    (
        "Flash",
        "702.8",
        "Flash lets you play the card any time you could cast an instant, rather "
        "than only at sorcery speed.",
    ),
    (
        "Reach",
        "702.17",
        "A creature with reach can block creatures with flying. It grants no "
        "evasion of its own.",
    ),
    (
        "First strike",
        "702.7",
        "A creature with first strike deals its combat damage in a separate, "
        "earlier combat damage step. Creatures without first strike or double "
        "strike deal theirs in the normal step that follows.",
    ),
    (
        "Menace",
        "702.111",
        "A creature with menace can't be blocked except by two or more creatures.",
    ),
    (
        "Lifelink",
        "702.15",
        "Damage dealt by a source with lifelink also causes that source's "
        "controller to gain that much life. It applies to any damage, not just "
        "combat damage.",
    ),
    (
        "Deathtouch",
        "702.2",
        "Any nonzero amount of damage dealt by a source with deathtouch counts as "
        "lethal: a creature dealt such damage is destroyed as a state-based "
        "action, whatever its toughness.",
    ),
    (
        "Defender",
        "702.3",
        "A creature with defender can't attack. It can still block normally.",
    ),
    (
        "Indestructible",
        "702.12",
        "A permanent with indestructible can't be destroyed: it is not destroyed "
        "by lethal damage and ignores effects that say 'destroy'. It can still "
        "leave the battlefield by other means, such as sacrifice, exile, or "
        "having 0 toughness.",
    ),
    (
        "Mill",
        "701.17",
        "To mill a number of cards, a player puts that many cards from the top of "
        "their library into their graveyard.",
    ),
    (
        "Scry",
        "701.22",
        "To scry N, look at the top N cards of your library, put any number of "
        "them on the bottom in any order, and the rest back on top in any order.",
    ),
    (
        "Regenerate",
        "701.19",
        "Regenerating a permanent creates a shield: the next time it would be "
        "destroyed this turn, instead all damage marked on it is removed and its "
        "controller taps it, removing it from combat if it was attacking or "
        "blocking.",
    ),
]


def validate(doc, keyword: str, rule_number: str) -> str | None:
    """Return an error message if the keyword or its rule is not in the CR."""
    if rule_number not in doc.by_number:
        return f"rule {rule_number} does not exist in the parsed CR"
    glossary = {normalize_name(entry.term) for entry in doc.glossary}
    if normalize_name(keyword) not in glossary:
        return f"{keyword!r} is not a glossary term"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate and print only")
    args = parser.parse_args()

    doc = parse_cr()
    print(f"CR effective {doc.effective_date}: {len(doc.rules):,} rules, {len(doc.glossary)} glossary terms\n")

    questions, errors = [], []
    for keyword, rule_number, answer in _DEFINITIONS:
        problem = validate(doc, keyword, rule_number)
        if problem:
            errors.append(f"  {keyword:<16} {problem}")
            continue
        questions.append(build_definition_question(keyword, rule_number, answer))
        print(f"  ok  {keyword:<16} -> {rule_number}")

    if errors:
        print("\nValidation failed:")
        print("\n".join(errors))
        return 1

    print(f"\n{len(questions)} definition_1hop questions, all vector_should=tie")
    if args.dry_run:
        print("Dry run: wrote nothing.")
        return 0

    dump_golden(questions, OUT_PATH)
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
