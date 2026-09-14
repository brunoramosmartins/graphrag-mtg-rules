"""The directional claim is the finding, so the direction test is the pin.

"The judge never graded better than the human" is what licenses reading every
correctness figure in this project as a floor. It is a statement about the
confusion matrix being zero below its diagonal, and a `scored_up` that returned
zero for the wrong reason — a reversed ladder, a missing label, a comparison on
strings — would license the same claim from data that does not support it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import judge_direction as jd


class TestTheLadderIsOrderedBestToWorst:
    def test_the_three_labels_in_order(self) -> None:
        assert jd.LADDER == ("correct", "partial", "incorrect")

    def test_the_collapse_boundary_is_the_first_rung(self) -> None:
        # E-001 publishes `correct` against everything else, so the collapse
        # splits the ladder after its first entry and nowhere else.
        assert jd.LADDER[0] == "correct"


class TestScoredUpCountsOnlyUpgrades:
    def test_perfect_agreement_has_no_upgrades(self) -> None:
        table = {("correct", "correct"): 5, ("incorrect", "incorrect"): 9}
        assert jd.scored_up(table) == 0

    def test_a_strict_judge_has_no_upgrades(self) -> None:
        # Human said correct, judge said partial: the judge graded DOWN.
        table = {("correct", "partial"): 4, ("partial", "incorrect"): 10}
        assert jd.scored_up(table) == 0

    def test_a_lenient_judge_is_counted(self) -> None:
        # Human said partial, judge said correct: an upgrade, and the finding
        # would not hold.
        assert jd.scored_up({("partial", "correct"): 1}) == 1

    def test_every_upgrade_is_counted_not_just_adjacent_ones(self) -> None:
        assert jd.scored_up({("incorrect", "correct"): 2, ("incorrect", "partial"): 3}) == 5

    def test_upgrades_and_downgrades_together(self) -> None:
        table = {
            ("correct", "correct"): 13,
            ("correct", "partial"): 4,
            ("correct", "incorrect"): 1,
            ("partial", "incorrect"): 10,
            ("incorrect", "incorrect"): 23,
            ("partial", "correct"): 2,
        }
        assert jd.scored_up(table) == 2

    def test_the_published_matrix_has_no_upgrades(self) -> None:
        # The 55 audited answers, transcribed. If this ever fails, the claim
        # that correctness figures are floors fails with it.
        published = {
            ("correct", "correct"): 13,
            ("correct", "partial"): 4,
            ("correct", "incorrect"): 1,
            ("partial", "partial"): 4,
            ("partial", "incorrect"): 10,
            ("incorrect", "incorrect"): 23,
        }
        assert sum(published.values()) == 55
        assert jd.scored_up(published) == 0


class TestWilsonIsTheProjectsInterval:
    def test_a_full_house_has_a_lower_bound_below_one(self) -> None:
        low, high = jd.wilson(37, 37)
        assert high == pytest.approx(1.0)
        assert 0.8 < low < 1.0

    def test_the_published_correct_cell(self) -> None:
        # 13/18 = 0.722 [0.491, 0.875] — the figure the whole amendment turns
        # on, and the one that sits 0.002 above a bar placed on its lower bound.
        low, high = jd.wilson(13, 18)
        assert low == pytest.approx(0.491, abs=0.002)
        assert high == pytest.approx(0.875, abs=0.002)

    def test_an_empty_cell_does_not_divide_by_zero(self) -> None:
        assert jd.wilson(0, 0) == (0.0, 0.0)

    def test_the_interval_tightens_with_n_at_a_fixed_rate(self) -> None:
        widths = [jd.wilson(round(0.722 * n), n)[1] - jd.wilson(round(0.722 * n), n)[0]
                  for n in (18, 100, 1000)]
        assert widths == sorted(widths, reverse=True)


class TestTheBarCannotBeClearedAtTheObservedRate:
    """The amendment's load-bearing arithmetic, pinned.

    The registered bar is 0.720 on a lower bound and the observed point
    estimate is 0.722. If a moderate n cleared it, the audit would be worth
    buying and the amendment would be wrong to close it.
    """

    def test_the_bar_is_the_registered_one_and_is_not_adjustable_here(self) -> None:
        assert jd.THRESHOLD == 0.720

    def test_thirty_does_not_clear_it(self) -> None:
        assert jd.wilson(round(0.722 * jd.GATE_N), jd.GATE_N)[0] < jd.THRESHOLD

    def test_even_six_thousand_does_not_clear_it(self) -> None:
        assert jd.wilson(round(0.722 * 6400), 6400)[0] < jd.THRESHOLD

    def test_a_clearly_better_judge_would_clear_it_easily(self) -> None:
        # The test that stops the one above from passing for the wrong reason:
        # the bar is reachable, just not at this judge's accuracy.
        assert jd.wilson(round(0.90 * 100), 100)[0] > jd.THRESHOLD


class TestTheReanalysisIsPinnedToTheOriginalFigure:
    def test_it_knows_what_e011a_published(self) -> None:
        assert jd.PUBLISHED_THREE_WAY == (40, 55)

    def test_the_published_figure_is_the_one_wilson_reproduces(self) -> None:
        hits, total = jd.PUBLISHED_THREE_WAY
        low, high = jd.wilson(hits, total)
        assert low == pytest.approx(0.598, abs=0.002)
        assert high == pytest.approx(0.827, abs=0.002)
