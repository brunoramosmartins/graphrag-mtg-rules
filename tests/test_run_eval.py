"""E-001's harness: which side it runs, and what it refuses to open.

The evaluation split is 57 questions opened once, in Phase 8. Nothing in
this file measures anything; every test here guards the one irreversible
mistake available in `run_eval.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_eval


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def golden(tmp_path: Path) -> tuple[Path, Path]:
    directory = tmp_path / "golden"
    write_jsonl(
        directory / "ids_v0.jsonl",
        [
            {"id": "rg-1", "stratum": "definition_1hop", "question": None},
            {"id": "rg-2", "stratum": "interaction_multihop", "question": None},
        ],
    )
    write_jsonl(
        directory / "authored_v0.jsonl",
        [{"id": "hand-1", "stratum": "definition_1hop", "question": "What does trample do?"}],
    )
    split = directory / "phase4_dev_ids.json"
    split.write_text(json.dumps({"dev_ids": ["rg-1", "hand-1"]}), encoding="utf-8")
    return directory, split


class TestQuestionRows:
    def test_dev_is_the_frozen_draw(self, golden: tuple[Path, Path]) -> None:
        directory, split = golden
        assert {row["id"] for row in run_eval.question_rows(directory, split, "dev")} == {
            "rg-1",
            "hand-1",
        }

    def test_eval_is_the_complement(self, golden: tuple[Path, Path]) -> None:
        # A question added to the pool later lands on the evaluation side
        # by default rather than quietly joining the tuning set.
        directory, split = golden
        assert {row["id"] for row in run_eval.question_rows(directory, split, "eval")} == {"rg-2"}


class TestGuardSide:
    def namespace(self, **kw) -> argparse.Namespace:
        return argparse.Namespace(
            **{"split_side": "dev", "open_the_evaluation_split": False, **kw}
        )

    def test_dev_passes(self) -> None:
        assert run_eval.guard_side(self.namespace()) == "dev"

    def test_eval_is_refused_without_saying_so(self) -> None:
        # E-006's first run read 0.067 from two harness bugs and was
        # re-runnable only because it was the development split. There is
        # no second draw here.
        with pytest.raises(SystemExit, match="opened once"):
            run_eval.guard_side(self.namespace(split_side="eval"))

    def test_eval_passes_when_meant(self) -> None:
        assert (
            run_eval.guard_side(
                self.namespace(split_side="eval", open_the_evaluation_split=True)
            )
            == "eval"
        )


class TestTextOf:
    def test_prefers_the_inline_question(self, tmp_path: Path) -> None:
        row = {"id": "hand-1", "question": "What does trample do?"}
        assert run_eval.text_of(row, tmp_path) == "What does trample do?"

    def test_falls_back_to_the_gitignored_cache(self, tmp_path: Path) -> None:
        # RulesGuru rows carry null and keep the text out of the repo —
        # the licence posture the golden set already uses.
        (tmp_path / "rg-1.json").write_text(
            json.dumps({"questionSimple": "Does it trigger?"}), encoding="utf-8"
        )
        assert run_eval.text_of({"id": "rg-1", "question": None}, tmp_path) == "Does it trigger?"

    def test_says_which_file_is_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="rg-9"):
            run_eval.text_of({"id": "rg-9", "question": None}, tmp_path)


class TestRegisteredConfiguration:
    def test_the_incompleteness_notice_is_suppressed(self) -> None:
        # E-001 pin 11. Flipping this is a change to the registered
        # protocol, not a flag to try, so it is asserted rather than
        # trusted to stay where it was put.
        assert run_eval.NOTICE is False

    def test_only_the_built_arm_is_offerable(self) -> None:
        # Naming the unbuilt arms keeps `--arm` from implying arm B is the
        # whole experiment, and keeps the rehearsal from reading complete.
        assert set(run_eval.ARMS) == {"B"}
        assert set(run_eval.UNBUILT) == {"A", "C"}
