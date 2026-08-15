"""E-007's runner: where its outputs land, and what it refuses to destroy.

Both tests here exist because the audit run overwrote the development
run. `runs/` is gitignored, so those ten answers were the only copy of the
text 118 claim labels described, and a single default output path was
enough to lose them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e007


def namespace(**kwargs) -> argparse.Namespace:
    defaults = {"out": None, "side": "audit", "force": False, "dry_run": False}
    return argparse.Namespace(**{**defaults, **kwargs})


class TestAnswersPath:
    def test_each_side_writes_its_own_file(self) -> None:
        assert run_e007.answers_path(namespace(side="dev")).name == "e007_answers_dev.jsonl"
        assert run_e007.answers_path(namespace(side="audit")).name == "e007_answers_audit.jsonl"

    def test_the_two_sides_never_share_a_path(self) -> None:
        """The defect itself: one default, and the second run wins."""
        assert run_e007.answers_path(namespace(side="dev")) != run_e007.answers_path(
            namespace(side="audit")
        )

    def test_an_explicit_out_still_wins(self, tmp_path: Path) -> None:
        chosen = tmp_path / "elsewhere.jsonl"
        assert run_e007.answers_path(namespace(out=chosen)) == chosen


class TestGenerationRefusesToClobber:
    def frozen(self, tmp_path: Path) -> Path:
        path = tmp_path / "sufficiency.json"
        path.write_text('{"frozen": true, "labels": {}}', encoding="utf-8")
        return path

    def test_an_existing_answers_file_stops_the_run(self, tmp_path: Path) -> None:
        out = tmp_path / "answers.jsonl"
        out.write_text("{}\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="already exists"):
            run_e007.run_generation(
                namespace(out=out, sufficiency=self.frozen(tmp_path), retrieval=tmp_path / "r.jsonl")
            )

    def test_the_refusal_precedes_reading_the_retrieval_dump(self, tmp_path: Path) -> None:
        """It must fire before any work, or a costly run dies after the damage."""
        out = tmp_path / "answers.jsonl"
        out.write_text("{}\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="already exists"):
            run_e007.run_generation(
                namespace(
                    out=out,
                    sufficiency=self.frozen(tmp_path),
                    retrieval=tmp_path / "does-not-exist.jsonl",
                )
            )
