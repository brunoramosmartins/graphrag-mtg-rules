"""Reachability of gold rules through the deterministic graph (Phase 4 decision)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from reachability import ball, seeds_for

CARDS = {
    "Lightning Bolt": {"name": "Lightning Bolt", "keywords": []},
    "Serra Angel": {"name": "Serra Angel", "keywords": ["Flying", "Vigilance"]},
}
KW_RULES = {"flying": {"702.9"}, "vigilance": {"702.20"}}

# 702.9 -> 509.1a -> 509.1 -> 509 : a chain, so hop counts are checkable.
ADJACENCY = {
    "702.9": {"509.1a"},
    "509.1a": {"702.9", "509.1"},
    "509.1": {"509.1a", "509"},
    "509": {"509.1"},
    "613.1f": set(),  # a rule no keyword reaches
}


def seeds(entities: list[str]) -> set[str]:
    found, _ = seeds_for(entities, cards=CARDS, kw_rules=KW_RULES)
    return found


class TestSeeds:
    def test_a_card_seeds_through_its_keywords(self) -> None:
        assert seeds(["Serra Angel"]) == {"702.9", "702.20"}

    def test_a_keyword_named_directly_is_seeded(self) -> None:
        """gold_entities mixes card names with keyword names."""
        assert seeds(["Flying"]) == {"702.9"}

    def test_a_card_with_no_keywords_seeds_nothing(self) -> None:
        """The finding, not an edge case: no keyword means no way into the graph."""
        assert seeds(["Lightning Bolt"]) == set()

    def test_an_unknown_entity_is_counted_not_crashed_on(self) -> None:
        found, counts = seeds_for(["Nonesuch"], cards=CARDS, kw_rules=KW_RULES)
        assert found == set() and counts["unknown"] == 1

    def test_the_resolution_breakdown_is_reported(self) -> None:
        _, counts = seeds_for(
            ["Serra Angel", "Lightning Bolt", "Flying"], cards=CARDS, kw_rules=KW_RULES
        )
        assert counts == {
            "keyword": 1,
            "card_with_kw": 1,
            "card_no_kw": 1,
            "unknown": 0,
        }


class TestBall:
    def test_zero_hops_is_the_seed(self) -> None:
        assert ball({"702.9"}, ADJACENCY, 0) == {"702.9"}

    def test_each_hop_adds_one_ring(self) -> None:
        assert ball({"702.9"}, ADJACENCY, 1) == {"702.9", "509.1a"}
        assert ball({"702.9"}, ADJACENCY, 2) == {"702.9", "509.1a", "509.1"}

    def test_expansion_stops_when_the_component_is_exhausted(self) -> None:
        """More hops must not invent reach: 613.1f is in another component."""
        assert "613.1f" not in ball({"702.9"}, ADJACENCY, 99)

    def test_an_empty_seed_reaches_nothing(self) -> None:
        assert ball(set(), ADJACENCY, 5) == set()
