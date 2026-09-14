"""The refusals that stand between E-018's design and a number it cannot mean.

Every test here guards a way the run could produce three tidy columns that are
not the comparison the entry registered: a placebo that stopped controlling
volume, a control that is no longer E-001's, an injection that never reached
the prompt, or a budget that trimmed one condition and not another.

The checks are tested as *refusals*, not as warnings. A run that prints a
caveat and continues has already spent the money, and the caveat is then a
postmortem — which is the shape of every finding this entry exists because of.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e018 as e018
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph


@dataclass
class FakeRule:
    number: str
    level: int
    text: str
    parent: str | None = None


class FakeCR:
    """Enough of a `CRDocument` to build injections from."""

    def __init__(self, rules: list[FakeRule]) -> None:
        self.rules = rules

    @property
    def by_number(self) -> dict[str, FakeRule]:
        return {rule.number: rule for rule in self.rules}

    def subtree(self, number: str) -> list[FakeRule]:
        return [r for r in self.rules if r.number == number or r.parent == number]


def cr_with(n: int = 60) -> FakeCR:
    """A CR of level-2 rules, each with one level-3 subrule, all same size."""
    rules: list[FakeRule] = []
    for index in range(n):
        parent = f"{100 + index}.1"
        rules.append(FakeRule(parent, 2, "parent text " * 6))
        rules.append(FakeRule(f"{parent}a", 3, "child text " * 6, parent=parent))
    return FakeCR(rules)


def subgraph(evidence: list[Evidence]) -> Subgraph:
    return Subgraph(question="q", evidence=evidence)


def retrieved(kind: str, key: str) -> Evidence:
    return Evidence(kind=kind, key=key, text="t", template="card_core", path="(:Card)", distance=0)


class TestInjectedEvidenceIsIndistinguishableFromRetrieved:
    """A citation of an injected rule must count as a citation."""

    def test_it_is_the_same_dataclass_with_the_same_handle_contract(self) -> None:
        item = e018.injected("613.7", "Some continuous effects have a timestamp.")
        assert isinstance(item, Evidence)
        assert item.cite() == "rule:613.7"
        assert item.kind == "rule"

    def test_the_path_names_the_node_and_does_not_claim_a_traversal(self) -> None:
        # A fabricated provenance inside the file that measures honesty about
        # provenance would be the whole project's failure in miniature.
        item = e018.injected("613.7", "text")
        assert item.path == "(:Rule {613.7})"
        assert "-[:" not in item.path

    def test_it_is_marked_so_the_run_can_find_what_it_injected(self) -> None:
        assert e018.injected("613.7", "text").template == e018.INJECTION_TEMPLATE

    def test_the_subtree_is_injected_not_the_bare_rule(self) -> None:
        # Amendment 2026-09-13b: injecting 701.15 alone injects the word
        # "Goad" and omits the four subrules that say what goading is.
        cr = FakeCR(
            [
                FakeRule("701.15", 2, "Goad"),
                FakeRule("701.15a", 3, "Certain spells can goad.", parent="701.15"),
                FakeRule("701.15b", 3, "Goaded is a designation.", parent="701.15"),
                FakeRule("702.1", 2, "unrelated"),
            ]
        )
        keys = [item.key for item in e018.subtree_evidence("701.15", cr)]
        assert keys == ["701.15", "701.15a", "701.15b"]


class TestThePlaceboControlsVolumeAndShape:
    """Registered as the falsifier. A placebo that drifts falsifies nothing."""

    def test_the_pool_is_indexed_by_level_and_excludes_the_treatment(self) -> None:
        cr = cr_with(4)
        pools = e018.rule_pools(cr, {"100.1", "100.1a"})
        assert "100.1" not in pools[2]
        assert "100.1a" not in pools[3]
        assert "101.1" in pools[2]

    def test_a_draw_matches_the_gold_rules_level_by_level(self) -> None:
        # Level carries both controls: a level-2 subtree is roughly twice a
        # level-3 subrule, so drawing across levels makes the token match a
        # lottery, and the two read as different shapes of context.
        cr = cr_with(40)
        pools = e018.rule_pools(cr, set())
        # Measured from the fixture rather than guessed: a hardcoded target
        # would make this test assert the tolerance arithmetic by accident.
        target = e018.tokens_of(
            e018.subtree_evidence("100.1a", cr) + e018.subtree_evidence("101.1a", cr)
        )
        items = e018.draw_placebo(
            random.Random(1), pools, cr, [3, 3], target=target, items_target=2
        )
        assert all(item.key.endswith("a") for item in items)

    def test_a_draw_that_cannot_match_refuses_instead_of_returning_the_closest(self) -> None:
        # The failure that mattered in practice: the first implementation drew
        # level-1 chapters, nothing landed inside tolerance, and a silent
        # fallback would have shipped a placebo controlling nothing.
        cr = cr_with(40)
        pools = e018.rule_pools(cr, set())
        rng = random.Random(1)
        with pytest.raises(SystemExit, match="cannot match"):
            e018.draw_placebo(rng, pools, cr, [2, 2], target=1, items_target=4)

    def test_the_same_rule_is_never_drawn_twice_in_one_placebo(self) -> None:
        cr = cr_with(40)
        pools = e018.rule_pools(cr, set())
        target = e018.tokens_of(
            [
                item
                for number in ("100.1", "101.1", "102.1")
                for item in e018.subtree_evidence(number, cr)
            ]
        )
        items = e018.draw_placebo(
            random.Random(7), pools, cr, [2, 2, 2], target=target, items_target=6
        )
        roots = [item.key for item in items if not item.key.endswith("a")]
        assert len(set(roots)) == len(roots)

    def test_the_tolerance_is_the_registered_one(self) -> None:
        # Widening this after seeing a result is the move the entry forbids.
        assert e018.TOKEN_TOLERANCE == 0.20


class TestTheControlMustBeE001s:
    """Every contrast is measured against it; if it drifted, it names nothing."""

    def test_a_matching_control_passes(self) -> None:
        record = {"evidence": [{"kind": "card", "key": "Humility"}]}
        e018.check_control("q", subgraph([retrieved("card", "Humility")]), record)

    def test_an_added_item_refuses(self) -> None:
        record = {"evidence": [{"kind": "card", "key": "Humility"}]}
        with pytest.raises(SystemExit, match="not E-001's"):
            e018.check_control(
                "q",
                subgraph([retrieved("card", "Humility"), retrieved("rule", "613.7")]),
                record,
            )

    def test_a_missing_item_refuses(self) -> None:
        record = {
            "evidence": [{"kind": "card", "key": "Humility"}, {"kind": "rule", "key": "613.7"}]
        }
        with pytest.raises(SystemExit, match="not E-001's"):
            e018.check_control("q", subgraph([retrieved("card", "Humility")]), record)


class TestNothingMayBeTrimmedInAnyCondition:
    """An evicted item makes this a measurement of `enforce_budget`."""

    def test_a_clean_subgraph_passes(self) -> None:
        e018.check_budget("q", "treatment", subgraph([retrieved("card", "X")]))

    def test_a_dropped_item_refuses_and_names_the_budget(self) -> None:
        trimmed = subgraph([retrieved("card", "X")])
        trimmed.dropped["rule"] = 2
        with pytest.raises(SystemExit, match="evicted evidence"):
            e018.check_budget("q", "treatment", trimmed)

    def test_a_capped_item_refuses_too(self) -> None:
        trimmed = subgraph([retrieved("card", "X")])
        trimmed.capped["rule"] = 1
        with pytest.raises(SystemExit, match="evicted evidence"):
            e018.check_budget("q", "placebo", trimmed)


class TestTheManipulationMustHaveHappened:
    """A null under an injection that silently failed looks like a real null."""

    def test_a_prompt_carrying_every_handle_passes(self) -> None:
        items = [e018.injected("613.7", "t"), e018.injected("613.7a", "t")]
        prompt = "## CONTEXT\n[rule:613.7] t\n[rule:613.7a] t\n"
        e018.check_injection("q", "treatment", prompt, items)

    def test_a_missing_handle_refuses(self) -> None:
        items = [e018.injected("613.7", "t"), e018.injected("613.7a", "t")]
        prompt = "## CONTEXT\n[rule:613.7] t\n"
        with pytest.raises(SystemExit, match="not in the prompt"):
            e018.check_injection("q", "treatment", prompt, items)

    def test_a_rule_number_in_prose_does_not_count_as_the_handle(self) -> None:
        # The E-010 defect: a regex over the serialized text would count a
        # ruling that happens to quote the number.
        items = [e018.injected("613.7", "t")]
        prompt = "## CONTEXT\n[ruling:abc] See rule 613.7 for the order.\n"
        with pytest.raises(SystemExit, match="not in the prompt"):
            e018.check_injection("q", "treatment", prompt, items)


class TestTheConstantsTheEntryRegistered:
    """Kept where an edit trips a test rather than changing a published run."""

    def test_the_ceiling_is_the_one_that_was_read(self) -> None:
        assert e018.CEILING == 17

    def test_the_arm_and_split_come_from_the_ceiling_module(self) -> None:
        # One definition, so the runner and the frozen population cannot
        # disagree about which arm E-018 is an intervention on.
        from e018_ceiling import ARM, SPLIT

        assert (e018.ARM, e018.SPLIT) == (ARM, SPLIT)

    def test_the_conditions_are_the_three_registered_ones(self) -> None:
        assert e018.CONDITIONS == ("control", "placebo", "treatment")

    def test_the_budget_is_well_above_the_shipped_one(self) -> None:
        from graphrag_mtg.retrieval.subgraph import DEFAULT_TOKEN_BUDGET

        assert e018.TOKEN_BUDGET >= 4 * DEFAULT_TOKEN_BUDGET
