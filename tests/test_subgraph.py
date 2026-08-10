"""Subgraph assembly: budgets, hub caps, and failures that stay explicit."""

from __future__ import annotations

from graphrag_mtg.retrieval.subgraph import (
    DEFAULT_KIND_CAP,
    Evidence,
    Outcome,
    Subgraph,
    add_evidence,
    enforce_budget,
    serialize,
)


def ev(kind: str, key: str, text: str = "text", *, template: str = "t", distance: int = 0):
    return Evidence(kind=kind, key=key, text=text, template=template, path="p", distance=distance)


class TestEvidence:
    def test_the_citation_handle_names_kind_and_key(self) -> None:
        assert ev("rule", "702.9").cite() == "rule:702.9"

    def test_size_grows_with_the_text(self) -> None:
        assert ev("rule", "r", "word " * 100).tokens > ev("rule", "r", "word").tokens


class TestAddEvidence:
    def test_duplicates_do_not_accumulate(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9"), ev("rule", "702.9")])
        assert len(sg.evidence) == 1

    def test_the_same_key_from_a_different_template_is_kept(self) -> None:
        """Two traversals reaching one rule is corroboration, and each cites its own path."""
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9", template="a"), ev("rule", "702.9", template="b")])
        assert len(sg.evidence) == 2

    def test_a_hub_is_capped_and_the_overflow_is_counted(self) -> None:
        """One traversal returning thousands of cards for `flying` is the failure mode."""
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("card", f"c{i}") for i in range(60)], kind_cap=25)
        assert len(sg.evidence) == 25
        assert sg.capped["card"] == 35

    def test_the_cap_is_per_template_and_kind(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("card", f"a{i}", template="a") for i in range(5)], kind_cap=3)
        add_evidence(sg, [ev("card", f"b{i}", template="b") for i in range(5)], kind_cap=3)
        assert len(sg.evidence) == 6

    def test_the_default_cap_is_finite(self) -> None:
        assert DEFAULT_KIND_CAP > 0


class TestBudget:
    def test_a_small_subgraph_is_untouched(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9")])
        enforce_budget(sg, budget=10_000)
        assert len(sg.evidence) == 1 and not sg.dropped

    def test_the_farthest_evidence_goes_first(self) -> None:
        """Budget is spent on what the question named, not on what the walk found."""
        sg = Subgraph(question="q")
        add_evidence(
            sg,
            [ev("rule", f"r{i}", "word " * 80, distance=i % 4) for i in range(30)],
        )
        enforce_budget(sg, budget=1000)
        assert max(e.distance for e in sg.evidence) < 3

    def test_eviction_is_recorded_not_silent(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", f"r{i}", "word " * 80, distance=3) for i in range(30)])
        enforce_budget(sg, budget=500)
        assert sum(sg.dropped.values()) > 0
        assert "dropped" in sg.note

    def test_the_result_fits(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", f"r{i}", "word " * 80, distance=1) for i in range(30)])
        enforce_budget(sg, budget=1000)
        assert sg.tokens <= 1000


class TestSerialize:
    def test_every_line_carries_its_handle_and_path(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9", "Flying means...", template="kw")])
        rendered = serialize(sg)
        assert "[rule:702.9]" in rendered and "via kw:" in rendered

    def test_a_trimmed_context_announces_itself(self) -> None:
        """A model told the context is incomplete can hedge; one told nothing cannot."""
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", f"r{i}", "word " * 80, distance=2) for i in range(30)])
        enforce_budget(sg, budget=500)
        assert "NOTICE" in serialize(sg)

    def test_a_complete_context_carries_no_notice(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9")])
        assert "NOTICE" not in serialize(sg)


class TestExplicitFailure:
    def test_empty_renders_its_outcome(self) -> None:
        """The DoD forbids silence: non-empty subgraph or a named failure."""
        sg = Subgraph(question="q", outcome=Outcome.NO_SEED, note="no keyword to seed from")
        rendered = serialize(sg)
        assert "NO EVIDENCE" in rendered and "no_seed" in rendered

    def test_every_outcome_other_than_resolved_is_a_failure_the_caller_sees(self) -> None:
        assert set(Outcome) - {Outcome.RESOLVED} == {
            Outcome.NO_ENTITIES,
            Outcome.AMBIGUOUS,
            Outcome.NO_SEED,
            Outcome.NO_MATCH,
        }

    def test_citations_are_deduped_in_order(self) -> None:
        sg = Subgraph(question="q")
        add_evidence(sg, [ev("rule", "702.9", template="a"), ev("rule", "702.9", template="b")])
        assert sg.citations() == ["rule:702.9"]
