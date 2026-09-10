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


class TestOneCorpusNotTwo:
    def test_both_halves_of_arm_a_resolve_the_same_way(self) -> None:
        # Arm A's corpus is cards plus rulings, and `corpus_sha256` hashes
        # the mixture — so a corpus built from today's cards and a legacy
        # rulings array gets a hash that describes it perfectly and tells
        # nobody anything is wrong. Both halves go through `bulk_path`.
        import run_eval

        assert run_eval.RULINGS_PATH == bulk_path(RULINGS_STEM)

    def test_the_graph_and_the_index_read_the_same_card_file(self) -> None:
        # The loader fills the graph arms retrieve from; `run_eval` builds
        # the index arm A retrieves from. They are supposed to be one
        # corpus, and pin 8's parity argument assumes it.
        import run_eval

        assert oracle_cards_path() == bulk_path(ORACLE_CARDS_STEM)
        assert run_eval.load_cards.__module__ == "run_eval"
