"""The pairing is the entry, so the pairing is what the tests pin.

E-027 exists because a published non-overlapping interval turned out to be an
artefact of pooling clustered items. The bootstrap here resamples **questions**,
carrying both arms' values together; resampling items, or resampling the two
arms independently, reproduces exactly the error the entry was written to
correct. These tests make that difference fail loudly rather than quietly.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e027_economy as eco


def rng() -> random.Random:
    return random.Random(eco.SEED)


class TestThePairedDifferenceIsPaired:
    def test_a_constant_shift_is_recovered_exactly(self) -> None:
        a = [1.0, 5.0, 9.0, 2.0, 7.0]
        b = [x + 3.0 for x in a]
        _, _, delta, low, high = eco.paired(a, b, rng(), 2000)
        assert delta == pytest.approx(3.0)
        # A perfectly constant difference has no spread, paired.
        assert low == pytest.approx(3.0)
        assert high == pytest.approx(3.0)

    def test_the_unpaired_spread_would_have_been_large(self) -> None:
        # The same data, if the arms were treated as independent samples,
        # carries the whole between-question variance. Pairing removes it, and
        # that is why the pairing changes conclusions rather than decimals.
        a = [1.0, 5.0, 9.0, 2.0, 7.0]
        b = [x + 3.0 for x in a]
        assert statistics.stdev(a) > 3.0
        assert statistics.stdev([x - y for x, y in zip(b, a, strict=True)]) == 0.0

    def test_the_order_of_questions_does_not_matter(self) -> None:
        a = [1.0, 5.0, 9.0, 2.0, 7.0]
        b = [2.0, 4.0, 11.0, 3.0, 6.0]
        first = eco.paired(a, b, rng(), 2000)[2]
        order = [3, 0, 4, 1, 2]
        second = eco.paired([a[i] for i in order], [b[i] for i in order], rng(), 2000)[2]
        assert first == pytest.approx(second)

    def test_mismatched_lengths_are_refused_not_zipped_short(self) -> None:
        # strict=True. A silently truncated pairing would compare one arm's
        # first forty questions against the other's, which is not a comparison.
        with pytest.raises(ValueError):
            eco.paired([1.0, 2.0, 3.0], [1.0, 2.0], rng(), 100)


class TestTheIntervalBehaves:
    def test_a_zero_difference_interval_contains_zero(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        _, _, delta, low, high = eco.paired(values, list(values), rng(), 2000)
        assert delta == pytest.approx(0.0)
        assert low <= 0 <= high

    def test_a_large_consistent_difference_excludes_zero(self) -> None:
        a = [float(i) for i in range(30)]
        b = [x + 10.0 for x in a]
        _, _, delta, low, high = eco.paired(a, b, rng(), 2000)
        assert low > 0
        # And the interval brackets the difference it is an interval for: an
        # interval that excludes zero while missing the effect would satisfy
        # the assertion above for the wrong reason.
        assert low <= delta <= high
        assert delta == pytest.approx(10.0)

    def test_a_noisy_small_difference_does_not_exclude_zero(self) -> None:
        source = random.Random(7)
        a = [source.gauss(0, 1) for _ in range(30)]
        b = [x + source.gauss(0.02, 1) for x in a]
        _, _, _, low, high = eco.paired(a, b, rng(), 4000)
        assert low < 0 < high

    def test_the_interval_is_reported_around_the_measured_difference(self) -> None:
        source = random.Random(11)
        a = [source.gauss(5, 2) for _ in range(40)]
        b = [x + source.gauss(1.5, 0.5) for x in a]
        mean_a, mean_b, delta, low, high = eco.paired(a, b, rng(), 4000)
        assert low < delta < high
        assert delta == pytest.approx(mean_b - mean_a)


class TestTheEndpointExtractors:
    def test_items_count_the_evidence(self) -> None:
        assert eco.item_count({"evidence": [{}, {}, {}]}) == 3.0
        assert eco.item_count({}) == 0.0

    def test_tokens_prefer_the_recorded_total(self) -> None:
        record = {"tokens": 900, "evidence": [{"tokens": 1}, {"tokens": 2}]}
        assert eco.token_count(record) == 900.0

    def test_tokens_fall_back_to_summing_the_items(self) -> None:
        # Some dumps predate the field. Summing is the documented fallback;
        # returning zero would silently shrink one arm's spend.
        assert eco.token_count({"evidence": [{"tokens": 10}, {"tokens": 5}]}) == 15.0

    def test_rules_are_counted_from_the_evidence_kind_not_from_prose(self) -> None:
        # A ruling quoting a rule number in its text is not a retrieved rule.
        record = {
            "evidence": [
                {"kind": "rule", "key": "613.4b"},
                {"kind": "ruling", "key": "r1", "text": "see 613.4b"},
                {"kind": "rule", "key": "701.6"},
            ]
        }
        assert eco.rule_count(record) == 2.0


class TestStandingRuleNineAgainstTheHeadline:
    """The check that asks what *else* makes arm B's spend look small."""

    def test_a_pipeline_refusal_is_found_by_the_field_that_records_it(self) -> None:
        # `generated` is the field, and it lives on the answers dump. Reading
        # `refused` instead would miss the five `no_seed` cases, which carry
        # generated=False and are the whole point of the check.
        answers = {
            "q1": {"generated": True, "refused": False},
            "q2": {"generated": False, "refused": True},
            "q3": {"generated": True, "refused": True},
        }
        assert eco.non_generated(answers) == {"q2"}

    def test_a_row_without_the_field_counts_as_generated(self) -> None:
        # The default matters: a dump predating the field must not turn every
        # question into a refusal and empty the kept population.
        assert eco.non_generated({"q1": {}, "q2": {"generated": False}}) == {"q2"}

    def test_the_ratio_spread_says_whether_the_mean_is_carried_by_a_few(self) -> None:
        # Two arms where B is uniformly cheaper: the median ratio is the
        # evidence that the economy is general rather than a few collapses.
        a = [100.0, 200.0, 400.0, 800.0]
        b = [10.0, 20.0, 40.0, 80.0]
        ratios, above = eco.ratio_spread(a, b)
        assert above == 0
        assert statistics.median(ratios) == pytest.approx(0.1)

    def test_a_mean_carried_by_one_collapse_is_visible_in_the_median(self) -> None:
        # The mean ratio here is dragged down by q1 alone; the median reports
        # that the other three questions are not economical at all. This is the
        # failure mode the check exists to expose.
        a = [1000.0, 100.0, 100.0, 100.0]
        b = [0.0, 100.0, 100.0, 100.0]
        ratios, above = eco.ratio_spread(a, b)
        assert statistics.fmean(ratios) < 0.8
        assert statistics.median(ratios) == pytest.approx(1.0)
        assert above == 0

    def test_questions_where_b_spends_more_are_counted_not_clipped(self) -> None:
        ratios, above = eco.ratio_spread([10.0, 10.0, 10.0], [5.0, 12.0, 30.0])
        assert above == 2
        assert ratios[-1] == pytest.approx(3.0)

    def test_a_zero_denominator_is_dropped_rather_than_dividing(self) -> None:
        ratios, above = eco.ratio_spread([0.0, 10.0], [5.0, 5.0])
        assert ratios == [pytest.approx(0.5)]
        assert above == 0


class TestTheOutcomeComesFromTheAnswersDump:
    def test_answers_and_verdicts_read_different_artefacts(self) -> None:
        # The bug this pins: `outcome_of` reads `generated` and `refused`, and
        # only the answers dump carries them. Passing the retrieval rows made
        # the pipeline-refusal branch unreachable and every refusal fell
        # through to the judge's label.
        from e001_inspect import artefacts

        retrieval, answers, verdicts = artefacts("B", "eval")
        assert eco.answers_for.__doc__ is not None
        assert answers != retrieval
        assert verdicts != answers
        assert "answers" in answers.name
        assert "verdicts" in verdicts.name


class TestTheArmsAreTheTwoTheThesisContrasts:
    def test_only_the_vector_and_graph_arms_are_compared(self) -> None:
        # The hybrid is reported by E-001 and deliberately absent here; adding
        # it would widen the comparison family for a question nobody asked.
        assert set(eco.ARMS) == {"A", "B"}

    def test_the_seed_is_recorded_rather_than_drawn_fresh(self) -> None:
        assert isinstance(eco.SEED, int)
        assert eco.paired([1.0, 4.0, 2.0], [2.0, 9.0, 1.0], rng(), 500) == eco.paired(
            [1.0, 4.0, 2.0], [2.0, 9.0, 1.0], rng(), 500
        )
