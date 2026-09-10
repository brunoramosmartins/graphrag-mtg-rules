"""Shared pytest fixtures/config.

Integration tests (marked ``@pytest.mark.integration``) require a live
Neo4j and are the only tests CI runs against a service container. Unit
tests must never require a running service.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def _span_exporter():
    """Install one in-memory TracerProvider for the whole session.

    Session-scoped because OpenTelemetry allows exactly one provider per
    process: a second `set_tracer_provider` logs a warning and is ignored,
    so a per-test provider would silently record into the first one and
    every assertion after the first test would be reading stale spans.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    # Simple, not batched: a batch processor would hand the assertions
    # whatever had been flushed so far, which is a race, not a test.
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture
def recorded(_span_exporter):
    """Spans emitted by the test, cleared on both sides."""
    _span_exporter.clear()
    yield _span_exporter
    _span_exporter.clear()
