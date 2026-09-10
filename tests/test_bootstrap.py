"""Clean machine to first answer: the order, the checks, and the timings.

Nothing here touches a network or a database. What it holds are the
decisions the script makes before it does anything expensive — which
sources it insists on, which question it is allowed to ask, and whether a
run that skipped everything still reports honestly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bootstrap


class TestStepOrder:
    def test_sources_arrive_before_the_graph_that_needs_them(self) -> None:
        names = [name for name, _ in bootstrap.STEPS]
        assert names.index("download") < names.index("graph")

    def test_the_graph_is_built_before_it_is_queried(self) -> None:
        names = [name for name, _ in bootstrap.STEPS]
        assert names.index("graph") < names.index("answer")

    def test_the_schema_is_applied_before_the_load(self) -> None:
        # Constraints before MERGE: creating them afterwards fails on any
        # duplicate the load already wrote.
        names = [name for name, _ in bootstrap.STEPS]
        assert names.index("schema") < names.index("graph")


class TestRequiredSources:
    def test_all_three_deterministic_sources_are_checked(self) -> None:
        # Checked by name rather than inferred from the download's exit
        # code: `resolve_comprehensive_rules` prints a message and returns
        # an empty list when WotC's JS-rendered page hides the link, and
        # the run still exits 0. Unchecked, the missing file surfaces two
        # steps later as a FileNotFoundError naming the file, not the
        # reason.
        labels = " ".join(label for label, _ in bootstrap.REQUIRED).lower()
        assert "rules" in labels
        assert "cards" in labels
        assert "rulings" in labels

    def test_each_entry_resolves_to_a_path(self) -> None:
        for _, locate in bootstrap.REQUIRED:
            assert isinstance(locate(), Path)


class TestTheQuestionItAsks:
    """It must be a question the repo actually contains.

    Authored and generated golden rows carry their text inline; RulesGuru
    rows carry `null` and keep theirs in a gitignored cache. Reaching for
    one of those on a clean machine would fail for a licensing reason
    wearing a missing-file costume.
    """

    def test_an_inline_question_is_used(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "authored.jsonl"
        path.write_text(
            json.dumps({"id": "a-1", "stratum": "definition_1hop", "question": "What is trample?"})
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(bootstrap, "GOLDEN", path)
        assert bootstrap.first_authored_question() == "What is trample?"

    def test_a_row_with_no_inline_text_is_skipped(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "authored.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps({"id": "rg-1", "stratum": "definition_1hop", "question": None}),
                    json.dumps({"id": "a-1", "stratum": "definition_1hop", "question": "Inline?"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(bootstrap, "GOLDEN", path)
        assert bootstrap.first_authored_question() == "Inline?"

    def test_a_missing_file_falls_back_rather_than_crashing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(bootstrap, "GOLDEN", tmp_path / "absent.jsonl")
        assert bootstrap.first_authored_question() == bootstrap.FALLBACK_QUESTION

    def test_a_file_of_only_cached_rows_falls_back(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "authored.jsonl"
        path.write_text(json.dumps({"id": "rg-1", "question": None}) + "\n", encoding="utf-8")
        monkeypatch.setattr(bootstrap, "GOLDEN", path)
        assert bootstrap.first_authored_question() == bootstrap.FALLBACK_QUESTION


class TestReport:
    def test_the_total_is_the_sum_of_the_steps(self) -> None:
        report = bootstrap.Report()
        report.add("download", 3.6, "current")
        report.add("graph", 129.7, "loaded")
        assert report.total == pytest.approx(133.3)

    def test_an_empty_report_totals_nothing(self) -> None:
        assert bootstrap.Report().total == 0

    def test_the_json_keeps_the_step_order(self) -> None:
        # The published onboarding figure is a sequence, not a set: which
        # step cost the time is the whole content of the measurement.
        report = bootstrap.Report()
        for name in ("download", "schema", "graph", "answer"):
            report.add(name, 1.0, "")
        payload = report.as_dict()
        assert [step["name"] for step in payload["steps"]] == [
            "download",
            "schema",
            "graph",
            "answer",
        ]

    def test_a_skipped_step_still_appears(self) -> None:
        # A warm run's value is in showing that a step cost nothing, so
        # dropping zero-second steps would delete the finding.
        report = bootstrap.Report()
        report.add("download", 0.0, "skipped (--no-download)")
        assert report.as_dict()["steps"][0]["detail"].startswith("skipped")


class TestSkippingTheDownload:
    def test_no_download_reports_that_it_skipped(self, monkeypatch) -> None:
        # Scryfall regenerates its bulk daily, so "unchanged" has a
        # shelf life of about a day: a fresh bulk reloads the graph and
        # invalidates any vector index keyed on the old corpus hash. The
        # flag makes that a choice rather than a surprise.
        called = []
        monkeypatch.setattr(bootstrap, "download_main", lambda argv: called.append(argv))
        args = type("A", (), {"no_download": True, "force": False})()
        assert "skipped" in bootstrap.step_download(args)
        assert called == []
