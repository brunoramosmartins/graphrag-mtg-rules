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

    def test_a_frozen_subset_round_trips(self, tmp_path: Path) -> None:
        out = tmp_path / "subset.json"
        drawn = self.population(3)
        metaqa.freeze(drawn, out, seed=20260815)
        assert metaqa.load_frozen(out) == drawn


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


class CountResult:
    """The single row the guard reads back from a session."""

    def __init__(self, nodes: int) -> None:
        self.nodes = nodes

    def single(self) -> dict[str, int]:
        return {"nodes": self.nodes}


class TestTheLoaderRefusesANonEmptyDatabase:
    """E-008 loaded 9 nodes into production and its teardown deleted real rules.

    MetaQA is ~43,000 triples. The registration says separate database; this
    is the check that makes the registration true at runtime.
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
