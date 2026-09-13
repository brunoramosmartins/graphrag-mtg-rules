"""The refusals that stand between E-014's files and E-014's branch.

E-014 changes exactly one thing — the generator — and every guard here exists
because something else could change quietly and produce a number that looks
identical to a clean one: a resumed run that switched model mid-flight, an
edited prompt, a harness change that altered which questions are excluded.

The registered prediction that the two runs cover *identical* question sets is
not a nicety. Exclusion is decided by retrieval, before any model call, so a
difference is proof the harness moved. It is tested here as a hard failure.

The branch rule is tested as a pure function, including the case it was written
to prevent: a D that narrows without a significant paired contrast is branch 3,
never branch 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e014_analysis as ana
from run_e012 import SIZES, parse_sizes, refuse_if_unloaded


def row(qid: str, hops: int, k: int, correct: bool, *, model="gpt-4o", prompt="a3") -> dict:
    return {
        "qid": qid,
        "hops": hops,
        "k": k,
        "items": k,
        "predicted": ["x"],
        "correct": correct,
        "refused": False,
        "prompt_version": prompt,
        "model": model,
    }


def pair_of_runs(
    *, base_correct: dict[int, int], treat_correct: dict[int, int], n: int = 10
) -> tuple[list[dict], list[dict]]:
    """Two runs over the same question ids, with a chosen number of hits per hop."""
    base: list[dict] = []
    treat: list[dict] = []
    for hops in (1, 2, 3):
        for index in range(n):
            qid = f"q{hops}-{index}"
            base.append(
                row(qid, hops, 16, index < base_correct[hops], model=ana.BASELINE_MODEL)
            )
            treat.append(row(qid, hops, 16, index < treat_correct[hops]))
    return base, treat


# --- parse_sizes -------------------------------------------------------------


def test_parse_sizes_accepts_registered_sizes_and_returns_registered_order():
    assert parse_sizes("256,16") == (16, 256)


def test_parse_sizes_refuses_a_size_e012_never_registered():
    # A cell with no gpt-4o-mini counterpart has nothing to pair against, and
    # the pairing is the whole design.
    assert 32 not in SIZES
    with pytest.raises(SystemExit):
        parse_sizes("32")


def test_parse_sizes_refuses_duplicates_and_junk_and_empty():
    for bad in ("16,16", "sixteen", "", " , "):
        with pytest.raises(SystemExit):
            parse_sizes(bad)


# --- an empty KB must not read as a clean run --------------------------------


def test_every_question_excluded_is_refused_as_an_empty_kb():
    # What an unloaded MetaQA instance produces. Before this guard it printed
    # "Nothing to answer" and exited 0, which is what a legitimate run prints.
    with pytest.raises(SystemExit) as caught:
        refuse_if_unloaded(900, 900)
    assert "run_e002.py load" in str(caught.value)


def test_a_high_but_partial_exclusion_rate_is_allowed():
    # E-012's own confirmatory run excluded 213 of 900 and is a valid result;
    # the guard must not second-guess a number the registration already owns.
    refuse_if_unloaded(900, 213)
    refuse_if_unloaded(900, 899)


def test_the_guard_does_not_fire_on_an_empty_question_list():
    # `--limit 0` on a filtered split is a different mistake with its own
    # message; this guard claims nothing about it.
    refuse_if_unloaded(0, 0)


# --- guards ------------------------------------------------------------------


def test_guards_pass_on_two_clean_runs():
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    base_model, treat_model = ana.guards(base, treat, Path("b.jsonl"), Path("t.jsonl"))
    assert base_model == ana.BASELINE_MODEL
    assert treat_model == "gpt-4o"


def test_guards_refuse_a_file_written_by_two_models():
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    treat[0] = {**treat[0], "model": "gpt-4o-mini"}
    with pytest.raises(SystemExit):
        ana.guards(base, treat, Path("b.jsonl"), Path("t.jsonl"))


def test_guards_refuse_when_both_files_hold_the_same_model():
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    treat = [{**r, "model": ana.BASELINE_MODEL} for r in treat]
    with pytest.raises(SystemExit):
        ana.guards(base, treat, Path("b.jsonl"), Path("t.jsonl"))


def test_guards_refuse_an_edited_prompt():
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    treat = [{**r, "prompt_version": "a4"} for r in treat]
    with pytest.raises(SystemExit):
        ana.guards(base, treat, Path("b.jsonl"), Path("t.jsonl"))


def test_guards_refuse_when_the_runs_cover_different_questions():
    """Registered prediction 4: exclusion happens before any model call."""
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    treat = [r for r in treat if r["qid"] != "q3-4"]
    with pytest.raises(SystemExit):
        ana.guards(base, treat, Path("b.jsonl"), Path("t.jsonl"))


def test_cell_refuses_a_duplicated_question():
    rows = [row("q1", 3, 16, True), row("q1", 3, 16, False)]
    with pytest.raises(SystemExit):
        ana.cell(rows, 3, 16)


# --- the instrument check, which must be able to fail ------------------------


def test_instrument_check_passes_when_one_hop_barely_moves():
    base, treat = pair_of_runs(
        base_correct={1: 9, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    ok, gain = ana.instrument_ok(base, treat)
    assert ok and gain == pytest.approx(0.0)


def test_instrument_check_fails_when_one_hop_jumps():
    # One hop at k=16 involves no chaining. A 0.30 gain there is formatting or
    # answer-matching, and the depth cells stop being readable as reasoning.
    base, treat = pair_of_runs(
        base_correct={1: 6, 2: 7, 3: 5}, treat_correct={1: 9, 2: 8, 3: 8}
    )
    ok, gain = ana.instrument_ok(base, treat)
    assert not ok
    assert gain == pytest.approx(0.30)


# --- the registered branch rule ----------------------------------------------


def test_branch_1_needs_both_halves():
    assert ana.branch(0.10, rejected=True) == "1"


def test_a_narrowed_spread_on_noise_is_branch_3_not_branch_1():
    """The case the ordering exists to prevent."""
    assert ana.branch(0.10, rejected=False) == "3"


def test_branch_2_holds_whatever_the_paired_test_says():
    # D >= 0.25 is the depth effect surviving; a significant paired contrast
    # there means the model improved everywhere, not that depth stopped costing.
    assert ana.branch(0.30, rejected=True) == "2"
    assert ana.branch(0.30, rejected=False) == "2"


def test_the_middle_band_is_branch_3():
    assert ana.branch(0.20, rejected=True) == "3"


def test_the_boundaries_are_inclusive_as_registered():
    assert ana.branch(ana.BRANCH_1_MAX_D, rejected=True) == "1"
    assert ana.branch(ana.BRANCH_2_MIN_D, rejected=True) == "2"


def test_the_published_prior_is_outside_branch_1():
    """E-012's own D must land in branch 2, or the rule was written to pass."""
    prior = ana.E012_K16[1] - ana.E012_K16[3]
    assert prior == pytest.approx(0.379)
    assert ana.branch(prior, rejected=True) == "2"


# --- Holm --------------------------------------------------------------------


def test_holm_stops_rejecting_at_the_first_failure():
    adjusted = ana.holm({"1-hop": 0.001, "2-hop": 0.400, "3-hop": 0.410})
    assert adjusted["1-hop"][1] is True
    assert adjusted["2-hop"][1] is False
    assert adjusted["3-hop"][1] is False


def test_holm_adjusted_p_is_monotone_and_clipped():
    adjusted = ana.holm({"a": 0.02, "b": 0.30, "c": 0.40})
    values = [adjusted[k][0] for k in ("a", "b", "c")]
    assert values == sorted(values)
    assert all(v <= 1.0 for v in values)
