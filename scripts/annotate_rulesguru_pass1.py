#!/usr/bin/env python
"""First annotation pass over the RulesGuru rows (issue #9).

Applies the procedure in docs/annotation-guide.md to every ``rulesguru``
row in ``data/golden/ids_v0.jsonl``: re-derive ``stratum`` from the
question's shape and RulesGuru ``tags`` (the seeded value came from
``complexity``, which measures difficulty, not traversal depth), set
``hops``, write ``gold_path``, fill ``gold_cr_rules`` where RulesGuru left
them empty, and record ``vector_should`` with a reason.

Every rule number added here was looked up in the downloaded CR, not
recalled; ``scripts/check_cr_citations.py`` re-proves that afterwards.

The answer keys themselves are untouched and unreviewed by design - they
are judge-curated. What this pass asserts is our classification.

Usage:
    python scripts/annotate_rulesguru_pass1.py
    python scripts/annotate_rulesguru_pass1.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from graphrag_mtg.evaluation.golden import (
    Source,
    Stratum,
    VectorExpectation,
    dump_golden,
    load_golden,
)

GOLDEN = Path("data/golden/ids_v0.jsonl")

_IM = Stratum.interaction_multihop
_NT = Stratum.negative_temporal
_KR = Stratum.keyword_rule_2hop

# id -> (stratum, hops, gold_path, vector_should, reason, extra_cr_rules or None)
# `extra_cr_rules` replaces the seeded list; None keeps RulesGuru's own
# citations, which are reliable when present.
ANNOTATIONS: dict[str, tuple] = {
    "rg-3": (
        _IM, 3,
        "(:Card {Cultivator of Blades}) x4 -> trigger ordering (:Rule {603.3b}); each resolution re-reads power",
        "Four copies pump each other as their triggers resolve in an order the controller picks; the maximum is a computed sequence, not a stated fact.",
        ["603.3b"],
    ),
    "rg-20": (
        _IM, 3,
        "(:Card {Rite of Replication})->(:Card {Hamletback Goliath}) -> (:Rule {603.3b}) ordering + (:Rule {608.2h}) resolution",
        "The maximum total power depends on the order the controller stacks the triggers and on each trigger re-checking power on resolution.",
        None,
    ),
    "rg-30": (
        _NT, 2,
        "(:Card {Mina and Denn, Wildborn}) static land-play modifier -> (:Rule {305.2a}); blinking does not reset plays already made",
        "The answer is 'no' because a resource already spent is not restored by a new object entering; nothing states this non-effect.",
        None,
    ),
    "rg-51": (
        _NT, 3,
        "manifested (:Card {Progenitus}) has no abilities -> replacement (:Rule {614.4}) must pre-exist the event -> graveyard",
        "Turns on a replacement effect *not* existing at the moment of the event; a passage describing Progenitus says the opposite of what happens here.",
        None,
    ),
    "rg-102": (
        _IM, 3,
        "(:Card {Death's Shadow}) CDA power-from-life + (:Card {Temur Battle Rage}) double strike -> two damage steps (:Rule {510.4}) -> (:Rule {704.3}) SBAs between them",
        "Damage is assigned across two combat damage steps while both creatures' power changes with life totals; the final number is a simulation, not a passage.",
        None,
    ),
    "rg-198": (
        _IM, 3,
        "(:Card {Forerunner of the Empire}) damage trigger <-> (:Card {Polyraptor}) creation loop -> (:Rule {603.3b})",
        "The count comes from a self-feeding trigger loop between two permanents; no passage states how many end up on the battlefield.",
        ["603.3b"],
    ),
    "rg-271": (
        _IM, 2,
        "(:Card {Aurelia, the Warleader}) adds a phase -> (:Card {Time Stop}) ends the turn -> (:Rule {500.8})",
        "Requires knowing an added phase is part of the current turn's structure and is therefore skipped; the interaction is stated in neither card.",
        None,
    ),
    "rg-396": (
        _IM, 3,
        "(:Card {Heat Shimmer}) token copy -> copiable values (:Rule {707.9a}) -> populate copies the copy",
        "A copy of a copy inherits added abilities only because they became copiable values; the chain is not written in any single passage.",
        None,
    ),
    "rg-539": (
        _IM, 3,
        "six attacking (:Card)-[:HAS_KEYWORD]->(:Keyword {mentor})-[:DEFINED_BY]->(:Rule {702.134a}) -> ordering (:Rule {603.3b})",
        "Total damage depends on the order six mentor triggers resolve, each changing the power that later triggers check.",
        ["702.134a", "603.3b"],
    ),
    "rg-615": (
        _NT, 3,
        "(:Card {Yixlid Jailer}) removes graveyard abilities (layer 6, :Rule {613.1f}) -> (:Card {Dearly Departed}) ability absent -> no counter",
        "The answer is 'no' because an ability does not exist in the graveyard; a passage about Dearly Departed states the opposite.",
        ["613.1f"],
    ),
    "rg-650": (
        _IM, 3,
        "(:Card {Sindbad}) draw -> replaced by (:Card {Enduring Renewal}) (:Rule {614.6}) -> downstream discard never happens",
        "One replacement effect consumes the event a second effect depended on; the outcome is a chain, not a stated rule.",
        None,
    ),
    "rg-705": (
        _IM, 3,
        "(:Card {Wolf's Quarry}) tokens -> six triggers (:Rule {603.3b}) ordered so (:Card {Midnight Guard}) untaps between (:Card {Mentor of the Meek}) payments (:Rule {603.5})",
        "Feasibility depends on interleaving six simultaneous triggers in a chosen order; nothing states that the payment can be made three times.",
        None,
    ),
    "rg-778": (
        _NT, 2,
        "opening-hand action (:Card {Leyline Axe}) vs mulligan completion order -> (:Rule {103.6})",
        "The answer is 'no' purely because of the order two start-of-game procedures happen in; neither card mentions the other.",
        None,
    ),
    "rg-1029": (
        _NT, 3,
        "(:Card {Firemane Angel}) intervening-if trigger (:Rule {603.4}) + object identity across zones (:Rule {400.7})",
        "No life is gained because the intervening-if clause re-checks a specific object that no longer exists as the same object.",
        None,
    ),
    "rg-1182": (
        _IM, 3,
        "(:Card {Seasoned Pyromancer}) discard -> destination replaced by (:Card {Leyline of the Void}) (:Rule {701.9a}) -> effect still sees the cards (:Rule {400.7j})",
        "The token count turns on an effect still 'seeing' cards whose destination was replaced; the two cards never reference each other.",
        None,
    ),
    "rg-1469": (
        _IM, 3,
        "(:Card {Prismatic Omen}) + (:Card {Magus of the Moon}) type-changing (:Rule {613.1d}) resolved by dependency (:Rule {613.8a}) -> land subtypes (:Rule {305.7})",
        "Two type-changing effects apply in an order fixed by dependency, not timestamp; the resulting subtypes are stated nowhere.",
        None,
    ),
    "rg-1591": (
        _NT, 2,
        "(:Card {Bring to Light}) cast is legal but (:Card {Teferi, Time Raveler}) static (:Rule {307.5}) blocks the exiled cast (:Rule {608.2n})",
        "The answer splits: the spell resolves but its payoff cannot; a passage about either card alone gives the wrong answer.",
        None,
    ),
    "rg-1951": (
        _IM, 2,
        "(:Card {Golgari Grave-Troll}) self-counting replacement (:Rule {614.12}) checked while still in the graveyard (:Rule {614.4})",
        "The count depends on when the game checks the replacement effect relative to the zone change; the number is not stated.",
        None,
    ),
    "rg-2066": (
        _KR, 2,
        "(:Keyword {mutate})-[:DEFINED_BY]->(:Rule {702.140a}) - a mutating creature spell is a creature spell",
        None,
        None,
    ),
    "rg-2249": (
        _IM, 3,
        "(:Card {Strionic Resonator}) copies the trigger (:Rule {707.10}) -> copy resolves first (:Rule {603.3b}) -> (:Card {Omnath, Locus of Creation}) counts resolutions",
        "The outcome depends on a copied trigger resolving before the original and changing which mode the original takes.",
        ["707.10", "603.3b"],
    ),
    "rg-2333": (
        _IM, 3,
        "(:Card {Tentative Connection}) control change (:Rule {506.2}) + equipment stays with its controller (:Rule {301.5d}) -> token controller (:Rule {506.3b})",
        "Token control follows the Equipment's controller, not the attacking player; the split is a composition of three rules.",
        None,
    ),
    "rg-2569": (
        _IM, 3,
        "three counter-replacement effects on one ETB -> controller orders them (:Rule {616.1}), checked from the graveyard (:Rule {614.12})",
        "The count is 5 or 6 depending on an ordering choice among three replacement effects; no passage gives a number.",
        None,
    ),
    "rg-2711": (
        _IM, 3,
        "(:Card {Brutal Cathar}) leaves -> exiled card returns mid-resolution (:Rule {608.2}) -> (:Card {Angel of Vitality}) replaces the life gain (:Rule {614.1a}) -> (:Rule {610.3})",
        "The counter count depends on a zone change happening mid-resolution and a replacement effect that turns out not to matter; a passage cannot state it.",
        None,
    ),
    "rg-3155": (
        _IM, 3,
        "marked damage persists across a type change -> (:Rule {120.6})",
        "The creature dies because damage marked earlier survived it ceasing to be a creature; the answer contradicts the naive reading.",
        None,
    ),
    "rg-3228": (
        _IM, 3,
        "(:Card {Magus of the Moon}) type-change (layer 4, :Rule {613.1d}) applied before (:Card {Honest Work}) ability removal (layer 6, :Rule {613.1f})",
        "The land is a Mountain only because layer 4 precedes layer 6; the outcome is the layer order, not either card's text.",
        None,
    ),
    "rg-3915": (
        _IM, 2,
        "(:Card {Strixhaven Stadium}) triggers twice simultaneously -> controller orders them (:Rule {603.3b}) -> which opponent loses",
        "Who loses is decided by a stacking choice between two simultaneous triggers, not by anything the card states.",
        None,
    ),
    "rg-4640": (
        _KR, 2,
        "(:Keyword {protection})-[:DEFINED_BY]->(:Rule {702.16b})/(:Rule {702.16e}) - protection is from other sources, not itself",
        None,
        None,
    ),
    "rg-4853": (
        _IM, 2,
        "control change leaves the Equipment attached -> 'modified' definition (:Rule {700.9})",
        "Being modified survives a control change because nothing unattached the Equipment; two rules must be composed.",
        None,
    ),
    "rg-6370": (
        _IM, 3,
        "animated (:Card {Inkmoth Nexus}) + (:Card {Dress Down}) ability removal (layer 6, :Rule {613.1f}) ordered by timestamp (:Rule {613.7})",
        "The permanent's final characteristics come from two continuous effects applied in timestamp order; no passage describes the result.",
        ["613.1f", "613.7"],
    ),
    "rg-7749": (
        _IM, 3,
        "two (:Card {Ocelot Pride}) triggers resolve in sequence (:Rule {603.3b}); each copies the tokens the previous one made",
        "The final token count is a sequence where each trigger copies what the previous created; the number is computed, not stated.",
        ["603.3b"],
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    args = parser.parse_args()

    questions = load_golden(args.golden)
    changed = 0
    missing = set(ANNOTATIONS)

    for question in questions:
        if question.source != Source.rulesguru:
            continue
        spec = ANNOTATIONS.get(question.id)
        if spec is None:
            print(f"  !! no annotation for {question.id}")
            continue
        missing.discard(question.id)
        stratum, hops, path, reason, rules = spec

        question.stratum = stratum
        question.hops = hops
        question.gold_path = path
        question.vector_should = (
            VectorExpectation.lose if reason is None else VectorExpectation.fail
        )
        question.vector_should_reason = reason
        if rules is not None:
            question.gold_cr_rules = rules
        question.verified = True
        changed += 1

    print(f"annotated {changed} RulesGuru row(s)")
    if missing:
        print(f"  !! annotations with no matching row: {sorted(missing)}")

    if args.dry_run:
        print("Dry run: wrote nothing.")
        return 0

    dump_golden(questions, args.golden)
    print(f"Wrote {len(questions)} row(s) to {args.golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
