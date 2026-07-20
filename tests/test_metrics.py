"""Metrics part 1: micro P/R/F1, bootstrap CIs, stratified reports."""

from __future__ import annotations

from typing import ClassVar

from graphrag_mtg.evaluation.metrics import (
    bootstrap_ci,
    evaluate_by_stratum,
    micro_prf,
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
