"""Unit tests for the deterministic golden-question generators."""

from __future__ import annotations

from graphrag_mtg.evaluation.generators import (
    build_definition_question,
    build_legality_question,
)
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


# ─── definition_1hop ─────────────────────────────────────────────────────────


def _definition(keyword="First strike", rule="702.7", answer="Deals damage in an earlier step."):
    return build_definition_question(keyword, rule, answer)


def test_definition_question_predicts_a_tie_with_a_reason():
    # This stratum exists to be losable: if nothing predicts a draw, no run can
    # falsify the hypothesis. The reason is recorded a priori.
    q = _definition()
    assert q.stratum == Stratum.definition_1hop
    assert q.vector_should == VectorExpectation.tie
    assert q.vector_should_reason
    assert q.hops == 1
    assert q.verified is True


def test_definition_question_is_authored_content():
    # The answer prose is ours, not CR text, so the row is committable in full.
    q = _definition()
    assert q.source == Source.authored
    assert q.question == "What does first strike do?"
    assert q.answer == "Deals damage in an earlier step."


def test_definition_gold_path_uses_the_normalized_keyword_key():
    # Must match how the loader merges Keyword nodes, or the path never resolves.
    q = _definition(keyword="First Strike")
    assert "name:'first strike'" in q.gold_path
    assert "number:'702.7'" in q.gold_path
    assert q.gold_cr_rules == ["702.7"]
    # The display spelling is what a human reads.
    assert q.gold_entities == ["First Strike"]


def test_definition_ids_are_stable_across_spellings():
    assert _definition(keyword="First strike").id == _definition(keyword="First Strike").id
    assert _definition(keyword="Flying").id == "hand-def-flying"


def test_definition_snapshot_changes_with_the_answer():
    assert _definition(answer="a").snapshot_sha256 != _definition(answer="b").snapshot_sha256
