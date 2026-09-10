"""OpenTelemetry wiring: one tracer, one optional exporter, no invention.

Two facts about OTel decide the whole design of this module, and both are
the library's contract rather than anything built here:

- **The API alone is a no-op.** With no `TracerProvider` installed,
  `trace.get_tracer(...)` returns a proxy whose spans do nothing and cost
  a couple of attribute lookups. So the pipeline can be instrumented
  unconditionally: an unconfigured process pays nothing and exports
  nothing, and there is no `if tracing_enabled` branch anywhere in the
  retrieval code to get out of step with reality.
- **The SDK is what costs something.** `opentelemetry-sdk` and the OTLP
  exporter live in the `tracing` extra, and only :func:`configure` touches
  them. (`observability` is `tracing` plus the Phoenix *viewer*; an
  application that exports spans does not need a web server to look at
  them, which is why the application container installs the smaller one.)

Hence the dependency split: `opentelemetry-api` is a **core** dependency
and is imported at the top of this file unguarded. A guarded import
falling back to a silent no-op would turn "the extra was never installed"
into "no traces ever appeared", which is the failure this project keeps
finding — a missing thing that reports nothing rather than reporting that
it is missing.

Usage in a script or app::

    from graphrag_mtg.observability import tracing
    tracing.configure()          # only here does the SDK get involved
    ...
    tracing.shutdown()           # flush before a short process exits
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

#: Instrumentation scope. Every span this project emits carries it, so a
#: Phoenix project holding traces from more than one service can still be
#: filtered down to ours.
TRACER_NAME = "graphrag_mtg"

#: `service.name` on the resource — what Phoenix labels the trace with.
SERVICE_NAME = "graphrag-mtg-rules"

#: Phoenix's own OTLP/HTTP collector when run locally, and the value
#: `.env.example` suggests. Used only when neither the caller nor the
#: environment names one.
DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"

#: Set by `configure`, read by `active_endpoint`. Not a lock: it exists so
#: a second `configure` pointing somewhere else fails instead of quietly
#: leaving the first provider in place and exporting to the wrong Phoenix.
_endpoint: str | None = None


def tracer() -> Tracer:
    """The one tracer this project emits from."""
    return trace.get_tracer(TRACER_NAME)


def active_endpoint() -> str | None:
    """Where spans are being exported, or None when nothing is configured."""
    return _endpoint


def resolve_endpoint(endpoint: str | None = None) -> str:
    """Where traces would be exported: argument, then environment, then default.

    Pure, and separate from :func:`configure` for the reason `plan_arm` is
    separate from the harness that runs it — the decision is the part
    worth testing, and a test of it should not need an SDK, a network, or
    a provider that can only be installed once per process.
    """
    return endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or DEFAULT_ENDPOINT


def clean_attribute(value: Any) -> Any:
    """Coerce to something OTel will accept, or None to drop the attribute.

    OTel takes `str`, `bool`, `int`, `float`, and homogeneous sequences of
    those; anything else is dropped with a warning at export time, which
    is a silent hole in a trace. Coercing here keeps every call site free
    of the question.
    """
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        # `str()` rather than the value itself: a StrEnum member renders as
        # its value, so `Outcome.NO_SEED` reaches the span as "no_seed"
        # rather than as a repr no reader can filter on.
        return str(value)
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return str(value)


def annotate(span: Span, **attributes: Any) -> None:
    """Set attributes on a span, dropping the ones that are None.

    None means "this did not apply to this run" — an absent attribute says
    that; the string ``"None"`` says something false.
    """
    for key, value in attributes.items():
        cleaned = clean_attribute(value)
        if cleaned is not None:
            span.set_attribute(key, cleaned)


#: OpenInference's attribute for what kind of step a span is. Phoenix reads
#: it to decide how to render one: a span with no kind is drawn as a bare
#: name with no panels, which is why an uninstrumented-looking trace and a
#: trace with a rich private vocabulary look the same in the viewer.
OPENINFERENCE_SPAN_KIND = "openinference.span.kind"

#: Filled by the vocabulary module at import — see
#: `observability.spans.SPAN_KINDS`. It lives here because :func:`stage` is
#: the one place every span passes through, and it is a registry rather
#: than a constant because the reverse dependency is the wrong way round:
#: this module is OTel wiring and must not know what a `traversal` is.
SPAN_KINDS: dict[str, str] = {}


def register_span_kinds(mapping: dict[str, str]) -> None:
    """Declare which OpenInference kind each span name maps to."""
    SPAN_KINDS.update(mapping)


@contextmanager
def stage(name: str, **attributes: Any) -> Iterator[Span]:
    """One pipeline stage as a span, with its attributes already set.

    Exceptions are recorded and the span's status set to ERROR by the SDK
    itself (`record_exception` and `set_status_on_exception` both default
    to True), then re-raised — so a stage that fails is visible in the
    trace and still fails the caller.
    """
    with tracer().start_as_current_span(name) as span:
        kind = SPAN_KINDS.get(name)
        if kind:
            annotate(span, **{OPENINFERENCE_SPAN_KIND: kind})
        annotate(span, **attributes)
        yield span


def configure(endpoint: str | None = None, *, service_name: str = SERVICE_NAME) -> str:
    """Install a TracerProvider exporting over OTLP/HTTP, once.

    Args:
        endpoint: OTLP/HTTP traces endpoint. Falls back to
            ``OTEL_EXPORTER_OTLP_ENDPOINT``, then to
            :data:`DEFAULT_ENDPOINT`.
        service_name: `service.name` on the resource.

    Returns:
        The endpoint now in use.

    Raises:
        RuntimeError: If the `observability` extra is not installed, or if
            a previous call configured a *different* endpoint. The second
            case is not pedantry: OTel keeps the first provider and
            ignores the second silently, so the process would export to
            one Phoenix while the caller believed it was exporting to
            another.
    """
    global _endpoint

    chosen = resolve_endpoint(endpoint)

    if _endpoint is not None:
        if _endpoint != chosen:
            raise RuntimeError(
                f"tracing is already exporting to {_endpoint}; a second configure() "
                f"asking for {chosen} would be ignored by OpenTelemetry, not honoured"
            )
        return _endpoint

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as error:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "tracing export needs the SDK and the OTLP exporter: "
            "pip install -e '.[tracing]' — or '.[observability]', which adds the "
            "Phoenix viewer for running it from a host venv rather than the "
            "compose service"
        ) from error

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=chosen)))
    trace.set_tracer_provider(provider)
    _endpoint = chosen
    return chosen


def shutdown() -> None:
    """Flush pending spans and tear the provider down.

    A batch processor holds spans for up to five seconds. A CLI answering
    one question and exiting is shorter than that, so without this the
    interesting trace is the one that never arrives.
    """
    global _endpoint
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
    _endpoint = None
