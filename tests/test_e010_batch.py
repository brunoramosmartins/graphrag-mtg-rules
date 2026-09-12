"""What a batch of verdicts must refuse.

Labelling 180 slots one command at a time is 180 chances to lose one, and
the author lost one already: `guess s0003 graph && label s0003 irrelevant`
on a slot outside the blinding subsample, where the guess exited non-zero
and the `&&` swallowed the label. The batch entry point exists to stop
that, so its tests are about the ways a batch can *look* applied while
part of it was not.

Two invariants carry the instrument:

1. All-or-nothing. A batch that writes the first six lines and dies on the
   seventh leaves the annotator guessing which six landed — the same
   failure, moved.
2. The guess precedes the relevance. A subsample slot with no guess on
   file cannot be labelled in the two-token form, because once the item
   has been read for relevance the guess is no longer a blind one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e010 as e010


SAMPLE = {
    "blinding_subsample": ["s0001"],
    "blind_claim_withdrawn_above": 0.70,
    "slots": [
        {"slot": "s0000", "question_id": "q0", "arm": "A"},
        {"slot": "s0001", "question_id": "q0", "arm": "B"},
        {"slot": "s0002", "question_id": "q1", "arm": "C"},
    ],
}


def test_plain_line_outside_the_subsample() -> None:
    plan = e010._parse_batch(["s0000 relevant"], SAMPLE, {})
    assert plan == [{"slot": "s0000", "relevance": "relevant"}]


def test_comments_and_blank_lines_are_skipped() -> None:
    lines = ["", "  ", "# the template's own header", "s0002 irrelevant  # noisy card"]
    plan = e010._parse_batch(lines, SAMPLE, {})
    assert plan == [{"slot": "s0002", "relevance": "irrelevant"}]


def test_subsample_slot_carries_its_guess_first() -> None:
    plan = e010._parse_batch(["s0001 graph relevant"], SAMPLE, {})
    assert plan == [{"slot": "s0001", "guess": "graph", "relevance": "relevant"}]
    # The dict order is the claim: written this way, `batch` cannot record a
    # relevance and then backfill the guess that was supposed to precede it.
    assert list(plan[0]) == ["slot", "guess", "relevance"]


def test_subsample_slot_without_a_guess_is_refused() -> None:
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0001 relevant"], SAMPLE, {})
    assert "blinding subsample" in str(excinfo.value)


def test_subsample_slot_with_a_recorded_guess_takes_the_short_form() -> None:
    rows = {"s0001": {"slot": "s0001", "guess": "A"}}
    plan = e010._parse_batch(["s0001 relevant"], SAMPLE, rows)
    assert plan == [{"slot": "s0001", "relevance": "relevant"}]


def test_a_guess_is_not_revised_on_the_way_in() -> None:
    rows = {"s0001": {"slot": "s0001", "guess": "A"}}
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0001 graph relevant"], SAMPLE, rows)
    assert "already guessed" in str(excinfo.value)


def test_guess_on_a_slot_outside_the_subsample_is_refused() -> None:
    # The shape that started this: a guess where none is wanted. It must fail
    # loudly rather than be dropped, or the annotator believes 36 slots carry
    # a blinding check when only the real subsample does.
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0000 graph relevant"], SAMPLE, {})
    assert "not in the blinding subsample" in str(excinfo.value)


def test_relabelling_is_refused() -> None:
    rows = {"s0000": {"slot": "s0000", "relevance": "relevant"}}
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0000 irrelevant"], SAMPLE, rows)
    assert "already labelled" in str(excinfo.value)


def test_a_slot_twice_in_one_batch_is_refused() -> None:
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0000 relevant", "s0000 irrelevant"], SAMPLE, {})
    assert "twice" in str(excinfo.value)


def test_unknown_slot_and_unknown_verdict() -> None:
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s9999 relevant"], SAMPLE, {})
    assert "no such slot" in str(excinfo.value)
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(["s0000 maybe"], SAMPLE, {})
    assert "relevance must be" in str(excinfo.value)


def test_one_bad_line_reports_every_error_and_writes_nothing() -> None:
    lines = ["s0000 relevant", "s0001 relevant", "s9999 irrelevant"]
    with pytest.raises(SystemExit) as excinfo:
        e010._parse_batch(lines, SAMPLE, {})
    message = str(excinfo.value)
    # Both failures surface in one pass — fixing them one round-trip at a time
    # is how a 180-slot pass becomes unbearable.
    assert "blinding subsample" in message
    assert "no such slot" in message
    assert "Nothing was written" in message
