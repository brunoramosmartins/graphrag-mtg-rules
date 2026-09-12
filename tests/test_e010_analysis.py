"""The guards that have to fire before E-010's verdict is printed.

The registered rule for part (a) is mechanical — an accuracy against 0.70, a
direction against zero — so the risk is never that the rule is misapplied. It
is that the rule is applied to data that does not support it: a partial pass
read as complete, a stray guess changing the blinding denominator, an unbalanced
sample read as a paired design. Every one of those prints a number that looks
exactly like a number from a clean run.

So these tests are about refusals, plus the one property of the bootstrap that
makes it the registered analysis rather than a narrower one: it resamples
questions, carrying both arms together, not slots.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e010_analysis as ana


def make(slots: list[tuple[str, str, str]], subsample: list[str]) -> dict:
    return {
        "blinding_subsample": subsample,
        "slots": [
            {"slot": slot, "question_id": qid, "arm": arm} for slot, qid, arm in slots
        ],
    }


SLOTS = [
    ("s0", "q1", "A"), ("s1", "q1", "B"),
    ("s2", "q2", "A"), ("s3", "q2", "B"),
]
SAMPLE = make(SLOTS, ["s0"])
ITEMS = {s: {"slot": s, "kind": "rule", "tokens": 10} for s, _, _ in SLOTS}


def complete_rows() -> dict[str, dict]:
    rows = {s: {"slot": s, "relevance": "relevant"} for s, _, _ in SLOTS}
    rows["s0"]["guess"] = "A"
    return rows


def test_a_complete_pass_passes() -> None:
    ana.guard(SAMPLE, ITEMS, complete_rows(), interim=False)


def test_partial_pass_is_refused_without_interim() -> None:
    rows = complete_rows()
    del rows["s3"]
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "unlabelled" in str(excinfo.value)


def test_partial_pass_is_tolerated_under_interim() -> None:
    rows = complete_rows()
    del rows["s3"]
    ana.guard(SAMPLE, ITEMS, rows, interim=True)


def test_missing_guess_on_a_subsample_slot_is_refused() -> None:
    rows = complete_rows()
    del rows["s0"]["guess"]
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "without a guess" in str(excinfo.value)


def test_a_stray_guess_outside_the_subsample_is_refused() -> None:
    # Not cosmetic: the published blinding figure has a denominator, and a
    # guess recorded where none was asked changes it.
    rows = complete_rows()
    rows["s2"]["guess"] = "graph"
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "outside the blinding subsample" in str(excinfo.value)


def test_unbalanced_arms_are_refused() -> None:
    sample = make(SLOTS + [("s4", "q3", "A")], ["s0"])
    items = dict(ITEMS, s4={"slot": "s4", "kind": "rule", "tokens": 10})
    rows = complete_rows()
    rows["s4"] = {"slot": "s4", "relevance": "relevant"}
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(sample, items, rows, interim=False)
    assert "unbalanced" in str(excinfo.value)


def test_values_outside_the_producers_encoding_are_refused() -> None:
    rows = complete_rows()
    rows["s1"]["relevance"] = "maybe"
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "relevance values outside" in str(excinfo.value)

    rows = complete_rows()
    rows["s0"]["guess"] = "B"
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "guesses outside" in str(excinfo.value)


def test_labels_for_unknown_slots_are_refused() -> None:
    rows = complete_rows()
    rows["s99"] = {"slot": "s99", "relevance": "relevant"}
    with pytest.raises(SystemExit) as excinfo:
        ana.guard(SAMPLE, ITEMS, rows, interim=False)
    assert "not in the sample" in str(excinfo.value)


def test_cells_key_on_question_and_arm() -> None:
    cell = ana.cells(SAMPLE, ITEMS, complete_rows())
    assert set(cell) == {("q1", "A"), ("q1", "B"), ("q2", "A"), ("q2", "B")}
    assert cell[("q1", "A")] == {"hits": 1, "n": 1, "rel_tokens": 10, "tokens": 10}


def test_the_bootstrap_pairs_within_a_question() -> None:
    """A resample carries both arms of a question or neither.

    This is the whole reason the registered analysis is a *cluster* bootstrap.
    Build a case where one question favours A and the other favours B by the
    same amount: the paired difference is exactly zero in every resample,
    because each draw takes both arms together. An unpaired bootstrap over
    slots would wobble around zero instead.
    """
    cell = {
        ("q1", "A"): {"hits": 4, "n": 4, "rel_tokens": 40, "tokens": 40},
        ("q1", "B"): {"hits": 0, "n": 4, "rel_tokens": 0, "tokens": 40},
        ("q2", "A"): {"hits": 0, "n": 4, "rel_tokens": 0, "tokens": 40},
        ("q2", "B"): {"hits": 4, "n": 4, "rel_tokens": 40, "tokens": 40},
    }
    point, low, high = ana.paired_diff(cell, ["q1", "q2"], "A", "B", 0, 0.05)
    assert point == pytest.approx(0.0)
    # Resampling {q1,q1} gives +1, {q2,q2} gives -1: the interval is wide, and
    # it is wide for a reason the reader can name — two clusters.
    assert low == pytest.approx(-1.0)
    assert high == pytest.approx(1.0)


def test_token_index_reads_the_token_normalised_figure() -> None:
    cell = {
        ("q1", "A"): {"hits": 1, "n": 2, "rel_tokens": 90, "tokens": 100},
        ("q1", "B"): {"hits": 1, "n": 2, "rel_tokens": 10, "tokens": 100},
    }
    # Identical item precision, opposite token-normalised precision — index 1
    # has to see the difference index 0 cannot.
    assert ana.paired_diff(cell, ["q1"], "A", "B", 0, 0.05)[0] == pytest.approx(0.0)
    assert ana.paired_diff(cell, ["q1"], "A", "B", 1, 0.05)[0] == pytest.approx(0.8)
