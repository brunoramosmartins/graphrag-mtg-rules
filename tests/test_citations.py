"""The citation format: what the model may write, and what it cannot fake.

The design under test is that the model writes bare handles and this
module renders the graph path from the retrieved evidence. That makes a
fabricated *path* impossible and leaves exactly one failure available —
citing a handle the subgraph does not hold — which must be detected and
shown rather than quietly dropped.
"""

from __future__ import annotations

from graphrag_mtg.generation.citations import (
    UNVERIFIED,
    cited_handles,
    expand,
    index,
    resolve,
    strip_citations,
    uncited_sentences,
)
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph


def subgraph() -> Subgraph:
    return Subgraph(
        question="What happens with Humility and Opalescence?",
        evidence=[
            Evidence(
                kind="rule",
                key="613.4",
                text="Continuous effects apply in timestamp order.",
                template="rule_subtree",
                path="(:Rule {613})-[:HAS_SUBRULE]->(:Rule {613.4})",
            ),
            Evidence(
                kind="ruling",
                key="2009-10-01",
                text="Humility's effect applies in layer 6.",
                template="card_rulings",
                path='(:Card {Humility})-[:HAS_RULING]->(:Ruling)',
                distance=1,
            ),
        ],
    )


class TestHandles:
    def test_a_marker_yields_its_handle(self) -> None:
        assert cited_handles("Timestamps decide [rule:613.4].") == ["rule:613.4"]

    def test_one_marker_may_carry_several(self) -> None:
        assert cited_handles("Both [rule:613.4; ruling:2009-10-01] apply.") == [
            "rule:613.4",
            "ruling:2009-10-01",
        ]

    def test_repeats_collapse(self) -> None:
        text = "First [rule:613.4]. Then again [rule:613.4]."
        assert cited_handles(text) == ["rule:613.4"]


class TestStripping:
    def test_markers_go_and_punctuation_stays(self) -> None:
        """E-007 segments the stripped text, so sentence ends must survive."""
        assert strip_citations("It applies [rule:613.4]. Then it stops.") == (
            "It applies. Then it stops."
        )

    def test_stripping_is_what_makes_segmentation_blind(self) -> None:
        """Where a sentence ends must not depend on where a citation sits."""
        cited = "A is true [rule:613.4]. B follows [ruling:2009-10-01]."
        uncited = "A is true. B follows."
        assert strip_citations(cited) == uncited


class TestRendering:
    def test_the_path_comes_from_the_evidence_not_the_model(self) -> None:
        rendered, unknown = expand("Timestamps decide [rule:613.4].", subgraph())
        assert unknown == []
        assert "[path: (:Rule {613})-[:HAS_SUBRULE]->(:Rule {613.4})]" in rendered
        assert "[CR 613.4]" in rendered

    def test_a_ruling_renders_with_its_id(self) -> None:
        rendered, _ = expand("As ruled [ruling:2009-10-01].", subgraph())
        assert "[ruling 2009-10-01]" in rendered

    def test_two_handles_in_one_marker_render_both_paths(self) -> None:
        rendered, _ = expand("Both [rule:613.4; ruling:2009-10-01] apply.", subgraph())
        assert rendered.count("[path: ") == 1
        assert "[CR 613.4]" in rendered and "[ruling 2009-10-01]" in rendered

    def test_prose_around_the_marker_is_untouched(self) -> None:
        rendered, _ = expand("Timestamps decide [rule:613.4].", subgraph())
        assert rendered.startswith("Timestamps decide ")
        assert rendered.endswith(".")


class TestFabricatedCitations:
    """The one failure the design still allows — and it must be loud."""

    def test_a_handle_not_in_the_subgraph_is_reported(self) -> None:
        _, unknown = expand("It says so [rule:999.9].", subgraph())
        assert unknown == ["rule:999.9"]

    def test_it_is_marked_in_the_answer_not_dropped(self) -> None:
        """A silently removed bad citation looks exactly like a good one."""
        rendered, _ = expand("It says so [rule:999.9].", subgraph())
        assert f"[{UNVERIFIED} rule:999.9]" in rendered

    def test_a_mixed_marker_keeps_the_good_half(self) -> None:
        rendered, unknown = expand("See [rule:613.4; rule:999.9].", subgraph())
        assert unknown == ["rule:999.9"]
        assert "[CR 613.4]" in rendered
        assert f"[{UNVERIFIED} rule:999.9]" in rendered


class TestLookup:
    def test_the_index_keys_on_the_handle_the_prompt_shows(self) -> None:
        assert set(index(subgraph())) == {"rule:613.4", "ruling:2009-10-01"}

    def test_resolving_separates_known_from_unknown(self) -> None:
        citation = resolve("rule:613.4; rule:999.9", index(subgraph()))
        assert [item.key for item in citation.items] == ["613.4"]
        assert citation.unknown == ("rule:999.9",)


class TestPreAuditHint:
    def test_it_finds_a_sentence_with_no_marker(self) -> None:
        text = "It applies [rule:613.4]. So it stays a 1/1."
        assert uncited_sentences(text) == ["So it stays a 1/1."]

    def test_it_is_not_the_measurement(self) -> None:
        """Sanity: this counts sentences, and E-007 counts labelled claims."""
        text = "You asked about Humility. It applies [rule:613.4]."
        assert uncited_sentences(text) == ["You asked about Humility."]
