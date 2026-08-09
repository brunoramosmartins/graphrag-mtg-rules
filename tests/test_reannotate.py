"""Blind subsampling for the intra-annotator ceiling (E-003)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from reannotate import allocate, as_items, blind_row, cited, draw_sample


def row(rid: str, stratum: str, *, split: str = "annotation", reviewed: bool = True) -> dict:
    return {
        "ruling_id": rid,
        "split": split,
        "stratum": stratum,
        "text": f"text of {rid}",
        "mentions": [{"surface": "Opt", "start": 0, "end": 3, "target_oracle_id": "opt-1"}],
        "cited_rules": [{"rule_number": "603.7"}],
        "citations_reviewed": reviewed,
        "notes": f"note on {rid}",
        "annotator": "Bruno",
    }


ROWS = (
    [row(f"h{i}", "homonym") for i in range(60)]
    + [row(f"m{i}", "multiword") for i in range(50)]
    + [row(f"p{i}", "plain") for i in range(40)]
    + [row(f"e{i}", "explicit") for i in range(5)]
)


class TestAllocate:
    def test_quota_sums_to_n(self) -> None:
        quota = allocate({"a": 60, "b": 50, "c": 40, "d": 5}, 20)
        assert sum(quota.values()) == 20

    def test_shares_follow_the_population(self) -> None:
        quota = allocate({"a": 60, "b": 50, "c": 40, "d": 5}, 20)
        assert quota["a"] > quota["b"] > quota["c"] > quota["d"]

    def test_never_asks_for_more_than_a_stratum_has(self) -> None:
        quota = allocate({"a": 100, "d": 1}, 20)
        assert quota["d"] <= 1

    def test_asking_for_everything_returns_everything(self) -> None:
        counts = {"a": 3, "b": 2}
        assert allocate(counts, 99) == counts

    def test_empty_population(self) -> None:
        assert allocate({}, 20) == {}


class TestDrawSample:
    def test_same_seed_same_sample(self) -> None:
        assert draw_sample(ROWS, 20, 1, "annotation") == draw_sample(ROWS, 20, 1, "annotation")

    def test_different_seed_different_sample(self) -> None:
        assert draw_sample(ROWS, 20, 1, "annotation") != draw_sample(ROWS, 20, 2, "annotation")

    def test_sample_is_stratified_like_the_split(self) -> None:
        by_id = {r["ruling_id"]: r for r in ROWS}
        drawn = draw_sample(ROWS, 20, 1, "annotation")
        counts: dict[str, int] = {}
        for rid in drawn:
            counts[by_id[rid]["stratum"]] = counts.get(by_id[rid]["stratum"], 0) + 1
        assert counts == {"homonym": 8, "multiword": 6, "plain": 5, "explicit": 1}

    def test_unreviewed_rows_are_not_eligible(self) -> None:
        """A row with no pass 1 has nothing to disagree with."""
        rows = [row("a", "plain"), row("b", "plain", reviewed=False)]
        assert draw_sample(rows, 2, 1, "annotation") == ["a"]

    def test_other_splits_are_excluded(self) -> None:
        rows = [row("a", "plain"), row("d", "plain", split="dev")]
        assert draw_sample(rows, 2, 1, "annotation") == ["a"]


class TestBlindRow:
    def test_the_citation_decision_is_removed(self) -> None:
        blinded = blind_row(row("a", "plain"))
        assert blinded["cited_rules"] == []
        assert blinded["citations_reviewed"] is False
        assert blinded["notes"] == ""

    def test_the_text_and_mentions_survive(self) -> None:
        """Pass 2 must read the same ruling; only the answer is hidden."""
        original = row("a", "plain")
        blinded = blind_row(original)
        assert blinded["text"] == original["text"]
        assert blinded["mentions"] == original["mentions"]

    def test_the_original_row_is_not_mutated(self) -> None:
        original = row("a", "plain")
        blind_row(original)
        assert original["cited_rules"] == [{"rule_number": "603.7"}]


class TestItems:
    def test_legacy_rule_key_is_read(self) -> None:
        assert cited({"cited_rules": [{"rule": "104.3a"}]}) == {"104.3a"}

    def test_items_are_keyed_like_the_scorer(self) -> None:
        items = as_items({"r1": {"cited_rules": [{"rule_number": "603.7"}]}})
        assert items == {"r1": frozenset({("r1", "603.7")})}

    def test_a_ruling_citing_nothing_keeps_an_empty_entry(self) -> None:
        """Reviewed-and-empty is a decision, not an absent document."""
        assert as_items({"r1": {"cited_rules": []}}) == {"r1": frozenset()}
