"""The sample standing rule 8 asks for, and the case it must not miss.

`flipped` decides which questions get read. On this run it selects four, and
one of them — `rg-271`, where the label moved and the answer cited nothing that
was injected — is the case that halved the reported effect. A selector that
returned only the questions whose *collapsed* outcome moved would have dropped
the ordinal movers, and the ordinal shift is a registered blocker on branch 3.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e018_inspect as insp


def table(**by_question: tuple[str, str, str]) -> dict[str, dict[str, str]]:
    return {
        qid: dict(zip(("control", "placebo", "treatment"), triple, strict=True))
        for qid, triple in by_question.items()
    }


class TestEveryCaseThatMovedIsSelected:
    def test_a_question_where_nothing_moved_is_not_selected(self) -> None:
        assert insp.flipped(table(a=("correct", "correct", "correct"))) == []

    def test_a_treatment_gain_is_selected(self) -> None:
        assert insp.flipped(table(a=("incorrect", "incorrect", "correct"))) == ["a"]

    def test_a_treatment_loss_is_selected_too(self) -> None:
        # A regression is as much a case to read as a gain, and it is what
        # branch 4 would rest on if there were more of them.
        assert insp.flipped(table(a=("partial", "partial", "incorrect"))) == ["a"]

    def test_a_placebo_move_is_selected_even_when_treatment_did_not_move(self) -> None:
        # The placebo is the registered falsifier. A placebo that moves is
        # exactly the evidence that would send the entry to branch 2.
        assert insp.flipped(table(a=("correct", "partial", "correct"))) == ["a"]

    def test_a_move_inside_the_collapse_is_still_selected(self) -> None:
        # incorrect -> partial does not change the two-way outcome, and it is
        # precisely what the ordinal blocker counts. Selecting only collapsed
        # movers would hide the evidence that stops branch 3 firing.
        assert insp.flipped(table(a=("incorrect", "incorrect", "partial"))) == ["a"]

    def test_a_question_with_no_control_row_is_skipped_not_guessed(self) -> None:
        # Without a control there is nothing to have moved from.
        assert insp.flipped({"a": {"treatment": "correct"}}) == []

    def test_the_selection_is_ordered_so_two_readings_cover_the_same_cases(self) -> None:
        selected = insp.flipped(
            table(
                zebra=("incorrect", "incorrect", "correct"),
                alpha=("incorrect", "incorrect", "correct"),
            )
        )
        assert selected == ["alpha", "zebra"]


class TestTheCliSuppliesWhatPrepareReads:
    """`prepare` reads four attributes off the namespace it is given.

    The inspector built its own namespace and supplied three of them, so every
    invocation raised `AttributeError: 'Namespace' object has no attribute
    'population'` — after the imports, before any output. The tool was
    unrunnable from the day it was written and nothing said so, because no test
    reached the parser.
    """

    def test_every_attribute_prepare_reads_is_on_the_namespace(self) -> None:
        args = insp.build_parser().parse_args(["--qid", "rg-51"])
        for attribute in ("population", "limit", "golden", "caches"):
            assert hasattr(args, attribute), attribute

    def test_the_population_defaults_to_the_one_the_run_used(self) -> None:
        args = insp.build_parser().parse_args(["--qid", "rg-51"])
        assert args.population == "primary"

    def test_the_population_is_restricted_to_the_frozen_ones(self) -> None:
        with pytest.raises(SystemExit):
            insp.build_parser().parse_args(["--qid", "rg-51", "--population", "invented"])


class TestTheRunFileFollowsThePopulation:
    """Reading one population's run against the other's rebuild is not a caveat.

    The digest check would refuse it, which is correct but arrives as a wall of
    hash mismatches. Deriving the path means the two cannot be crossed by
    forgetting a flag.
    """

    def test_each_population_resolves_to_its_own_run_file(self) -> None:
        primary = insp.outputs("primary")[1]
        present = insp.outputs("present")[1]
        assert primary != present

    def test_an_explicit_run_path_still_wins(self) -> None:
        args = insp.build_parser().parse_args(["--qid", "rg-51", "--run", "runs/other.jsonl"])
        assert args.run is not None
        assert args.run.name == "other.jsonl"
