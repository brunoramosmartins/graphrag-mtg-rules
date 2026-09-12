"""The demo draws a graph from recorded path strings, and must not invent one.

`retrieval.pipeline` records a `path` on every piece of evidence, but not every
path is a path: text-retrieved evidence carries a **sentence** ("hybrid
retrieval over the shared corpus") and a traversal that produced none carries
the placeholder "(no path recorded)". Both are non-empty strings in the same
field. A renderer that trusts the field draws edges the graph does not have —
in a demo whose whole claim is that the answer's evidence is traceable.

`app/paths.py` exists so this is testable without the app extra: `demo.py`
imports streamlit at module scope, and a test that needs streamlit installed to
check a regex is a test that gets skipped.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from paths import build_graph, has_path, parse_path


@dataclass(frozen=True)
class FakeEvidence:
    path: str
    key: str = "k"


class TestHasPath:
    @pytest.mark.parametrize(
        "path",
        [
            "(:Card {Humility})",
            "(:Keyword {Trample})-[:DEFINED_BY]->(:Rule {702.19})",
            "(:Rule {702.2})-[:HAS_SUBRULE*]->(:Rule)",
        ],
    )
    def test_real_traversals_are_paths(self, path: str) -> None:
        assert has_path(FakeEvidence(path)) is True

    @pytest.mark.parametrize(
        "path",
        ["", "hybrid retrieval over the shared corpus", "(no path recorded)"],
    )
    def test_prose_and_placeholders_are_not_paths(self, path: str) -> None:
        # Each of these is a non-empty string in the same field as a real
        # path. This is the distinction the whole graph view rests on.
        assert has_path(FakeEvidence(path)) is False


class TestParsePath:
    def test_a_lone_node_has_no_edges(self) -> None:
        assert parse_path("(:Card {Humility})", "k") == ([("Card", "Humility")], [])

    def test_a_two_node_hop(self) -> None:
        nodes, edges = parse_path(
            "(:Keyword {Deathtouch})-[:DEFINED_BY]->(:Rule {702.2})", "k"
        )
        assert nodes == [("Keyword", "Deathtouch"), ("Rule", "702.2")]
        assert edges == [(0, 1, "DEFINED_BY")]

    def test_an_anonymous_terminal_takes_the_evidence_key(self) -> None:
        # Without this, every ruling in one answer collapses into a single
        # node labelled "Ruling" and the graph shows one edge where there are
        # ten.
        nodes, _ = parse_path("(:Card {Humility})-[:HAS_RULING]->(:Ruling)", "rg-42")
        assert nodes == [("Card", "Humility"), ("Ruling", "rg-42")]

    def test_a_variable_length_relation_keeps_its_star(self) -> None:
        # `HAS_SUBRULE*` is a whole subtree, not one hop. Dropping the star
        # would draw a parent-to-child edge where the traversal took many.
        _, edges = parse_path("(:Rule {702.2})-[:HAS_SUBRULE*]->(:Rule)", "k")
        assert edges == [(0, 1, "HAS_SUBRULE*")]

    def test_direction_is_preserved(self) -> None:
        # An arrow rendered the wrong way round is a claim about the graph
        # that is exactly backwards.
        _, edges = parse_path("(:A {x})<-[:REV]-(:B {y})", "k")
        assert edges == [(1, 0, "REV")]

    def test_prose_parses_to_nothing_rather_than_guessing(self) -> None:
        assert parse_path("hybrid retrieval over the shared corpus", "k") == ([], [])

    def test_a_three_hop_chain_indexes_its_edges_correctly(self) -> None:
        nodes, edges = parse_path(
            "(:Card {X})-[:HAS_KEYWORD]->(:Keyword {flying})"
            "-[:DEFINED_BY]->(:Rule {702.9})",
            "k",
        )
        assert len(nodes) == 3
        assert edges == [(0, 1, "HAS_KEYWORD"), (1, 2, "DEFINED_BY")]


@dataclass(frozen=True)
class Ev:
    """Enough of an `Evidence` for the graph builder."""

    path: str
    key: str
    text: str = ""
    distance: int = 1


class TestBuildGraph:
    """What the viewer reads, as opposed to what the schema stores."""

    def test_a_ruling_is_numbered_not_hexadecimal(self) -> None:
        # The first screenshot of this demo drew `539a01a4ff17f48d5e9e…`,
        # which is the node reciting its primary key. An ordinal is what the
        # context already hands the model, so the two agree.
        nodes, _ = build_graph([
            Ev("(:Card {Humility})-[:HAS_RULING]->(:Ruling)", "539a01a4ff17f48d5e9e", "text"),
            Ev("(:Card {Humility})-[:HAS_RULING]->(:Ruling)", "be0b71cd44f4af5c52", "more"),
        ])
        labels = {node.label for node in nodes}
        assert {"Ruling 1", "Ruling 2"} <= labels
        assert not any("539a01" in node.label for node in nodes)

    def test_ruling_numbers_are_stable_per_id(self) -> None:
        nodes, _ = build_graph([
            Ev("(:Card {X})-[:HAS_RULING]->(:Ruling)", "aaa"),
            Ev("(:Card {Y})-[:HAS_RULING]->(:Ruling)", "bbb"),
            Ev("(:Card {Z})-[:HAS_RULING]->(:Ruling)", "aaa"),
        ])
        rulings = [n.label for n in nodes if n.kind == "Ruling"]
        assert sorted(rulings) == ["Ruling 1", "Ruling 2"]

    def test_a_rule_says_it_is_a_rule(self) -> None:
        nodes, _ = build_graph([Ev("(:Rule {701.6a})", "701.6a")])
        assert [n.label for n in nodes] == ["Rule 701.6a"]

    def test_the_terminal_node_carries_the_items_text_as_its_tooltip(self) -> None:
        nodes, _ = build_graph([
            Ev("(:Keyword {Trample})-[:DEFINED_BY]->(:Rule {702.19})", "702.19", "Trample text")
        ])
        by_kind = {node.kind: node for node in nodes}
        assert "Trample text" in by_kind["Rule"].title
        # The intermediate node was not retrieved, so it has no text to show
        # and must not borrow the terminal's.
        assert "Trample text" not in by_kind["Keyword"].title

    def test_a_seed_is_distance_zero_not_first_position(self) -> None:
        """Heading a path is not the same as having been named.

        Rule 701.6 heads `(:Rule {701.6})-[:HAS_SUBRULE*]->(:Rule)` and was
        itself reached one hop earlier through DEFINED_BY. Marking it as a
        seed would draw the traversal starting where it did not.
        """
        nodes, _ = build_graph([
            Ev("(:Keyword {Counter})", "Counter", "kw", distance=0),
            Ev("(:Keyword {Counter})-[:DEFINED_BY]->(:Rule {701.6})", "701.6", "r", distance=1),
            Ev("(:Rule {701.6})-[:HAS_SUBRULE*]->(:Rule)", "701.6a", "s", distance=2),
        ])
        seeds = {node.label for node in nodes if node.seed}
        assert seeds == {"Counter"}

    def test_a_node_seen_twice_keeps_the_visit_that_knew_more(self) -> None:
        nodes, _ = build_graph([
            Ev("(:Card {Humility})-[:HAS_RULING]->(:Ruling)", "r1", "ruling text", distance=1),
            Ev("(:Card {Humility})", "Humility", "card text", distance=0),
        ])
        card = next(node for node in nodes if node.kind == "Card")
        # Met first as a bare waypoint, then as the retrieved item itself.
        assert card.seed is True
        assert "card text" in card.title

    def test_duplicate_edges_are_drawn_once(self) -> None:
        _, edges = build_graph([
            Ev("(:Card {X})-[:HAS_RULING]->(:Ruling)", "same"),
            Ev("(:Card {X})-[:HAS_RULING]->(:Ruling)", "same"),
        ])
        assert len(edges) == 1

    def test_text_retrieved_evidence_contributes_nothing(self) -> None:
        nodes, edges = build_graph([Ev("hybrid retrieval over the shared corpus", "k", "t")])
        assert (nodes, edges) == ([], [])
