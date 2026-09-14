"""The floor decides a phase, so it is the number that most needs checking.

E-026 concluded that none of nine measured correctness effects was detectable,
and Phase 10 was rebuilt on that. A floor computed slightly wrong in the
convenient direction would justify abandoning a comparison that was in fact
reachable. These tests pin the arithmetic against values derived independently
of the implementation, and pin the contrast list against being quietly trimmed.
"""

from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import detectability as det


class TestThePowerFunctionIsTheStandardOne:
    def test_zero_effect_has_power_equal_to_alpha(self) -> None:
        # A test with no effect rejects at exactly its own significance level.
        assert det.power(0.0, 0.1) == pytest.approx(0.05, abs=1e-3)

    def test_the_classic_2_8_sigma_rule(self) -> None:
        # 80% power two-sided at alpha=.05 is the textbook 2.80 standard errors.
        assert det.power(2.80 * 0.1, 0.1) == pytest.approx(0.80, abs=0.01)

    def test_power_rises_with_the_effect(self) -> None:
        assert det.power(0.1, 0.1) < det.power(0.3, 0.1) < det.power(0.9, 0.1)

    def test_power_rises_as_the_standard_error_falls(self) -> None:
        assert det.power(0.2, 0.2) < det.power(0.2, 0.1) < det.power(0.2, 0.05)


class TestTheStandardErrors:
    def test_the_simple_se_is_the_paired_formula(self) -> None:
        assert det.se_simple(57, 0.298) == pytest.approx(sqrt(0.298 / 57))

    def test_an_interaction_costs_twice_the_variance(self) -> None:
        # Two groups, so twice the variance and therefore sqrt(2) the SE. This
        # is the whole reason an interaction needs about four times the n, and
        # it is the line that withdrew E-019.
        simple = det.se_simple(50, 0.3)
        interaction = det.se_interaction(50, 0.3)
        assert interaction == pytest.approx(simple * sqrt(2))

    def test_four_times_the_n_buys_back_the_interaction_penalty(self) -> None:
        assert det.se_interaction(200, 0.3) == pytest.approx(det.se_simple(100, 0.3))


class TestTheFloor:
    def test_the_floor_is_where_power_reaches_the_target(self) -> None:
        floor = det.mde(57, det.POOLED_DISCORDANCE)
        assert det.power(floor, det.se_simple(57, det.POOLED_DISCORDANCE)) == pytest.approx(
            det.TARGET_POWER, abs=0.01
        )

    def test_just_below_the_floor_is_underpowered(self) -> None:
        floor = det.mde(57, det.POOLED_DISCORDANCE)
        se = det.se_simple(57, det.POOLED_DISCORDANCE)
        assert det.power(floor - 0.02, se) < det.TARGET_POWER

    def test_the_floor_falls_as_the_sample_grows(self) -> None:
        floors = [det.mde(n, det.POOLED_DISCORDANCE) for n in (20, 57, 120, 400)]
        assert floors == sorted(floors, reverse=True)

    def test_the_interaction_floor_is_always_worse(self) -> None:
        for n in (20, 57, 200):
            assert det.mde(n, det.POOLED_DISCORDANCE, interaction=True) > det.mde(
                n, det.POOLED_DISCORDANCE
            )

    def test_the_published_floor_at_the_evaluation_split(self) -> None:
        # 0.203 is the number quoted in E-026, docs/evaluation.md and the
        # README. If this moves, those move with it.
        assert det.mde(57, det.POOLED_DISCORDANCE) == pytest.approx(0.203, abs=0.002)


class TestNForIsTheInverseOfTheFloor:
    def test_the_n_it_returns_actually_reaches_the_target(self) -> None:
        n = det.n_for(0.30, det.POOLED_DISCORDANCE)
        assert n is not None
        assert det.power(0.30, det.se_simple(n, det.POOLED_DISCORDANCE)) >= det.TARGET_POWER

    def test_one_question_fewer_does_not(self) -> None:
        n = det.n_for(0.30, det.POOLED_DISCORDANCE)
        assert n is not None
        assert det.power(0.30, det.se_simple(n - 1, det.POOLED_DISCORDANCE)) < det.TARGET_POWER

    def test_an_effect_of_zero_needs_no_reportable_n(self) -> None:
        assert det.n_for(0.0, det.POOLED_DISCORDANCE) is None


class TestTheContrastListIsNotASelection:
    """The count of detectable effects is only meaningful over all of them.

    A tuple that quietly lost the largest contrast would report a floor nobody
    cleared, which is exactly the defect this instrument exists to find in
    other people's numbers.
    """

    def test_every_contrast_carries_counts_and_a_sample_size(self) -> None:
        for label, b_wins, a_wins, n in det.MEASURED:
            assert n > 0, label
            assert b_wins >= 0 and a_wins >= 0, label
            assert b_wins + a_wins <= n, label

    def test_the_discordant_counts_reproduce_the_published_effects(self) -> None:
        by_label = {row[0]: row for row in det.MEASURED}
        _, b, a, n = by_label["E-001 interaction_multihop"]
        assert (b - a) / n == pytest.approx(-0.136, abs=0.001)
        _, b, a, n = by_label["E-001 definition_1hop"]
        assert (b - a) / n == pytest.approx(0.182, abs=0.001)

    def test_the_per_stratum_contrasts_sum_to_the_overall_one(self) -> None:
        # E-001's five strata are a partition of its 57 questions. If they stop
        # summing, a contrast was added, dropped, or double-counted.
        strata = [row for row in det.MEASURED if row[0].startswith("E-001 ") and "overall" not in row[0]]
        assert sum(row[3] for row in strata) == 57
        overall = next(row for row in det.MEASURED if "overall" in row[0])
        assert sum(row[1] for row in strata) == overall[1]
        assert sum(row[2] for row in strata) == overall[2]

    def test_none_of_the_measured_effects_clears_its_own_floor(self) -> None:
        # The finding itself, pinned. If a future contrast clears its floor
        # this fails, and that failure is the signal to rewrite E-026 rather
        # than to relax the test.
        cleared = [
            label
            for label, b, a, n in det.MEASURED
            if abs((b - a) / n) >= det.mde(n, det.POOLED_DISCORDANCE)
        ]
        assert cleared == []


class TestThePooledDiscordanceIsWhatWasMeasured:
    def test_it_is_seventeen_of_fifty_seven(self) -> None:
        assert abs(det.POOLED_DISCORDANCE - 17 / 57) < 1e-12

    def test_it_is_an_ordinary_rate_not_an_extreme_one(self) -> None:
        # One of the three alternative readings E-026 had to rule out: a floor
        # unreachable because the comparison itself is unstable.
        assert 0.1 < det.POOLED_DISCORDANCE < 0.5
