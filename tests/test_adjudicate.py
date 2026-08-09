"""E-003b: deriving the disagreements, and the ordering guard that protects E-003a."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adjudicate import (
    ceiling_is_measured,
    disagreements,
    gold_citations,
    load_verdicts,
    predicted_citations,
)

GOLD_ROWS = [
    {
        "ruling_id": "r1",
        "split": "annotation",
        "cited_rules": [{"rule_number": "709.3"}, {"rule_number": "709.3c"}],
        "citations_reviewed": True,
    },
    {
        "ruling_id": "r2",
        "split": "annotation",
        "cited_rules": [{"rule": "601.2c"}],  # older key
        "citations_reviewed": True,
    },
    {
        "ruling_id": "r3",
        "split": "annotation",
        "cited_rules": [],
        "citations_reviewed": False,  # no gold at all, not empty gold
    },
    {
        "ruling_id": "d1",
        "split": "dev",
        "cited_rules": [{"rule_number": "104.3a"}],
        "citations_reviewed": True,
    },
]


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return path


class TestGold:
    def test_only_the_named_split(self) -> None:
        assert set(gold_citations(GOLD_ROWS, "annotation")) == {"r1", "r2"}

    def test_unreviewed_rows_have_no_gold(self) -> None:
        """Absent, not empty — otherwise every prediction there is a false positive."""
        assert "r3" not in gold_citations(GOLD_ROWS, "annotation")

    def test_the_older_rule_key_is_read(self) -> None:
        assert gold_citations(GOLD_ROWS, "annotation")["r2"] == {"601.2c"}


class TestPredicted:
    def test_only_citation_edges_on_scored_rulings(self, tmp_path: Path) -> None:
        gated = write_jsonl(
            tmp_path / "gated.jsonl",
            [
                {"edge_type": "CITES_RULE", "source_key": "r1", "target_key": "701.9"},
                {"edge_type": "MENTIONS", "source_key": "r1", "target_key": "opt-1"},
                {"edge_type": "CITES_RULE", "source_key": "r3", "target_key": "100.1"},
            ],
        )
        assert predicted_citations(gated, {"r1", "r2"}) == {"r1": {"701.9"}, "r2": set()}

    def test_a_ruling_with_no_edges_is_present_and_empty(self, tmp_path: Path) -> None:
        """A skipped ruling is a document with zero predictions, not a missing one."""
        gated = write_jsonl(tmp_path / "gated.jsonl", [])
        assert predicted_citations(gated, {"r1"}) == {"r1": set()}


class TestDisagreements:
    def test_both_directions_become_cases(self) -> None:
        gold = {"r1": {"709.3", "709.3c"}}
        predicted = {"r1": {"709.3", "701.9"}}
        cases = disagreements(gold, predicted)
        assert cases == [
            {"ruling_id": "r1", "kind": "fp", "rule_number": "701.9"},
            {"ruling_id": "r1", "kind": "fn", "rule_number": "709.3c"},
        ]

    def test_agreement_produces_no_case(self) -> None:
        assert disagreements({"r1": {"709.3"}}, {"r1": {"709.3"}}) == []

    def test_one_case_per_rule_number(self) -> None:
        cases = disagreements({"r1": set()}, {"r1": {"a", "b", "c"}})
        assert len(cases) == 3


class TestCeilingGuard:
    def test_a_missing_blind_pass_blocks(self, tmp_path: Path) -> None:
        ok, why = ceiling_is_measured(tmp_path / "nope.jsonl")
        assert not ok and "no blind second pass" in why

    def test_an_unfinished_blind_pass_blocks(self, tmp_path: Path) -> None:
        blind = write_jsonl(
            tmp_path / "blind.jsonl",
            [{"citations_reviewed": True}, {"citations_reviewed": False}],
        )
        ok, why = ceiling_is_measured(blind)
        assert not ok and "1 of 2" in why

    def test_a_finished_blind_pass_allows(self, tmp_path: Path) -> None:
        blind = write_jsonl(tmp_path / "blind.jsonl", [{"citations_reviewed": True}])
        assert ceiling_is_measured(blind) == (True, "")


class TestVerdicts:
    def test_a_later_verdict_supersedes_an_earlier_one(self, tmp_path: Path) -> None:
        """Verdicts are appended, so a corrected call must win without erasing history."""
        path = write_jsonl(
            tmp_path / "v.jsonl",
            [
                {"case": 1, "verdict": "gold_right"},
                {"case": 1, "verdict": "both_defensible"},
            ],
        )
        assert load_verdicts(path)[1]["verdict"] == "both_defensible"

    def test_no_file_means_nothing_judged(self, tmp_path: Path) -> None:
        assert load_verdicts(tmp_path / "absent.jsonl") == {}
