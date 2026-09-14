"""The readings `e001_inspect.py` must not allow.

This script exists because aggregates hid a defect for months, so the tests
here are about the ways a rendering can *look* right and mislead: an outcome
category that pools three different failures, a rule number counted because a
ruling happened to quote it, and a reconstruction presented as a record.

The ordering inside `outcome_of` is the load-bearing part and is tested as
such. A pipeline refusal and a model refusal both carry `refused=True` and both
receive the judge's `incorrect`, so any implementation that consults the label
first collapses three findings into one — which is exactly what happened to six
of arm B's seven refusals.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e001_inspect as insp
from graphrag_mtg.generation.answerer import SYSTEM, prompt_digest


def answer_row(**overrides: object) -> dict:
    """An answers-dump row with the fields `outcome_of` reads."""
    row = {
        "question_id": "q1",
        "arm": "B",
        "generated": True,
        "refused": False,
        "text": "Yes [rule:613.4].",
        "stratum": "definition_1hop",
        "unknown_handles": [],
        "prompt_version": "p5-a3",
    }
    row.update(overrides)
    return row


def verdict_row(label: str) -> dict:
    return {"question_id": "q1", "label": label, "rationale": "because"}


class TestARefusalIsNotAReasoningFailure:
    """The three things that all arrive labelled `incorrect`."""

    def test_the_pipeline_refusal_is_named_even_though_the_judge_said_incorrect(self) -> None:
        # The model was never called. The judge still labelled the refusal
        # string `incorrect`, so a label-first implementation reports a
        # generation failure for a question generation never saw.
        row = answer_row(generated=False, refused=True)
        assert insp.outcome_of(row, verdict_row("incorrect")) == "refused_by_pipeline"

    def test_the_model_refusal_is_separated_from_the_pipeline_refusal(self) -> None:
        row = answer_row(generated=True, refused=True)
        assert insp.outcome_of(row, verdict_row("incorrect")) == "refused_by_model"

    def test_a_genuine_incorrect_answer_keeps_its_label(self) -> None:
        assert insp.outcome_of(answer_row(), verdict_row("incorrect")) == "incorrect"

    @pytest.mark.parametrize("label", ["correct", "partial", "void"])
    def test_the_judged_labels_pass_through(self, label: str) -> None:
        assert insp.outcome_of(answer_row(), verdict_row(label)) == label

    def test_an_answer_with_no_verdict_is_unjudged_not_incorrect(self) -> None:
        assert insp.outcome_of(answer_row(), None) == "unjudged"

    def test_a_label_the_rubric_does_not_define_is_unjudged(self) -> None:
        # A rubric change that renames a label must not silently land in a
        # bucket that already means something else.
        assert insp.outcome_of(answer_row(), verdict_row("mostly-right")) == "unjudged"

    def test_a_missing_generated_field_is_read_as_generated(self) -> None:
        # Older dumps predate the field. Defaulting to False would report
        # every one of their rows as a pipeline refusal.
        row = answer_row()
        del row["generated"]
        assert insp.outcome_of(row, verdict_row("correct")) == "correct"

    def test_every_outcome_is_in_the_declared_tuple(self) -> None:
        # `--counts` builds its tally from OUTCOMES; a value outside it would
        # raise a KeyError on a run rather than on a test.
        cases = [
            (answer_row(generated=False, refused=True), verdict_row("incorrect")),
            (answer_row(refused=True), verdict_row("incorrect")),
            (answer_row(), verdict_row("correct")),
            (answer_row(), None),
        ]
        for row, verdict in cases:
            assert insp.outcome_of(row, verdict) in insp.OUTCOMES


class TestARuleIsNotARuleBecauseSomethingQuotedIt:
    """`retrieved_rules` reads the evidence kind, never the prose."""

    def test_only_rule_evidence_counts(self) -> None:
        record = {
            "evidence": [
                {"kind": "rule", "key": "613.4", "text": "..."},
                {"kind": "card", "key": "Humility", "text": "..."},
            ]
        }
        assert insp.retrieved_rules(record) == {"613.4"}

    def test_a_ruling_quoting_a_rule_number_is_not_a_retrieved_rule(self) -> None:
        # E-010's first pass regexed rule numbers out of the serialized
        # context and counted exactly this. The figure it produced looked
        # identical to a clean one.
        record = {
            "evidence": [
                {"kind": "ruling", "key": "abc", "text": "See rule 613.4b for the order."},
            ]
        }
        assert insp.retrieved_rules(record) == set()

    def test_no_evidence_is_an_empty_set_not_an_error(self) -> None:
        assert insp.retrieved_rules({}) == set()


class TestAReconstructionIsNotARecord:
    """The header must say how much of what follows is evidence."""

    def build(self) -> tuple[str, str]:
        context = "## card\n[card:X] text\n"
        prompt = f"## CONTEXT\n{context}\n\n## QUESTION\nWhat?\n"
        return context, prompt

    def test_a_matching_prompt_hash_verifies(self) -> None:
        context, prompt = self.build()
        answer = answer_row(prompt_sha256=prompt_digest(SYSTEM, prompt))
        state, _ = insp.verification(answer, {"context": context}, prompt, context)
        assert state == "verified"

    def test_a_differing_prompt_hash_is_a_mismatch_and_is_not_shown(self) -> None:
        context, prompt = self.build()
        answer = answer_row(prompt_sha256="0" * 64)
        state, lines = insp.verification(answer, {"context": context}, prompt, context)
        assert state == "mismatch"
        assert any("skipped" in line.lower() for line in lines)

    def test_without_a_hash_a_matching_context_is_verified_only_as_context(self) -> None:
        context, prompt = self.build()
        state, lines = insp.verification(answer_row(), {"context": context}, prompt, context)
        assert state == "context"
        # The claim is bounded: the system prompt is not covered by it.
        assert any("system prompt cannot be checked" in line.lower() for line in lines)

    def test_a_context_that_no_longer_serializes_the_same_is_a_mismatch(self) -> None:
        context, prompt = self.build()
        state, _ = insp.verification(answer_row(), {"context": "something else"}, prompt, context)
        assert state == "mismatch"

    def test_with_neither_hash_nor_context_the_header_says_unverified(self) -> None:
        context, prompt = self.build()
        state, lines = insp.verification(answer_row(), {}, prompt, context)
        assert state == "unverified"
        assert any("UNVERIFIED" in line for line in lines)

    def test_a_prompt_version_the_module_has_moved_past_is_called_out(self) -> None:
        # The context can match byte for byte while the system prompt printed
        # underneath it is one the answer was never generated under.
        context, prompt = self.build()
        answer = answer_row(prompt_version="p5-a1")
        state, lines = insp.verification(answer, {"context": context}, prompt, context)
        assert state == "context"
        assert any("NOT the one this answer was generated under" in line for line in lines)


class TestOneCasePerCategory:
    """`--each` is standing rule 8 in one command, so it must not skip one."""

    def args(self, **overrides: object) -> argparse.Namespace:
        namespace = argparse.Namespace(
            qid=None, stratum=None, fabricated=False, each=True, outcome="any", limit=2
        )
        for key, value in overrides.items():
            setattr(namespace, key, value)
        return namespace

    def population(self) -> tuple[list[dict], dict[str, dict]]:
        answers = [
            answer_row(question_id="a", generated=False, refused=True),
            answer_row(question_id="b"),
            answer_row(question_id="c"),
            answer_row(question_id="d", refused=True),
            answer_row(question_id="e"),
        ]
        verdicts = {
            "a": verdict_row("incorrect"),
            "b": verdict_row("correct"),
            "c": verdict_row("correct"),
            "d": verdict_row("incorrect"),
            "e": verdict_row("partial"),
        }
        return answers, verdicts

    def test_each_category_appears_exactly_once(self) -> None:
        answers, verdicts = self.population()
        chosen = insp.select(answers, verdicts, self.args())
        seen = [insp.outcome_of(row, verdicts.get(row["question_id"])) for row in chosen]
        assert seen == sorted(set(seen), key=insp.OUTCOMES.index)
        assert set(seen) == {"correct", "partial", "refused_by_model", "refused_by_pipeline"}

    def test_each_ignores_the_limit(self) -> None:
        # A category dropped because `--limit` happened to be 2 is the rule
        # silently unmet, which is worse than not running it.
        answers, verdicts = self.population()
        chosen = insp.select(answers, verdicts, self.args(limit=1))
        assert len(chosen) == 4

    def test_filtering_by_outcome_returns_only_that_category(self) -> None:
        answers, verdicts = self.population()
        chosen = insp.select(
            answers, verdicts, self.args(each=False, outcome="refused_by_pipeline", limit=0)
        )
        assert [row["question_id"] for row in chosen] == ["a"]

    def test_fabricated_selects_only_answers_citing_a_handle_that_is_not_there(self) -> None:
        answers, verdicts = self.population()
        answers[1]["unknown_handles"] = ["rule:999.9"]
        chosen = insp.select(
            answers, verdicts, self.args(each=False, fabricated=True, limit=0)
        )
        assert [row["question_id"] for row in chosen] == ["b"]


class TestWhereTheBudgetActuallyWent:
    """E-013 asked which rules the graph cannot reach. This asks what it
    reaches instead, which is the number a repair has to beat."""

    def test_the_keyword_templates_are_the_two_that_expand_a_keyword(self) -> None:
        # Adding a third traversal to the graph without adding it here would
        # silently shrink the share and read as a repair.
        assert {"card_keyword_rules", "keyword_definition"} == insp.KEYWORD_TEMPLATES

    def test_the_share_is_computed_over_tokens_not_items(self, capsys) -> None:
        # One 900-token ruling and nine 20-token subrules are not "90% rules".
        # The budget is spent in tokens and that is what a trim would free.
        records = [
            {
                "question_id": "q",
                "stratum": "s",
                "evidence": [
                    {
                        "kind": "rule",
                        "key": "702.9a",
                        "text": "x" * 400,
                        "template": "keyword_definition",
                        "path": "(:Rule)",
                        "distance": 1,
                    },
                    {
                        "kind": "ruling",
                        "key": "abc",
                        "text": "y" * 400,
                        "template": "card_rulings",
                        "path": "(:Card)",
                        "distance": 1,
                    },
                ],
            }
        ]
        insp.context_share(records, {}, {})
        out = capsys.readouterr().out
        assert "EXPLORATORY" in out
        assert "50%" in out

    def test_a_question_with_no_gold_rules_shows_a_dash_not_a_zero(self, capsys) -> None:
        # `0/0` would read as a reach failure on a stratum that has no target.
        records = [
            {
                "question_id": "q",
                "stratum": "legality_1hop",
                "evidence": [
                    {
                        "kind": "card",
                        "key": "X",
                        "text": "t",
                        "template": "card_core",
                        "path": "(:Card)",
                        "distance": 0,
                    }
                ],
            }
        ]
        insp.context_share(records, {}, {})
        assert "—" in capsys.readouterr().out


class TestTheFilenameNamesTheConfiguration:
    """Arm discovery reads the slug, because a slug is the exact config."""

    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            ("e001_B_answers_eval.jsonl", "B"),
            ("e001_A-hybrid_answers_dev.jsonl", "A-hybrid"),
            ("e001_C-vector-hybrid-routed_answers_eval.jsonl", "C-vector-hybrid-routed"),
        ],
    )
    def test_the_slug_is_recovered(self, name: str, slug: str) -> None:
        match = insp._SLUG.match(name)
        assert match is not None
        assert match["slug"] == slug

    @pytest.mark.parametrize(
        "name", ["smoke_B_answers_eval.jsonl", "e001_B_retrieval_eval.jsonl", "notes.txt"]
    )
    def test_a_file_that_is_not_an_e001_answers_dump_is_not_an_arm(self, name: str) -> None:
        # `runs/` also holds smoke output and tagged runs, and a smoke arm
        # appearing in `--counts` would put a synthetic number beside real ones.
        assert insp._SLUG.match(name) is None
