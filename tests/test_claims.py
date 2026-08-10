"""The E-007 claim unit — where the phase's only threshold gets its denominator.

Every test here pins something the red-team pass found missing before any
answer existed: the degenerate 0/0 pass, the shrinking denominator, and
the partial case that had no rule.
"""

from __future__ import annotations

from graphrag_mtg.evaluation.claims import (
    ClaimRow,
    Failure,
    Label,
    Sufficiency,
    Support,
    classify_refusals,
    coverage,
    failure_counts,
    segment_answer,
    split_sentences,
    support_clusters,
    worksheet_hash,
)


def row(
    qid: str,
    index: int,
    sentence: str,
    *,
    cited: bool = False,
    label: Label = Label.FACTUAL,
    support: Support = Support.NOT_APPLICABLE,
    failure: Failure | None = None,
) -> ClaimRow:
    return ClaimRow(qid, index, sentence, cited=cited, label=label, support=support, failure=failure)


class TestSegmentation:
    def test_ordinary_sentences_split(self) -> None:
        assert split_sentences("It applies. Then it stops.") == [
            "It applies.",
            "Then it stops.",
        ]

    def test_a_rule_number_is_not_a_sentence_boundary(self) -> None:
        """This corpus is full of dots that are not full stops."""
        assert split_sentences("Apply rule 613.4 then stop.") == ["Apply rule 613.4 then stop."]

    def test_a_subrule_mid_sentence_survives(self) -> None:
        assert len(split_sentences("Under 608.2b the ability resolves and the token dies.")) == 1

    def test_a_sentence_ending_in_a_number_still_splits(self) -> None:
        assert split_sentences("It is a 1/1. That is the result.") == [
            "It is a 1/1.",
            "That is the result.",
        ]

    def test_it_is_deterministic(self) -> None:
        """The worksheet hash rests on this."""
        text = "One thing. Two things. Three."
        assert split_sentences(text) == split_sentences(text)


class TestSegmentAnswer:
    """Boundaries from the stripped text, flags from the same chunk."""

    def test_the_sentence_arrives_without_its_marker(self) -> None:
        assert segment_answer("It applies [rule:613.4].") == [("It applies.", True)]

    def test_an_uncited_sentence_is_flagged_as_such(self) -> None:
        assert segment_answer("So it stays a 1/1.") == [("So it stays a 1/1.", False)]

    def test_flags_stay_aligned_with_their_sentences(self) -> None:
        """The failure the sentinel exists to prevent: two splits disagreeing."""
        answer = "It applies [rule:613.4]. So it stays a 1/1. And that ends it [ruling:x]."
        assert segment_answer(answer) == [
            ("It applies.", True),
            ("So it stays a 1/1.", False),
            ("And that ends it.", True),
        ]

    def test_a_marker_cannot_move_a_boundary(self) -> None:
        cited = "A is true [rule:613.4]. B follows [ruling:2009-10-01]."
        uncited = "A is true. B follows."
        assert [s for s, _ in segment_answer(cited)] == [s for s, _ in segment_answer(uncited)]

    def test_a_rule_number_inside_a_sentence_does_not_split_it(self) -> None:
        answer = "Rule 613.4 orders them [rule:613.4]."
        assert segment_answer(answer) == [("Rule 613.4 orders them.", True)]


class TestWorksheetHash:
    def test_the_segmentation_is_covered(self) -> None:
        one = [row("q1", 0, "A."), row("q1", 1, "B.")]
        two = [row("q1", 0, "A."), row("q1", 1, "B changed.")]
        assert worksheet_hash(one) != worksheet_hash(two)

    def test_labels_are_not_covered(self) -> None:
        """Labels are supposed to change; the segmentation is not."""
        before = [row("q1", 0, "A.", label=Label.UNLABELLED)]
        after = [row("q1", 0, "A.", label=Label.FACTUAL)]
        assert worksheet_hash(before) == worksheet_hash(after)


class TestCoverage:
    def test_only_factual_rows_are_the_denominator(self) -> None:
        rows = [
            row("q1", 0, "You asked about Humility.", label=Label.NON_FACTUAL),
            row("q1", 1, "It removes abilities.", cited=True),
        ]
        result = coverage(rows)
        assert (result.cited, result.factual) == (1, 1)
        assert result.rate == 1.0

    def test_an_uncited_connective_costs_coverage(self) -> None:
        """The class E-007 predicts round 1 fails on."""
        rows = [
            row("q1", 0, "It removes abilities.", cited=True),
            row("q1", 1, "So it stays a 1/1."),
        ]
        assert coverage(rows).rate == 0.5

    def test_a_run_of_refusals_is_not_coverage_one(self) -> None:
        """The degenerate pass: 0/0 is undefined, not perfect."""
        rows = [row("q1", 0, "CANNOT ANSWER.", label=Label.NON_FACTUAL)]
        result = coverage(rows)
        assert result.factual == 0
        assert result.rate is None

    def test_heavy_exclusion_voids_the_figure(self) -> None:
        """The one lever that shrinks the denominator is watched."""
        rows = [row("q1", i, "x.", label=Label.NON_FACTUAL) for i in range(3)]
        rows += [row("q1", 3, "y.", cited=True)]
        result = coverage(rows)
        assert result.exclusion_rate == 0.75
        assert result.voided

    def test_a_normal_exclusion_rate_does_not_void(self) -> None:
        rows = [row("q1", i, "y.", cited=True) for i in range(9)]
        rows += [row("q1", 9, "x.", label=Label.NON_FACTUAL)]
        assert not coverage(rows).voided

    def test_answering_clusters_and_answers_are_counted_apart(self) -> None:
        """Refusals are answers that contribute no cluster."""
        rows = [
            row("q1", 0, "It applies.", cited=True),
            row("q2", 0, "CANNOT ANSWER.", label=Label.NON_FACTUAL),
        ]
        result = coverage(rows)
        assert (result.clusters, result.answers) == (1, 2)


class TestSupport:
    def test_clusters_are_questions_not_claims(self) -> None:
        rows = [
            row("q1", 0, "a", cited=True, support=Support.SUPPORTED),
            row("q1", 1, "b", cited=True, support=Support.UNSUPPORTED, failure=Failure.WRONG_LEAF),
            row("q2", 0, "c", cited=True, support=Support.SUPPORTED),
        ]
        clusters = support_clusters(rows)
        assert clusters == [[True, False], [True]]

    def test_uncited_and_non_factual_rows_do_not_enter(self) -> None:
        rows = [
            row("q1", 0, "a", cited=True, support=Support.SUPPORTED),
            row("q1", 1, "b"),
            row("q1", 2, "c", label=Label.NON_FACTUAL),
        ]
        assert support_clusters(rows) == [[True]]

    def test_the_taxonomy_is_tallied(self) -> None:
        rows = [
            row("q1", 0, "a", cited=True, support=Support.UNSUPPORTED, failure=Failure.WRONG_LEAF),
            row("q2", 0, "b", cited=True, support=Support.UNSUPPORTED, failure=Failure.WRONG_LEAF),
            row(
                "q3",
                0,
                "c",
                cited=True,
                support=Support.UNSUPPORTED,
                failure=Failure.EVIDENCE_ABSENT,
            ),
        ]
        assert failure_counts(rows) == {"wrong_leaf": 2, "evidence_absent": 1}


class TestRefusalClassification:
    SUFFICIENCY = {
        "q1": Sufficiency.SUFFICIENT,
        "q2": Sufficiency.INSUFFICIENT,
        "q3": Sufficiency.PARTIAL,
    }

    def test_refusing_with_the_evidence_present_blocks_the_dod(self) -> None:
        report = classify_refusals({"q1": True}, self.SUFFICIENCY)
        assert report.over_refusal == ["q1"]
        assert report.blocks_dod

    def test_refusing_without_evidence_is_correct(self) -> None:
        report = classify_refusals({"q2": True}, self.SUFFICIENCY)
        assert report.correct_refusal == ["q2"]
        assert not report.blocks_dod

    def test_answering_without_evidence_is_the_leak_surface(self) -> None:
        report = classify_refusals({"q2": False}, self.SUFFICIENCY)
        assert report.unsupported_answering == ["q2"]

    def test_both_partial_outcomes_are_correct_behaviour(self) -> None:
        """serialize() invites the hedge; punishing either side penalises the design."""
        refused = classify_refusals({"q3": True}, self.SUFFICIENCY)
        answered = classify_refusals({"q3": False}, self.SUFFICIENCY)
        assert refused.partial_refused == ["q3"] and not refused.blocks_dod
        assert answered.partial_answered == ["q3"] and not answered.blocks_dod

    def test_an_unlabelled_question_is_counted_nowhere(self) -> None:
        """Sufficiency is frozen first; a question missing from it is a harness bug."""
        report = classify_refusals({"ghost": True}, self.SUFFICIENCY)
        assert not any(
            [
                report.over_refusal,
                report.correct_refusal,
                report.unsupported_answering,
                report.partial_refused,
                report.partial_answered,
            ]
        )
