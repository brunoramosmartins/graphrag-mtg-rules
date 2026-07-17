"""Shared pytest fixtures/config.

Integration tests (marked ``@pytest.mark.integration``) require a live
Neo4j and are the only tests CI runs against a service container. Unit
tests must never require a running service.
"""
