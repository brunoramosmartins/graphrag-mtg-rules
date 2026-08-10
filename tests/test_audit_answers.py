"""The audit harness's ordering guards — the part that cannot be re-derived later.

Whether the author looked at an answer before freezing the sufficiency
labels is invisible after the fact. So the tool refuses, and these tests
pin the refusals rather than the arithmetic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_answers  # noqa: E402


def write(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def retrieval_run(tmp_path: Path) -> Path:
    return write(
        tmp_path / "retrieval.jsonl",
        [
            {"question_id": "rg-1", "outcome": "resolved", "citations": ["rule:613.4"]},
            {"question_id": "rg-2", "outcome": "no_seed", "citations": []},
        ],
    )


def answers_run(tmp_path: Path) -> Path:
    return write(
        tmp_path / "answers.jsonl",
        [
            {
                "question_id": "rg-1",
                "text": "It applies [rule:613.4]. So it stays a 1/1.",
                "refused": False,
            },
            {"question_id": "rg-2", "text": "CANNOT ANSWER — no rule retrieved.", "refused": True},
        ],
    )


def init_sufficiency(tmp_path: Path) -> Path:
    out = tmp_path / "sufficiency.json"
    audit_answers.sufficiency_init(
        argparse.Namespace(retrieval=retrieval_run(tmp_path), out=out, force=False)
    )
    return out


def label(path: Path, labels: dict[str, str]) -> None:
    meta = json.loads(path.read_text(encoding="utf-8"))
    for question, value in labels.items():
        meta["labels"][question]["label"] = value
    path.write_text(json.dumps(meta), encoding="utf-8")


class TestSufficiencyFirst:
    def test_init_writes_one_unlabelled_row_per_question(self, tmp_path: Path) -> None:
        meta = json.loads(init_sufficiency(tmp_path).read_text(encoding="utf-8"))
        assert set(meta["labels"]) == {"rg-1", "rg-2"}
        assert meta["frozen"] is False

    def test_it_refuses_to_overwrite_existing_labels(self, tmp_path: Path) -> None:
        out = init_sufficiency(tmp_path)
        with pytest.raises(SystemExit, match="refusing to overwrite"):
            audit_answers.sufficiency_init(
                argparse.Namespace(retrieval=retrieval_run(tmp_path), out=out, force=False)
            )

    def test_freezing_requires_every_label(self, tmp_path: Path) -> None:
        out = init_sufficiency(tmp_path)
        label(out, {"rg-1": "sufficient"})
        with pytest.raises(SystemExit, match="needs a label"):
            audit_answers.sufficiency_freeze(argparse.Namespace(out=out))

    def test_an_invalid_label_is_not_a_label(self, tmp_path: Path) -> None:
        out = init_sufficiency(tmp_path)
        label(out, {"rg-1": "probably fine", "rg-2": "insufficient"})
        with pytest.raises(SystemExit, match="needs a label"):
            audit_answers.sufficiency_freeze(argparse.Namespace(out=out))

    def test_freezing_records_a_hash(self, tmp_path: Path) -> None:
        out = init_sufficiency(tmp_path)
        label(out, {"rg-1": "sufficient", "rg-2": "insufficient"})
        audit_answers.sufficiency_freeze(argparse.Namespace(out=out))
        meta = json.loads(out.read_text(encoding="utf-8"))
        assert meta["frozen"] and len(meta["hash"]) == 64


class TestSegmentationOrdering:
    def test_segmenting_before_freezing_is_refused(self, tmp_path: Path) -> None:
        """The guard that keeps the refusal rule from being circular."""
        out = init_sufficiency(tmp_path)
        with pytest.raises(SystemExit, match="not frozen"):
            audit_answers.segment(
                argparse.Namespace(
                    answers=answers_run(tmp_path),
                    out=tmp_path / "claims.jsonl",
                    sufficiency=out,
                    force=False,
                )
            )

    def test_a_missing_sufficiency_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="No sufficiency file"):
            audit_answers.segment(
                argparse.Namespace(
                    answers=answers_run(tmp_path),
                    out=tmp_path / "claims.jsonl",
                    sufficiency=tmp_path / "absent.json",
                    force=False,
                )
            )


class TestSegmentation:
    def frozen(self, tmp_path: Path) -> Path:
        out = init_sufficiency(tmp_path)
        label(out, {"rg-1": "sufficient", "rg-2": "insufficient"})
        audit_answers.sufficiency_freeze(argparse.Namespace(out=out))
        return out

    def run(self, tmp_path: Path) -> Path:
        worksheet = tmp_path / "claims.jsonl"
        audit_answers.segment(
            argparse.Namespace(
                answers=answers_run(tmp_path),
                out=worksheet,
                sufficiency=self.frozen(tmp_path),
                force=False,
            )
        )
        return worksheet

    def test_sentences_arrive_stripped_of_citations(self, tmp_path: Path) -> None:
        rows = audit_answers.load_rows(self.run(tmp_path))
        assert rows[0].sentence == "It applies."

    def test_whether_a_sentence_was_cited_survives_the_stripping(self, tmp_path: Path) -> None:
        rows = audit_answers.load_rows(self.run(tmp_path))
        assert rows[0].cited is True
        assert rows[1].cited is False

    def test_every_row_starts_unlabelled(self, tmp_path: Path) -> None:
        rows = audit_answers.load_rows(self.run(tmp_path))
        assert all(row.label.value == "unlabelled" for row in rows)

    def test_re_segmenting_over_labels_is_refused(self, tmp_path: Path) -> None:
        worksheet = self.run(tmp_path)
        with pytest.raises(SystemExit, match="refusing to re-segment"):
            audit_answers.segment(
                argparse.Namespace(
                    answers=answers_run(tmp_path),
                    out=worksheet,
                    sufficiency=tmp_path / "sufficiency.json",
                    force=False,
                )
            )
