"""Integration smoke test for the Neo4j driver.

Requires a live Neo4j (``docker compose up -d``). Skipped by default in
plain ``pytest`` runs unless the ``integration`` marker is selected; CI
runs it against a service container.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.graph.connection import verify_connectivity


@pytest.mark.integration
def test_neo4j_round_trip() -> None:
    assert verify_connectivity() is True
