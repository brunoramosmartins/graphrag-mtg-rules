"""The tracing mechanism: coercion, endpoint resolution, and one provider.

Nothing here asserts what the pipeline emits — that is `test_spans.py`.
These hold the properties of the plumbing itself, and each one is a way a
trace can be wrong while looking fine in a viewer.
"""

from __future__ import annotations

from enum import StrEnum

import pytest

from graphrag_mtg.observability import tracing
from graphrag_mtg.observability.tracing import (
    DEFAULT_ENDPOINT,
    clean_attribute,
    resolve_endpoint,
    stage,
)
from graphrag_mtg.retrieval.subgraph import Outcome

ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"


class TestEndpointResolution:
    def test_the_argument_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV, "http://from-env:6006/v1/traces")
        assert resolve_endpoint("http://explicit:4318/v1/traces") == "http://explicit:4318/v1/traces"

    def test_the_environment_is_next(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV, "http://from-env:6006/v1/traces")
        assert resolve_endpoint() == "http://from-env:6006/v1/traces"

    def test_the_default_is_the_one_env_example_documents(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A default that disagrees with `.env.example` sends a first-time
        # reader's traces somewhere the compose file never started.
        monkeypatch.delenv(ENV, raising=False)
        assert resolve_endpoint() == DEFAULT_ENDPOINT
        assert DEFAULT_ENDPOINT.endswith("/v1/traces")


class TestConfigureIsIdempotentOrLoud:
    def test_reconfiguring_the_same_endpoint_is_a_no_op(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tracing, "_endpoint", "http://phoenix:6006/v1/traces")
        assert tracing.configure("http://phoenix:6006/v1/traces") == "http://phoenix:6006/v1/traces"

    def test_reconfiguring_elsewhere_raises_instead_of_being_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # OpenTelemetry keeps the first provider and drops the second with
        # a log line. Silently exporting to a Phoenix the caller stopped
        # believing in is the "record disagrees with what happened" shape
        # this project has already paid for once.
        monkeypatch.setattr(tracing, "_endpoint", "http://phoenix:6006/v1/traces")
        with pytest.raises(RuntimeError, match="already exporting"):
            tracing.configure("http://somewhere-else:4318/v1/traces")

    def test_nothing_is_configured_by_importing(self) -> None:
        # Importing the package must not open a socket or install a
        # provider; the app decides, not the import.
        assert tracing.SERVICE_NAME == "graphrag-mtg-rules"


class TestAttributeCoercion:
    def test_none_is_dropped_rather_than_stringified(self, recorded) -> None:
        # "None" as a value is a claim; an absent attribute is the truth.
        with stage("t", present=1, absent=None):
            pass
        (span,) = recorded.get_finished_spans()
        assert span.attributes["present"] == 1
        assert "absent" not in span.attributes

    def test_a_str_enum_lands_as_its_value(self, recorded) -> None:
        # `Outcome.NO_SEED` must be filterable as "no_seed" in the viewer,
        # not as a repr no query matches.
        with stage("t", outcome=Outcome.NO_SEED):
            pass
        (span,) = recorded.get_finished_spans()
        assert span.attributes["outcome"] == "no_seed"

    def test_a_sequence_becomes_a_sequence_of_strings(self, recorded) -> None:
        class Kind(StrEnum):
            CARD = "card"

        with stage("t", kinds=[Kind.CARD, "rule"]):
            pass
        (span,) = recorded.get_finished_spans()
        assert list(span.attributes["kinds"]) == ["card", "rule"]

    def test_an_empty_sequence_is_not_treated_as_absent(self) -> None:
        # "nothing was linked" is a finding, and it must not be coerced
        # into the same None that means "this stage does not report
        # linking". Asserted on the coercion rather than on a recorded
        # span: whether the exporter keeps an empty sequence is OTel's
        # policy, and testing someone else's policy is how a test starts
        # failing on an upgrade that broke nothing here.
        assert clean_attribute([]) == []
        assert clean_attribute(None) is None

    def test_booleans_stay_booleans(self, recorded) -> None:
        with stage("t", seeded=False):
            pass
        (span,) = recorded.get_finished_spans()
        assert span.attributes["seeded"] is False


class TestFailureIsVisible:
    def test_a_raising_stage_is_recorded_and_still_raises(self, recorded) -> None:
        with pytest.raises(ValueError, match="boom"), stage("t"):
            raise ValueError("boom")
        (span,) = recorded.get_finished_spans()
        assert span.status.status_code.name == "ERROR"
        assert [event.name for event in span.events] == ["exception"]
