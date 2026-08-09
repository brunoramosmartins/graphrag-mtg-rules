"""The mechanical gold audit — consistency checks that never touch the LLM.

The severity split is the part worth pinning: `error` findings are objectively
wrong and block publication, while `no-shared-vocabulary` is advisory precisely
because it fires on correct citations found by reading rather than searching.
Promoting it to an error would push an annotator to "fix" good labels.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_gold import ERROR, REVIEW, audit, audit_row, cited_numbers, summarise
from graphrag_mtg.etl.cr_parser import CRDocument, Rule


def rule(number: str, text: str) -> Rule:
    return Rule(number=number, level=2, text=text, parent="700", section="x")


def doc() -> CRDocument:
    return CRDocument(
        effective_date=None,
        rules=[
            rule("702.44a", "Sunburst is a static ability that functions as an object enters."),
            rule("707.2", "When copying an object, the copy acquires the copiable values."),
            rule("702.2", "Deathtouch is a static ability."),
        ],
        glossary=[],
    )


def row(ruling_id: str, text: str, *numbers: str, reviewed: bool = True) -> dict:
    return {
        "ruling_id": ruling_id,
        "text": text,
        "stratum": "plain",
        "citations_reviewed": reviewed,
        "cited_rules": [{"rule_number": n} for n in numbers],
    }


SUNBURST = "If the artifact has sunburst, the copy gets counters for each color of mana."


class TestCitedNumbers:
    def test_reads_the_canonical_key(self) -> None:
        assert cited_numbers(row("r1", "t", "707.2", "702.44a")) == ["707.2", "702.44a"]

    def test_tolerates_the_older_rule_key(self) -> None:
        assert cited_numbers({"cited_rules": [{"rule": "707.2"}]}) == ["707.2"]

    def test_no_citation_is_not_a_finding(self) -> None:
        assert cited_numbers(row("r1", "t")) == []


class TestAuditRow:
    def test_a_well_grounded_citation_produces_nothing(self) -> None:
        assert audit_row(row("r1", SUNBURST, "702.44a"), doc()) == []

    def test_rule_absent_from_the_cr_is_an_error(self) -> None:
        (finding,) = audit_row(row("r1", SUNBURST, "999.9z"), doc())
        assert (finding.check, finding.severity) == ("unresolvable", ERROR)

    def test_chapter_level_citation_is_an_error(self) -> None:
        (finding,) = audit_row(row("r1", SUNBURST, "704"), doc())
        assert (finding.check, finding.severity) == ("chapter-level", ERROR)

    def test_the_same_rule_cited_twice_is_an_error(self) -> None:
        findings = audit_row(row("r1", SUNBURST, "702.44a", "702.44a"), doc())
        assert [(f.check, f.severity) for f in findings] == [("duplicate", ERROR)]

    def test_citation_sharing_no_vocabulary_is_advisory_only(self) -> None:
        """The mistyped-number detector — deliberately not an error."""
        (finding,) = audit_row(row("r1", SUNBURST, "702.2"), doc())
        assert (finding.check, finding.severity) == ("no-shared-vocabulary", REVIEW)

    def test_a_ruling_with_no_text_is_not_flagged_for_vocabulary(self) -> None:
        assert audit_row(row("r1", "", "702.2"), doc()) == []


class TestAudit:
    def test_unreviewed_rows_are_skipped(self) -> None:
        rows = [row("r1", SUNBURST, "999.9z", reviewed=False)]
        assert audit(rows, doc()) == []

    def test_errors_are_reported_before_reviews(self) -> None:
        rows = [row("r1", SUNBURST, "702.2"), row("r2", SUNBURST, "999.9z")]
        assert [f.severity for f in audit(rows, doc())] == [ERROR, REVIEW]


class TestSummarise:
    def test_counts_reviewed_and_unreviewed_separately(self) -> None:
        rows = [row("r1", SUNBURST, "702.44a"), row("r2", SUNBURST, reviewed=False)]
        stats = summarise(rows)
        assert (stats["reviewed"], stats["unreviewed"]) == (1, 1)

    def test_reports_the_uncited_rate_per_stratum(self) -> None:
        rows = [row("r1", SUNBURST, "702.44a"), row("r2", SUNBURST)]
        assert summarise(rows)["uncited_by_stratum"] == {"plain": (1, 2)}

    def test_surfaces_a_rule_carrying_an_outsized_share(self) -> None:
        rows = [row(f"r{i}", SUNBURST, "702.44a") for i in range(3)]
        stats = summarise(rows)
        assert stats["most_cited"][0] == ("702.44a", 3)
        assert stats["cited_once"] == 0
