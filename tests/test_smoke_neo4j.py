"""Integration smoke test for the Neo4j driver.

Requires a live *and healthy* Neo4j (``docker compose up -d --wait``) — Docker
publishes port 7687 before Bolt is listening, so connecting too early fails the
handshake rather than the config.

Marked ``integration``, but note these still run in a plain ``pytest`` invocation:
nothing deselects them by default, deliberately, so missing infrastructure fails
loudly instead of silently passing. Skip them explicitly with
``pytest -m "not integration"``. CI runs them against a service container.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.graph.connection import verify_connectivity


@pytest.mark.integration
def test_neo4j_round_trip() -> None:
    assert verify_connectivity() is True
