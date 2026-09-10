"""Observability (Phase 7): OpenTelemetry spans, Arize Phoenix as viewer.

`tracing` holds the mechanism — one tracer, one optional OTLP exporter.
`spans` holds the vocabulary — the span names, the attribute names, and
the root span that stamps every trace with the arm that produced it.

Instrumentation is unconditional: with no exporter configured the OTel
API's spans are no-ops, so nothing in the retrieval path branches on
whether tracing is on.
"""
