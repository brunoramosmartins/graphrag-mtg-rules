#!/usr/bin/env python
"""Author the hard-interaction golden questions (our content, CR-grounded).

Emits ``data/golden/authored_v0.jsonl`` — genuine multi-card interactions
(layers, replacement effects, timestamps, SBAs) that are the "hard core"
the graph thesis exists to answer. Fully committable (our content, zero
third-party license).

Verification: every CR citation is machine-checked against the downloaded
Comprehensive Rules (that check caught four wrong citations - the layer-7
sublayers are 613.4a-d, not 613.7), and the author has signed off on the
rulings. Re-run that check after editing:

    python scripts/check_cr_citations.py

Usage:
    python scripts/build_authored_set.py
"""

from __future__ import annotations

from pathlib import Path

from graphrag_mtg.evaluation.golden import (
    GoldenQuestion,
    Source,
    Stratum,
    VectorExpectation,
    content_sha256,
    dump_golden,
)

OUT_PATH = Path("data/golden/authored_v0.jsonl")

# (id, stratum, hops, question, answer, entities, cr_rules, path, vector, reason)
_SPECS: list[tuple] = [
    (
        "hand-humility-opalescence",
        Stratum.interaction_multihop,
        3,
        "You control Humility, Opalescence, and Ghostly Prison. Humility entered before "
        "Opalescence. What are Ghostly Prison's power and toughness?",
        "3/3 (its mana value), with no abilities. Opalescence makes each other non-Aura "
        "enchantment a creature (layer 4) with base P/T equal to its mana value (layer 7b). "
        "Humility removes abilities (layer 6) and sets creatures' base P/T to 1/1 (layer 7b). "
        "Both set base P/T in layer 7b (613.4b), so timestamps decide within that sublayer "
        "(613.7): Opalescence is later, so its mana-value setting wins, giving Ghostly Prison "
        "3/3. Humility's layer-6 ability removal still applies, so it has no abilities.",
        ["Humility", "Opalescence", "Ghostly Prison"],
        ["613.4b", "613.7"],
        "(:Card)-[:HAS_KEYWORD|MENTIONS]->... layer-system Rule subtree 613 (types 4, abilities 6, P/T 7b) + 613.7 timestamps",
        VectorExpectation.fail,
        "The answer is the resolution of two 7b effects by timestamp across the layer system; no single passage states it.",
    ),
    (
        "hand-humility-plus-counter",
        Stratum.interaction_multihop,
        3,
        "A 2/2 creature has a +1/+1 counter on it (shown as 3/3). Humility then enters. "
        "What are its power and toughness?",
        "2/2. Humility sets base P/T to 1/1 in layer 7b (613.4b). The +1/+1 counter applies in "
        "layer 7c (613.4c), which always comes after 7b regardless of timestamp - 613.4 fixes "
        "the order of sublayers 7a-7d. So 1/1 base + 1/1 counter = 2/2. The common mistake is "
        "to think Humility makes it 1/1.",
        ["Humility", "+1/+1 counter"],
        ["613.4b", "613.4c"],
        "Rule 613.4 sublayer ordering: base-set (7b) before counters (7c)",
        VectorExpectation.fail,
        "Requires knowing the fixed 7b-before-7c sublayer order, not a fact stated in any single card or passage.",
    ),
    (
        "hand-deathtouch-trample",
        Stratum.interaction_multihop,
        2,
        "You attack with a 5/5 that has deathtouch and trample, blocked by a single 4/4. "
        "How much combat damage can you assign to the defending player?",
        "Up to 4. With deathtouch, any nonzero damage counts as lethal for assignment (702.2c), "
        "so only 1 must be assigned to the 4/4 blocker; trample then lets the remaining 4 be "
        "assigned to the player (702.19e).",
        ["deathtouch", "trample"],
        ["702.2c", "702.19e", "510.1c"],
        "(:Keyword {deathtouch})-[:DEFINED_BY]->(:Rule 702.2c) + (:Keyword {trample})-[:DEFINED_BY]->(:Rule 702.19e)",
        VectorExpectation.fail,
        "Composes the deathtouch lethal-damage rule with the trample assignment rule; the number 4 appears in no passage.",
    ),
    (
        "hand-protection-from-red-debt",
        Stratum.keyword_rule_2hop,
        2,
        "A creature has protection from red. Can it be blocked by a red creature, enchanted by a "
        "red Aura, targeted by a red spell, or dealt damage by a red source?",
        "None of those. Protection from red covers DEBT: it can't be Damaged by red sources, "
        "Enchanted/Equipped by red, Blocked by red creatures, or Targeted by red spells or "
        "abilities (702.16e). Protection does not stop red non-targeted, non-damage effects "
        "(e.g. a red 'destroy all creatures').",
        ["protection"],
        ["702.16e"],
        "(:Keyword {protection})-[:DEFINED_BY]->(:Rule 702.16e)",
        VectorExpectation.lose,
        None,
    ),
    (
        "hand-lifelink-prevented-damage",
        Stratum.negative_temporal,
        2,
        "Your creature with lifelink would deal 3 combat damage, but that damage is prevented. "
        "Do you gain 3 life?",
        "No. Lifelink gains life only when the source actually deals damage (702.15). Prevented "
        "damage is never dealt (615.1), so no life is gained.",
        ["lifelink"],
        ["702.15", "615.1"],
        "(:Keyword {lifelink})-[:DEFINED_BY]->(:Rule 702.15) + prevention Rule 615.1",
        VectorExpectation.fail,
        "The 'no' depends on chaining prevention (no damage dealt) with lifelink's trigger condition; it is a negative result nothing states directly.",
    ),
    (
        "hand-indestructible-zero-toughness",
        Stratum.negative_temporal,
        2,
        "A creature with indestructible has its toughness reduced to 0. Does indestructible keep "
        "it alive?",
        "No. A creature with 0 or less toughness is put into the graveyard as a state-based "
        "action (704.5f). Indestructible only prevents destruction and lethal damage (702.12b); "
        "it does nothing against the 0-toughness rule, so the creature dies.",
        ["indestructible"],
        ["704.5f", "702.12b"],
        "(:Keyword {indestructible})-[:DEFINED_BY]->(:Rule 702.12b) vs state-based action Rule 704.5f",
        VectorExpectation.fail,
        "Requires knowing indestructible's scope excludes the 0-toughness SBA; the correct 'it dies' contradicts the naive reading.",
    ),
    (
        "hand-clone-copies-printed-pt",
        Stratum.interaction_multihop,
        3,
        "A creature is currently a 1/1 because of an effect setting its power and toughness. You "
        "cast Clone to copy it. What are the copy's power and toughness?",
        "The copy has the original's copiable (printed) power and toughness, not 1/1. Copy "
        "effects apply in layer 1 and copy only copiable values (613.2, 706.2); a layer-7 effect "
        "setting the original's P/T is not copiable. (A characteristic-defining ability or copy "
        "effect on the original would be copied, since those are part of copiable values.)",
        ["Clone", "copy"],
        ["613.2", "706.2"],
        "Rule 706.2 copiable values + 613.2 layer-1 copy applied before layer-7 P/T",
        VectorExpectation.fail,
        "The answer depends on what counts as copiable across the layer system; no passage states this creature's resulting P/T.",
    ),
    (
        "hand-doubling-season-planeswalker",
        Stratum.interaction_multihop,
        2,
        "You control Doubling Season and cast a planeswalker that enters with 3 starting loyalty. "
        "How much loyalty does it enter with?",
        "6. A planeswalker enters with loyalty counters (306.5b). Doubling Season is a "
        "replacement effect: if an effect would put counters on a permanent you control, it puts "
        "twice as many (616), so 3 becomes 6.",
        ["Doubling Season"],
        ["306.5b", "616.1"],
        "loyalty-as-counters Rule 306.5b + replacement Rule 616.1 (Doubling Season)",
        VectorExpectation.fail,
        "Requires treating starting loyalty as counters and applying a replacement effect; the value 6 is not written anywhere.",
    ),
    (
        "hand-blood-moon-nonbasic",
        Stratum.interaction_multihop,
        2,
        "You control Blood Moon and a Gaea's Cradle. What can Gaea's Cradle tap for?",
        "One red mana. Blood Moon turns all nonbasic lands into Mountains (a type-changing effect "
        "in layer 4), removing their other land types, text, and abilities and granting the "
        "intrinsic 'T: Add R' of a Mountain (305.7). Gaea's Cradle loses its own ability.",
        ["Blood Moon", "Gaea's Cradle"],
        ["305.7", "613.1d"],
        "(:Card {Blood Moon}) type-change (layer 4) -> (:Card {Gaea's Cradle}) gains Mountain intrinsic (305.7)",
        VectorExpectation.fail,
        "The answer emerges from applying a type-changing effect plus the basic-land intrinsic-ability rule; no passage states Cradle taps for R.",
    ),
    (
        "hand-replacement-order-counters",
        Stratum.interaction_multihop,
        2,
        "A creature you control is entering with one +1/+1 counter, and you control both Doubling "
        "Season and Hardened Scales. Who picks the order the replacements apply, and does it "
        "matter?",
        "You (the affected permanent's controller) choose the order (616.1). It matters: Doubling "
        "Season then Hardened Scales gives 1->2->3 counters; Hardened Scales then Doubling Season "
        "gives 1->2->4. You pick the order you prefer.",
        ["Doubling Season", "Hardened Scales"],
        ["616.1"],
        "two replacement effects on the same event -> Rule 616.1 (controller orders)",
        VectorExpectation.fail,
        "Requires the multiple-replacement ordering rule and arithmetic over both; the outcomes 3 vs 4 are stated nowhere.",
    ),
    (
        "hand-regeneration-zero-toughness",
        Stratum.negative_temporal,
        2,
        "A creature has a regeneration shield and its toughness becomes 0. Does regeneration save "
        "it?",
        "No. Regeneration replaces a destruction event (701.15). A creature with 0 toughness is "
        "put into the graveyard by a state-based action, which is not destruction (704.5f), so "
        "the shield does nothing and the creature dies.",
        ["regeneration"],
        ["701.15", "704.5f"],
        "regeneration replacement Rule 701.15 vs 0-toughness state-based action Rule 704.5f",
        VectorExpectation.fail,
        "The 'no' depends on regeneration replacing only destruction, not the SBA; a negative that contradicts the naive reading.",
    ),
    (
        "hand-first-strike-deathtouch",
        Stratum.interaction_multihop,
        2,
        "Your 2/2 with first strike and deathtouch is blocked by a 3/3 with no first strike. What "
        "happens?",
        "Your creature deals 2 damage in the first-strike combat damage step; with deathtouch "
        "that is lethal, destroying the 3/3 (702.7, 702.2). The 3/3 is gone before the regular "
        "damage step, so it never deals its 3 back and your creature survives.",
        ["first strike", "deathtouch"],
        ["702.7", "702.2b", "510.4"],
        "(:Keyword {first strike})-[:DEFINED_BY]->(:Rule 702.7) + (:Keyword {deathtouch})-[:DEFINED_BY]->(:Rule 702.2)",
        VectorExpectation.fail,
        "Composes first strike's separate damage step with deathtouch lethality; the survival outcome is a path, not a passage.",
    ),
]


def build() -> list[GoldenQuestion]:
    questions: list[GoldenQuestion] = []
    for qid, stratum, hops, question, answer, entities, rules, path, vector, reason in _SPECS:
        questions.append(
            GoldenQuestion(
                id=qid,
                source=Source.authored,
                stratum=stratum,
                hops=hops,
                question=question,
                answer=answer,
                gold_entities=entities,
                gold_cr_rules=rules,
                gold_path=path,
                vector_should=vector,
                vector_should_reason=reason,
                snapshot_sha256=content_sha256(question + "|" + answer),
                # Verified as: every CR citation machine-checked to exist in the
                # downloaded Comprehensive Rules (this caught and fixed four wrong
                # citations), plus author sign-off. Citation existence is proven;
                # semantic correctness of each ruling rests on that sign-off.
                verified=True,
            )
        )
    return questions


def main() -> int:
    questions = build()
    dump_golden(questions, OUT_PATH)
    print(f"Wrote {len(questions)} authored questions to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
