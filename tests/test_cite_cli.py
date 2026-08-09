"""The cite.py citation recorder — core logic over in-memory rows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cite import apply_citation

KNOWN = {"113.7a", "603.10a", "704.5", "608.2b"}


def rows() -> list[dict]:
    return [
        {"ruling_id": "r1", "cited_rules": [], "citations_reviewed": False, "annotator": ""},
        {"ruling_id": "r2", "cited_rules": [{"rule_number": "704.5"}], "annotator": "x"},
    ]


class TestApplyCitation:
    def test_records_rules_and_marks_reviewed(self) -> None:
        data = rows()
        apply_citation(data, "r1", ["113.7a", "603.10a"], KNOWN)
        assert data[0]["cited_rules"] == [{"rule_number": "113.7a"}, {"rule_number": "603.10a"}]
        assert data[0]["citations_reviewed"] is True

    def test_none_marks_reviewed_with_no_citation(self) -> None:
        data = rows()
        apply_citation(data, "r1", [], KNOWN, mark_none=True)
        assert data[0]["cited_rules"] == []
        assert data[0]["citations_reviewed"] is True

    def test_replace_is_the_default(self) -> None:
        data = rows()
        apply_citation(data, "r2", ["608.2b"], KNOWN)
        assert data[1]["cited_rules"] == [{"rule_number": "608.2b"}]

    def test_add_appends_without_duplicating(self) -> None:
        data = rows()
        apply_citation(data, "r2", ["704.5", "608.2b"], KNOWN, append=True)
        numbers = [c["rule_number"] for c in data[1]["cited_rules"]]
        assert numbers == ["704.5", "608.2b"]  # 704.5 not duplicated

    def test_annotator_set_when_given(self) -> None:
        data = rows()
        apply_citation(data, "r1", ["113.7a"], KNOWN, annotator="Bruno")
        assert data[0]["annotator"] == "Bruno"

    def test_unknown_rule_number_rejected(self) -> None:
        with pytest.raises(ValueError, match="not in the CR"):
            apply_citation(rows(), "r1", ["999.9z"], KNOWN)

    def test_unknown_ruling_rejected(self) -> None:
        with pytest.raises(ValueError, match="not in the draft"):
            apply_citation(rows(), "ghost", ["113.7a"], KNOWN)

    def test_empty_without_none_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one rule"):
            apply_citation(rows(), "r1", [], KNOWN)
