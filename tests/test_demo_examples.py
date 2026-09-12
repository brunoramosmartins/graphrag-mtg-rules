"""A question the repository is not allowed to redistribute is not a crash.

The golden set stores RulesGuru rows as `question: null` on purpose — the repo
versions their ids and a gitignored fetch retrieves the text. Eight of the
twenty development questions are such rows, so on a clean clone the demo's
example picker has eight `None`s to handle, and the first version handled them
by slicing one: `row["question"][:90]`, `TypeError`, dead page.

These tests pin the two behaviours that matter: a missing text never raises,
and the count of withheld questions is returned rather than dropped — a picker
that is quietly short looks broken, one that says "8 not listed, and here is
why" looks like compliance, which is what it is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from examples import question_text, resolve


def write_cache(root: Path, name: str, qid: str, payload: dict) -> Path:
    cache = root / name
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{qid}.json").write_text(json.dumps(payload), encoding="utf-8")
    return cache


def test_inline_text_is_used_when_present(tmp_path: Path) -> None:
    row = {"id": "hand-1", "question": "What does trample do?"}
    assert question_text(row, tmp_path, caches=[Path("nowhere")]) == "What does trample do?"


def test_a_null_question_falls_back_to_the_cache(tmp_path: Path) -> None:
    write_cache(tmp_path, "cache", "rg-1", {"questionSimple": "From the fetch."})
    row = {"id": "rg-1", "question": None}
    assert question_text(row, tmp_path, caches=[Path("cache")]) == "From the fetch."


def test_the_simple_field_wins_over_the_long_one(tmp_path: Path) -> None:
    # Both pools write both fields; `questionSimple` is the one the harness
    # reads, so the demo must read the same one or the screenshot and the
    # experiment disagree about what was asked.
    write_cache(tmp_path, "cache", "rg-1", {"questionSimple": "short", "question": "long"})
    assert question_text({"id": "rg-1"}, tmp_path, caches=[Path("cache")]) == "short"


def test_caches_are_consulted_in_order(tmp_path: Path) -> None:
    write_cache(tmp_path, "second", "rg-1", {"questionSimple": "second"})
    write_cache(tmp_path, "first", "rg-1", {"questionSimple": "first"})
    found = question_text({"id": "rg-1"}, tmp_path, caches=[Path("first"), Path("second")])
    assert found == "first"


def test_a_cache_entry_with_no_text_falls_through(tmp_path: Path) -> None:
    # An empty payload must not count as a hit, or the picker lists a blank
    # entry that retrieves nothing and looks like a pipeline failure.
    write_cache(tmp_path, "first", "rg-1", {"answerSimple": "only the answer"})
    write_cache(tmp_path, "second", "rg-1", {"questionSimple": "the question"})
    found = question_text({"id": "rg-1"}, tmp_path, caches=[Path("first"), Path("second")])
    assert found == "the question"


def test_nothing_anywhere_returns_empty_rather_than_raising(tmp_path: Path) -> None:
    # The harness's question_and_key raises SystemExit here. Correct for a
    # batch script, fatal for a page.
    assert question_text({"id": "rg-1", "question": None}, tmp_path) == ""


def test_resolve_reports_what_it_withheld(tmp_path: Path) -> None:
    write_cache(tmp_path, "cache", "rg-2", {"questionSimple": "fetched"})
    rows = [
        {"id": "hand-1", "question": "inline"},
        {"id": "rg-2", "question": None},
        {"id": "rg-3", "question": None},
    ]
    kept, withheld = resolve(rows, tmp_path, caches=[Path("cache")])
    assert [row["id"] for row in kept] == ["hand-1", "rg-2"]
    assert withheld == 1


def test_resolve_does_not_mutate_the_rows_it_was_given(tmp_path: Path) -> None:
    rows = [{"id": "rg-1", "question": None}]
    resolve(rows, tmp_path, caches=[Path("cache")])
    assert rows[0]["question"] is None


def test_every_row_missing_yields_an_empty_list_not_an_error(tmp_path: Path) -> None:
    rows = [{"id": f"rg-{i}", "question": None} for i in range(8)]
    kept, withheld = resolve(rows, tmp_path, caches=[Path("cache")])
    assert kept == []
    assert withheld == 8
