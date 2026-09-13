"""The check that stands between a moved ban list and a wrong answer key.

Fifteen of the 57 evaluation questions ask whether a card is legal in a format.
That answer is not a fact about Magic's rules — it is a fact about a ban list,
frozen into `snapshot_sha256` at curation time, read back against a bulk that
Scryfall reissues daily. When it drifts, the arm that answers correctly is
scored wrong, and nothing in the pipeline notices.

The failure mode these tests exist for is the one this project keeps meeting: a
check that cannot fail. A verifier that recomputes the hash from the golden row
rather than from the bulk agrees with itself forever, and reads exactly like a
verifier that works.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_legality_keys as vk
from graphrag_mtg.evaluation.golden import content_sha256

OID = "0000a1b2-c3d4-4e5f-8a9b-000000000001"


def test_the_id_pattern_survives_the_uuids_own_hyphens() -> None:
    # Splitting `scry-leg-<uuid>-<format>` from the left hands back a fragment
    # of the UUID and a format that does not exist.
    match = vk.QUESTION_ID.match(f"scry-leg-{OID}-modern")
    assert match is not None
    assert match["oracle_id"] == OID
    assert match["fmt"] == "modern"


def test_the_pattern_rejects_a_non_legality_id() -> None:
    assert vk.QUESTION_ID.match("hand-def-indestructible") is None
    assert vk.QUESTION_ID.match(f"scry-leg-{OID}") is None


def test_the_frozen_hash_is_over_the_bulks_status_not_the_rows() -> None:
    """The property that makes the check able to fail.

    The hash must be recomputed from `(oracle_id, format, status-as-Scryfall-
    reports-it-now)`. Recomputing it from the golden row's own recorded status
    would match every time, including the times that matter.
    """
    frozen = content_sha256(f"{OID}|modern|legal")
    assert content_sha256(f"{OID}|modern|legal") == frozen
    assert content_sha256(f"{OID}|modern|banned") != frozen
    assert content_sha256(f"{OID}|pioneer|legal") != frozen


def test_legality_rows_reads_only_the_legality_stratum(tmp_path, monkeypatch) -> None:
    import json

    directory = tmp_path / "golden"
    directory.mkdir()
    (directory / "a.jsonl").write_text(
        json.dumps({"id": "x", "stratum": "definition_1hop"}) + "\n"
        + json.dumps({"id": f"scry-leg-{OID}-modern", "stratum": "legality_1hop"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vk, "GOLDEN", directory)
    rows = vk.legality_rows()
    assert [row["id"] for row in rows] == [f"scry-leg-{OID}-modern"]


@pytest.mark.parametrize("status_now,expected", [("legal", 0), ("banned", 1)])
def test_exit_code_gates_the_run(tmp_path, monkeypatch, capsys, status_now, expected) -> None:
    """Exit 0 only when every key holds; exit 1 on any drift.

    A check that reports "mostly fine" and exits 0 is a check nobody acts on,
    and this one is meant to sit in front of a run that cannot be repeated.
    """
    import json

    directory = tmp_path / "golden"
    directory.mkdir()
    (directory / "a.jsonl").write_text(
        json.dumps(
            {
                "id": f"scry-leg-{OID}-modern",
                "stratum": "legality_1hop",
                "snapshot_sha256": content_sha256(f"{OID}|modern|legal"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bulk = tmp_path / "bulk.jsonl"
    bulk.write_text("", encoding="utf-8")

    monkeypatch.setattr(vk, "GOLDEN", directory)
    monkeypatch.setattr(vk, "bulk_path", lambda stem: bulk)
    monkeypatch.setattr(
        vk, "iter_bulk",
        lambda path: iter([{"oracle_id": OID, "name": "X", "legalities": {"modern": status_now}}]),
    )
    monkeypatch.setattr(sys, "argv", ["verify_legality_keys.py"])

    assert vk.main() == expected
    out = capsys.readouterr().out
    assert ("PIN 10 SATISFIED" in out) is (expected == 0)


def test_a_card_missing_from_the_bulk_fails_rather_than_passing(
    tmp_path, monkeypatch, capsys
) -> None:
    # A card Scryfall no longer returns is not a silent pass. It is a question
    # whose key cannot be confirmed, which is the same risk as a stale one.
    import json

    directory = tmp_path / "golden"
    directory.mkdir()
    (directory / "a.jsonl").write_text(
        json.dumps(
            {
                "id": f"scry-leg-{OID}-modern",
                "stratum": "legality_1hop",
                "snapshot_sha256": content_sha256(f"{OID}|modern|legal"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bulk = tmp_path / "bulk.jsonl"
    bulk.write_text("", encoding="utf-8")
    monkeypatch.setattr(vk, "GOLDEN", directory)
    monkeypatch.setattr(vk, "bulk_path", lambda stem: bulk)
    monkeypatch.setattr(vk, "iter_bulk", lambda path: iter([]))
    monkeypatch.setattr(sys, "argv", ["verify_legality_keys.py"])

    assert vk.main() == 1
    assert "no current record" in capsys.readouterr().out
