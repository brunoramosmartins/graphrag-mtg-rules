"""Reading Scryfall bulk artifacts across formats.

Scryfall swapped `download_uri` (a JSON array) for `jsonl_download_uri`
(gzipped JSONL) and broke ingestion outright. These tests pin both halves of
the fix: that all three shapes read identically, and that an already-downloaded
legacy array is still found and read — stranding 180 MB of downloaded corpus
mid-annotation would be a worse outcome than the bug.
"""

from __future__ import annotations

import gzip
import json

import pytest

from graphrag_mtg.etl.bulk import BULK_SUFFIXES, bulk_path, iter_bulk, load_bulk

RECORDS = [
    {"oracle_id": "oid-1", "name": "Opt"},
    {"oracle_id": "oid-2", "name": "Fear"},
]


def write_array(path):
    path.write_text(json.dumps(RECORDS), encoding="utf-8")
    return path


def write_jsonl(path):
    path.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n", encoding="utf-8")
    return path


def write_jsonl_gz(path):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for record in RECORDS:
            fh.write(json.dumps(record) + "\n")
    return path


class TestIterBulk:
    @pytest.mark.parametrize(
        ("writer", "name"),
        [
            (write_jsonl_gz, "bulk.jsonl.gz"),
            (write_jsonl, "bulk.jsonl"),
            (write_array, "bulk.json"),
        ],
    )
    def test_every_shipped_format_reads_identically(self, tmp_path, writer, name) -> None:
        assert load_bulk(writer(tmp_path / name)) == RECORDS

    def test_format_comes_from_content_not_from_the_file_name(self, tmp_path) -> None:
        """A mislabelled file must still read: the name is only a convention."""
        mislabelled = write_array(tmp_path / "actually_an_array.jsonl")
        assert load_bulk(mislabelled) == RECORDS

    def test_leading_whitespace_does_not_confuse_detection(self, tmp_path) -> None:
        path = tmp_path / "padded.json"
        path.write_text("\n  " + json.dumps(RECORDS), encoding="utf-8")
        assert load_bulk(path) == RECORDS

    def test_blank_lines_in_jsonl_are_skipped(self, tmp_path) -> None:
        path = tmp_path / "gappy.jsonl"
        path.write_text(
            json.dumps(RECORDS[0]) + "\n\n" + json.dumps(RECORDS[1]) + "\n", encoding="utf-8"
        )
        assert load_bulk(path) == RECORDS

    def test_empty_file_yields_nothing(self, tmp_path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        assert list(iter_bulk(path)) == []

    def test_records_stream_rather_than_materialise(self, tmp_path) -> None:
        """JSONL must be consumable one record at a time, not read whole."""
        stream = iter_bulk(write_jsonl(tmp_path / "bulk.jsonl"))
        assert next(stream) == RECORDS[0]


class TestBulkPath:
    def test_prefers_the_current_format_over_the_legacy_array(self, tmp_path) -> None:
        for suffix in BULK_SUFFIXES:
            (tmp_path / f"scryfall_rulings{suffix}").write_text("[]", encoding="utf-8")
        assert bulk_path("scryfall_rulings", tmp_path).name == "scryfall_rulings.jsonl.gz"

    def test_falls_back_to_an_already_downloaded_legacy_array(self, tmp_path) -> None:
        write_array(tmp_path / "scryfall_rulings.json")
        assert bulk_path("scryfall_rulings", tmp_path).name == "scryfall_rulings.json"

    def test_missing_artifact_resolves_to_what_a_download_would_write(self, tmp_path) -> None:
        assert bulk_path("scryfall_rulings", tmp_path).name == "scryfall_rulings.jsonl.gz"
