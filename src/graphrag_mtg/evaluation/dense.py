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

from graphrag_mtg.config import get_settings
from graphrag_mtg.extraction.llm import MAX_ATTEMPTS, RETRY_STATUSES, retry_delay

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
            response = self._http.post(OPENAI_EMBEDDINGS_URL, json=payload)
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                response.raise_for_status()
                break
            delay = retry_delay(response, attempt)
            print(f"  {response.status_code} from the provider; retrying in {delay:.0f}s")
            time.sleep(delay)
        rows = sorted(response.json()["data"], key=lambda row: row["index"])
        return [normalise(row["embedding"]) for row in rows]


@dataclass(frozen=True)
class Hit:
    """One scored document. Mirrors `bm25.Hit` so fusion sees one shape."""

    doc_id: str
    score: float


class DenseIndex:
    """A flat index: every vector compared against the query.

    Exact rather than approximate, deliberately. 115k dot products of 1536
    floats is well under a second in pure Python per query, the golden set
    is 77 questions, and an ANN structure would introduce a recall
    parameter that becomes one more thing arm A could be accused of having
    been handicapped by.
    """

    def __init__(self, doc_ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        if len(doc_ids) != len(vectors):
            raise ValueError(
                f"{len(vectors)} vectors against {len(doc_ids)} ids — the index would "
                "score documents under the wrong handles."
            )
        self.doc_ids = list(doc_ids)
        self.vectors = [list(v) for v in vectors]

    def __len__(self) -> int:
        return len(self.doc_ids)

    def search(self, query_vector: Sequence[float], *, k: int = 20) -> list[Hit]:
        """The `k` most similar documents. Ties break by `doc_id`."""
        scored = [
            (sum(a * b for a, b in zip(query_vector, vector, strict=True)), index)
            for index, vector in enumerate(self.vectors)
        ]
        ranked = sorted(scored, key=lambda pair: (-pair[0], self.doc_ids[pair[1]]))
        return [Hit(doc_id=self.doc_ids[i], score=score) for score, i in ranked[:k]]


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

    def load(self, *, corpus_hash: str, encoder: str, count: int) -> list[list[float]] | None:
        """Cached vectors, or None when nothing valid is stored."""
        if not (self.path.exists() and self.header_path.exists()):
            return None
        header = json.loads(self.header_path.read_text(encoding="utf-8"))
        if (
            header.get("corpus_sha256") != corpus_hash
            or header.get("encoder") != encoder
            or header.get("count") != count
        ):
            return None
        dimensions = header["dimensions"]
        raw = self.path.read_bytes()
        stride = dimensions * 4
        if len(raw) != count * stride:
            return None
        return [
            list(struct.unpack_from(f"<{dimensions}f", raw, index * stride))
            for index in range(count)
        ]

    def save(
        self, vectors: Sequence[Sequence[float]], *, corpus_hash: str, encoder: str
    ) -> None:
        """Write the vectors and the header that makes them re-usable."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        dimensions = len(vectors[0]) if vectors else 0
        with self.path.open("wb") as handle:
            for vector in vectors:
                handle.write(struct.pack(f"<{dimensions}f", *vector))
        self.header_path.write_text(
            json.dumps(
                {
                    "corpus_sha256": corpus_hash,
                    "encoder": encoder,
                    "count": len(vectors),
                    "dimensions": dimensions,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


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
