"""The MetaQA adapter's guards, without a database.

What is worth pinning is not that the parser parses. It is that a malformed
release fails loudly instead of producing a shorter benchmark, that the
frozen subset cannot be redrawn, that the scoring rule was fixed before any
failure was inspected, and that nothing can interpolate an unvetted string
into Cypher.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphrag_mtg.evaluation import metaqa

KB = "Kismet|directed_by|Sidney Lanfield\nKismet|starred_actors|Ronald Colman\n"
QA = (
    "what movies did [Sidney Lanfield] direct\tKismet|Second Chorus\n"
    "who acted in [Kismet]\tRonald Colman\n"
)


def kb_file(tmp_path: Path, text: str = KB) -> Path:
    path = tmp_path / "kb.txt"
    path.write_text(text, encoding="utf-8")
    return path


def qa_file(tmp_path: Path, text: str = QA) -> Path:
    path = tmp_path / "qa_test.txt"
    path.write_text(text, encoding="utf-8")
    return path


def release(tmp_path: Path, hops: int = 1, text: str = QA) -> Path:
    """A minimal MetaQA release on disk, in the layout the adapter expects."""
    root = tmp_path / "metaqa"
    vanilla = root / f"{hops}-hop" / "vanilla"
    vanilla.mkdir(parents=True, exist_ok=True)
    (vanilla / "qa_test.txt").write_text(text, encoding="utf-8")
    (root / "kb.txt").write_text(KB, encoding="utf-8")
    return root


class TestAMalformedReleaseFailsLoudly:
    """A silently shorter benchmark is a wrong number nobody can see."""

    def test_a_missing_file_says_this_adapter_downloads_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(metaqa.MetaQAFormatError, match="downloads nothing"):
            metaqa.read_kb(tmp_path / "absent.txt")

    def test_a_two_field_triple_is_refused_with_its_line_number(self, tmp_path: Path) -> None:
        path = kb_file(tmp_path, "Kismet|directed_by|Sidney Lanfield\nKismet|orphan\n")
        with pytest.raises(metaqa.MetaQAFormatError, match=r":2:"):
            metaqa.read_kb(path)

    def test_an_empty_kb_is_an_error_not_an_empty_list(self, tmp_path: Path) -> None:
        with pytest.raises(metaqa.MetaQAFormatError, match="no triples"):
            metaqa.read_kb(kb_file(tmp_path, "\n\n"))

    def test_a_question_without_a_seed_entity_is_refused(self, tmp_path: Path) -> None:
        path = qa_file(tmp_path, "what movies did Sidney Lanfield direct\tKismet\n")
        with pytest.raises(metaqa.MetaQAFormatError, match="no bracketed seed"):
            metaqa.read_questions(path, hops=1)

    def test_a_question_without_answers_is_refused(self, tmp_path: Path) -> None:
        path = qa_file(tmp_path, "what movies did [Sidney Lanfield] direct\n")
        with pytest.raises(metaqa.MetaQAFormatError, match="question<TAB>answers"):
            metaqa.read_questions(path, hops=1)


class TestParsing:
    def test_the_seed_entity_is_kept_and_its_brackets_are_not(self, tmp_path: Path) -> None:
        first = metaqa.read_questions(qa_file(tmp_path), hops=1)[0]
        assert first.seed == "Sidney Lanfield"
        assert first.text == "what movies did Sidney Lanfield direct"
        assert "[" not in first.text

    def test_every_answer_is_kept(self, tmp_path: Path) -> None:
        """Scoring against only the first answer would penalise correct output."""
        first = metaqa.read_questions(qa_file(tmp_path), hops=1)[0]
        assert first.answers == ("Kismet", "Second Chorus")

    def test_the_id_carries_the_hop_and_the_line(self, tmp_path: Path) -> None:
        rows = metaqa.read_questions(qa_file(tmp_path), hops=2)
        assert [r.qid for r in rows] == ["mq-2-1", "mq-2-2"]

    def test_duplicate_triples_survive_parsing(self, tmp_path: Path) -> None:
        """Deduplicating here would hide a corrupt release."""
        path = kb_file(tmp_path, "A|r|B\nA|r|B\n")
        assert len(metaqa.read_kb(path)) == 2
        assert metaqa.entity_names(metaqa.read_kb(path)) == ["A", "B"]


class TestScoringWasFixedBeforeAnyFailureWasSeen:
    def test_any_member_of_the_answer_set_counts(self, tmp_path: Path) -> None:
        question = metaqa.read_questions(qa_file(tmp_path), hops=1)[0]
        assert metaqa.hits_at_1("Second Chorus", question)
        assert metaqa.hits_at_1("Kismet", question)

    def test_case_and_spacing_do_not_decide_correctness(self, tmp_path: Path) -> None:
        question = metaqa.read_questions(qa_file(tmp_path), hops=1)[0]
        assert metaqa.hits_at_1("  second   chorus ", question)

    def test_no_prediction_is_a_miss_not_a_crash(self, tmp_path: Path) -> None:
        question = metaqa.read_questions(qa_file(tmp_path), hops=1)[0]
        assert not metaqa.hits_at_1(None, question)
        assert not metaqa.hits_at_1("", question)


class TestTheSubsetIsDrawnOnceAndFrozen:
    def population(self, n: int) -> list[metaqa.Question]:
        return [
            metaqa.Question(qid=f"mq-1-{i}", hops=1, text="q", seed="s", answers=("a",))
            for i in range(n)
        ]

    def test_the_same_seed_draws_the_same_questions(self) -> None:
        pool = self.population(50)
        assert metaqa.sample(pool, 10, seed=1) == metaqa.sample(pool, 10, seed=1)

    def test_a_different_seed_draws_differently(self) -> None:
        pool = self.population(50)
        assert metaqa.sample(pool, 10, seed=1) != metaqa.sample(pool, 10, seed=2)

    def test_asking_for_more_than_exists_is_an_error(self) -> None:
        """A silent short draw changes the n every interval is computed against."""
        with pytest.raises(ValueError, match="registered subset size"):
            metaqa.sample(self.population(5), 500, seed=1)

    def test_freezing_twice_is_refused(self, tmp_path: Path) -> None:
        out = tmp_path / "subset.json"
        metaqa.freeze(self.population(3), out, seed=20260815)
        with pytest.raises(SystemExit, match="frozen"):
            metaqa.freeze(self.population(3), out, seed=20260815)

    def test_a_frozen_subset_round_trips_through_the_release(self, tmp_path: Path) -> None:
        root = release(tmp_path)
        drawn = metaqa.read_questions(metaqa.question_path(root, 1), hops=1)
        out = tmp_path / "subset.json"
        metaqa.freeze(drawn, out, seed=20260815)
        assert metaqa.load_frozen(out, root) == drawn

    def test_the_frozen_file_holds_ids_and_no_benchmark_text(self, tmp_path: Path) -> None:
        """Somebody else's dataset under somebody else's licence: version ids."""
        root = release(tmp_path)
        out = tmp_path / "subset.json"
        metaqa.freeze(metaqa.read_questions(metaqa.question_path(root, 1), hops=1), out, seed=1)
        written = out.read_text(encoding="utf-8")
        assert "mq-1-1" in written
        assert "what movies" not in written
        assert "Ronald Colman" not in written

    def test_an_id_the_release_does_not_hold_is_refused(self, tmp_path: Path) -> None:
        """A release that is not the one drawn from would score a different sample."""
        root = release(tmp_path)
        out = tmp_path / "subset.json"
        metaqa.freeze(metaqa.read_questions(metaqa.question_path(root, 1), hops=1), out, seed=1)
        metaqa.question_path(root, 1).write_text(
            "who acted in [Kismet]\tRonald Colman\n", encoding="utf-8"
        )
        with pytest.raises(metaqa.MetaQAFormatError, match="different release"):
            metaqa.load_frozen(out, root)


class TestNothingUnvettedReachesCypher:
    """The relationship type cannot be a parameter, so it is built, not passed."""

    def test_the_type_is_prefixed_and_sanitised(self) -> None:
        triple = metaqa.Triple("A", "written_by", "B")
        assert triple.rel_type == "MQ_WRITTEN_BY"

    def test_punctuation_in_a_relation_becomes_an_underscore(self) -> None:
        assert metaqa.Triple("A", "in-language", "B").rel_type == "MQ_IN_LANGUAGE"

    def test_an_unprefixed_type_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unvetted"):
            metaqa.edge_statement("DIRECTED_BY")

    def test_an_injection_attempt_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unvetted"):
            metaqa.edge_statement("MQ_X]->() DETACH DELETE n //")

    def test_a_vetted_type_produces_a_prefixed_statement(self) -> None:
        cypher = metaqa.edge_statement("MQ_DIRECTED_BY")
        assert ":MQ_DIRECTED_BY]" in cypher
        assert metaqa.ENTITY_LABEL in cypher


class TestTheE012ReductionKeepsTheAnswerAtEverySize:
    """A size comparison on a context that lost the answer measures nothing."""

    def chain(self) -> list:
        """A | r1 | B, B | r2 | C, plus noise that must be droppable."""
        triples = [
            metaqa.Triple("A", "directed_by", "B"),
            metaqa.Triple("B", "starred_actors", "C"),
        ]
        noise = [metaqa.Triple("A", "has_genre", f"G{i}") for i in range(20)]
        items = metaqa.triple_evidence(triples, distance=1, start=1)
        items += metaqa.triple_evidence(noise, distance=2, start=3)
        return items

    def test_the_path_to_the_answer_is_found_through_the_evidence(self) -> None:
        path = metaqa.answer_path(self.chain(), seed="A", answers=("C",))
        assert path is not None
        assert [item.text for item in path] == [
            "A | directed_by | B",
            "B | starred_actors | C",
        ]

    def test_an_unreachable_answer_is_none_not_an_empty_path(self) -> None:
        """None excludes the question; an empty list would silently keep it."""
        assert metaqa.answer_path(self.chain(), seed="A", answers=("Z",)) is None

    def test_the_seed_itself_being_the_answer_needs_no_chain(self) -> None:
        assert metaqa.answer_path(self.chain(), seed="A", answers=("A",)) == []

    def test_reduction_keeps_the_chain_and_cuts_the_noise(self) -> None:
        evidence = self.chain()
        keep = metaqa.answer_path(evidence, seed="A", answers=("C",))
        reduced = metaqa.reduce_to_k(evidence, keep, k=8)
        assert len(reduced) == 8
        assert "A | directed_by | B" in [item.text for item in reduced]
        assert "B | starred_actors | C" in [item.text for item in reduced]

    def test_a_k_below_the_chain_length_still_keeps_the_chain(self) -> None:
        evidence = self.chain()
        keep = metaqa.answer_path(evidence, seed="A", answers=("C",))
        reduced = metaqa.reduce_to_k(evidence, keep, k=1)
        assert len(reduced) == 2

    def test_reduction_is_deterministic(self) -> None:
        evidence = self.chain()
        keep = metaqa.answer_path(evidence, seed="A", answers=("C",))
        first = metaqa.reduce_to_k(evidence, keep, k=6)
        second = metaqa.reduce_to_k(evidence, keep, k=6)
        assert [i.key for i in first] == [i.key for i in second]

    def test_retrieval_order_survives_the_cut(self) -> None:
        evidence = self.chain()
        keep = metaqa.answer_path(evidence, seed="A", answers=("C",))
        reduced = metaqa.reduce_to_k(evidence, keep, k=10)
        positions = [evidence.index(item) for item in reduced]
        assert positions == sorted(positions)


class TestThePredictionRuleUnderPromptA2:
    """A2 reasons first and answers last, so the last ANSWER line decides."""

    def test_the_answer_line_wins_over_the_reasoning_above_it(self) -> None:
        text = (
            "step: The Man in the Iron Mask | written_by | Randall Wallace [triple:3]\n"
            "step: Braveheart | written_by | Randall Wallace [triple:17]\n"
            "ANSWER: Braveheart"
        )
        assert metaqa.parse_prediction(text) == "Braveheart"

    def test_a_refusal_on_the_answer_line_is_not_a_prediction(self) -> None:
        assert metaqa.parse_prediction("step: nothing\nANSWER: CANNOT ANSWER") is None

    def test_markdown_around_the_marker_does_not_hide_it(self) -> None:
        assert metaqa.parse_prediction('**ANSWER:** "Kismet".') == "Kismet"

    def test_the_last_answer_line_is_the_one_that_counts(self) -> None:
        text = "ANSWER: Draft\nreconsidering\nANSWER: Final"
        assert metaqa.parse_prediction(text) == "Final"

    def test_a_step_mentioning_the_word_answer_is_not_the_marker(self) -> None:
        text = "step: the film ANSWER: Wrong [triple:1]\nANSWER: Right"
        assert metaqa.parse_prediction(text) == "Right"


class TestThePredictionRuleWasFixedBeforeAnyAnswerWasRead:
    """Deciding later how generously to read the output is deciding the score.

    These cover prompt `e002-a1`, whose run is on disk and must stay
    readable: a number scored under one prompt cannot become unparseable
    because a later prompt changed the format.
    """

    def test_the_first_line_is_the_prediction(self) -> None:
        assert metaqa.parse_prediction("Kismet\n[triple:4]") == "Kismet"

    def test_citation_markers_never_reach_the_prediction(self) -> None:
        assert metaqa.parse_prediction("Kismet [triple:4; triple:9]") == "Kismet"

    def test_leading_blank_lines_are_skipped(self) -> None:
        assert metaqa.parse_prediction("\n\nSecond Chorus\n[triple:1]") == "Second Chorus"

    def test_surrounding_punctuation_is_not_part_of_the_name(self) -> None:
        assert metaqa.parse_prediction('"Kismet".') == "Kismet"

    def test_a_refusal_is_not_a_prediction(self) -> None:
        assert metaqa.parse_prediction("CANNOT ANSWER — no director edge") is None

    def test_empty_output_is_not_a_prediction(self) -> None:
        assert metaqa.parse_prediction("") is None
        assert metaqa.parse_prediction("\n \n") is None


class TestEvidenceIsCitableAndOrdered:
    def test_the_handle_is_an_ordinal_that_continues_across_levels(self) -> None:
        first = metaqa.triple_evidence([metaqa.Triple("A", "directed_by", "B")], 1, start=1)
        second = metaqa.triple_evidence([metaqa.Triple("B", "written_by", "C")], 2, start=2)
        assert first[0].cite() == "triple:1"
        assert second[0].cite() == "triple:2"

    def test_the_distance_is_the_hop_the_budget_trims_by(self) -> None:
        items = metaqa.triple_evidence([metaqa.Triple("A", "directed_by", "B")], 3, start=1)
        assert items[0].distance == 3
        assert items[0].text == "A | directed_by | B"

    def test_the_relation_survives_the_round_trip_through_cypher(self) -> None:
        triple = metaqa.Triple("A", "written_by", "B")
        assert metaqa.display_relation(triple.rel_type) == "written_by"


class CountResult:
    """The single row the guard reads back from a session."""

    def __init__(self, nodes: int) -> None:
        self.nodes = nodes

    def single(self) -> dict[str, int]:
        return {"nodes": self.nodes}


class TestTheLoaderRefusesANonEmptyDatabase:
    """E-008 loaded 9 nodes into production and its teardown deleted real rules.

    MetaQA is 135,000 triples over 43,000 entities. The registration says a
    separate target; this is the check that makes it true at runtime.
    """

    class FakeSession:
        """Answers a node count and nothing else."""

        def __init__(self, nodes: int) -> None:
            self.nodes = nodes

        def run(self, _cypher: str) -> CountResult:
            return CountResult(self.nodes)

    def test_a_populated_database_stops_the_load(self) -> None:
        with pytest.raises(SystemExit, match="already holds 117489"):
            metaqa.assert_database_is_empty(self.FakeSession(117489))

    def test_the_message_names_the_incident_and_the_fix(self) -> None:
        with pytest.raises(
            SystemExit, match=r"E-008.*empty MetaQA database or instance"
        ):
            metaqa.assert_database_is_empty(self.FakeSession(1))

    def test_an_empty_database_passes(self) -> None:
        assert metaqa.assert_database_is_empty(self.FakeSession(0)) is None
