"""Which file is "the corpus" must be decided once, and decided late.

On 2026-09-10 the loader put 34,236 cards into the graph from a legacy
`.json` array downloaded in July, and stamped them with the SHA-256 of the
`.jsonl.gz` it had just fetched. Nothing failed. The graph simply claimed
a provenance it did not have, which is worse than being out of date,
because being out of date is visible.

The cause was a module constant: `ORACLE_CARDS_PATH = bulk_path(...)`
binds when the module is imported, and `scripts/bootstrap.py` imports,
then downloads, then loads. A second instance of the same shape had arm
A indexing today's cards beside rulings from a legacy array, because one
half of that corpus went through `bulk_path` and the other was a literal
path.
"""

from __future__ import annotations

import gzip
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, RULINGS_STEM, bulk_path
from graphrag_mtg.etl.cards import load_oracle_cards, oracle_cards_path
from graphrag_mtg.graph.loader import rulings_path


class TestBulkPathRereads:
    def test_a_newly_arrived_preferred_format_wins_immediately(self, tmp_path: Path) -> None:
        # The whole failure in one assertion: the answer changes when the
        # directory changes, so anything that caches it is wrong.
        legacy = tmp_path / f"{ORACLE_CARDS_STEM}.json"
        legacy.write_text("[]", encoding="utf-8")
        assert bulk_path(ORACLE_CARDS_STEM, tmp_path) == legacy

        current = tmp_path / f"{ORACLE_CARDS_STEM}.jsonl.gz"
        current.write_bytes(gzip.compress(b"{}\n"))
        assert bulk_path(ORACLE_CARDS_STEM, tmp_path) == current

    def test_an_absent_bulk_names_the_file_a_download_would_write(
        self, tmp_path: Path
    ) -> None:
        # Not an exception: the caller reports a missing file rather than
        # a confusing fallback, which is what `bootstrap.py` relies on.
        assert bulk_path(ORACLE_CARDS_STEM, tmp_path).name.endswith(".jsonl.gz")


class TestResolvedAtCallTime:
    def test_the_card_bulk_is_a_function_not_a_constant(self) -> None:
        assert callable(oracle_cards_path)
        assert isinstance(oracle_cards_path(), Path)

    def test_the_rulings_bulk_is_a_function_not_a_constant(self) -> None:
        assert callable(rulings_path)
        assert isinstance(rulings_path(), Path)

    def test_the_loader_default_is_not_bound_at_import(self) -> None:
        # The guard that would have caught the original defect. A `Path`
        # here means the answer was computed when the module was imported,
        # which is before any download in the one process that does both.
        default = inspect.signature(load_oracle_cards).parameters["path"].default
        assert default is None

    def test_an_explicit_path_still_wins(self, tmp_path: Path) -> None:
        bulk = tmp_path / "cards.jsonl"
        bulk.write_text(
            json.dumps(
                {
                    "oracle_id": "o1",
                    "name": "Test Card",
                    "layout": "normal",
                    "cmc": 1.0,
                    "type_line": "Artifact",
                    "legalities": {"modern": "legal"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        assert [card.oracle_id for card in load_oracle_cards(bulk)] == ["o1"]


class TestTheReaderFollowsThePath:
    """Resolving a path correctly is half of it; the other half reads it.

    On 2026-09-10 the path fix landed and the reader did not. `RULINGS_PATH`
    started resolving to `.jsonl.gz`, `load_corpus` still did
    `json.loads(path.read_text())`, and the first real run died on
    `UnicodeDecodeError: invalid start byte 0x8b` — which is gzip's magic
    number, arriving where a `[` was expected. The legacy `.json` arrays had
    been deleted the same day, so there was nothing to fall back to.
    """

    def _rulings_gz(self, tmp_path: Path) -> Path:
        path = tmp_path / f"{RULINGS_STEM}.jsonl.gz"
        rows = [
            {"oracle_id": "o1", "comment": "A ruling about the stack.", "published_at": "2026-01-01"},
            {"oracle_id": "o1", "comment": "A second ruling.", "published_at": "2026-01-02"},
        ]
        path.write_bytes(gzip.compress("\n".join(json.dumps(r) for r in rows).encode("utf-8")))
        return path

    def test_the_corpus_builder_reads_a_compressed_bulk(self, tmp_path: Path) -> None:
        # The exact call that failed. It goes through the bulk reader now,
        # which detects the format from the content rather than the name.
        from graphrag_mtg.etl.bulk import load_bulk

        rows = load_bulk(self._rulings_gz(tmp_path))
        assert [r["oracle_id"] for r in rows] == ["o1", "o1"]

    @pytest.mark.parametrize(
        "script", ["run_eval.py", "sweep_arm_a.py", "load_smoke_graph.py",
                   "extraction_cost_report.py", "sample_rulings_for_annotation.py",
                   "prefill_extraction_annotations.py"]
    )
    def test_no_script_reads_a_bulk_as_plain_text(self, script: str) -> None:
        # A grep-shaped guard, deliberately. Every one of these scripts had
        # the same two lines, and each was written before the file it reads
        # could be compressed. The next one will be written the same way.
        source = (Path(__file__).resolve().parents[1] / "scripts" / script).read_text(
            encoding="utf-8"
        )
        for forbidden in ("rulings.read_text", "cards.read_text",
                          "rulings.open(encoding", "cards.open(encoding"):
            assert forbidden not in source, (
                f"{script} reads a bulk as plain text via `{forbidden}`; a "
                "`.jsonl.gz` fails there with a UnicodeDecodeError on 0x8b. "
                "Use `load_bulk` or `iter_bulk`."
            )


class TestOneCorpusNotTwo:
    def test_both_halves_of_arm_a_resolve_the_same_way(self) -> None:
        # Arm A's corpus is cards plus rulings, and `corpus_sha256` hashes
        # the mixture — so a corpus built from today's cards and a legacy
        # rulings array gets a hash that describes it perfectly and tells
        # nobody anything is wrong. Both halves go through `bulk_path`.
        import run_eval

        assert bulk_path(RULINGS_STEM) == run_eval.RULINGS_PATH

    def test_the_graph_and_the_index_read_the_same_card_file(self) -> None:
        # The loader fills the graph arms retrieve from; `run_eval` builds
        # the index arm A retrieves from. They are supposed to be one
        # corpus, and pin 8's parity argument assumes it.
        import run_eval

        assert oracle_cards_path() == bulk_path(ORACLE_CARDS_STEM)
        assert run_eval.load_cards.__module__ == "run_eval"
