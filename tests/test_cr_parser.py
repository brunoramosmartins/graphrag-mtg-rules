"""Golden-file tests for the deterministic CR parser.

Runs against ``tests/fixtures/cr_excerpt.txt``: a frozen, fair-use-sized
excerpt of the real Comprehensive Rules that deliberately reproduces the
document's structural traps — a table of contents that repeats every heading,
UTF-8 with a BOM, a trailing-period numbered rule beside a lettered subrule,
an ``Example:`` line, and an indented continuation line.

The expected values here were derived by parsing the real 939 KB document, not
invented: the full CR yields exactly 3,120 numbered and lettered rules across
146 chapters, which is the Phase 2 coverage bar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphrag_mtg.etl.cr_parser import (
    CRDocument,
    Rule,
    extract_references,
    level_of,
    parent_of,
    parse_cr,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cr_excerpt.txt"


@pytest.fixture(scope="module")
def doc() -> CRDocument:
    return parse_cr(FIXTURE)


def test_fixture_is_utf8_with_a_bom():
    # The real CR ships with a BOM; if the fixture ever loses it, the tests
    # would stop covering the encoding that actually bit us.
    assert FIXTURE.read_bytes().startswith(b"\xef\xbb\xbf")


def test_parses_the_expected_tree(doc):
    assert doc.effective_date == "February 27, 2026"
    assert len(doc.rules) == 13
    assert [r.number for r in doc.rules] == [
        "613", "613.3", "613.4", "613.4a", "613.4b", "613.4c", "613.7", "613.8",
        "614", "614.1",
        "702", "702.2", "702.2c",
    ]


def test_table_of_contents_is_not_parsed_as_rules(doc):
    # The TOC repeats "613. Interaction of Continuous Effects" et al. Parsing it
    # would duplicate every chapter in the graph — the single most likely
    # regression in this parser.
    numbers = [r.number for r in doc.rules]
    assert numbers.count("613") == 1
    assert numbers.count("614") == 1
    assert numbers.count("702") == 1
    assert len(numbers) == len(set(numbers))


def test_levels_and_parents_form_a_connected_tree(doc):
    by_number = doc.by_number
    assert by_number["613"].level == 1
    assert by_number["613.4"].level == 2
    assert by_number["613.4b"].level == 3

    assert by_number["613"].parent is None
    assert by_number["613.4"].parent == "613"
    assert by_number["613.4b"].parent == "613.4"

    # No rule may point at a parent that does not exist.
    assert all(r.parent is None or r.parent in by_number for r in doc.rules)


@pytest.mark.parametrize(
    ("number", "expected"),
    [("613", None), ("613.4", "613"), ("613.4b", "613.4"), ("702.19e", "702.19")],
)
def test_parent_of(number, expected):
    assert parent_of(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"), [("613", 1), ("613.4", 2), ("613.4b", 3), ("702.179", 2)]
)
def test_level_of(number, expected):
    assert level_of(number) == expected


def test_sections_are_carried_onto_their_rules(doc):
    by_number = doc.by_number
    assert by_number["613.4b"].section == "Spells, Abilities, and Effects"
    assert by_number["702.2c"].section == "Additional Rules"


def test_explicit_cross_references_become_edges(doc):
    assert doc.by_number["613.3"].references == ["613.7", "613.8"]
    # "See rules 613.3 and 613.4." — the multi-target phrasing.
    assert doc.by_number["613.8"].references == ["613.3", "613.4"]


def test_references_to_rules_outside_the_document_are_dropped(doc):
    # 613.4a cites "rule 604.3", which the excerpt does not contain. Keeping it
    # would create a dangling edge, so it must be dropped, not invented.
    assert doc.by_number["613.4a"].references == []
    assert all(ref in doc.by_number for r in doc.rules for ref in r.references)


def test_a_rule_does_not_reference_itself(doc):
    assert all(r.number not in r.references for r in doc.rules)


def test_example_lines_attach_to_the_preceding_rule(doc):
    assert len(doc.by_number["613.4c"].examples) == 1
    assert doc.by_number["613.4c"].examples[0].startswith("Example:")
    # An example must not become a rule of its own.
    assert all(not r.text.startswith("Example:") for r in doc.rules)


def test_indented_continuation_joins_the_previous_rule(doc):
    text = doc.by_number["613.7"].text
    assert text.endswith("rather than starting a new rule.")
    assert "timestamp order." in text


def test_subtree_returns_the_chapter_and_its_descendants(doc):
    assert [r.number for r in doc.subtree("613")] == [
        "613", "613.3", "613.4", "613.4a", "613.4b", "613.4c", "613.7", "613.8",
    ]
    assert [r.number for r in doc.subtree("613.4")] == ["613.4", "613.4a", "613.4b", "613.4c"]


def test_chapter_subtrees_partition_every_rule(doc):
    # Each rule must be reachable from exactly one chapter: no orphans, no
    # double counting. Holds on the real document too (3,266 = 3,266).
    covered = sum(len(doc.subtree(r.number)) for r in doc.rules if r.level == 1)
    assert covered == len(doc.rules)


def test_subtree_follows_the_tree_not_number_prefixes():
    # Two traps in one: "613.4b" does not start with "613.4." (lettered subrules
    # append with no separator), and a plain "613.4" prefix would wrongly swallow
    # "613.41". Built by hand so the frozen excerpt stays a real excerpt.
    rules = [
        Rule(number="613", level=1, text="", parent=None, section="s"),
        Rule(number="613.4", level=2, text="", parent="613", section="s"),
        Rule(number="613.4a", level=3, text="", parent="613.4", section="s"),
        Rule(number="613.41", level=2, text="", parent="613", section="s"),
    ]
    document = CRDocument(effective_date=None, rules=rules, glossary=[])

    assert [r.number for r in document.subtree("613.4")] == ["613.4", "613.4a"]
    assert [r.number for r in document.subtree("613")] == ["613", "613.4", "613.4a", "613.41"]
    assert document.subtree("999") == []


def test_glossary_entries_are_parsed_with_their_definitions(doc):
    terms = {g.term: g for g in doc.glossary}
    assert set(terms) == {"Abandon", "Ability", "Deathtouch"}
    # A multi-sense entry keeps both senses in one definition.
    assert terms["Ability"].definition.startswith("1. Text on an object")
    assert "2. An activated or triggered ability" in terms["Ability"].definition


def test_glossary_keyword_entries_link_to_their_rule(doc):
    # This is the deterministic source of Keyword-[:DEFINED_BY]->Rule and of the
    # definition_1hop stratum.
    deathtouch = next(g for g in doc.glossary if g.term == "Deathtouch")
    assert deathtouch.references == ["702.2"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see rule 704.5 for details", ["704.5"]),
        ("See rules 602.2a and 603.3.", ["602.2a", "603.3"]),
        ("see rule 603.7 and rule 603.12", ["603.7", "603.12"]),
        ("rule 613.4b, rule 613.4c", ["613.4b", "613.4c"]),
        ("no references here", []),
        ("rule 999.9 does not exist", []),
    ],
)
def test_extract_references_handles_the_real_phrasings(text, expected):
    known = {"704.5", "602.2a", "603.3", "603.7", "603.12", "613.4b", "613.4c"}
    assert extract_references(text, known) == expected


def test_missing_structural_landmarks_fail_loudly(tmp_path):
    # A restructured CR must raise, never parse into a plausible wrong tree.
    no_glossary = tmp_path / "broken.txt"
    no_glossary.write_text("1. Game Concepts\n\n100. General\n\n100.1. Text.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Glossary"):
        parse_cr(no_glossary)

    no_rules = tmp_path / "empty.txt"
    no_rules.write_text("Contents\n\nGlossary\n\nCredits\n", encoding="utf-8")
    with pytest.raises(ValueError, match="numbered rule"):
        parse_cr(no_rules)
