"""Metrics part 1: micro P/R/F1, bootstrap CIs, stratified reports."""

from __future__ import annotations

from typing import ClassVar

import pytest

from graphrag_mtg.evaluation.metrics import (
    bootstrap_ci,
    by_family,
    cluster_proportion_ci,
    evaluate_by_stratum,
    micro_prf,
    rule_family,
    rule_of_three_upper,
)


def fs(*items: str) -> frozenset[str]:
    return frozenset(items)


class TestMicroPrf:
    def test_perfect(self) -> None:
        result = micro_prf([(fs("a", "b"), fs("a", "b"))])
        assert result.precision == result.recall == result.f1 == 1.0

    def test_counts_pooled_across_documents(self) -> None:
        pairs = [
            (fs("a"), fs("a", "b")),  # tp=1, fn=1
            (fs("c", "x"), fs("c")),  # tp=1, fp=1
        ]
        result = micro_prf(pairs)
        assert (result.tp, result.fp, result.fn) == (2, 1, 1)
        assert result.precision == result.recall == 2 / 3

    def test_empty_everything_is_zero_not_crash(self) -> None:
        result = micro_prf([(fs(), fs())])
        assert result.f1 == 0.0


class TestBootstrap:
    PAIRS: ClassVar[list[tuple[frozenset[str], frozenset[str]]]] = [
        (fs("a"), fs("a")),
        (fs("b"), fs("b")),
        (fs("x"), fs("y")),
        (fs("c"), fs("c")),
    ]

    def test_deterministic_given_seed(self) -> None:
        one = bootstrap_ci(self.PAIRS, lambda p: micro_prf(p).f1, seed=13)
        two = bootstrap_ci(self.PAIRS, lambda p: micro_prf(p).f1, seed=13)
        assert (one.low, one.high) == (two.low, two.high)

    def test_interval_brackets_the_point(self) -> None:
        ci = bootstrap_ci(self.PAIRS, lambda p: micro_prf(p).f1)
        assert ci.low <= ci.point <= ci.high
        assert ci.n_docs == 4

    def test_empty_sample(self) -> None:
        ci = bootstrap_ci([], lambda p: micro_prf(p).f1)
        assert (ci.point, ci.n_docs) == (0.0, 0)


class TestEvaluateByStratum:
    def test_missing_prediction_counts_as_false_negative(self) -> None:
        reports = evaluate_by_stratum(
            predicted_by_doc={},
            gold_by_doc={"r1": fs("a")},
        )
        (overall,) = reports
        assert overall.stratum == "overall"
        assert overall.counts.fn == 1

    def test_unannotated_predictions_are_ignored(self) -> None:
        reports = evaluate_by_stratum(
            predicted_by_doc={"r1": fs("a"), "ghost": fs("z")},
            gold_by_doc={"r1": fs("a")},
        )
        (overall,) = reports
        assert overall.counts.fp == 0 and overall.counts.tp == 1

    def test_strata_reported_alongside_overall(self) -> None:
        reports = evaluate_by_stratum(
            predicted_by_doc={"r1": fs("a"), "r2": fs()},
            gold_by_doc={"r1": fs("a"), "r2": fs("b")},
            stratum_by_doc={"r1": "multiword", "r2": "homonym"},
        )
        by_name = {r.stratum: r for r in reports}
        assert set(by_name) == {"overall", "multiword", "homonym"}
        assert by_name["multiword"].counts.f1 == 1.0
        assert by_name["homonym"].counts.fn == 1


class TestRuleFamily:
    """The secondary citation key: right rule, wrong leaf is its own failure."""

    def test_subrule_letter_is_dropped(self) -> None:
        assert rule_family("702.33d") == "702.33"
        assert rule_family("608.2b") == "608.2"

    def test_a_letterless_rule_is_its_own_family(self) -> None:
        assert rule_family("101.4") == "101.4"
        assert rule_family("704") == "704"

    def test_items_are_rekeyed_onto_the_family(self) -> None:
        scored = {"r1": {("r1", "608.2b"), ("r1", "608.2d")}}
        assert by_family(scored) == {"r1": frozenset({("r1", "608.2")})}

    def test_a_depth_error_scores_as_a_family_hit(self) -> None:
        gold = by_family({"r1": {("r1", "702.33d")}})
        predicted = by_family({"r1": {("r1", "702.33")}})
        assert gold == predicted


class TestClusterProportionCi:
    def test_the_point_estimate_pools_over_items(self) -> None:
        interval = cluster_proportion_ci([[True, False], [True, True]])
        assert interval.point == 0.75

    def test_clusters_not_items_are_the_sample_size(self) -> None:
        """Correlated cases inside one ruling are one draw, not several."""
        interval = cluster_proportion_ci([[True, True, True], [False]])
        assert interval.n_docs == 2

    def test_unanimity_gives_a_degenerate_interval(self) -> None:
        """Pinned because it is a trap, not a feature.

        A percentile bootstrap resamples observed values, so a sample with
        no variation resamples to itself and reports [1.0, 1.0] — which
        reads as certainty. Callers must detect this and report
        ``rule_of_three_upper`` instead.
        """
        interval = cluster_proportion_ci([[True], [True]])
        assert (interval.point, interval.low, interval.high) == (1.0, 1.0, 1.0)

    def test_no_cases_is_not_a_crash(self) -> None:
        assert cluster_proportion_ci([]).n_docs == 0


class TestRuleOfThree:
    def test_the_bound_shrinks_with_the_sample(self) -> None:
        assert rule_of_three_upper(33) > rule_of_three_upper(80)

    def test_thirty_three_clean_clusters(self) -> None:
        assert rule_of_three_upper(33) == pytest.approx(0.0909, abs=1e-4)

    def test_no_trials_bounds_nothing(self) -> None:
        assert rule_of_three_upper(0) == 1.0
