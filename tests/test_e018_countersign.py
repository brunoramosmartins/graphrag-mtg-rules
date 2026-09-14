"""The countersign records a reading; it must never manufacture one.

Every test here is about a way the tool could produce a letter nobody read: a
default that fills a blank row, a score over a partial sheet, a re-run that
wipes marks, a silent overwrite, or a departure from the published split that
prints like agreement. A countersign that can be produced without reading is
worth less than an open checkbox, because the checkbox at least says so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e018_countersign as cs


def sheet(**marks: str) -> dict:
    payload = cs.seed(sorted(cs.PROPOSED))
    for row in payload["rows"]:
        if row["question_id"] in marks:
            row["group"] = marks[row["question_id"]]
    return payload


class TestNothingIsMarkedByDefault:
    def test_a_fresh_sheet_has_no_groups(self) -> None:
        assert all(row["group"] is None for row in cs.seed(sorted(cs.PROPOSED))["rows"])

    def test_the_proposal_is_carried_but_is_not_the_mark(self) -> None:
        # The published letter has to be visible for a disagreement to be
        # visible. It must not double as an answer.
        rows = cs.seed(["rg-51"])["rows"]
        assert rows[0]["proposed"] == "D"
        assert rows[0]["group"] is None


class TestAMarkThatDepartsSaysSo:
    def test_agreeing_with_the_proposal_is_reported_plainly(self) -> None:
        row = {"question_id": "rg-51", "proposed": "D", "group": None, "note": ""}
        assert "DEPARTS" not in cs.apply_mark(row, "D", None)

    def test_departing_from_the_proposal_is_announced(self) -> None:
        row = {"question_id": "rg-51", "proposed": "D", "group": None, "note": ""}
        assert "DEPARTS" in cs.apply_mark(row, "A", None)

    def test_overwriting_an_earlier_mark_is_announced(self) -> None:
        # A mistyped worksheet number would otherwise replace a reading that
        # already happened, with nothing saying which one.
        row = {"question_id": "rg-51", "proposed": "D", "group": "D", "note": ""}
        assert "CHANGED" in cs.apply_mark(row, "C", None)

    def test_remarking_the_same_letter_is_not_a_change(self) -> None:
        row = {"question_id": "rg-51", "proposed": "D", "group": "D", "note": ""}
        assert "CHANGED" not in cs.apply_mark(row, "D", None)

    def test_a_note_is_recorded_when_given_and_left_alone_when_not(self) -> None:
        row = {"question_id": "rg-51", "proposed": "D", "group": None, "note": "kept"}
        cs.apply_mark(row, "D", None)
        assert row["note"] == "kept"
        cs.apply_mark(row, "D", "replaced")
        assert row["note"] == "replaced"


class TestTheTargetMustNameARow:
    """Resolution never falls through to a default row."""

    def test_a_worksheet_number_resolves(self) -> None:
        rows = cs.seed(["rg-51", "rg-396"])["rows"]
        assert cs.resolve("2", rows) == 1

    def test_an_id_resolves(self) -> None:
        rows = cs.seed(["rg-51", "rg-396"])["rows"]
        assert cs.resolve("rg-51", rows) == 0

    def test_a_number_past_the_end_is_refused(self) -> None:
        rows = cs.seed(["rg-51"])["rows"]
        with pytest.raises(SystemExit):
            cs.resolve("7", rows)

    def test_an_unknown_id_is_refused(self) -> None:
        rows = cs.seed(["rg-51"])["rows"]
        with pytest.raises(SystemExit):
            cs.resolve("rg-9999", rows)


class TestTheGroupsMatchThePublishedFile:
    def test_every_proposed_letter_is_a_defined_group(self) -> None:
        assert set(cs.PROPOSED.values()) <= set(cs.GROUPS)

    def test_the_released_figure_is_a_and_d_only(self) -> None:
        # "Generation fails with the evidence in hand" is A plus D. B is
        # arithmetic and C reached the key's verdict; folding either in
        # inflates the one claim this file is allowed to release.
        assert set(cs.GENERATION_GROUPS) == {"A", "D"}

    def test_the_proposal_reproduces_the_published_counts(self) -> None:
        counts = dict.fromkeys(cs.GROUPS, 0)
        for letter in cs.PROPOSED.values():
            counts[letter] += 1
        assert counts == {"A": 3, "B": 2, "C": 3, "D": 1}


class TestARerunDoesNotDestroyAReading:
    def test_marks_survive_a_second_worksheet(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "sheet.json"
        monkeypatch.setattr(cs, "SHEET", path)
        path.write_text(json.dumps(sheet(**{"rg-51": "A"})) + "\n", encoding="utf-8")

        carried = {row["question_id"]: row for row in cs.load_sheet()["rows"]}
        assert carried["rg-51"]["group"] == "A"

    def test_a_missing_sheet_is_refused_rather_than_invented(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(cs, "SHEET", tmp_path / "absent.json")
        with pytest.raises(SystemExit):
            cs.load_sheet()
