"""Reading Scryfall bulk artifacts, across the formats Scryfall has shipped.

Scryfall changed its bulk-data contract: `download_uri` (one large JSON array,
uncompressed) became `jsonl_download_uri` (gzipped JSONL). The switch broke
`etl/download.py` outright — it raised `KeyError: 'download_uri'`, so nothing
could be re-ingested at all.

This module is the reading half of the fix, and it is deliberately tolerant of
*all three* shapes: gzipped JSONL, plain JSONL, and the legacy JSON array. That
tolerance is not future-proofing for its own sake — an already-downloaded
180 MB array on disk is real work, and a reader that only understood the new
format would strand it mid-annotation for no gain.

JSONL is also the better shape for this corpus: the oracle bulk is parsed one
record at a time instead of held whole in memory. The legacy array cannot be
streamed and is still read in one gulp, which is one more reason to let the
next download replace it.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from itertools import chain
from pathlib import Path
from typing import IO, Any

RAW_DIR = Path("data/raw")

ORACLE_CARDS_STEM = "scryfall_oracle_cards"
RULINGS_STEM = "scryfall_rulings"

#: Extensions in preference order: what `download.py` writes now comes first,
#: the legacy array last. `bulk_path` returns the first one that exists.
BULK_SUFFIXES = (".jsonl.gz", ".jsonl", ".json")


def bulk_path(stem: str, raw_dir: Path = RAW_DIR) -> Path:
    """Return the artifact for ``stem``, preferring the current format.

    Args:
        stem: Manifest stem, e.g. ``"scryfall_rulings"``.
        raw_dir: Directory holding the downloaded bulks.

    Returns:
        The first existing artifact; if none exists, the path a fresh download
        would write, so the caller reports a missing file rather than a
        confusing fallback.
    """
    for suffix in BULK_SUFFIXES:
        candidate = raw_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return raw_dir / f"{stem}{BULK_SUFFIXES[0]}"


def _open_text(path: Path) -> IO[str]:
    """Open ``path`` as UTF-8 text, transparently decompressing ``.gz``."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def iter_bulk(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each record of a Scryfall bulk file.

    The format is detected from the first non-whitespace character rather than
    from the file name, because the name is only a convention and a mislabelled
    file should still read correctly: ``[`` means the legacy JSON array, ``{``
    means JSONL.

    Args:
        path: A ``.jsonl.gz``, ``.jsonl`` or legacy ``.json`` bulk file.

    Yields:
        One record dict per card or ruling.
    """
    with _open_text(path) as fh:
        head = fh.read(1)
        while head and head.isspace():
            head = fh.read(1)
        if not head:
            return
        if head == "[":
            yield from json.loads(head + fh.read())
            return
        for line in chain([head + fh.readline()], fh):
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def load_bulk(path: Path) -> list[dict[str, Any]]:
    """Read a whole bulk file into a list — for callers that need random access."""
    return list(iter_bulk(path))
