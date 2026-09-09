"""Arm A: fusion, budget parity, and the ablations that must not lie.

The roadmap marks a strawman baseline **critical** for credibility. Every
test here holds a property that, if broken, would let arm A be weaker than
it is reported to be — or reported as something it is not.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.evaluation.baseline_vector import (
    Retrieved,
    VectorArm,
    build_arm,
    enforce_budget,
    estimate_tokens,
    gold_rules_found,
    legality_fact_present,
    reciprocal_rank_fusion,
    serialize,
)
from graphrag_mtg.evaluation.bm25 import Bm25Index
from graphrag_mtg.evaluation.corpus import Document
from graphrag_mtg.evaluation.dense import DenseIndex, normalise


def doc(doc_id: str, text: str, **kw) -> Document:
    return Document(
        doc_id=doc_id,
        kind=kw.pop("kind", "rule"),
        title=kw.pop("title", doc_id),
        text=text,
        **kw,
    )


CORPUS = [
    doc("rule:702.19", "Trample lets excess combat damage through to the player.",
        rule_number="702.19"),
    doc("rule:613.7", "Timestamp order determines which continuous effect applies first.",
        rule_number="613.7"),
    doc("card:o1", "Mindsparker First strike. Mindsparker is legal in Modern.",
        kind="card", oracle_id="o1", legalities={"modern": "legal", "pauper": "not_legal"}),
]


class TestReciprocalRankFusion:
    def test_a_document_both_halves_found_beats_one_only_half_found(self) -> None:
        # This is the property fusion exists for, and it is not the same
        # as "the document both halves agree is middling wins".
        assert reciprocal_rank_fusion([["x", "only_a"], ["x", "only_b"]])[0] == "x"

    def test_a_deep_hit_in_one_half_survives_a_top_hit_in_the_other(self) -> None:
        # 30th by one half and 2nd by the other is exactly the document a
        # single retriever loses, and the reason CANDIDATE_DEPTH is read
        # deeper than the final k.
        deep = [f"filler{i}" for i in range(29)] + ["wanted"]
        fused = reciprocal_rank_fusion([deep, ["top", "wanted"]])
        assert fused[0] == "wanted"

    def test_the_extremes_beat_the_middle_on_reversed_rankings(self) -> None:
        # Counterintuitive and worth pinning rather than discovering: with
        # two exactly reversed rankings, ranks (1,3) sum to more than
        # (2,2), because 1/(k+1) + 1/(k+3) > 2/(k+2) — 1/x is convex. A
        # document both halves rank *second* therefore loses to one each
        # half disagrees about. Real rankings are not reversals, so this
        # is a property of the metric and not a defect, but an intuition
        # that "agreed-on documents win" is wrong in exactly this shape.
        assert reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "a"]]) == ["a", "c", "b"]

    def test_reads_ranks_not_scores(self) -> None:
        # BM25 scores and cosine similarities live on incomparable scales.
        # A weighted sum would need a normalisation constant, and a constant
        # chosen after seeing which arm it favours is what pin 7 forbids.
        assert reciprocal_rank_fusion([["a"], ["b"]]) == ["a", "b"]

    def test_ties_break_by_id_so_runs_reproduce(self) -> None:
        assert reciprocal_rank_fusion([["b", "a"], ["a", "b"]]) == ["a", "b"]

    def test_a_document_only_one_half_found_still_survives(self) -> None:
        # The whole point of fusion: 30th by one half and 2nd by the other
        # is exactly the document a single retriever loses.
        fused = reciprocal_rank_fusion([["a", "b"], ["c"]])
        assert "c" in fused


class TestEnforceBudget:
    def test_keeps_rank_order_until_the_budget_is_spent(self) -> None:
        documents = [doc(f"rule:{i}", "word " * 400) for i in range(10)]
        kept, tokens, truncated = enforce_budget(documents, budget=500)
        assert kept == documents[: len(kept)]
        assert tokens <= 500 and truncated == 10 - len(kept)

    def test_never_returns_an_empty_context(self) -> None:
        # A single document larger than the budget still goes through:
        # returning nothing would score as a retrieval failure when the
        # retrieval succeeded and only the budget was small.
        big = doc("rule:1", "word " * 5000)
        kept, _, truncated = enforce_budget([big], budget=10)
        assert kept == [big] and truncated == 0

    def test_the_trim_is_returned_not_logged(self) -> None:
        # Pin 11 suppresses the notice that would tell the model, so the
        # run record is the only place the trim can be seen.
        _, _, truncated = enforce_budget([doc(f"r{i}", "word " * 400) for i in range(5)], 100)
        assert truncated > 0


class TestBuildArm:
    def test_lexical_mode_needs_no_vectors(self) -> None:
        arm = build_arm(CORPUS, mode="lexical")
        assert arm.mode == "lexical" and arm.dense is None

    def test_a_dense_mode_without_vectors_is_refused(self) -> None:
        # Silently degrading to lexical would publish an ablation under
        # the hybrid's name.
        with pytest.raises(ValueError, match="needs vectors"):
            build_arm(CORPUS, mode="hybrid")

    def test_an_unknown_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown mode"):
            build_arm(CORPUS, mode="semantic")

    def test_an_arm_with_neither_half_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one half"):
            VectorArm(documents=CORPUS, lexical=None, dense=None)

    def test_a_dense_index_without_an_encoder_is_refused(self) -> None:
        index = DenseIndex(["a"], [[1.0, 0.0]])
        with pytest.raises(ValueError, match="cannot embed a query"):
            VectorArm(documents=CORPUS, lexical=None, dense=index, encoder=None)


class TestRetrieve:
    def test_finds_the_rule_a_question_names(self) -> None:
        arm = build_arm(CORPUS, mode="lexical", token_budget=10_000)
        got = arm.retrieve("What does trample do?")
        assert "rule:702.19" in got.doc_ids
        assert got.mode == "lexical" and got.rounds == 1

    def test_iterative_runs_a_second_round(self) -> None:
        # Pin 13: the affordance the hypothesis calls path-walking, offered
        # to arm A because denying it would make beating arm A on the
        # multi-hop stratum close to uninformative.
        arm = build_arm(CORPUS, mode="lexical", token_budget=10_000)
        assert arm.retrieve("trample", iterative=True).rounds == 2

    def test_records_what_the_budget_cut(self) -> None:
        arm = build_arm(CORPUS, mode="lexical", token_budget=1)
        got = arm.retrieve("trample")
        assert got.considered >= len(got.documents)
        assert got.truncated == got.considered - len(got.documents)


class TestGrading:
    def test_rule_recall_counts_gold_numbers_present(self) -> None:
        got = Retrieved(documents=[CORPUS[0], CORPUS[1]])
        assert gold_rules_found(got, ["702.19", "104.1"]) == (1, 2)

    def test_an_empty_gold_wants_nothing(self) -> None:
        # `legality_1hop` carries an empty `gold_cr_rules` by construction.
        # Pin 9 gives it its own metric rather than pooling an undefined
        # recall into rule-number recall.
        assert gold_rules_found(Retrieved(documents=list(CORPUS)), []) == (0, 0)

    def test_duplicate_gold_rules_are_counted_once(self) -> None:
        assert gold_rules_found(Retrieved(documents=[CORPUS[0]]), ["702.19", "702.19"]) == (1, 1)

    def test_the_legality_fact_is_read_from_the_card_document(self) -> None:
        got = Retrieved(documents=list(CORPUS))
        assert legality_fact_present(got, "o1", "modern") == "legal"
        assert legality_fact_present(got, "o1", "pauper") == "not_legal"

    def test_a_card_that_never_reached_the_context_reads_none(self) -> None:
        # None is "arm A could not see the fact", which is a retrieval
        # failure. Returning "not_legal" would score it as a wrong answer.
        assert legality_fact_present(Retrieved(documents=[CORPUS[0]]), "o1", "modern") is None


class TestSerialize:
    def test_carries_the_same_handle_shape_as_the_graph_arms(self) -> None:
        # `p5-a3` asks for kind:key handles and pin 1 compares the
        # malformed-citation rate per arm. A differently-shaped context
        # would make that comparison measure the adapter.
        rendered = serialize(Retrieved(documents=[CORPUS[0]]))
        assert "[rule:702.19]" in rendered

    def test_emits_no_incompleteness_notice(self) -> None:
        # Pin 11, for every arm.
        rendered = serialize(Retrieved(documents=list(CORPUS), truncated=99))
        assert "NOTICE" not in rendered

    def test_an_empty_retrieval_says_so(self) -> None:
        assert "NO EVIDENCE" in serialize(Retrieved(documents=[]))


class TestDenseIndex:
    def test_ranks_by_cosine_similarity(self) -> None:
        index = DenseIndex(["a", "b"], [normalise([1.0, 0.0]), normalise([0.0, 1.0])])
        assert index.search(normalise([0.9, 0.1]), k=1)[0].doc_id == "a"

    def test_mismatched_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="wrong handles"):
            DenseIndex(["a", "b"], [[1.0]])

    def test_normalise_survives_a_zero_vector(self) -> None:
        assert normalise([0.0, 0.0]) == [0.0, 0.0]


class TestBm25:
    def test_mismatched_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="wrong handles"):
            Bm25Index(["a", "b"], ["only one text"])

    def test_estimate_tokens_matches_the_project_heuristic(self) -> None:
        assert estimate_tokens("a" * 400) == 100
