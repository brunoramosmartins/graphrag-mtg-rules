"""The audit harness's ordering guards — the part that cannot be re-derived later.

Whether the author looked at an answer before freezing the sufficiency
labels is invisible after the fact. So the tool refuses, and these tests
pin the refusals rather than the arithmetic.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_answers


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


class TestClaimLabelling:
    """The combinations a worksheet must never hold.

    Every rule here is in `docs/claim-annotation-guide.md`; enforcing them
    at write time is what keeps the report from having to interpret a row
    whose fields contradict each other.
    """

    def worksheet(self, tmp_path: Path) -> tuple[Path, Path]:
        sufficiency = init_sufficiency(tmp_path)
        label(sufficiency, {"rg-1": "sufficient", "rg-2": "insufficient"})
        audit_answers.sufficiency_freeze(argparse.Namespace(out=sufficiency))
        worksheet = tmp_path / "claims.jsonl"
        audit_answers.segment(
            argparse.Namespace(
                answers=answers_run(tmp_path),
                out=worksheet,
                sufficiency=sufficiency,
                force=False,
            )
        )
        return worksheet, sufficiency

    def set(self, tmp_path: Path, prepared: tuple[Path, Path] | None = None, **kwargs) -> Path:
        worksheet, sufficiency = prepared or self.worksheet(tmp_path)
        defaults = {
            "question_id": "rg-1",
            "index": "0",
            "label": "factual",
            "support": None,
            "failure": None,
            "comment": "",
            "worksheet": worksheet,
            "sufficiency": sufficiency,
        }
        audit_answers.claims_set(argparse.Namespace(**{**defaults, **kwargs}))
        return worksheet

    def test_a_judgement_is_written_without_touching_the_segmentation(
        self, tmp_path: Path
    ) -> None:
        """The hash covers the sentences, so labelling must leave it alone."""
        prepared = self.worksheet(tmp_path)
        before = audit_answers.worksheet_hash(audit_answers.load_rows(prepared[0]))
        rows = audit_answers.load_rows(self.set(tmp_path, prepared, support="supported"))
        assert rows[0].label.value == "factual"
        assert rows[0].support.value == "supported"
        assert audit_answers.worksheet_hash(rows) == before

    def test_an_unsupported_row_without_a_failure_code_is_refused(self, tmp_path: Path) -> None:
        """E-007 predicts which failure dominates; unscored, that is not a prediction."""
        with pytest.raises(SystemExit, match="needs --failure"):
            self.set(tmp_path, support="unsupported")

    def test_a_failure_code_without_an_unsupported_row_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="describes an unsupported row"):
            self.set(tmp_path, support="supported", failure="wrong_leaf")

    def test_a_non_factual_row_is_not_judged_for_support(self, tmp_path: Path) -> None:
        """Excluded from the denominator means excluded, not scored as supported."""
        with pytest.raises(SystemExit, match="not judged for support"):
            self.set(tmp_path, label="non_factual", support="supported")

    def test_an_uncited_row_has_nothing_to_support(self, tmp_path: Path) -> None:
        """Row 1 carries no marker: a factual one there is a coverage miss."""
        with pytest.raises(SystemExit, match="no citation marker"):
            self.set(tmp_path, index="1", support="supported")

    def test_a_row_that_does_not_exist_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="No row rg-1\\[99\\]"):
            self.set(tmp_path, index="99")

    def test_several_rows_take_one_label_at_once(self, tmp_path: Path) -> None:
        """Step 1 judges a sentence's kind; one shell command per row invites speed."""
        rows = audit_answers.load_rows(self.set(tmp_path, index="0,1", label="factual"))
        assert [r.label.value for r in rows if r.question_id == "rg-1"] == ["factual", "factual"]

    def test_a_range_is_accepted(self, tmp_path: Path) -> None:
        assert audit_answers.parse_indices("0-4") == [0, 1, 2, 3, 4]
        assert audit_answers.parse_indices("0,2,5") == [0, 2, 5]

    def test_support_is_never_batched(self, tmp_path: Path) -> None:
        """Reading one row's evidence is the judgement; a batch skips the reading."""
        with pytest.raises(SystemExit, match="pass a single index"):
            self.set(tmp_path, index="0,1", support="supported")

    def test_a_partly_valid_batch_writes_nothing(self, tmp_path: Path) -> None:
        prepared = self.worksheet(tmp_path)
        with pytest.raises(SystemExit, match="No row rg-1\\[99\\]"):
            self.set(tmp_path, prepared, index="0,99")
        rows = audit_answers.load_rows(prepared[0])
        assert all(r.label is audit_answers.Label.UNLABELLED for r in rows)


class TestShuffledCitationControl:
    """The control the second DoD clause is read against, and its blinding.

    Without it a support figure says only that the citations looked
    plausible to the person scoring them.
    """

    ANSWER: ClassVar[str] = (
        "A holds [rule:1.1]. B follows [rule:2.2]. C ends it [ruling:3]."
    )

    def prepared(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        answers = write(
            tmp_path / "answers.jsonl",
            [{"question_id": "rg-1", "text": self.ANSWER, "refused": False},
             {"question_id": "rg-2", "text": "Only one cited [rule:9.9].", "refused": False}],
        )
        sufficiency = init_sufficiency(tmp_path)
        label(sufficiency, {"rg-1": "sufficient", "rg-2": "partial"})
        audit_answers.sufficiency_freeze(argparse.Namespace(out=sufficiency))
        worksheet = tmp_path / "claims.jsonl"
        audit_answers.segment(
            argparse.Namespace(
                answers=answers, out=worksheet, sufficiency=sufficiency, force=False
            )
        )
        return worksheet, answers, sufficiency

    def labelled(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        worksheet, answers, sufficiency = self.prepared(tmp_path)
        for question_id, indices in (("rg-1", "0-2"), ("rg-2", "0")):
            audit_answers.claims_set(
                argparse.Namespace(
                    question_id=question_id,
                    index=indices,
                    label="factual",
                    support=None,
                    failure=None,
                    comment="",
                    worksheet=worksheet,
                    sufficiency=sufficiency,
                )
            )
        return worksheet, answers, sufficiency

    def build(self, tmp_path: Path, seed: int = 7) -> list[dict]:
        worksheet, answers, sufficiency = self.labelled(tmp_path)
        out = tmp_path / "control.jsonl"
        audit_answers.control_build(
            argparse.Namespace(
                worksheet=worksheet,
                answers=answers,
                sufficiency=sufficiency,
                out=out,
                seed=seed,
                force=False,
            )
        )
        return audit_answers.load_control(out)

    def test_a_derangement_never_returns_a_row_its_own_citation(self) -> None:
        """A fixed point would score a real pairing as if it were random."""
        rng = random.Random(3)
        for n in range(2, 9):
            order = audit_answers.derange(n, rng)
            assert sorted(order) == list(range(n))
            assert all(i != j for i, j in enumerate(order))

    def test_a_single_claim_cannot_be_deranged_against_itself(self) -> None:
        with pytest.raises(ValueError):
            audit_answers.derange(1, random.Random(0))

    def test_each_claim_appears_once_per_arm(self, tmp_path: Path) -> None:
        entries = self.build(tmp_path)
        assert sum(1 for e in entries if e["arm"] == "real") == 3
        assert sum(1 for e in entries if e["arm"] == "shuffled") == 3

    def test_a_shuffled_row_never_carries_its_own_citation(self, tmp_path: Path) -> None:
        entries = self.build(tmp_path)
        truth = {e["index"]: e["handles"] for e in entries if e["arm"] == "real"}
        assert all(
            e["handles"] != truth[e["index"]] for e in entries if e["arm"] == "shuffled"
        )

    def test_an_answer_with_one_cited_claim_is_excluded(self, tmp_path: Path) -> None:
        """Permuting across answers would cite another subgraph entirely."""
        entries = self.build(tmp_path)
        assert {e["question_id"] for e in entries} == {"rg-1"}

    def test_building_before_the_claims_are_labelled_is_refused(self, tmp_path: Path) -> None:
        worksheet, answers, sufficiency = self.prepared(tmp_path)
        with pytest.raises(SystemExit, match="still unlabelled"):
            audit_answers.control_build(
                argparse.Namespace(
                    worksheet=worksheet,
                    answers=answers,
                    sufficiency=sufficiency,
                    out=tmp_path / "control.jsonl",
                    seed=1,
                    force=False,
                )
            )

    def test_comparing_before_every_row_is_judged_is_refused(self, tmp_path: Path) -> None:
        """A visible gap would let the last judgements aim at the verdict."""
        self.build(tmp_path)
        with pytest.raises(SystemExit, match="unjudged"):
            audit_answers.control_compare(
                argparse.Namespace(control=tmp_path / "control.jsonl")
            )

    def test_the_same_seed_rebuilds_the_same_pairing(self, tmp_path: Path, tmp_path_factory) -> None:
        other = tmp_path_factory.mktemp("again")
        first = [(e["slot"], e["arm"], e["handles"]) for e in self.build(tmp_path, seed=11)]
        second = [(e["slot"], e["arm"], e["handles"]) for e in self.build(other, seed=11)]
        assert first == second
