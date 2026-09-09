"""The guard that keeps E-002 off the corpus instance.

No database is touched here. What is worth pinning is that resolving the
MetaQA target fails loudly when it resolves to the corpus, and that the
comparison is not fooled by a trailing slash — a guard that only catches
byte-identical URIs would pass every review and stop nothing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from graphrag_mtg.config import get_settings
from graphrag_mtg.graph import connection

CORPUS = "bolt://localhost:7687"
SECOND = "bolt://localhost:7688"


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Settings are cached; every case here changes the environment."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_metaqa_target_is_the_second_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", CORPUS)
    monkeypatch.setenv("METAQA_NEO4J_URI", SECOND)
    target = connection.metaqa_target()
    assert target.uri == SECOND
    assert target.name == "metaqa"


def test_the_same_uri_stops_the_load_before_a_driver_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", CORPUS)
    monkeypatch.setenv("METAQA_NEO4J_URI", CORPUS)
    with pytest.raises(SystemExit, match="same Neo4j instance"):
        connection.metaqa_target()


def test_the_message_names_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", CORPUS)
    monkeypatch.setenv("METAQA_NEO4J_URI", CORPUS)
    with pytest.raises(SystemExit, match=r"--profile metaqa up -d"):
        connection.metaqa_target()


@pytest.mark.parametrize(
    "disguise",
    ["bolt://localhost:7687/", "BOLT://LOCALHOST:7687", " bolt://localhost:7687 "],
)
def test_a_trailing_slash_or_a_capital_is_still_the_corpus(
    monkeypatch: pytest.MonkeyPatch, disguise: str
) -> None:
    monkeypatch.setenv("NEO4J_URI", CORPUS)
    monkeypatch.setenv("METAQA_NEO4J_URI", disguise)
    with pytest.raises(SystemExit, match="same Neo4j instance"):
        connection.metaqa_target()


def test_the_corpus_target_carries_its_own_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", CORPUS)
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "corpus-secret")
    monkeypatch.setenv("METAQA_NEO4J_PASSWORD", "metaqa-throwaway")
    corpus = connection.corpus_target()
    assert corpus.password == "corpus-secret"
    assert corpus.name == "corpus"
