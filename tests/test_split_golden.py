"""The Phase 4 development split: proportional, seeded, and frozen once."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from split_golden import allocate, composition, draw, load_questions

ROWS = (
    [{"id": f"im-{i}", "stratum": "interaction_multihop"} for i in range(30)]
    + [{"id": f"lg-{i}", "stratum": "legality_1hop"} for i in range(20)]
    + [{"id": f"df-{i}", "stratum": "definition_1hop"} for i in range(15)]
    + [{"id": f"nt-{i}", "stratum": "negative_temporal"} for i in range(9)]
    + [{"id": f"kw-{i}", "stratum": "keyword_rule_2hop"} for i in range(3)]
)


class TestAllocate:
    def test_quota_sums_to_n(self) -> None:
        assert sum(allocate({"a": 30, "b": 20, "c": 3}, 20).values()) == 20

    def test_bigger_strata_get_more(self) -> None:
        quota = allocate({"a": 30, "b": 20, "c": 3}, 20)
        assert quota["a"] > quota["b"] > quota["c"]

    def test_a_stratum_is_never_over_drawn(self) -> None:
        assert allocate({"a": 30, "c": 3}, 20)["c"] <= 3


class TestDraw:
    def test_the_seed_fixes_the_split(self) -> None:
        assert draw(ROWS, 20, 1) == draw(ROWS, 20, 1)

    def test_a_different_seed_gives_a_different_split(self) -> None:
        assert draw(ROWS, 20, 1) != draw(ROWS, 20, 2)

    def test_the_dev_subset_looks_like_the_whole_set(self) -> None:
        """Proportional, so template coverage on dev predicts coverage on eval."""
        dev = set(draw(ROWS, 20, 1))
        assert composition(ROWS, dev) == {
            "interaction_multihop": 8,
            "legality_1hop": 5,
            "definition_1hop": 4,
            "negative_temporal": 2,
            "keyword_rule_2hop": 1,
        }

    def test_dev_and_eval_partition_the_set(self) -> None:
        dev = set(draw(ROWS, 20, 1))
        every = {row["id"] for row in ROWS}
        assert len(dev) == 20
        assert dev < every and len(every - dev) == len(ROWS) - 20

    def test_every_drawn_id_is_real(self) -> None:
        every = {row["id"] for row in ROWS}
        assert all(qid in every for qid in draw(ROWS, 20, 7))


class TestLoadingAnAlternatePool:
    """E-007 splits its own audit pool with the same seeded draw.

    A second implementation of "draw a stratified subset" is a second
    thing that can be subtly wrong, so the pool reuses this one — which
    means `load_questions` has to admit rows that carry a stratum but no
    `gold_path`, since an audit-pool skeleton has no gold path.
    """

    def write(self, directory: Path, name: str, rows: list[dict]) -> None:
        (directory / name).write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
        )

    def test_a_pool_row_without_a_gold_path_is_loaded(self, tmp_path: Path) -> None:
        self.write(tmp_path, "pool.jsonl", [{"id": "rg-1", "stratum": "interaction_multihop"}])
        assert len(load_questions(tmp_path, ["pool.jsonl"])) == 1

    def test_the_golden_set_files_are_not_swept_in(self, tmp_path: Path) -> None:
        """Naming the file explicitly is what keeps the two pools apart."""
        self.write(tmp_path, "pool.jsonl", [{"id": "rg-1", "stratum": "definition_1hop"}])
        self.write(tmp_path, "ids_v0.jsonl", [{"id": "rg-9", "stratum": "definition_1hop"}])
        loaded = {row["id"] for row in load_questions(tmp_path, ["pool.jsonl"])}
        assert loaded == {"rg-1"}

    def test_a_row_with_neither_marker_is_ignored(self, tmp_path: Path) -> None:
        self.write(tmp_path, "pool.jsonl", [{"id": "junk"}])
        assert load_questions(tmp_path, ["pool.jsonl"]) == []
