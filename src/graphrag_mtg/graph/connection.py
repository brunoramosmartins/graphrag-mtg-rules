"""Neo4j driver helpers.

Thin wrappers around the official ``neo4j`` driver so the rest of the
codebase never constructs a driver ad hoc. Connection details come from
:mod:`graphrag_mtg.config`.

Two targets exist, and they are two *servers*, not two databases. The
corpus target holds Magic; the MetaQA target is a disposable instance that
only E-002 ever touches. Neo4j Community serves exactly one user database,
so "a separate database" is not available here — and the alternative, a
namespace inside the Magic graph, is what deleted three real CR rules when
E-008's teardown ran. See the E-002 amendment of 2026-09-02.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from neo4j import Driver, GraphDatabase

from graphrag_mtg.config import get_settings


@dataclass(frozen=True)
class Target:
    """Where to connect, as one unit.

    URI and credentials travel together so they cannot drift apart — a
    right password against the wrong URI is exactly how a throwaway
    experiment reaches a production graph.

    Attributes:
        uri: Bolt URI of the instance.
        user: Neo4j username.
        password: Neo4j password.
        name: Short label used in error messages.
    """

    uri: str
    user: str
    password: str
    name: str


def corpus_target() -> Target:
    """The instance holding the Magic corpus."""
    settings = get_settings()
    return Target(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        name="corpus",
    )


def metaqa_target() -> Target:
    """The disposable instance E-002 loads the MetaQA KB into.

    Returns:
        The second instance's target, after checking it is a second
        instance at all.

    Raises:
        SystemExit: If it resolves to the same URI as the corpus. The
            check is here rather than in the caller because there is no
            situation in which loading 43k foreign triples into the Magic
            graph is the intent, and a misconfigured ``.env`` is the most
            likely way it would happen.
    """
    settings = get_settings()
    target = Target(
        uri=settings.metaqa_neo4j_uri,
        user=settings.metaqa_neo4j_user,
        password=settings.metaqa_neo4j_password,
        name="metaqa",
    )
    if _same_instance(target.uri, settings.neo4j_uri):
        raise SystemExit(
            f"refusing to use {target.uri} for MetaQA: it is the same Neo4j "
            "instance as the corpus. E-002 requires a separate instance — "
            "start it with `docker compose --profile metaqa up -d` and point "
            "METAQA_NEO4J_URI at it (bolt://localhost:7688 by default)."
        )
    return target


def get_driver(target: Target | None = None) -> Driver:
    """Create a Neo4j :class:`~neo4j.Driver` for one target.

    Args:
        target: Which instance to connect to. ``None`` means the corpus,
            which is what every caller outside E-002 wants.

    Returns:
        A driver the caller owns and must ``close()``, or use
        :func:`driver_session` for a scoped session.
    """
    resolved = target or corpus_target()
    return GraphDatabase.driver(
        resolved.uri, auth=(resolved.user, resolved.password)
    )


@contextmanager
def driver_session(target: Target | None = None) -> Iterator[object]:
    """Yield a Neo4j session, closing both session and driver afterwards.

    Args:
        target: Which instance to open the session against. ``None`` means
            the corpus.
    """
    driver = get_driver(target)
    try:
        with driver.session() as session:
            yield session
    finally:
        driver.close()


def verify_connectivity(target: Target | None = None) -> bool:
    """Return ``True`` if the target is reachable and answers a trivial query.

    Raises:
        neo4j.exceptions.Neo4jError: if the server rejects the connection
            (surfaced so smoke scripts can print an actionable message).
    """
    driver = get_driver(target)
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            record = session.run("RETURN 1 AS ok").single()
            return record is not None and record["ok"] == 1
    finally:
        driver.close()


def _same_instance(left: str, right: str) -> bool:
    """Whether two Bolt URIs address the same server.

    Compared case-insensitively and without a trailing slash, because
    ``BOLT://localhost:7687/`` and ``bolt://localhost:7687`` are the same
    server and a guard that misses that is decorative.
    """
    return left.strip().rstrip("/").casefold() == right.strip().rstrip("/").casefold()
