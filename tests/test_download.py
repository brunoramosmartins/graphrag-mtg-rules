"""Unit tests for etl.download pure logic (no network, no Neo4j).

The streaming download hits the network and is exercised manually / in
integration, not here. These cover the hashing, manifest round-trip, the
incremental change-detection predicate, and the Scryfall resolver — which is
fed a stubbed index rather than the live API, since it was a silent upstream
key change there that broke ingestion outright.
"""

from __future__ import annotations

import hashlib
import json

from graphrag_mtg.etl.download import (
    ResolvedSource,
    is_current,
    load_manifest,
    resolve_scryfall,
    save_manifest,
    sha256_of_file,
)


class StubClient:
    """Returns one canned bulk-data index; no network."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def get(self, url: str) -> StubClient:
        return self

    def raise_for_status(self) -> StubClient:
        return self

    def json(self) -> dict:
        return self._payload


def index(*items: dict) -> StubClient:
    return StubClient({"data": list(items)})


def test_resolver_reads_the_current_jsonl_key():
    client = index(
        {
            "type": "rulings",
            "jsonl_download_uri": "https://data.scryfall.io/rulings/rulings-1.jsonl.gz",
            "updated_at": "2026-08-08T09:00:36.304+00:00",
        }
    )
    (source,) = [s for s in resolve_scryfall(client) if s.name == "scryfall_rulings"]
    assert source.url.endswith(".jsonl.gz")
    assert source.filename == "scryfall_rulings.jsonl.gz"
    assert source.version == "2026-08-08T09:00:36.304+00:00"


def test_resolver_still_accepts_the_retired_array_key():
    """Old key, old extension — a mirror or a rollback must not crash the run."""
    client = index(
        {
            "type": "rulings",
            "download_uri": "https://data.scryfall.io/rulings/rulings-1.json",
            "updated_at": "2026-07-17T21:00:36.799+00:00",
        }
    )
    (source,) = [s for s in resolve_scryfall(client) if s.name == "scryfall_rulings"]
    assert source.filename == "scryfall_rulings.json"


def test_resolver_skips_an_entry_with_no_known_download_key(capsys):
    """The bug this replaces was a KeyError; a warning and a skip is the fix."""
    client = index({"type": "rulings", "updated_at": "2026-08-08T09:00:36.304+00:00"})
    assert [s for s in resolve_scryfall(client) if s.name == "scryfall_rulings"] == []
    assert "no known download key" in capsys.readouterr().out


def test_sha256_of_file_matches_hashlib(tmp_path):
    payload = b"Lightning Bolt deals 3 damage to any target.\n"
    f = tmp_path / "sample.txt"
    f.write_bytes(payload)
    assert sha256_of_file(f) == hashlib.sha256(payload).hexdigest()


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = {"scryfall_rulings": {"version": "2026-07-17", "sha256": "abc", "bytes": 10}}
    save_manifest(manifest, path)
    assert load_manifest(path) == manifest
    # Persisted as sorted, indented JSON for stable diffs.
    assert json.loads(path.read_text(encoding="utf-8")) == manifest


def test_load_manifest_missing_returns_empty(tmp_path):
    assert load_manifest(tmp_path / "does-not-exist.json") == {}


def _source() -> ResolvedSource:
    return ResolvedSource(
        name="scryfall_oracle_cards",
        url="https://example/oracle.json",
        version="2026-07-17T00:00:00Z",
        filename="scryfall_oracle_cards.json",
    )


def test_is_current_true_when_version_matches_and_file_present(tmp_path):
    src = _source()
    (tmp_path / src.filename).write_text("{}", encoding="utf-8")
    manifest = {src.name: {"version": src.version}}
    assert is_current(manifest, src, raw_dir=tmp_path) is True


def test_is_current_false_when_absent_from_manifest(tmp_path):
    src = _source()
    (tmp_path / src.filename).write_text("{}", encoding="utf-8")
    assert is_current({}, src, raw_dir=tmp_path) is False


def test_is_current_false_when_version_differs(tmp_path):
    src = _source()
    (tmp_path / src.filename).write_text("{}", encoding="utf-8")
    manifest = {src.name: {"version": "an-older-version"}}
    assert is_current(manifest, src, raw_dir=tmp_path) is False


def test_is_current_false_when_file_missing(tmp_path):
    src = _source()  # no file created
    manifest = {src.name: {"version": src.version}}
    assert is_current(manifest, src, raw_dir=tmp_path) is False
