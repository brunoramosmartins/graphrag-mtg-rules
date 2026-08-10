"""End-to-end retrieval assembly, with the database injected as a callable."""

from __future__ import annotations

from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon
from graphrag_mtg.retrieval.pipeline import retrieve
from graphrag_mtg.retrieval.subgraph import Outcome

CARDS = [
    {"name": "Serra Angel", "oracle_id": "serra", "layout": "normal"},
    {"name": "Humility", "oracle_id": "hum", "layout": "normal"},
    # The collision that made 6% of card names ambiguous until it was filtered.
    {"name": "Serra Angel // Serra Angel", "oracle_id": "serra-art", "layout": "art_series"},
]
ROWS = {
    "keyword_definition": [
        {
            "keyword": "Flying",
            "glossary": "A keyword ability.",
            "rule_number": "702.9",
            "rule_text": "Flying is a static ability.",
            "subrules": [{"number": "702.9a", "text": "A creature with flying."}],
        }
    ]
}


def linker() -> QueryLinker:
    return QueryLinker(
        build_card_lexicon(CARDS),
        keywords=["Flying"],
        keywords_by_oracle={"serra": ["Flying"], "hum": []},
    )


def runner(rows_by_marker: dict[str, list[dict]] | None = None):
    """Fake database: matches a query by a distinctive fragment of its Cypher."""
    table = rows_by_marker if rows_by_marker is not None else ROWS
    calls: list[str] = []

    def run(cypher: str, params):
        calls.append(cypher)
        for marker, rows in table.items():
            if marker == "keyword_definition" and "DEFINED_BY" in cypher and "HAS_KEYWORD" not in cypher:
                return rows
            if marker in cypher:
                return rows
        return []

    run.calls = calls  # type: ignore[attr-defined]
    return run


class TestLexicon:
    def test_art_series_prints_do_not_shadow_the_real_card(self) -> None:
        """2,116 of 2,196 name collisions in the corpus were art series."""
        lexicon = build_card_lexicon(CARDS)
        assert lexicon.exact["serra angel"] == {"serra"}


class TestResolvedRoute:
    def test_a_keyword_question_produces_citable_evidence(self) -> None:
        subgraph = retrieve("What does Flying do?", linker=linker(), run=runner())
        assert subgraph.outcome is Outcome.RESOLVED
        assert "rule:702.9" in subgraph.citations()

    def test_every_item_names_the_traversal_that_found_it(self) -> None:
        subgraph = retrieve("What does Flying do?", linker=linker(), run=runner())
        assert all(item.template for item in subgraph.evidence)

    def test_the_plan_decides_what_runs(self) -> None:
        """A keyword question must not fire the card traversals."""
        run = runner()
        retrieve("What does Flying do?", linker=linker(), run=run)
        assert len(run.calls) == 1


class TestExplicitFailures:
    def test_a_question_naming_nothing_touches_no_database(self) -> None:
        """The plan is inspected before anything expensive happens."""
        run = runner()
        subgraph = retrieve("what about the weather", linker=linker(), run=run)
        assert subgraph.outcome is Outcome.NO_ENTITIES
        assert run.calls == []

    def test_traversals_that_match_nothing_are_not_silence(self) -> None:
        subgraph = retrieve("What does Flying do?", linker=linker(), run=runner({}))
        assert subgraph.outcome is Outcome.NO_MATCH
        assert subgraph.is_empty
        assert "returned nothing" in subgraph.note

    def test_a_seedless_question_without_text_retrieval_says_so(self) -> None:
        """Humility has no keywords; without a searcher there is nothing to reach."""
        subgraph = retrieve("Tell me about Humility", linker=linker(), run=runner({}))
        assert subgraph.outcome is Outcome.NO_SEED
        assert "no text retrieval configured" in subgraph.note


class TestBudget:
    def test_a_hub_cannot_fill_the_context(self) -> None:
        rows = [
            {
                "keyword": "Flying",
                "glossary": "g",
                "rule_number": f"702.{i}",
                "rule_text": "word " * 200,
                "subrules": [],
            }
            for i in range(60)
        ]
        subgraph = retrieve(
            "What does Flying do?",
            linker=linker(),
            run=runner({"keyword_definition": rows}),
            token_budget=500,
        )
        assert subgraph.tokens <= 500

    def test_trimming_is_announced_in_the_note(self) -> None:
        rows = [
            {
                "keyword": "Flying",
                "glossary": "g",
                "rule_number": f"702.{i}",
                "rule_text": "word " * 200,
                "subrules": [],
            }
            for i in range(60)
        ]
        subgraph = retrieve(
            "What does Flying do?",
            linker=linker(),
            run=runner({"keyword_definition": rows}),
            token_budget=500,
        )
        assert subgraph.dropped or subgraph.capped
