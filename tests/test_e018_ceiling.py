"""The refusals that stand between E-018's populations and E-018's first call.

Everything here guards a way the ceiling could come out looking right while
measuring something else: a population quietly recomputed after it was frozen,
a half-read sheet scored as if it were finished, and a gold rule rendered as a
one-word heading so the reader judges derivability from the word "Goad".

The gate itself is a pure arithmetic claim registered before the reading — a
ceiling below 7 of 21 makes E-018's branch 1 unreachable whatever the
intervention does — so it is tested as a constant, not re-derived.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e018_ceiling as ceiling


@dataclass
class FakeRule:
    number: str
    text: str


class FakeCR:
    """Enough of a `CRDocument` to render a block, and nothing more."""

    def __init__(self, rules: list[FakeRule]) -> None:
        self._rules = rules

    @property
    def by_number(self) -> dict[str, FakeRule]:
        return {rule.number: rule for rule in self._rules}

    def subtree(self, number: str) -> list[FakeRule]:
        return [rule for rule in self._rules if rule.number.startswith(number)]


class TestFrozenMeansFrozen:
    """A population that can be silently recomputed is not a population."""

    def test_a_first_write_lands(self, tmp_path: Path) -> None:
        path = tmp_path / "ids.json"
        ceiling.freeze_file(path, ["a", "b"], what="primary")
        assert json.loads(path.read_text(encoding="utf-8"))["ids"] == ["a", "b"]

    def test_rewriting_the_same_ids_is_accepted(self, tmp_path: Path) -> None:
        path = tmp_path / "ids.json"
        ceiling.freeze_file(path, ["a", "b"], what="primary")
        ceiling.freeze_file(path, ["a", "b"], what="primary")
        assert json.loads(path.read_text(encoding="utf-8"))["ids"] == ["a", "b"]

    def test_a_changed_population_raises_and_names_both_directions(self, tmp_path: Path) -> None:
        # The failure this prevents: the golden set or the harness moves, the
        # file is rewritten, and the entry now measures a different population
        # under the same registered name.
        path = tmp_path / "ids.json"
        ceiling.freeze_file(path, ["a", "b"], what="primary")
        with pytest.raises(SystemExit) as raised:
            ceiling.freeze_file(path, ["a", "c"], what="primary")
        message = str(raised.value)
        assert "no longer present: ['b']" in message
        assert "newly present:     ['c']" in message

    def test_the_file_is_not_modified_when_it_disagrees(self, tmp_path: Path) -> None:
        path = tmp_path / "ids.json"
        ceiling.freeze_file(path, ["a", "b"], what="primary")
        with pytest.raises(SystemExit):
            ceiling.freeze_file(path, ["a"], what="primary")
        assert json.loads(path.read_text(encoding="utf-8"))["ids"] == ["a", "b"]


class TestABlankIsNotAFalse:
    """A ceiling over a half-read sheet is a ceiling over a reading order."""

    def sheet(self) -> list[dict]:
        return [
            {"question_id": "a", "derivable": True, "stale": False},
            {"question_id": "b", "derivable": False, "stale": False},
            {"question_id": "c", "derivable": None, "stale": False},
            {"question_id": "d", "derivable": False, "stale": True},
        ]

    def test_the_three_groups_are_separated(self) -> None:
        derivable, stale, blank = ceiling.partition(self.sheet())
        assert derivable == ["a"]
        assert stale == ["d"]
        assert blank == ["c"]

    def test_a_blank_is_neither_derivable_nor_false(self) -> None:
        derivable, _, blank = ceiling.partition(self.sheet())
        assert "c" not in derivable
        assert blank == ["c"]

    def test_a_stale_question_is_not_blank_and_does_not_hold_up_the_score(self) -> None:
        # There is no "these rules" to judge against when the annotation
        # points at a number this CR uses for something else, so a stale
        # question is answerable by nobody. It must not read as unread work.
        _, stale, blank = ceiling.partition(
            [{"question_id": "x", "derivable": None, "stale": True}]
        )
        assert stale == ["x"]
        assert blank == []

    def test_stale_is_recorded_beside_an_answer_when_the_reader_gave_one(self) -> None:
        # `stale` is a defect in the key file, not a fact about the corpus,
        # so it survives alongside whatever the reader answered.
        derivable, stale, _ = ceiling.partition(
            [{"question_id": "x", "derivable": True, "stale": True}]
        )
        assert derivable == ["x"]
        assert stale == ["x"]

    def test_a_sheet_with_no_stale_field_at_all_is_read_as_none_stale(self) -> None:
        derivable, stale, blank = ceiling.partition([{"question_id": "x", "derivable": True}])
        assert (derivable, stale, blank) == (["x"], [], [])


class TestTheReaderSeesWhatTheRuleActuallySays:
    """Judging derivability from the word "Deathtouch" is not judging it."""

    def test_a_rule_with_substance_renders_its_text(self) -> None:
        cr = FakeCR([FakeRule("704.5f", "If a creature has toughness 0 or less, it dies.")])
        block = ceiling.rule_block("704.5f", cr)
        assert block == ["- **704.5f** — If a creature has toughness 0 or less, it dies."]

    def test_a_heading_rule_is_flagged_and_its_subrules_are_shown(self) -> None:
        cr = FakeCR(
            [
                FakeRule("701.15", "Goad"),
                FakeRule("701.15a", "Certain spells can goad a creature."),
                FakeRule("701.15b", "Goaded is a designation."),
            ]
        )
        block = ceiling.rule_block("701.15", cr)
        assert "⚠" in block[1]
        assert "stale" in block[1]
        assert any("701.15a" in line for line in block)
        assert any("701.15b" in line for line in block)

    def test_subrules_are_rendered_for_a_parent_that_has_real_text_too(self) -> None:
        # `613.7` carries substance AND thirteen subrules. A reader asked
        # whether a key follows from it cannot answer from the parent alone.
        cr = FakeCR(
            [
                FakeRule("613.7", "Some continuous effects have a timestamp." * 3),
                FakeRule("613.7a", "An object receives a timestamp when it enters."),
            ]
        )
        block = ceiling.rule_block("613.7", cr)
        assert "⚠" not in "".join(block)
        assert any("613.7a" in line for line in block)

    def test_a_number_this_cr_does_not_have_says_so_rather_than_rendering_blank(self) -> None:
        block = ceiling.rule_block("999.9", FakeCR([]))
        assert len(block) == 1
        assert "NOT IN THIS CR" in block[0]


class TestTheReaderIsJudgingTheContextTheTreatmentProduces:
    """Control plus the rules, not the rules alone — see amendment 2026-09-13b."""

    def test_the_evidence_already_present_is_listed_by_kind_and_handle(self) -> None:
        # A count would not do. "12 rulings" does not tell a reader whether
        # the ruling the key turns on is among them, and that is the judgement.
        record = {
            "evidence": [
                {"kind": "card", "key": "Blood Moon"},
                {"kind": "card", "key": "Gaea's Cradle"},
                {"kind": "rule", "key": "701.26"},
            ]
        }
        summary = ceiling.evidence_summary(record)
        assert "2 card: `Blood Moon`, `Gaea's Cradle`" in summary
        assert "1 rule: `701.26`" in summary

    def test_an_empty_subgraph_says_so_rather_than_rendering_nothing(self) -> None:
        # A blank line here would read as "no evidence listed" and be judged
        # as though the context were merely unremarkable.
        assert "nothing" in ceiling.evidence_summary({"evidence": []}).lower()

    def test_the_question_is_about_the_retrieved_context_plus_the_rules(self) -> None:
        # The earlier phrasing asked whether the key followed from the rules
        # alone, which would mark false exactly where the card text was
        # present and the rule was the only missing piece.
        assert "retrieval already brought" in ceiling.QUESTION
        assert "alone" not in ceiling.QUESTION


class TestTheGateWasRegisteredBeforeTheReading:
    """The arithmetic behind it, kept where a later edit would trip a test."""

    def test_the_gate_is_seven(self) -> None:
        # 0.333 x 21 rounded up. 0.333 is the smallest net lift that clears
        # the strict Holm step at n = 21 (7:0 discordant, exact p = 0.0156).
        assert ceiling.GATE == 7

    def test_the_arm_and_split_are_the_registered_ones(self) -> None:
        # E-018 is a within-arm intervention on arm B's evaluation run. An
        # arm swap here would produce a ceiling for a different experiment.
        assert (ceiling.ARM, ceiling.SPLIT) == ("B", "eval")

    def test_the_worksheet_stays_out_of_git(self) -> None:
        # It carries CR rule text and answer keys, which the Fan Content
        # Policy forbids committing. `data/interim/` is gitignored; the
        # verdict file carries ids and booleans only and is versioned.
        assert ceiling.WORKSHEET.parts[:2] == ("data", "interim")
        assert ceiling.VERDICTS.parts[:2] == ("data", "golden")
        assert ceiling.ABSENT_IDS.parts[:2] == ("data", "golden")
