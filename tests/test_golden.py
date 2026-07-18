"""Unit tests for the golden-set model, loader, and snapshot hashing."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from graphrag_mtg.evaluation.golden import (
    GoldenQuestion,
    Source,
    Stratum,
    VectorExpectation,
    content_sha256,
    dump_golden,
    load_golden,
    snapshot_hash,
)


def _authored(**overrides) -> GoldenQuestion:
    base = {
        "id": "hand-1",
        "source": Source.authored,
        "stratum": Stratum.interaction_multihop,
        "hops": 3,
        "question": "Humility and Opalescence are both on the battlefield. What are the P/T?",
        "answer": "Timestamp order in layer 7b decides; ...",
        "vector_should": VectorExpectation.fail,
        "vector_should_reason": "Answer is a layer-system path, not a stated passage.",
        "verified": True,
    }
    base.update(overrides)
    return GoldenQuestion(**base)


def test_authored_question_valid():
    q = _authored()
    assert q.stratum == Stratum.interaction_multihop
    assert q.verified is True


def test_rulesguru_row_must_not_carry_text():
    with pytest.raises(ValidationError):
        GoldenQuestion(
            id="rg-42",
            source=Source.rulesguru,
            stratum=Stratum.rulings_2hop,
            hops=2,
            question="not allowed to commit this",
            vector_should=VectorExpectation.lose,
        )


def test_authored_row_requires_question():
    with pytest.raises(ValidationError):
        GoldenQuestion(
            id="hand-2",
            source=Source.authored,
            stratum=Stratum.negative_temporal,
            hops=2,
            vector_should=VectorExpectation.fail,
            vector_should_reason="x",
            verified=True,
        )


def test_verified_path_question_requires_reason():
    with pytest.raises(ValidationError):
        _authored(vector_should_reason=None, verified=True)


def test_unverified_skeleton_may_omit_reason():
    # A skeleton (verified=False) on a path stratum is allowed to be incomplete.
    q = GoldenQuestion(
        id="rg-7",
        source=Source.rulesguru,
        stratum=Stratum.interaction_multihop,
        hops=3,
        vector_should=VectorExpectation.fail,
        verified=False,
    )
    assert q.verified is False


def test_content_sha256_matches_hashlib():
    assert content_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_snapshot_hash_is_order_independent():
    a = GoldenQuestion(
        id="rg-1", source=Source.rulesguru, stratum=Stratum.rulings_2hop, hops=2,
        vector_should=VectorExpectation.lose, snapshot_sha256="aaa",
    )
    b = GoldenQuestion(
        id="rg-2", source=Source.rulesguru, stratum=Stratum.rulings_2hop, hops=2,
        vector_should=VectorExpectation.lose, snapshot_sha256="bbb",
    )
    assert snapshot_hash([a, b]) == snapshot_hash([b, a])


def test_snapshot_hash_changes_on_content_drift():
    a = GoldenQuestion(
        id="rg-1", source=Source.rulesguru, stratum=Stratum.rulings_2hop, hops=2,
        vector_should=VectorExpectation.lose, snapshot_sha256="aaa",
    )
    drifted = a.model_copy(update={"snapshot_sha256": "zzz"})
    assert snapshot_hash([a]) != snapshot_hash([drifted])


def test_load_dump_round_trip(tmp_path):
    path = tmp_path / "golden.jsonl"
    questions = [
        _authored(),
        GoldenQuestion(
            id="rg-99", source=Source.rulesguru, stratum=Stratum.rulings_2hop, hops=2,
            vector_should=VectorExpectation.lose, rulesguru_url="https://rulesguru.org/?id=99",
        ),
    ]
    dump_golden(questions, path)
    loaded = load_golden(path)
    assert [q.id for q in loaded] == ["hand-1", "rg-99"]
    assert loaded[0].vector_should == VectorExpectation.fail


def test_load_ignores_blank_and_comment_lines(tmp_path):
    path = tmp_path / "golden.jsonl"
    row = GoldenQuestion(
        id="rg-1", source=Source.rulesguru, stratum=Stratum.rulings_2hop, hops=2,
        vector_should=VectorExpectation.lose,
    ).model_dump_json()
    path.write_text(f"// header comment\n\n{row}\n", encoding="utf-8")
    assert len(load_golden(path)) == 1
