"""Invariants over every template traversal — enforced, not reviewed.

These run over ``TEMPLATES`` rather than over a hand-listed set, so a
traversal added later cannot quietly skip the read-only or LIMIT rule.
"""

from __future__ import annotations

import re

import pytest

from graphrag_mtg.retrieval.templates import (
    BY_NAME,
    DEPTH_MARKER,
    MAX_TREE_DEPTH,
    TEMPLATES,
    WRITE_CLAUSES,
    Template,
    templates_for,
)

GOLDEN_STRATA = {
    "definition_1hop",
    "legality_1hop",
    "keyword_rule_2hop",
    "interaction_multihop",
    "negative_temporal",
}


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
class TestEveryTemplate:
    def test_is_read_only(self, template: Template) -> None:
        upper = template.cypher.upper()
        assert not [c for c in WRITE_CLAUSES if c in upper]

    def test_carries_a_limit(self, template: Template) -> None:
        """Unbounded retrieval is how a hub blows up the token budget."""
        assert "$limit" in template.cypher

    def test_takes_values_as_parameters_not_interpolation(self, template: Template) -> None:
        """No f-string ever reaches Cypher; a card name is data, not syntax."""
        assert "{}" not in template.cypher
        assert not re.search(r"\{[a-z_]+\}", template.cypher)

    def test_declares_every_parameter_it_uses(self, template: Template) -> None:
        used = set(re.findall(r"\$([a-z_]+)", template.cypher)) - {"limit"}
        assert used == set(template.params)

    def test_bounds_variable_length_expansion(self, template: Template) -> None:
        """`*` with no ceiling walks the whole component."""
        for hop in re.findall(r"\*([^\]\s]*)", template.cypher):
            assert re.fullmatch(r"1\.\.\d+", hop), f"unbounded expansion: *{hop}"

    def test_the_depth_marker_was_substituted(self, template: Template) -> None:
        """A template shipping its placeholder would be a syntax error at run time."""
        assert DEPTH_MARKER not in template.cypher

    def test_expansion_uses_the_shared_ceiling(self, template: Template) -> None:
        """A hand-written depth would drift from MAX_TREE_DEPTH silently."""
        for hop in re.findall(r"\*1\.\.(\d+)", template.cypher):
            assert int(hop) == MAX_TREE_DEPTH

    def test_names_only_real_strata(self, template: Template) -> None:
        assert set(template.strata) <= GOLDEN_STRATA

    def test_is_described(self, template: Template) -> None:
        assert len(template.description) > 20


class TestRegistry:
    def test_names_are_unique(self) -> None:
        assert len(BY_NAME) == len(TEMPLATES)

    def test_the_roadmap_minimum_is_met(self) -> None:
        """Phase 4 DoD asks for at least seven traversals."""
        assert len(TEMPLATES) >= 7

    def test_every_stratum_has_at_least_one_traversal(self) -> None:
        for stratum in GOLDEN_STRATA:
            assert templates_for(stratum), stratum

    def test_an_unknown_stratum_returns_nothing_rather_than_raising(self) -> None:
        """A question the templates do not cover is routed, not an error."""
        assert templates_for("no_such_stratum") == ()

    def test_tree_depth_covers_the_cr(self) -> None:
        """Chapter -> rule -> subrule is three levels; less would truncate."""
        assert MAX_TREE_DEPTH >= 3


class TestCoverageMatchesTheMeasurement:
    """Declared coverage must follow scripts/reachability.py, not optimism."""

    def test_the_strata_the_graph_reaches_have_a_dedicated_traversal(self) -> None:
        # 100% of gold rules at k=2 for these, per ADR-007.
        assert "keyword_definition" in {t.name for t in templates_for("definition_1hop")}
        assert "card_keyword_rules" in {t.name for t in templates_for("keyword_rule_2hop")}

    def test_interaction_is_served_but_not_claimed_alone(self) -> None:
        """Half of interaction_multihop has no keyword seed; text retrieval covers it."""
        names = {t.name for t in templates_for("interaction_multihop")}
        assert {"card_rulings", "card_interaction"} <= names

    def test_the_negative_stratum_returns_violations(self) -> None:
        """An empty result is the legal answer; every row is a citable reason."""
        assert "e.status <> 'legal'" in BY_NAME["deck_legality"].cypher
