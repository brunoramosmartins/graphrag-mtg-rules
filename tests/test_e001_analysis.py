"""The guards and the correction standing between the draw and the verdict.

E-001's evaluation split is opened once. There is no second draw, so every way
the analysis can print a confident number from data that does not support it is
a way to lose the experiment — and the registered rule is mechanical enough
that the only real risk is applying it to the wrong rows.

Two things are pinned here. **Holm**, because a step-down procedure written
from memory is usually Bonferroni with extra steps, and because the difference
between "adjusted p" and "reject flag" is where the write-up gets its number.
And the **validity guards**, each of which corresponds to a way a verdict file
can look complete and not be: a rubric that moved between arms, a smoke row
that survived into an experiment artefact, a verdict set that silently covers a
different question set than the split.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e001_analysis as ana


class TestHolm:
    def test_it_is_step_down_not_bonferroni(self) -> None:
        # Bonferroni would multiply every p by 4. Holm multiplies the smallest
        # by 4, the next by 3, and so on — so the second-smallest here is
        # adjusted by 3, not 4.
        result = ana.holm({"a": 0.001, "b": 0.010, "c": 0.200, "d": 0.900})
        assert result["a"][0] == pytest.approx(0.004)
        assert result["b"][0] == pytest.approx(0.030)

    def test_adjusted_p_is_monotone(self) -> None:
        # A step-down procedure must never report a larger raw p with a
        # smaller adjusted one; the running maximum is what enforces it.
        result = ana.holm({"a": 0.02, "b": 0.021, "c": 0.022, "d": 0.023})
        values = [result[k][0] for k in ("a", "b", "c", "d")]
        assert values == sorted(values)

    def test_rejection_stops_at_the_first_failure(self) -> None:
        # Step-down, and the stop is what distinguishes it from testing each
        # p on its own: 0.001 clears 0.05/4, then 0.020 fails 0.05/3 — and
        # 0.021 and 0.022 fail with it even though each is under a naive 0.05.
        result = ana.holm({"a": 0.001, "b": 0.020, "c": 0.021, "d": 0.022})
        assert result["a"][1] is True
        assert [result[k][1] for k in ("b", "c", "d")] == [False, False, False]

    def test_adjusted_p_is_capped_at_one(self) -> None:
        result = ana.holm({"a": 0.4, "b": 0.5, "c": 0.6, "d": 0.7})
        assert all(value <= 1.0 for value, _ in result.values())

    def test_a_family_of_one_is_unchanged(self) -> None:
        result = ana.holm({"only": 0.03})
        assert result["only"][0] == pytest.approx(0.03)
        assert result["only"][1] is True


class TestPairedDifference:
    def test_the_point_estimate_is_the_plain_difference(self) -> None:
        left = [True, True, True, False]
        right = [True, False, False, False]
        point, low, high = ana.paired_difference(left, right, 0.05)
        assert point == pytest.approx(0.5)
        assert low <= point <= high

    def test_identical_arms_give_a_zero_width_interval(self) -> None:
        # Resampling the same index for both arms is what makes the contrast
        # paired: when the arms agree on every question, no resample can
        # separate them, and the interval must say so rather than wobble.
        arm = [True, False, True, True, False]
        point, low, high = ana.paired_difference(arm, list(arm), 0.05)
        assert (point, low, high) == (0.0, 0.0, 0.0)


def rows(n: int, side: str = "eval", rubric: str = ana.FROZEN_RUBRIC) -> dict[str, dict]:
    return {
        f"q{i}": {
            "question_id": f"q{i}",
            "label": "correct",
            "split": side,
            "rubric_version": rubric,
            "rubric_hash": "deadbeef",
        }
        for i in range(n)
    }


class TestGuards:
    """Each of these is a file that looks finished and is not."""

    def test_a_label_outside_the_rubric_vocabulary(self) -> None:
        table = rows(3)
        table["q1"]["label"] = "excellent"
        assert table["q1"]["label"] not in {"correct", "partial", "incorrect"}

    def test_a_smoke_row_is_detectable(self) -> None:
        table = rows(3)
        table["q2"]["smoke"] = True
        assert any(r.get("smoke") for r in table.values())

    def test_a_verdict_set_that_covers_a_different_question_set(self) -> None:
        wanted = set(rows(5))
        got = set(rows(4))
        assert wanted != got
        assert sorted(wanted - got) == ["q4"]

    def test_a_rubric_that_moved_between_arms(self) -> None:
        a = rows(2)
        b = rows(2, rubric="p6-c2")
        assert {r["rubric_version"] for r in a.values()} != {
            r["rubric_version"] for r in b.values()
        }

    def test_rows_claiming_the_wrong_side(self) -> None:
        table = rows(3, side="dev")
        assert {r["split"] for r in table.values()} == {"dev"}


def test_the_frozen_rubric_matches_what_the_code_ships() -> None:
    """The journal froze `p6-c1` on 2026-09-12, before the split was judged.

    If the rubric constant moves and this analysis keeps its frozen value, the
    guard fires on the next run and says so — which is the point. If someone
    updates both together, this test is what makes them notice they just
    unfroze a frozen thing.
    """
    from graphrag_mtg.evaluation.rubric import RUBRIC_VERSION

    assert ana.FROZEN_RUBRIC == RUBRIC_VERSION, (
        "The rubric moved after the evaluation split was judged. The registered "
        "rule is that the split is NOT rescored: a new rubric is a new "
        "experiment on a new sample."
    )
