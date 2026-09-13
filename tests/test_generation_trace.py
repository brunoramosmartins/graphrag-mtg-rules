"""The generation span carries what the model saw and what it said.

`generation` has been registered as an `LLM` span since Phase 7 — the kind
Phoenix renders with a prompt and a completion — and both fields were empty
until 2026-09-13. The trace could say what an answer *cited* and never what the
model was looking at, so "it was handed the right evidence and still failed"
was unfalsifiable from the trace. It took a separate script rendering one case
to find that 92% of an experiment's cell had been handed evidence that did not
answer its question (E-012's amendment, 2026-09-13).

These tests pin the repair: the prompt is on the span, the completion is on the
span, a long prompt is truncated *visibly*, and the hash covers the whole thing
so a reconstruction can be checked rather than trusted.
"""

from __future__ import annotations

from graphrag_mtg.generation.answerer import SYSTEM, answer, build_prompt, prompt_digest
from graphrag_mtg.observability import spans
from graphrag_mtg.retrieval.subgraph import Evidence, Outcome, Subgraph


def evidence(text: str = "Serra Angel | has_keyword | flying") -> Evidence:
    return Evidence(
        kind="triple",
        key="1",
        text=text,
        template="t",
        path="(:MQ_Entity {Serra Angel})-[:MQ_HAS_KEYWORD]->(:MQ_Entity {flying})",
        distance=1,
    )


def never_called(system: str, prompt: str) -> str:
    """A generator that fails the test if the pipeline calls it."""
    raise AssertionError("the model was called on a subgraph with nothing in it")


def one_span(recorded, name: str = spans.GENERATION):
    found = [s for s in recorded.get_finished_spans() if s.name == name]
    assert found, f"no {name} span was recorded"
    return found[-1]


def test_the_prompt_the_model_received_is_on_the_span(recorded) -> None:
    subgraph = Subgraph(question="does it fly?", evidence=[evidence()])
    answer("does it fly?", subgraph, lambda system, prompt: "It flies. [triple:1]")
    attributes = one_span(recorded).attributes
    assert "Serra Angel | has_keyword | flying" in attributes[spans.LLM_INPUT]
    assert attributes[spans.LLM_INPUT_MIME] == "text/plain"


def test_what_the_model_returned_is_on_the_span(recorded) -> None:
    subgraph = Subgraph(question="does it fly?", evidence=[evidence()])
    answer("does it fly?", subgraph, lambda system, prompt: "It flies. [triple:1]")
    attributes = one_span(recorded).attributes
    assert attributes[spans.LLM_OUTPUT] == "It flies. [triple:1]"
    assert attributes[spans.LLM_OUTPUT_MIME] == "text/plain"


def test_the_hash_covers_the_whole_prompt_not_the_clipped_attribute(recorded) -> None:
    subgraph = Subgraph(question="q", evidence=[evidence("x | r | y") for _ in range(400)])
    answer("q", subgraph, lambda system, prompt: "ANSWER: y")
    attributes = one_span(recorded).attributes
    expected = prompt_digest(SYSTEM, build_prompt("q", subgraph))
    assert attributes[spans.PROMPT_SHA256] == expected
    # The attribute itself was cut, so a hash of it would not match — which is
    # the whole point: the hash verifies a rebuild, the attribute only shows one.
    assert len(attributes[spans.LLM_INPUT]) < len(build_prompt("q", subgraph))


def test_truncation_says_so_rather_than_ending_mid_sentence(recorded) -> None:
    subgraph = Subgraph(question="q", evidence=[evidence("x | r | y") for _ in range(400)])
    answer("q", subgraph, lambda system, prompt: "ANSWER: y")
    value = one_span(recorded).attributes[spans.LLM_INPUT]
    assert "truncated at" in value
    assert spans.PROMPT_SHA256 in value


def test_a_short_prompt_is_not_marked_as_truncated() -> None:
    assert "truncated" not in spans.clip("short enough")


def test_a_refusal_decided_before_the_model_records_no_prompt(recorded) -> None:
    """No tokens were spent, so there is no prompt and no completion to show.

    An empty string here would read as "the model was sent nothing and replied
    nothing", which is a different event from "the model was never called".
    """
    subgraph = Subgraph(question="q", evidence=[], outcome=Outcome.NO_MATCH)
    result = answer("q", subgraph, never_called)
    assert result.refused and not result.generated
    attributes = one_span(recorded).attributes
    assert spans.LLM_INPUT not in attributes
    assert spans.LLM_OUTPUT not in attributes



def test_the_digest_changes_when_the_evidence_changes() -> None:
    first = Subgraph(question="q", evidence=[evidence("a | r | b")])
    second = Subgraph(question="q", evidence=[evidence("a | r | c")])
    assert prompt_digest(SYSTEM, build_prompt("q", first)) != prompt_digest(
        SYSTEM, build_prompt("q", second)
    )


def test_the_digest_covers_the_system_prompt_too() -> None:
    """A prompt edit that leaves the context identical must change the hash.

    E-012 and E-014 both pin the prompt version and declare that an edit voids
    the comparison; a digest blind to the system prompt could not detect one.
    """
    subgraph = Subgraph(question="q", evidence=[evidence()])
    prompt = build_prompt("q", subgraph)
    assert prompt_digest(SYSTEM, prompt) != prompt_digest(SYSTEM + " Be terse.", prompt)
