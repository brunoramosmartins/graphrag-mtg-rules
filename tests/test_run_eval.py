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

    def test_all_three_registered_arms_are_offerable(self) -> None:
        assert set(run_eval.ARMS) == {"A", "B", "C"}
        assert run_eval.UNBUILT == {}


class TestConfigure:
    """Arm identity determines configuration, in one place.

    The harness previously passed a text retriever unconditionally and
    labelled the output arm B. Text search fires on 2 of 20 development
    questions, so every summary number looked exactly as a graph-only arm
    would look, and the mislabel survived a full run and a registry entry.
    """

    def namespace(self, arm: str, **kw) -> argparse.Namespace:
        defaults = {
            "arm": arm,
            "mode": "lexical",
            "text": "tfidf",
            "always_text": False,
            "iterative": False,
        }
        return argparse.Namespace(**{**defaults, **kw})

    def test_arm_b_is_handed_no_text_retriever_at_all(self) -> None:
        # Graph-only means graph-only: a routed question must come back as
        # NO_SEED rather than quietly reaching for a half arm B is defined
        # as not having. Re-run properly, arm B gives 2 no_seed of 20 —
        # the property the mislabelled run concealed.
        searcher, uses_graph, always_text = run_eval.configure(self.namespace("B"))
        assert searcher is None and uses_graph and not always_text

    def test_arm_c_gets_a_text_half_and_the_graph(self) -> None:
        searcher, uses_graph, _ = run_eval.configure(self.namespace("C"))
        assert searcher == "tfidf" and uses_graph

    def test_arm_c_routing_is_off_by_default(self) -> None:
        # Off is the shipped behaviour, and always-on is the published
        # ablation — not the other way round.
        _, _, always_text = run_eval.configure(self.namespace("C"))
        assert always_text is False
        _, _, always_text = run_eval.configure(self.namespace("C", always_text=True))
        assert always_text is True

    def test_arm_a_touches_no_graph(self) -> None:
        _, uses_graph, always_text = run_eval.configure(self.namespace("A", mode="lexical"))
        assert not uses_graph and always_text


class TestDescribe:
    """Every run prints the configuration it used.

    A line spelling out the configuration is what would have made the
    arm B / arm C mislabel visible on the run that produced it.
    """

    def namespace(self, arm: str, **kw) -> argparse.Namespace:
        defaults = {
            "arm": arm,
            "mode": "hybrid",
            "text": "vector",
            "always_text": False,
            "iterative": False,
        }
        return argparse.Namespace(**{**defaults, **kw})

    def test_arm_b_says_it_has_no_text_retriever(self) -> None:
        assert "no text retriever" in run_eval.describe(self.namespace("B"))

    def test_arm_c_names_its_text_half_and_its_routing(self) -> None:
        line = run_eval.describe(self.namespace("C"))
        assert "vector text half" in line and "routed (shipped)" in line

    def test_arm_c_always_on_says_so(self) -> None:
        assert "always-on" in run_eval.describe(self.namespace("C", always_text=True))

    def test_arm_a_says_it_uses_no_graph(self) -> None:
        assert "vector only" in run_eval.describe(self.namespace("A"))
