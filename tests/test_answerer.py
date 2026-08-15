"""Grounded generation: what reaches the model, and what never does.

The behaviour most worth pinning is the one that costs nothing and
prevents the most: a subgraph that failed retrieval never reaches the
model at all. Phase 4 measured `interaction_multihop` rule recall at
0.12, and asking a model to write about an empty page is precisely when
it writes from memory.
"""

from __future__ import annotations

from graphrag_mtg.generation.answerer import (
    FAN_CONTENT_NOTICE,
    PROMPT_VERSION,
    REFUSAL,
    SYSTEM,
    answer,
    build_prompt,
    is_refusal,
)
from graphrag_mtg.generation.citations import UNVERIFIED
from graphrag_mtg.retrieval.subgraph import Evidence, Outcome, Subgraph


def resolved() -> Subgraph:
    return Subgraph(
        question="What does Flying do?",
        evidence=[
            Evidence(
                kind="rule",
                key="702.9b",
                text="A creature with flying can't be blocked except by flying.",
                template="keyword_definition",
                path="(:Keyword {flying})-[:DEFINED_BY]->(:Rule {702.9b})",
            )
        ],
    )


def failed(outcome: Outcome) -> Subgraph:
    return Subgraph(question="What about the weather?", outcome=outcome, note="nothing named")


def replies(text: str):
    """A generator that answers with `text` and records what it was sent."""
    calls: list[tuple[str, str]] = []

    def generate(system: str, prompt: str) -> str:
        calls.append((system, prompt))
        return text

    generate.calls = calls  # type: ignore[attr-defined]
    return generate


class TestRefusalWithoutGenerating:
    def test_a_failed_retrieval_never_reaches_the_model(self) -> None:
        generate = replies("should not be called")
        result = answer("What about the weather?", failed(Outcome.NO_ENTITIES), generate)
        assert generate.calls == []
        assert result.refused and not result.generated

    def test_the_named_outcome_survives_into_the_answer(self) -> None:
        result = answer("q", failed(Outcome.NO_SEED), replies("x"))
        assert result.outcome is Outcome.NO_SEED
        assert REFUSAL in result.text

    def test_an_empty_resolved_subgraph_is_also_refused(self) -> None:
        """RESOLVED with no evidence would otherwise read as an answerable page."""
        generate = replies("x")
        result = answer("q", Subgraph(question="q"), generate)
        assert result.refused and generate.calls == []


class TestGrounding:
    def test_the_context_and_the_question_both_reach_the_prompt(self) -> None:
        prompt = build_prompt("What does Flying do?", resolved())
        assert "[rule:702.9b]" in prompt
        assert "What does Flying do?" in prompt

    def test_the_system_prompt_forbids_the_model_s_own_knowledge(self) -> None:
        """The E-008 surface: saying it is the only defence the prompt has."""
        assert "not admissible" in SYSTEM

    def test_it_asks_for_connective_sentences_to_be_cited(self) -> None:
        """The class E-007 predicts round 1 will fail on."""
        assert "1/1" in SYSTEM and "claim about the game" in SYSTEM

    def test_it_forbids_writing_paths(self) -> None:
        """Matched on unwrapped text: rewording a line must not silence this."""
        assert "do not write graph paths" in " ".join(SYSTEM.split()).lower()

    def test_it_never_names_the_marker_the_renderer_owns(self) -> None:
        """`p5-a2` explained UNVERIFIED, and round 2 answers started writing it.

        Naming a token the audit machinery emits teaches the model to emit it
        too, which turns a mechanical signal — "this handle is not in the
        context" — into something the model can assert about itself.
        """
        assert UNVERIFIED not in SYSTEM

    def test_refusal_is_offered_as_a_correct_answer(self) -> None:
        assert REFUSAL in SYSTEM and "not a failure" in SYSTEM


class TestGeneratedAnswer:
    def test_handles_render_into_the_reader_format(self) -> None:
        result = answer("q", resolved(), replies("Flying blocks flying [rule:702.9b]."))
        assert "[CR 702.9b]" in result.rendered
        assert "[path: (:Keyword {flying})-[:DEFINED_BY]->(:Rule {702.9b})]" in result.rendered

    def test_a_fabricated_handle_is_collected(self) -> None:
        result = answer("q", resolved(), replies("It says [rule:999.9]."))
        assert result.unknown == ["rule:999.9"]

    def test_the_prose_property_is_what_the_audit_segments(self) -> None:
        result = answer("q", resolved(), replies("Flying blocks flying [rule:702.9b]."))
        assert result.prose == "Flying blocks flying."

    def test_a_model_refusal_is_recorded_as_generated(self) -> None:
        """Distinct from a pipeline refusal: this one cost tokens and a decision."""
        result = answer("q", resolved(), replies(f"{REFUSAL} — no ruling covers this."))
        assert result.refused and result.generated

    def test_the_prompt_version_travels_with_the_answer(self) -> None:
        assert answer("q", resolved(), replies("x [rule:702.9b].")).prompt_version == PROMPT_VERSION


class TestIncompleteContext:
    def test_a_trimmed_subgraph_is_flagged_on_the_answer(self) -> None:
        graph = resolved()
        graph.dropped["rule"] = 3
        result = answer("q", graph, replies("Flying [rule:702.9b]."))
        assert result.context_incomplete

    def test_the_notice_reaches_the_prompt(self) -> None:
        graph = resolved()
        graph.capped["rule"] = 2
        assert "NOTICE" in build_prompt("q", graph)


class TestDisplay:
    def test_every_rendered_answer_carries_the_fan_content_notice(self) -> None:
        """Phase 5 DoD, and a licence obligation before it is a criterion."""
        result = answer("q", resolved(), replies("Flying [rule:702.9b]."))
        assert FAN_CONTENT_NOTICE in result.with_notice()
        assert "Scryfall" in result.with_notice()


class TestRefusalDetection:
    def test_a_bare_refusal_is_detected(self) -> None:
        assert is_refusal(REFUSAL)

    def test_leading_prose_does_not_hide_it(self) -> None:
        assert is_refusal(f"I'm sorry — {REFUSAL} from this context.")

    def test_an_ordinary_answer_is_not_a_refusal(self) -> None:
        assert not is_refusal("Flying blocks flying [rule:702.9b].")
