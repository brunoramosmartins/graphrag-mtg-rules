"""Judge against human: what the comparison refuses to do.

E-011 withdrew the hand-picked pass marks and replaced them with one rule —
the judge passes a gated label if the lower bound of its agreement interval
reaches the lower bound of that label's human ceiling. Every guard here
protects a way that comparison could be made to look better than it is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_judge

HASH = "a" * 64


def worksheet(tmp_path: Path, labels: dict[str, str], **kw) -> Path:
    path = tmp_path / "m1.json"
    payload = {
        "batch": "b2",
        "arm": "C",
        "frozen": True,
        "rubric_version": "p6-c1",
        "rubric_hash": HASH,
        "labels": {qid: {"label": label} for qid, label in labels.items()},
        **kw,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def verdicts(tmp_path: Path, labels: dict[str, str], *, rubric_hash: str = HASH) -> Path:
    path = tmp_path / "verdicts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps({"question_id": qid, "label": label, "rubric_hash": rubric_hash})
            for qid, label in labels.items()
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def namespace(worksheet_path: Path, verdicts_path: Path, **kw) -> argparse.Namespace:
    """One batch, one verdicts file — the common case, in list shape."""
    return argparse.Namespace(
        worksheet=[worksheet_path],
        verdicts=[[verdicts_path]],
        ceiling_low=kw.pop("ceiling_low", None),
        allow_unfrozen=kw.pop("allow_unfrozen", False),
        **kw,
    )


class TestBlindnessGuards:
    def test_refuses_an_unfrozen_human_pass(self, tmp_path: Path) -> None:
        # A human pass finished with the judge's verdicts on screen is not
        # a blind pass, and freezing is what makes the ordering checkable
        # after the fact.
        human = worksheet(tmp_path, {"q1": "correct"}, frozen=False)
        with pytest.raises(SystemExit, match="not frozen"):
            audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"})))

    def test_the_escape_hatch_is_named_for_what_it_is(self, tmp_path: Path, capsys) -> None:
        human = worksheet(tmp_path, {"q1": "correct"}, frozen=False)
        args = namespace(human, verdicts(tmp_path, {"q1": "correct"}), allow_unfrozen=True)
        assert audit_judge.score(args) == 0

    def test_refuses_two_different_rubrics(self, tmp_path: Path) -> None:
        # Their agreement would not describe one instrument.
        human = worksheet(tmp_path, {"q1": "correct"})
        judged = verdicts(tmp_path, {"q1": "correct"}, rubric_hash="b" * 64)
        with pytest.raises(SystemExit, match="different rubrics"):
            audit_judge.score(namespace(human, judged))

    def test_refuses_an_unlabelled_row(self, tmp_path: Path) -> None:
        human = worksheet(tmp_path, {"q1": "correct", "q2": ""})
        with pytest.raises(SystemExit, match="q2 is unlabelled"):
            audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"})))


class TestScoring:
    def test_reports_agreement_with_an_interval(self, tmp_path: Path, capsys) -> None:
        human = worksheet(tmp_path, {"q1": "correct", "q2": "partial", "q3": "incorrect"})
        judged = verdicts(tmp_path, {"q1": "correct", "q2": "incorrect", "q3": "incorrect"})
        audit_judge.score(namespace(human, judged))
        printed = capsys.readouterr().out
        assert "exact agreement 2/3" in printed
        assert "n_clusters 3" in printed

    def test_breaks_agreement_down_by_the_humans_label(self, tmp_path: Path, capsys) -> None:
        # The E-011 amendment gates per label, not in aggregate: a judge
        # that is perfect on `incorrect` and hopeless on `partial` passes
        # an aggregate and should not.
        human = worksheet(tmp_path, {"q1": "correct", "q2": "partial", "q3": "partial"})
        judged = verdicts(tmp_path, {"q1": "correct", "q2": "correct", "q3": "correct"})
        audit_judge.score(namespace(human, judged))
        printed = capsys.readouterr().out
        assert "correct        1/1" in printed
        assert "partial        0/2" in printed

    def test_shows_where_the_disagreements_sit(self, tmp_path: Path, capsys) -> None:
        human = worksheet(tmp_path, {"q1": "partial"})
        judged = verdicts(tmp_path, {"q1": "incorrect"})
        audit_judge.score(namespace(human, judged))
        assert "partial    -> incorrect" in capsys.readouterr().out

    def test_a_thin_sample_gates_nothing(self, tmp_path: Path, capsys) -> None:
        # 19 rows can reach 0.895 and mean very little. The floor of 30 is
        # what stops that becoming a validated correctness figure.
        human = worksheet(tmp_path, {f"q{i}": "correct" for i in range(5)})
        judged = verdicts(tmp_path, {f"q{i}": "correct" for i in range(5)})
        audit_judge.score(namespace(human, judged))
        printed = " ".join(capsys.readouterr().out.split())
        assert "below the registered floor" in printed
        # The status *and* its consequence. A message that says a label is
        # descriptive without saying what may not be published from it
        # leaves the reader with a number and no instruction.
        assert "gate nothing" in printed
        assert "may be published as validated" in printed

    def test_a_labelled_answer_with_no_verdict_is_named(self, tmp_path: Path, capsys) -> None:
        # Silently dropping it would shrink the denominator without saying
        # so, which is the shape of every flattering evaluation bug.
        human = worksheet(tmp_path, {"q1": "correct", "q2": "partial"})
        audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"})))
        printed = capsys.readouterr().out
        assert "1 labelled answer(s) have no verdict" in printed
        assert "exact agreement 1/1" in printed


class TestPooling:
    """Batches are pooled because the ceiling they are read against is.

    Comparing a per-batch judge figure to a pooled human ceiling would put
    two different samples on the two sides of one inequality.
    """

    def test_a_batch_can_span_two_verdict_files(self, tmp_path: Path, capsys) -> None:
        # E-011a's batch 1 is E-007's audit side and dev side, generated
        # separately. Scoring it on one file would silently shrink its own
        # denominator.
        human = worksheet(tmp_path, {"q1": "correct", "q2": "partial"})
        one = tmp_path / "v1.jsonl"
        one.write_text(json.dumps({"question_id": "q1", "label": "correct",
                                   "rubric_hash": HASH}) + "\n", encoding="utf-8")
        two = tmp_path / "v2.jsonl"
        two.write_text(json.dumps({"question_id": "q2", "label": "partial",
                                   "rubric_hash": HASH}) + "\n", encoding="utf-8")
        args = argparse.Namespace(
            worksheet=[human], verdicts=[[one, two]], ceiling_low=None, allow_unfrozen=False
        )
        audit_judge.score(args)
        assert "exact agreement 2/2" in capsys.readouterr().out

    def test_pools_across_batches(self, tmp_path: Path, capsys) -> None:
        first = worksheet(tmp_path, {"q1": "correct"})
        second = tmp_path / "m1b.json"
        second.write_text(json.dumps({
            "batch": "b2", "frozen": True, "rubric_version": "p6-c1", "rubric_hash": HASH,
            "labels": {"q2": {"label": "partial"}},
        }), encoding="utf-8")
        args = argparse.Namespace(
            worksheet=[first, second],
            verdicts=[[verdicts(tmp_path, {"q1": "correct"})],
                      [verdicts(tmp_path / "b", {"q2": "incorrect"})]],
            ceiling_low=None,
            allow_unfrozen=False,
        )
        audit_judge.score(args)
        assert "pooled over 2 batch(es)" in capsys.readouterr().out


class TestGate:
    def test_without_a_ceiling_nothing_is_gated(self, tmp_path: Path, capsys) -> None:
        # E-011 permits exactly one mapping from a ceiling to a threshold,
        # so a run with no ceiling must decline rather than invent one.
        human = worksheet(tmp_path, {"q1": "correct"})
        audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"})))
        assert "No ceiling supplied" in capsys.readouterr().out

    def test_a_label_below_the_floor_is_not_gated(self, tmp_path: Path, capsys) -> None:
        # 55 answers gave 18 / 14 / 23 and gated nothing. The floor is per
        # label, and that is a fact about the audit's size.
        human = worksheet(tmp_path, {"q1": "correct"})
        audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"}),
                                    ceiling_low=0.72))
        # Whitespace-normalised: the message wraps across two print calls,
        # and an assertion that breaks when a line is rewrapped is testing
        # the formatter rather than the behaviour.
        printed = " ".join(capsys.readouterr().out.split())
        assert "not gated, descriptive" in printed
        assert "neither passed nor failed" in printed


class TestReferenceBand:
    def test_the_ceilings_are_labelled_with_their_sample(self, tmp_path: Path, capsys) -> None:
        # E-011 point 8 corrected a claim that a judge cannot exceed a
        # human's self-agreement: judge-vs-human is inter-rater and these
        # are intra-rater. They are a band to read against, not a bound.
        human = worksheet(tmp_path, {"q1": "correct"})
        audit_judge.score(namespace(human, verdicts(tmp_path, {"q1": "correct"})))
        printed = capsys.readouterr().out
        assert "not bounds on this" in printed
        assert "intra-rater" in printed

    def test_no_ceiling_is_presented_as_a_pass_mark(self) -> None:
        # The hand-picked 0.90 / 0.85 were withdrawn. Nothing here may
        # reintroduce a threshold by putting one in a constant.
        assert all(isinstance(v, tuple) and len(v) == 2 for v in audit_judge.CEILINGS.values())
        assert 0.90 not in {v[0] for v in audit_judge.CEILINGS.values()}
