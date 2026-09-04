"""The dense half of arm A: an encoder behind a protocol, and a flat index.

**Registered deviation, and the argument for it.** The roadmap names BGE-M3
"reuse from Project 1", and this uses OpenAI's `text-embedding-3-small`
instead. The corpus is 115,547 documents and roughly 8.6M tokens; BGE-M3 on
a CPU laptop is hours of compute and a 2.5 GB dependency, against about
US$ 0.17 and minutes through an API the project already authenticates to.

The reason that trade is *safe* rather than merely convenient is the
direction it moves the result. `text-embedding-3-small` is a stronger
English retrieval model than BGE-M3, so the deviation makes **arm A
stronger** — and arm A is the control the project's own hypothesis predicts
losing to the graph. A change that strengthens the control cannot
manufacture the predicted outcome; it can only make it harder to reach.
Had the substitution weakened arm A, it would not be admissible at any
price. Registered as an E-001 amendment before a single vector exists.

Vectors are cached on disk keyed by the corpus hash, so a re-run costs
nothing and a corpus change invalidates the cache instead of silently
scoring new documents against old vectors.
"""

from __future__ import annotations

import json
import math
import os
import struct
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np

from graphrag_mtg.config import get_settings
from graphrag_mtg.extraction.llm import (
    MAX_ATTEMPTS,
    RETRY_EXCEPTIONS,
    RETRY_STATUSES,
    backoff,
    retry_delay,
)

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

#: The registered model. 1536 dimensions, US$ 0.02 per 1M tokens.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

#: US dollars per 1M input tokens, for the estimate the cost rule requires.
#: Verified against the provider's published price before any full run —
#: the project's own standard is that a constant read from a document is
#: re-checked, not inherited.
PRICE_PER_MILLION = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}

#: Documents per request. The provider caps a single call well above this;
#: the limit that binds is the request body size on 400-word card
#: documents, and a failed batch costs whatever it already spent.
BATCH = 256


class Encoder(Protocol):
    """Whatever turns text into vectors.

    A protocol rather than a class so that the registered deviation stays
    a swap of one object: a local BGE-M3 encoder implementing this
    interface would drop in without touching the retriever, the fusion or
    the harness, which is what makes the amendment a configuration
    decision rather than a rewrite.
    """

    name: str
    dimensions: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors for `texts`, positionally aligned, L2-normalised."""
        ...


def normalise(vector: Sequence[float]) -> list[float]:
    """Unit-length copy of `vector`, so cosine similarity is a dot product.

    Normalising once at index time rather than at every comparison is the
    difference between 115k divisions per query and 115k over the life of
    the index.
    """
    norm = math.sqrt(sum(component * component for component in vector))
    if not norm:
        return list(vector)
    return [component / norm for component in vector]


@dataclass
class OpenAiEncoder:
    """`text-embedding-3-small` over plain httpx, retried like the LLM client.

    Shares `RETRY_STATUSES` and `retry_delay` with `extraction/llm.py`
    rather than re-deciding them: E-002 lost 163 of 500 answers to an
    unretried 429, and a second, subtly different retry policy is a second
    thing that can be wrong in the same way.
    """

    model: str = DEFAULT_EMBEDDING_MODEL
    dimensions: int = 1536

    def __post_init__(self) -> None:
        key = get_settings().openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No OpenAI API key configured. Set OPENAI_API_KEY in .env "
                "(see .env.example) — never on the command line."
            )
        self.name = self.model
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {key}"}, timeout=httpx.Timeout(180.0)
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors for `texts`, in order, unit-normalised.

        Raises:
            httpx.HTTPStatusError: on a non-retryable status or after
                :data:`MAX_ATTEMPTS`. A run that cannot embed a batch stops
                and says so rather than recording a silent gap — the
                failure mode E-002 spent 163 answers learning.
        """
        payload = {"model": self.model, "input": list(texts)}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http.post(OPENAI_EMBEDDINGS_URL, json=payload)
            except RETRY_EXCEPTIONS as exc:
                # A connection reset never becomes a status code, so the
                # status-only loop passed it straight through and killed a
                # pass at 16,640 of 115,547 documents.
                if attempt == MAX_ATTEMPTS:
                    raise
                delay = backoff(attempt)
                print(f"  {type(exc).__name__} in transport; retrying in {delay:.0f}s", flush=True)
                time.sleep(delay)
                continue
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                response.raise_for_status()
                break
            delay = retry_delay(response, attempt)
            print(f"  {response.status_code} from the provider; retrying in {delay:.0f}s", flush=True)
            time.sleep(delay)
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        return [normalise(row["embedding"]) for row in rows]


@dataclass(frozen=True)
class Hit:
    """One scored document. Mirrors `bm25.Hit` so fusion sees one shape."""

    doc_id: str
    score: float


class DenseIndex:
    """A flat index: every vector compared against the query, in float32.

    Exact rather than approximate, deliberately. The golden set is 77
    questions, so the whole run is a few hundred queries, and an ANN
    structure would introduce a recall parameter that becomes one more
    thing arm A could be accused of having been handicapped by. Exact
    search cannot be accused of anything.

    **Backed by a numpy array rather than lists, and the reason is not
    style.** 115,547 vectors of 1,536 dimensions is 710 MB as float32 and
    **5.7 GB** as `list[list[float]]`, because a CPython float is 24 bytes
    plus an 8-byte pointer. And one query is 177M multiply-adds: tens of
    seconds in a Python loop against tens of milliseconds as a single
    matrix product. The first draft of this class used lists, which was
    fine at test scale and unusable at corpus scale — the kind of defect
    that only appears when the data is real.
    """

    def __init__(self, doc_ids: Sequence[str], vectors: Sequence[Sequence[float]] | np.ndarray):
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            matrix = matrix.reshape(len(doc_ids), -1)
        if len(doc_ids) != matrix.shape[0]:
            raise ValueError(
                f"{matrix.shape[0]} vectors against {len(doc_ids)} ids — the index would "
                "score documents under the wrong handles."
            )
        self.doc_ids = list(doc_ids)
        self.matrix = matrix

    def __len__(self) -> int:
        return len(self.doc_ids)

    def search(self, query_vector: Sequence[float], *, k: int = 20) -> list[Hit]:
        """The `k` most similar documents. Ties break by `doc_id`.

        Vectors are unit-length at index time, so the similarity is one
        matrix-vector product and the sort is over `k`, not over 115k.
        """
        if not self.doc_ids:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        scores = self.matrix @ query
        take = min(k, scores.shape[0])
        # argpartition finds the top-k without ordering the other 115k.
        top = np.argpartition(-scores, take - 1)[:take]
        ranked = sorted(top, key=lambda i: (-float(scores[i]), self.doc_ids[i]))
        return [Hit(doc_id=self.doc_ids[i], score=float(scores[i])) for i in ranked]


class VectorCache:
    """Vectors on disk, keyed by the corpus hash and the encoder name.

    Two files: a JSON header naming what produced the vectors, and a flat
    binary of little-endian float32. A cache that did not carry the corpus
    hash would happily serve vectors for documents that no longer exist,
    which is a scoring error no downstream check could see.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.header_path = path.with_suffix(".json")

    def load(self, *, corpus_hash: str, encoder: str, count: int) -> np.ndarray | None:
        """Cached vectors as a `(count, dimensions)` float32 array, or None.

        Returned as an array rather than nested lists: 115,547 × 1,536 is
        710 MB in float32 and 5.7 GB as Python floats, so the conversion
        is not a convenience, it is the difference between loading and
        not.
        """
        if not (self.path.exists() and self.header_path.exists()):
            return None
        try:
            header = json.loads(self.header_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if (
            header.get("corpus_sha256") != corpus_hash
            or header.get("encoder") != encoder
            or header.get("count") != count
        ):
            return None
        dimensions = header["dimensions"]
        if self.path.stat().st_size != count * dimensions * 4:
            return None
        matrix = np.fromfile(self.path, dtype="<f4", count=count * dimensions)
        return matrix.reshape(count, dimensions)

    def save(
        self, vectors: Sequence[Sequence[float]], *, corpus_hash: str, encoder: str
    ) -> None:
        """Write the vectors and the header that makes them re-usable."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        dimensions = len(vectors[0]) if vectors else 0
        with self.path.open("wb") as handle:
            for vector in vectors:
                handle.write(struct.pack(f"<{dimensions}f", *vector))
        self._write_header(corpus_hash=corpus_hash, encoder=encoder, count=len(vectors),
                           dimensions=dimensions)

    def _write_header(
        self, *, corpus_hash: str, encoder: str, count: int, dimensions: int
    ) -> None:
        self.header_path.write_text(
            json.dumps(
                {
                    "corpus_sha256": corpus_hash,
                    "encoder": encoder,
                    "count": count,
                    "dimensions": dimensions,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def resume_count(self, *, corpus_hash: str, encoder: str) -> int:
        """How many vectors on disk may be kept and continued from.

        Embedding 115k documents is ~450 requests, and E-002 lost 163 of
        500 answers to one unretried 429 — the project's most expensive
        lesson about work that is not resumable. Vectors are therefore
        appended batch by batch and the header advanced with them, so a
        failure at request 400 costs one batch rather than everything.

        Returns 0 whenever anything about the run has changed, because a
        partial file from a different corpus or encoder is not a prefix of
        this one, it is a different index with the same filename.
        """
        if not (self.path.exists() and self.header_path.exists()):
            return 0
        try:
            header = json.loads(self.header_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return 0
        if header.get("corpus_sha256") != corpus_hash or header.get("encoder") != encoder:
            return 0
        count, dimensions = header.get("count", 0), header.get("dimensions", 0)
        if not dimensions:
            return 0
        # Trust the bytes over the header: a process killed mid-write
        # leaves a header claiming more than the file holds, and resuming
        # from the header would leave a hole no later check could see.
        on_disk = self.path.stat().st_size // (dimensions * 4)
        return min(count, on_disk)

    def append(
        self,
        vectors: Sequence[Sequence[float]],
        *,
        corpus_hash: str,
        encoder: str,
        done: int,
    ) -> int:
        """Append `vectors` after `done` existing ones; return the new total.

        The file is truncated to `done` vectors first, so a resume after a
        partial write overwrites the torn tail instead of appending past
        it.
        """
        if not vectors:
            return done
        dimensions = len(vectors[0])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stride = dimensions * 4
        with self.path.open("r+b" if self.path.exists() else "wb") as handle:
            handle.seek(done * stride)
            handle.truncate()
            for vector in vectors:
                handle.write(struct.pack(f"<{dimensions}f", *vector))
        total = done + len(vectors)
        self._write_header(
            corpus_hash=corpus_hash, encoder=encoder, count=total, dimensions=dimensions
        )
        return total


def estimate_embedding_cost(texts: Iterable[str], *, model: str) -> str:
    """A printable estimate, per the project's cost rule.

    Uses the same chars/4 heuristic `extraction/llm.py` prints, so the two
    numbers in a run log are comparable rather than derived two ways.
    """
    tokens = sum(len(text) for text in texts) / 4
    price = PRICE_PER_MILLION.get(model)
    if price is None:
        return f"~{tokens / 1e6:.2f}M tokens, price for {model} unknown — check before running"
    return (
        f"~{tokens / 1e6:.2f}M tokens at {model} = ~${tokens / 1e6 * price:.2f} "
        "(chars/4 heuristic; verify current pricing before a full run)"
    )
