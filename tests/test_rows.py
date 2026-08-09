"""Traversal rows to citable evidence, including Neo4j's sharper edges."""

from __future__ import annotations

from graphrag_mtg.retrieval.rows import to_evidence
from graphrag_mtg.retrieval.templates import BY_NAME, TEMPLATES, Emit, Template

TEMPLATE = Template(
    name="t",
    cypher="MATCH (r:Rule) RETURN r.number AS rule_number, r.text AS rule_text, [] AS subrules "
    "LIMIT $limit",
    params=(),
    strata=("definition_1hop",),
    description="fixture template used by these tests",
    emits=(
        Emit("rule", "rule_number", "rule_text", "(:Rule {{{rule_number}}})"),
        Emit("rule", "number", "text", "(:Rule)-[:HAS_SUBRULE]->(:Rule)",
             collection="subrules", distance=1),
    ),
)


class TestScalarColumns:
    def test_a_row_becomes_evidence(self) -> None:
        (item,) = to_evidence(TEMPLATE, [{"rule_number": "702.9", "rule_text": "Flying"}])
        assert (item.cite(), item.text) == ("rule:702.9", "Flying")

    def test_the_path_is_filled_from_the_row(self) -> None:
        (item,) = to_evidence(TEMPLATE, [{"rule_number": "702.9", "rule_text": "Flying"}])
        assert item.path == "(:Rule {702.9})"

    def test_a_missing_path_value_keeps_the_evidence(self) -> None:
        """Provenance is documentation, not control flow: never lose the fact."""
        emit = Emit("rule", "rule_number", "rule_text", "(:Card {{{absent}}})")
        template = Template("t", TEMPLATE.cypher, (), ("definition_1hop",), "x", (emit,))
        (item,) = to_evidence(template, [{"rule_number": "702.9", "rule_text": "Flying"}])
        assert item.key == "702.9"

    def test_a_null_key_produces_nothing(self) -> None:
        assert to_evidence(TEMPLATE, [{"rule_number": None, "rule_text": "x"}]) == []


class TestCollections:
    def test_each_entry_becomes_its_own_evidence(self) -> None:
        rows = [
            {
                "rule_number": "613.4",
                "rule_text": "Layer 7",
                "subrules": [{"number": "613.4a", "text": "7a"}, {"number": "613.4b", "text": "7b"}],
            }
        ]
        assert [e.key for e in to_evidence(TEMPLATE, rows)] == ["613.4", "613.4a", "613.4b"]

    def test_a_missed_optional_match_does_not_become_a_citation(self) -> None:
        """collect() over zero matches yields [{number: None}], not [].

        Passed through, that becomes a footnote pointing at nothing —
        confirmed against the loaded graph, not assumed.
        """
        rows = [{"rule_number": "613.4", "rule_text": "x", "subrules": [{"number": None, "text": None}]}]
        assert [e.key for e in to_evidence(TEMPLATE, rows)] == ["613.4"]

    def test_an_absent_column_is_not_an_error(self) -> None:
        assert len(to_evidence(TEMPLATE, [{"rule_number": "613.4", "rule_text": "x"}])) == 1

    def test_collected_evidence_is_further_away(self) -> None:
        rows = [{"rule_number": "613.4", "rule_text": "x", "subrules": [{"number": "613.4a", "text": "y"}]}]
        parent, child = to_evidence(TEMPLATE, rows)
        assert child.distance > parent.distance


class TestEveryShippedTemplate:
    def test_each_declares_how_its_rows_become_evidence(self) -> None:
        """A traversal nobody can cite from is a traversal that does nothing."""
        assert all(t.emits for t in TEMPLATES)

    def test_no_mapping_names_a_column_the_query_does_not_return(self) -> None:
        """The coupling that a RETURN edit would otherwise break in silence."""
        for template in TEMPLATES:
            columns = template.columns()
            for emit in template.emits:
                if emit.collection:
                    assert emit.collection in columns, (template.name, emit.collection)
                else:
                    assert {emit.key, emit.text} <= columns, (template.name, emit.key)

    def test_the_interaction_traversal_stages_its_keyword_join(self) -> None:
        """The two-sided pattern exhausts the server's memory pool — measured."""
        cypher = BY_NAME["card_interaction"].cypher
        assert "<-[:HAS_KEYWORD]-" not in cypher
        assert "a_keywords" in cypher
