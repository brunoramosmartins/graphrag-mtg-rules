"""Trivial unit tests — no external services required."""

from __future__ import annotations

import graphrag_mtg
from graphrag_mtg.config import Settings, get_settings


def test_package_version() -> None:
    assert graphrag_mtg.__version__ == "0.1.0"


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.neo4j_uri.startswith("bolt://")
    assert settings.neo4j_user == "neo4j"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
