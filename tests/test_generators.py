"""Unit tests for the deterministic legality-question generator."""

from __future__ import annotations

from graphrag_mtg.evaluation.generators import build_legality_question
from graphrag_mtg.evaluation.golden import Source, Stratum, VectorExpectation


def _card(**overrides) -> dict:
    base = {
        "name": "Lightning Bolt",
        "oracle_id": "abc-123",
        "type_line": "Instant",
        "legalities": {"modern": "legal", "standard": "not_legal", "vintage": "restricted"},
    }
    base.update(overrides)
    return base


def test_legal_status_builds_yes_answer():
    q = build_legality_question(_card(), "modern")
    assert q is not None
    assert q.source == Source.scryfall
    assert q.stratum == Stratum.legality_1hop
    assert q.hops == 1
    assert q.vector_should == VectorExpectation.lose
    assert q.verified is True
    assert q.question == "Is Lightning Bolt legal in Modern?"
    assert q.answer.startswith("Yes")
    assert q.gold_entities == ["Lightning Bolt"]
    assert q.id == "scry-leg-abc-123-modern"


def test_not_legal_and_restricted_answers():
    assert build_legality_question(_card(), "standard").answer.startswith("No")
    assert "restricted" in build_legality_question(_card(), "vintage").answer.lower()


def test_banned_status_answer():
    card = _card(legalities={"modern": "banned"})
    assert build_legality_question(card, "modern").answer.startswith("No")


def test_missing_format_returns_none():
    assert build_legality_question(_card(), "pauper") is None


def test_missing_oracle_id_returns_none():
    assert build_legality_question(_card(oracle_id=None), "modern") is None


def test_unknown_status_returns_none():
    card = _card(legalities={"modern": "future"})
    assert build_legality_question(card, "modern") is None


def test_snapshot_hash_is_deterministic():
    a = build_legality_question(_card(), "modern")
    b = build_legality_question(_card(), "modern")
    assert a.snapshot_sha256 == b.snapshot_sha256
