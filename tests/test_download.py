"""Unit tests for etl.download pure logic (no network, no Neo4j).

The resolvers and streaming download hit the network and are exercised
manually / in integration, not here. These cover the hashing, manifest
round-trip, and incremental change-detection predicate.
"""

from __future__ import annotations

import hashlib
import json

from graphrag_mtg.etl.download import (
    ResolvedSource,
    is_current,
    load_manifest,
    save_manifest,
    sha256_of_file,
)


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
