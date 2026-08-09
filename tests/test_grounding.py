"""Grounding context: keyword directory and host-card candidates, no I/O."""

from __future__ import annotations

from graphrag_mtg.etl.cr_parser import CRDocument, GlossaryEntry, Rule
from graphrag_mtg.extraction.grounding import (
    candidate_rules_for_keywords,
    chapter_map,
    directory_block,
    grounding_block,
    keyword_directory,
)


def rule(number: str, level: int, text: str, parent: str | None) -> Rule:
    return Rule(number=number, level=level, text=text, parent=parent, section="Keywords")


def doc() -> CRDocument:
    return CRDocument(
        effective_date=None,
        rules=[
            rule("702", 1, "Keyword Abilities", None),
            rule(
                "702.1",
                2,
                "Most keyword abilities are described in prose far longer than any name.",
                "702",
            ),
            rule("702.19", 2, "Trample", "702"),
            rule("702.19e", 3, "The controller of an attacking creature...", "702.19"),
            rule("702.131", 2, "Connive", "702"),
            rule("702.131a", 3, "Certain abilities instruct a creature to connive.", "702.131"),
            rule("601", 1, "Casting Spells", None),
            rule("601.2", 2, "To cast a spell...", "601"),
        ],
        glossary=[
            GlossaryEntry(term="Trample", definition="See rule 702.19.", references=["702.19"]),
            GlossaryEntry(term="Connive", definition="See rule 702.131.", references=["702.131"]),
        ],
    )


class TestKeywordDirectory:
    def test_only_keyword_chapter_children(self) -> None:
        directory = keyword_directory(doc())
        assert ("702.19", "Trample") in directory
        assert ("702.131", "Connive") in directory
        # Neither subrules, prose rules, nor non-keyword rules belong.
        numbers = [n for n, _ in directory]
        assert "702.19e" not in numbers
        assert "702.1" not in numbers  # prose, not a keyword name
        assert "601.2" not in numbers

    def test_block_names_every_entry(self) -> None:
        block = directory_block(keyword_directory(doc()))
        assert "702.131 Connive" in block
        assert "never invent" in block


class TestChapterMap:
    def test_only_level_one_rules(self) -> None:
        assert chapter_map(doc()) == [("702", "Keyword Abilities"), ("601", "Casting Spells")]


class TestGroundingBlock:
    def test_chapters_precede_keywords(self) -> None:
        # Round 2's finding: leading with keyword names collapses every
        # citation onto 701/702, so the chapter map must come first.
        block = grounding_block(doc())
        assert block.index("601 Casting Spells") < block.index("702.131 Connive")

    def test_names_procedural_chapters_explicitly(self) -> None:
        block = grounding_block(doc())
        assert "608" in block and "613" in block

    def test_keyword_directory_can_be_dropped(self) -> None:
        """E-003 iteration 2 ran without it; the chapter map must survive alone."""
        block = grounding_block(doc(), include_keywords=False)
        assert "702.131 Connive" not in block
        assert "601 Casting Spells" in block

    def test_directory_is_included_by_default(self) -> None:
        assert "702.131 Connive" in grounding_block(doc())


class TestCandidates:
    def test_keyword_resolves_through_glossary_with_subrules(self) -> None:
        candidates = candidate_rules_for_keywords(["Connive"], doc())
        numbers = [n for n, _ in candidates]
        assert numbers == ["702.131", "702.131a"]

    def test_case_and_spacing_insensitive(self) -> None:
        candidates = candidate_rules_for_keywords(["trample"], doc())
        assert candidates[0][0] == "702.19"

    def test_unknown_keyword_is_silently_skipped(self) -> None:
        assert candidate_rules_for_keywords(["Not A Keyword"], doc()) == []

    def test_no_duplicates_across_keywords(self) -> None:
        candidates = candidate_rules_for_keywords(["Trample", "Trample"], doc())
        numbers = [n for n, _ in candidates]
        assert len(numbers) == len(set(numbers))
