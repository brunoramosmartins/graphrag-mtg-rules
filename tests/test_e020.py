"""E-020 claims to vary order and nothing else, and the tests hold it to that.

The entry exists because E-018's floor measured decoding noise while its
contrast carried order. So the guards here are all about not repeating that:
the floor pair must share a prompt, the order samples must not, and the
orderings must differ in the **rendered prompt** rather than in the evidence
list — `serialize` groups by kind, so two different list orders can produce
identical text, and a pair that does would be a second floor reported as an
order comparison.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e020_analysis as ana
import run_e020 as e020
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph


def item(kind: str, key: str) -> Evidence:
    return Evidence(kind=kind, key=key, text="t", template="card_core", path="(:X)", distance=0)


def sub(items: list[Evidence]) -> Subgraph:
    return Subgraph(question="q", evidence=items)


class TestOrderIsDrawnInPromptSpace:
    """Two list orders that render the same text are one ordering."""

    def test_three_distinct_prompts_are_returned_when_they_exist(self) -> None:
        evidence = [item("rule", f"70{n}.1") for n in range(5)]
        drawn = e020.orderings(evidence, random.Random(1), lambda xs: str([x.key for x in xs]))
        assert set(drawn) == {"A", "B", "C"}
        rendered = {str([x.key for x in drawn[name]]) for name in drawn}
        assert len(rendered) == 3

    def test_a_context_that_cannot_render_three_prompts_returns_none(self) -> None:
        # Not an error. It is a question this design cannot move, and counting
        # it would dilute the rate with a question never at risk.
        evidence = [item("rule", "702.1"), item("rule", "702.2")]
        assert e020.orderings(evidence, random.Random(1), lambda xs: "constant") is None

    def test_distinctness_ignores_list_order_when_the_render_collapses_it(self) -> None:
        # The defect this replaced: checking the evidence sequence would call
        # these three orderings distinct while the model saw one prompt twice.
        evidence = [item("rule", "702.1"), item("rule", "702.2"), item("rule", "702.3")]
        render = lambda xs: str(sorted(x.key for x in xs))  # noqa: E731 — kind-grouped render
        assert e020.orderings(evidence, random.Random(1), render) is None


class TestTheFloorMustBeAFloor:
    def test_matching_floor_and_differing_orders_pass(self) -> None:
        e020.check_distinct("q", {"A1": "a", "A2": "a", "B": "b", "C": "c"})

    def test_a_floor_pair_with_different_prompts_refuses(self) -> None:
        with pytest.raises(SystemExit, match="not a floor"):
            e020.check_distinct("q", {"A1": "a", "A2": "different", "B": "b", "C": "c"})

    def test_an_order_sample_equal_to_the_floor_refuses(self) -> None:
        # It would be reported as an order comparison and measure decoding
        # noise — exactly E-018's mistake, inverted.
        with pytest.raises(SystemExit, match="same prompt as A"):
            e020.check_distinct("q", {"A1": "a", "A2": "a", "B": "a", "C": "c"})

    def test_two_identical_order_samples_refuse(self) -> None:
        with pytest.raises(SystemExit, match="same sequence"):
            e020.check_distinct("q", {"A1": "a", "A2": "a", "B": "b", "C": "b"})


class TestOnlyOrderMayVary:
    def test_identical_item_sets_pass(self) -> None:
        a, b = item("rule", "1"), item("rule", "2")
        e020.check_same_items("q", {"A1": sub([a, b]), "B": sub([b, a])})

    def test_an_added_item_refuses(self) -> None:
        a, b = item("rule", "1"), item("rule", "2")
        with pytest.raises(SystemExit, match="same items"):
            e020.check_same_items("q", {"A1": sub([a]), "B": sub([a, b])})

    def test_the_bar_is_off_the_grid_on_purpose(self) -> None:
        # At n around 20 every rate is a multiple of 0.05. E-018 put two bars
        # on multiples of 0.05 and landed exactly on both, deciding nothing.
        assert e020.EFFECT_BAR == 0.175
        assert (e020.EFFECT_BAR * 20) % 1 != 0


class TestTheTwoIndicators:
    def rows(self, a1: str, a2: str, b: str, c: str) -> dict[str, dict]:
        return {
            name: {"label": label, "items": 5}
            for name, label in zip(e020.SAMPLES, (a1, a2, b, c), strict=True)
        }

    def test_a_stable_question_moves_neither_indicator(self) -> None:
        assert ana.indicators(self.rows("correct", "correct", "correct", "correct")) == (
            False,
            False,
        )

    def test_the_floor_fires_when_the_same_prompt_disagrees(self) -> None:
        floor, order = ana.indicators(self.rows("correct", "incorrect", "correct", "correct"))
        assert floor is True

    def test_either_reordering_disagreeing_fires_order(self) -> None:
        # Registered as *either*, not both: requiring both would ask a
        # stricter question than the entry fixed and understate a real effect.
        _, order = ana.indicators(self.rows("correct", "correct", "incorrect", "correct"))
        assert order is True
        _, order = ana.indicators(self.rows("correct", "correct", "correct", "incorrect"))
        assert order is True

    def test_partial_and_incorrect_are_the_same_side_of_the_collapse(self) -> None:
        # The entry registered E-001's two-way outcome. Treating `partial` as
        # movement here would borrow a different measure after the fact.
        floor, order = ana.indicators(self.rows("partial", "incorrect", "partial", "incorrect"))
        assert (floor, order) == (False, False)

    def test_the_three_label_shift_still_sees_it(self) -> None:
        # Which is why it is reported beside the collapse rather than instead.
        assert ana.label_shift(self.rows("partial", "incorrect", "partial", "incorrect")) is True

    def test_no_movement_at_all_is_no_shift(self) -> None:
        assert ana.label_shift(self.rows("correct", "correct", "correct", "correct")) is False
