"""The shape reduction is the number, so the reduction is what the tests pin.

E-029's claim rests on "one arm's provenance field varies with the item, the
other's does not", quantified as distinct paths and distinct shapes. The first
version of `shape` kept hyphens, and card names contain them, so *Snow-Covered
Forest* split one shape into two and the report said six where there are four.
A shape count nobody checks is a number nobody can trust.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import provenance_demo as pd


class TestShapeStripsNodeContents:
    def test_a_hyphenated_card_name_does_not_change_the_shape(self) -> None:
        # The defect this function was rewritten for.
        plain = pd.shape("(:Card {Humility})")
        hyphenated = pd.shape("(:Card {Snow-Covered Forest})")
        assert plain == hyphenated

    def test_names_with_punctuation_collapse_too(self) -> None:
        names = ("(:Card {Ajani's Pridemate})", "(:Card {Jace, the Mind Sculptor})",
                 "(:Card {Look at Me, I'm the DCI})", "(:Card {Snow-Covered Forest})")
        assert len({pd.shape(name) for name in names}) == 1

    def test_a_rule_number_does_not_change_the_shape(self) -> None:
        assert pd.shape("(:Rule {702.2})-[:HAS_SUBRULE*]->(:Rule)") == pd.shape(
            "(:Rule {104.3a})-[:HAS_SUBRULE*]->(:Rule)"
        )

    def test_genuinely_different_traversals_stay_different(self) -> None:
        # The test that stops the ones above from passing by collapsing
        # everything into the empty string.
        shapes = {
            pd.shape("(:Card {X})"),
            pd.shape("(:Card {X})-[:HAS_RULING]->(:Ruling)"),
            pd.shape("(:Rule {1})-[:HAS_SUBRULE*]->(:Rule)"),
            pd.shape("(:Card {X})-[:HAS_KEYWORD]->(:Keyword)<-[:HAS_KEYWORD]-(:Card {Y})"),
        }
        assert len(shapes) == 4

    def test_a_shape_is_not_empty_for_a_real_path(self) -> None:
        assert pd.shape("(:Card {Humility})-[:HAS_RULING]->(:Ruling)")

    def test_the_vector_constant_reduces_to_nothing(self) -> None:
        # Prose has no graph structure in it, which is the point of the entry.
        assert pd.shape(pd.VECTOR_CONSTANT) == ""


class TestTheVectorConstantIsNamedNotGuessed:
    def test_it_is_the_string_the_dumps_carry(self) -> None:
        assert pd.VECTOR_CONSTANT == "hybrid retrieval over the shared corpus"

    def test_it_carries_no_node_and_no_edge(self) -> None:
        # If this ever starts containing a path, the entry's central claim
        # changes and this test is where that surfaces.
        assert "(" not in pd.VECTOR_CONSTANT
        assert "->" not in pd.VECTOR_CONSTANT


class TestTheArmsAreTheThreeE001Ran:
    def test_all_three_arms_are_surveyed(self) -> None:
        assert [label for label, _ in pd.ARMS] == ["A vector", "B graph", "C hybrid"]

    def test_the_side_by_side_uses_the_first_two(self) -> None:
        # The contrast is vector against graph; the hybrid contains both and
        # would blur the comparison the rendering exists to make.
        assert pd.ARMS[0][0] == "A vector"
        assert pd.ARMS[1][0] == "B graph"
