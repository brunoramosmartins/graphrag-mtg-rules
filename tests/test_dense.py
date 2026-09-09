"""The vector cache: resuming, and refusing to resume.

Embedding the corpus is ~450 requests. E-002 lost 163 of 500 answers to one
unretried 429, which is this project's most expensive lesson about work
that is not resumable — so every test here is about what happens when the
run does not finish cleanly.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from graphrag_mtg.evaluation.dense import (
    DenseIndex,
    VectorCache,
    estimate_embedding_cost,
    normalise,
)

HASH = "a" * 64
ENCODER = "text-embedding-3-small"


def cache(tmp_path: Path) -> VectorCache:
    return VectorCache(tmp_path / "vectors.bin")


def vectors(n: int, dimensions: int = 4) -> list[list[float]]:
    return [[float(i + d) for d in range(dimensions)] for i in range(n)]


class TestResume:
    def test_nothing_on_disk_starts_at_zero(self, tmp_path: Path) -> None:
        assert cache(tmp_path).resume_count(corpus_hash=HASH, encoder=ENCODER) == 0

    def test_a_completed_append_resumes_after_it(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.append(vectors(3), corpus_hash=HASH, encoder=ENCODER, done=0)
        assert store.resume_count(corpus_hash=HASH, encoder=ENCODER) == 3

    def test_appends_accumulate(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        done = store.append(vectors(2), corpus_hash=HASH, encoder=ENCODER, done=0)
        done = store.append(vectors(2), corpus_hash=HASH, encoder=ENCODER, done=done)
        assert done == 4
        loaded = store.load(corpus_hash=HASH, encoder=ENCODER, count=4)
        assert loaded is not None and loaded.shape == (4, 4)

    def test_a_different_corpus_starts_over(self, tmp_path: Path) -> None:
        # A partial file from a different corpus is not a prefix of this
        # one; it is a different index wearing the same filename.
        store = cache(tmp_path)
        store.append(vectors(3), corpus_hash=HASH, encoder=ENCODER, done=0)
        assert store.resume_count(corpus_hash="b" * 64, encoder=ENCODER) == 0

    def test_a_different_encoder_starts_over(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.append(vectors(3), corpus_hash=HASH, encoder=ENCODER, done=0)
        assert store.resume_count(corpus_hash=HASH, encoder="bge-m3") == 0

    def test_the_bytes_win_over_an_optimistic_header(self, tmp_path: Path) -> None:
        # A process killed mid-write leaves a header claiming more than the
        # file holds. Resuming from the header would leave a hole in the
        # vectors that no later check could see.
        store = cache(tmp_path)
        store.append(vectors(4), corpus_hash=HASH, encoder=ENCODER, done=0)
        header = json.loads(store.header_path.read_text(encoding="utf-8"))
        header["count"] = 99
        store.header_path.write_text(json.dumps(header), encoding="utf-8")
        assert store.resume_count(corpus_hash=HASH, encoder=ENCODER) == 4

    def test_a_torn_tail_is_overwritten_not_appended_past(self, tmp_path: Path) -> None:
        # Resuming after a partial write must replace the half-written
        # vector, or every later vector sits at the wrong offset and the
        # index scores documents under the wrong handles.
        store = cache(tmp_path)
        store.append(vectors(4), corpus_hash=HASH, encoder=ENCODER, done=0)
        with store.path.open("ab") as handle:
            handle.write(b"\x00" * 6)  # a torn, partial vector
        store.append(vectors(2), corpus_hash=HASH, encoder=ENCODER, done=4)
        loaded = store.load(corpus_hash=HASH, encoder=ENCODER, count=6)
        assert loaded is not None and loaded.shape == (6, 4)

    def test_a_corrupt_header_starts_over(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.append(vectors(3), corpus_hash=HASH, encoder=ENCODER, done=0)
        store.header_path.write_text("{not json", encoding="utf-8")
        assert store.resume_count(corpus_hash=HASH, encoder=ENCODER) == 0

    def test_appending_nothing_changes_nothing(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.append(vectors(2), corpus_hash=HASH, encoder=ENCODER, done=0)
        assert store.append([], corpus_hash=HASH, encoder=ENCODER, done=2) == 2


class TestLoad:
    def test_round_trips_the_values(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        original = [normalise([1.0, 2.0, 3.0, 4.0])]
        store.save(original, corpus_hash=HASH, encoder=ENCODER)
        loaded = store.load(corpus_hash=HASH, encoder=ENCODER, count=1)
        assert loaded is not None
        assert all(abs(a - b) < 1e-6 for a, b in zip(loaded[0], original[0], strict=True))

    def test_a_count_mismatch_refuses(self, tmp_path: Path) -> None:
        # Serving vectors for documents that no longer exist is a scoring
        # error no downstream check could see.
        store = cache(tmp_path)
        store.save(vectors(3), corpus_hash=HASH, encoder=ENCODER)
        assert store.load(corpus_hash=HASH, encoder=ENCODER, count=4) is None

    def test_a_truncated_file_refuses(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.save(vectors(3), corpus_hash=HASH, encoder=ENCODER)
        store.path.write_bytes(store.path.read_bytes()[:-4])
        assert store.load(corpus_hash=HASH, encoder=ENCODER, count=3) is None

    def test_the_binary_is_little_endian_float32(self, tmp_path: Path) -> None:
        store = cache(tmp_path)
        store.save([[1.5, 2.5]], corpus_hash=HASH, encoder=ENCODER)
        assert struct.unpack("<2f", store.path.read_bytes()) == (1.5, 2.5)

    def test_loads_as_a_float32_array_not_python_floats(self, tmp_path: Path) -> None:
        # 115,547 x 1,536 is 710 MB as float32 and 5.7 GB as nested Python
        # lists. The dtype is the difference between loading and not.
        store = cache(tmp_path)
        store.save(vectors(3), corpus_hash=HASH, encoder=ENCODER)
        loaded = store.load(corpus_hash=HASH, encoder=ENCODER, count=3)
        assert loaded is not None and loaded.dtype == np.float32


class TestNormalise:
    def test_produces_unit_length(self) -> None:
        # Normalising once at index time is the difference between 115k
        # divisions per query and 115k over the life of the index.
        vector = normalise([3.0, 4.0])
        assert abs(sum(c * c for c in vector) - 1.0) < 1e-9

    def test_makes_cosine_a_dot_product(self) -> None:
        index = DenseIndex(["a", "b"], [normalise([1.0, 1.0]), normalise([1.0, -1.0])])
        assert index.search(normalise([1.0, 0.9]), k=1)[0].score > 0.99


class TestEstimate:
    def test_prices_the_registered_model(self) -> None:
        estimate = estimate_embedding_cost(["x" * 4_000_000], model="text-embedding-3-small")
        assert "$0.02" in estimate

    def test_an_unpriced_model_says_so_rather_than_guessing(self) -> None:
        # A cost estimate that quietly invents a price is worse than none:
        # the project's rule is that a spend is approved against a number.
        assert "unknown" in estimate_embedding_cost(["x"], model="some-new-model")


class TestOpenAiEncoder:
    def test_missing_key_fails_loudly(self, monkeypatch) -> None:
        from graphrag_mtg.evaluation import dense

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(
            dense, "get_settings", lambda: type("S", (), {"openai_api_key": ""})()
        )
        with pytest.raises(RuntimeError, match="never on the command line"):
            dense.OpenAiEncoder()
