"""The correctness rubric: one hashed object, and what blinding removes.

E-011 fixes the judge's threshold as the lower bound of a human ceiling
"scored as the same correctness rubric the judge uses". These tests hold
the two properties that sentence depends on: the rubric is a single
constant whose hash moves when its text moves, and the rendering both
readers receive is the same one.
"""

from __future__ import annotations

from graphrag_mtg.evaluation import rubric
from graphrag_mtg.evaluation.rubric import (
    JUDGED,
    Correctness,
    render_for_judgement,
    rubric_hash,
)


class TestRubricHash:
    def test_is_stable_across_calls(self) -> None:
        assert rubric_hash() == rubric_hash()

    def test_moves_when_the_text_moves(self, monkeypatch) -> None:
        before = rubric_hash()
        monkeypatch.setattr(rubric, "RUBRIC", rubric.RUBRIC + "\n  7. Extra tie-break.\n")
        assert rubric_hash() != before

    def test_moves_when_the_version_moves(self, monkeypatch) -> None:
        before = rubric_hash()
        monkeypatch.setattr(rubric, "RUBRIC_VERSION", "p6-c2")
        assert rubric_hash() != before

    def test_moves_when_the_blinding_rule_moves(self, monkeypatch) -> None:
        # The blinding rule changes what the reader sees without changing a
        # single label definition, so it has to be inside the hash.
        before = rubric_hash()
        monkeypatch.setattr(rubric, "BLINDING", "Handles are shown.")
        assert rubric_hash() != before


class TestLabels:
    def test_void_is_not_a_judged_label(self) -> None:
        # Void says the key does not answer its own question. It describes
        # the key, not the answer, and E-011 excludes it from every
        # denominator — including the ceiling's.
        assert Correctness.VOID not in JUDGED

    def test_judged_labels_are_the_three_way_call(self) -> None:
        assert JUDGED == (Correctness.CORRECT, Correctness.PARTIAL, Correctness.INCORRECT)


class TestRenderForJudgement:
    def test_strips_citation_handles(self) -> None:
        text = "Trample assigns the excess [rule:702.19b] to the player [card:Rancor]."
        assert "[" not in render_for_judgement(text)

    def test_closes_the_gap_a_removed_handle_leaves(self) -> None:
        # A space before the full stop is a typo the model did not make,
        # and a reader who notices it knows a handle stood there — the
        # arm-identifying tell the blinding exists to remove.
        rendered = render_for_judgement("The creature dies [rule:704.5g].")
        assert rendered == "The creature dies."

    def test_keeps_paragraph_structure(self) -> None:
        rendered = render_for_judgement("First [rule:1.1].\n\nSecond [rule:2.2].")
        assert rendered.splitlines() == ["First.", "", "Second."]

    def test_is_idempotent(self) -> None:
        # The worksheet hashes this output; a second application must not
        # produce a third string, or the guard would fire on itself.
        once = render_for_judgement("A [card:Rancor] b [rule:702.19b].")
        assert render_for_judgement(once) == once

    def test_leaves_reminder_text_braces_alone(self) -> None:
        # Mana costs are square-bracket-free but curly-brace heavy, and an
        # over-eager stripper would eat the answer's substance.
        assert "{2}{G}" in render_for_judgement("It costs {2}{G} [card:Rancor].")
