"""Neo4j driver helpers.

Thin wrappers around the official ``neo4j`` driver so the rest of the
codebase never constructs a driver ad hoc. Connection details come from
:mod:`graphrag_mtg.config`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase

from graphrag_mtg.config import get_settings


def get_driver() -> Driver:
    """Create a Neo4j :class:`~neo4j.Driver` from the current settings.

    The caller owns the driver's lifecycle and must ``close()`` it, or use
    :func:`driver_session` for a scoped session.
    """
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


@contextmanager
def driver_session() -> Iterator[object]:
    """Yield a Neo4j session, closing both session and driver afterwards."""
    driver = get_driver()
    try:
        with driver.session() as session:
            yield session
    finally:
        driver.close()


def verify_connectivity() -> bool:
    """Return ``True`` if Neo4j is reachable and answers a trivial query.

    Raises:
        neo4j.exceptions.Neo4jError: if the server rejects the connection
            (surfaced so smoke scripts can print an actionable message).
    """
    driver = get_driver()
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            record = session.run("RETURN 1 AS ok").single()
            return record is not None and record["ok"] == 1
    finally:
        driver.close()
