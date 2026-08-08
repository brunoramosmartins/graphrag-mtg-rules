"""Tests for the CR version migration of manual citations.

The migration exists because rule *numbers* are not stable across CR releases
while the annotator's choice was made on rule *text*. These tests pin the four
verdicts and, above all, that a relocation is never invented: `edited` and
`orphaned` must survive `apply_plan` untouched, because guessing there would
silently corrupt the gold.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cr_migrate import (
    RELOCATION_FLOOR,
    apply_plan,
    judge,
    normalize,
    plan_migration,
    word_diff,
)

INITIATIVE = (
    "The initiative is a designation a player can have. There is no initiative "
    "in a game until an effect instructs a player to take the initiative."
)
MONARCH = (
    "The monarch is a designation a player can have. There is no monarch in a "
    "game until an effect instructs a player to become the monarch."
)


def draft_row(ruling_id: str, *rule_numbers: str) -> dict:
    return {
        "ruling_id": ruling_id,
        "cited_rules": [{"rule_number": n} for n in rule_numbers],
    }


def test_normalize_collapses_non_breaking_space_and_runs() -> None:
    assert normalize("a\u00a0b   c\n d") == "a b c d"


def test_identical_text_is_unchanged() -> None:
    verdict = judge("704.5", {"704.5": "same text"}, {"704.5": "same text"})
    assert verdict.status == "unchanged"


def test_whitespace_only_change_is_not_reported_as_edited() -> None:
    old = {"205.4c": normalize("ten\u00a0damage")}
    new = {"205.4c": normalize("ten damage")}
    assert judge("205.4c", old, new).status == "unchanged"


def test_text_moved_to_a_nearby_number_is_relocated() -> None:
    old = {"725.1": INITIATIVE}
    new = {"725.1": MONARCH, "726.1": INITIATIVE}
    verdict = judge("725.1", old, new)
    assert verdict.status == "relocated"
    assert verdict.new_number == "726.1"
    assert verdict.similarity == pytest.approx(1.0)


def test_edited_in_place_is_not_relocated() -> None:
    old = {"506.4": "A permanent is removed if its controller changes."}
    new = {"506.4": "A permanent is removed if its controller or protector changes."}
    verdict = judge("506.4", old, new)
    assert verdict.status == "edited"
    assert verdict.new_number is None
    assert verdict.similarity is not None


def test_a_weak_neighbouring_match_is_not_relocated() -> None:
    """Below the floor the tool must say "edited", not invent a destination."""
    old = {"725.1": INITIATIVE}
    new = {"725.1": MONARCH, "726.1": "Some unrelated provision about combat damage."}
    verdict = judge("725.1", old, new)
    assert verdict.status == "edited"
    assert verdict.new_number is None
    assert (verdict.similarity or 0.0) < RELOCATION_FLOOR


def test_number_gone_without_a_text_match_is_orphaned() -> None:
    old = {"999.1": "a rule that was deleted outright"}
    new = {"999.2": "an entirely different provision about something else"}
    assert judge("999.1", old, new).status == "orphaned"


def test_relocation_is_not_proposed_across_distant_chapters() -> None:
    """A match twelve chapters away is a coincidence, not a relocation."""
    old = {"100.1": INITIATIVE}
    new = {"100.1": MONARCH, "726.1": INITIATIVE}
    assert judge("100.1", old, new).status == "edited"


def test_chapter_only_citation_tracks_chapter_presence() -> None:
    new = {"704.5": "state-based actions"}
    assert judge("704", {}, new).status == "unchanged"
    assert judge("810", {}, new).status == "orphaned"


def test_plan_collects_ruling_ids_and_ranks_severest_first() -> None:
    rows = [
        draft_row("r1", "725.1"),
        draft_row("r2", "725.1", "704.5"),
        draft_row("r3", "999.1"),
    ]
    old = {"725.1": INITIATIVE, "704.5": "same text", "999.1": "deleted outright"}
    new = {"725.1": MONARCH, "726.1": INITIATIVE, "704.5": "same text"}

    verdicts = plan_migration(rows, old, new)

    assert [v.status for v in verdicts] == ["orphaned", "relocated", "unchanged"]
    relocated = next(v for v in verdicts if v.number == "725.1")
    assert relocated.ruling_ids == ["r1", "r2"]


def test_apply_remaps_relocated_and_records_provenance() -> None:
    rows = [draft_row("r1", "725.1")]
    old = {"725.1": INITIATIVE}
    new = {"725.1": MONARCH, "726.1": INITIATIVE}

    changes = apply_plan(rows, plan_migration(rows, old, new), "August 7, 2026")

    assert rows[0]["cited_rules"] == [{"rule_number": "726.1", "migrated_from": "725.1"}]
    assert rows[0]["cr_version"] == "August 7, 2026"
    assert changes == ["r1: 725.1 -> 726.1"]


def test_apply_leaves_edited_and_orphaned_citations_alone() -> None:
    rows = [draft_row("r1", "506.4"), draft_row("r2", "999.1")]
    old = {"506.4": "controller changes", "999.1": "deleted outright"}
    new = {"506.4": "controller or protector changes"}

    changes = apply_plan(rows, plan_migration(rows, old, new), "August 7, 2026")

    assert changes == []
    assert rows[0]["cited_rules"] == [{"rule_number": "506.4"}]
    assert rows[1]["cited_rules"] == [{"rule_number": "999.1"}]


def test_every_row_is_stamped_even_without_citations() -> None:
    """Unreviewed rows carry the version too — the whole draft moves at once."""
    rows = [{"ruling_id": "r1", "cited_rules": []}, {"ruling_id": "r2"}]
    apply_plan(rows, [], "August 7, 2026")
    assert all(row["cr_version"] == "August 7, 2026" for row in rows)


def test_word_diff_marks_both_sides_and_elides_unchanged_runs() -> None:
    diff = word_diff("one two three four five six seven eight", "one two three four five six seven nine")
    assert "[-eight-]" in diff
    assert "[+nine+]" in diff
    assert "[…]" in diff
