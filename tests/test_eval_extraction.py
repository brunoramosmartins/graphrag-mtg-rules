"""Gold/prediction loading for the E-003 scorer, over temp files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_extraction import (
    load_gold,
    load_predicted_citations,
    load_predicted_mentions,
)

GOLD_ROWS = [
    {
        "ruling_id": "r1",
        "split": "dev",
        "stratum": "homonym",
        "oracle_id": "host",
        "mentions": [
            {"surface": "Clone", "start": 3, "end": 8, "target_oracle_id": "clone-1"},
            # A negative: looks like a card name, is not one.
            {"surface": "fear", "start": 40, "end": 44, "target_oracle_id": None},
        ],
        "cited_rules": [{"rule_number": "706.2", "start": 0, "end": 5, "quote": "If Cl"}],
        "verified": True,
    },
    {
        "ruling_id": "r2",
        "split": "annotation",
        "stratum": "plain",
        "oracle_id": "host2",
        "mentions": [],
        "cited_rules": [],
        "verified": True,
    },
]


@pytest.fixture
def gold_file(tmp_path: Path) -> Path:
    path = tmp_path / "gold.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in GOLD_ROWS) + "\n", encoding="utf-8"
    )
    return path


class TestLoadGold:
    def test_split_is_honoured(self, gold_file: Path) -> None:
        _, _, strata = load_gold(gold_file, "dev")
        assert set(strata) == {"r1"}

    def test_null_targets_are_negatives_not_gold(self, gold_file: Path) -> None:
        mentions, _, _ = load_gold(gold_file, "dev")
        assert mentions["r1"] == {("r1", 3, "clone-1")}

    def test_citations_key_on_rule_number(self, gold_file: Path) -> None:
        _, citations, _ = load_gold(gold_file, "dev")
        assert citations["r1"] == {("r1", "706.2")}

    def test_empty_rows_still_present_as_documents(self, gold_file: Path) -> None:
        mentions, citations, strata = load_gold(gold_file, "annotation")
        assert strata == {"r2": "plain"}
        assert mentions["r2"] == set() and citations["r2"] == set()


class TestLoadPredictions:
    def test_unresolved_mentions_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "mentions.jsonl"
        rows = [
            {
                "ruling_id": "r1",
                "surface": "Clone",
                "oracle_id": "clone-1",
                "span": {"start": 3, "end": 8, "text": "Clone"},
                "method": "exact",
                "confidence": 1.0,
            },
            {
                "ruling_id": "r1",
                "surface": "Opt",
                "oracle_id": None,
                "span": {"start": 20, "end": 23, "text": "Opt"},
                "method": "surface",
                "confidence": 0.0,
                "candidate_oracle_ids": ["opt-1"],
            },
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        predicted = load_predicted_mentions(path, {"r1"})
        assert predicted == {"r1": {("r1", 3, "clone-1")}}

    def test_documents_outside_the_split_are_dropped(self, tmp_path: Path) -> None:
        path = tmp_path / "citations.jsonl"
        rows = [
            {
                "ruling_id": rid,
                "rule_number": "706.2",
                "span": {"start": 0, "end": 5, "text": "If Cl"},
                "rationale": "x",
                "method": "llm",
                "confidence": 0.9,
            }
            for rid in ("r1", "other")
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        assert load_predicted_citations(path, {"r1"}) == {"r1": {("r1", "706.2")}}

    def test_missing_file_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_predicted_mentions(tmp_path / "nope.jsonl", {"r1"}) == {}
