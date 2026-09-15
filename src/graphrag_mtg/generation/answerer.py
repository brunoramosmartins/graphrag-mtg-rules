"""Answer from the subgraph, cite every claim, or refuse and say why.

Three rules shape this module, and each of them exists because a
measurement said so.

**Refusal is a first-class output, not a fallback.** Phase 4 measured
`interaction_multihop` rule recall at 0.12: for many questions the rule
the answer needs is simply not in the subgraph. An answerer that always
produces prose would, on those, produce prose from somewhere else — which
is the parametric leak E-008 exists to detect. So a subgraph that failed
retrieval short-circuits to a named refusal **without calling the model at
all**: it costs nothing, it cannot hallucinate, and it makes "refused
because there was no evidence" a fact about the pipeline rather than a
judgement about the text.

**The model writes handles, never paths.** It cites ``[rule:613.4]`` and
`generation/citations.py` renders the graph path from the evidence that
was actually retrieved. A model asked to write a path writes a plausible
one, and a plausible path is indistinguishable from a real one to a
reader.

**The context is the only permitted source.** Magic is thirty years old
and the model knows it; the prompt says so explicitly rather than hoping,
and E-008 tests whether saying so worked.

The generator is injected as ``(system, prompt) -> str`` so this module
never imports an LLM client and the caller keeps control of cost.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from graphrag_mtg.generation.citations import cited_handles, expand, strip_citations
from graphrag_mtg.observability import spans
from graphrag_mtg.observability.tracing import annotate, stage
from graphrag_mtg.retrieval.subgraph import Outcome, Subgraph, serialize

#: Recorded with every run, per the E-007 configuration. A figure whose
#: prompt version is unknown is a figure that cannot be reproduced, and
#: this project has already retired three iterations for less.
PROMPT_VERSION = "p5-a3"

#: What the model writes when the context cannot answer the question.
#: Matched case-insensitively; the model is asked to follow it with one
#: sentence naming what is missing, which is the useful part.
REFUSAL = "CANNOT ANSWER"


def refusal_reason(subgraph: Subgraph) -> str:
    """Say what is actually missing, not that nothing arrived.

    This message used to read *"retrieval returned no usable evidence"* on
    every non-`RESOLVED` outcome. On `NO_SEED` that is **false**: entities
    resolved and the traversals ran, and on the E-001 evaluation split the five
    `no_seed` questions reached this branch carrying 1-6 cards and 4-22
    rulings. What is absent is a CR rule reachable from them, which is a very
    different thing to tell a reader — and a sentence that is false on the path
    where it is emitted is the shape of sentence that makes an aggregate read
    wrong six weeks later (E-018 amendment, 2026-09-14).

    The count is included because *"no rule was reachable from 22 rulings"* and
    *"nothing was retrieved"* are the two cases this message has to keep apart.

    Args:
        subgraph: The retrieval result that failed to qualify for generation.

    Returns:
        One sentence naming the outcome and what the context did hold.
    """
    held = len(subgraph.evidence)
    if subgraph.outcome is Outcome.NO_SEED and held:
        return (
            f"retrieval resolved {held} evidence item(s) but none reaches a "
            f"Comprehensive Rules entry ({subgraph.outcome})."
        )
    if subgraph.is_empty:
        return f"retrieval returned nothing ({subgraph.outcome})."
    return (
        f"retrieval returned {held} evidence item(s), not usable for this "
        f"question ({subgraph.outcome})."
    )

#: Required by the Wizards Fan Content Policy on every rendered answer.
FAN_CONTENT_NOTICE = (
    "Unofficial Fan Content permitted under the Wizards of the Coast Fan Content "
    "Policy. Not approved/endorsed by Wizards. Portions of the materials used are "
    "property of Wizards of the Coast. Card data and images from Scryfall."
)

SYSTEM = f"""You answer Magic: The Gathering rules questions from retrieved evidence.

THE EVIDENCE IS YOUR ONLY SOURCE.
You may know this game well. That knowledge is not admissible here. If the
context does not contain something, you do not know it — even if you are
certain, even for a famous card. An answer built on what you remember is a
wrong answer in this system, no matter how correct it happens to be.

CITE EVERY CLAIM.
Every sentence asserting anything about a card, a rule, a ruling, or what
happens in a game carries a citation marker. That includes the sentences
that feel like reasoning rather than facts — "so the creature is still a
1/1" is a claim about the game and needs its evidence like any other.

HOW TO CITE.
Copy the handles exactly as they appear in the context, in square brackets:
  [rule:613.4]              one handle
  [rule:613.4; ruling:3]    several in one marker
Cite ONLY handles that appear in the context, character for character. Do not
invent a handle, do not put a rule number in the `ruling:` namespace, and do
not write graph paths, rule text, or dates into the marker — the renderer
builds all of that from the evidence itself. If no handle in the context
supports what you are about to write, do not write that sentence: say what
is missing instead.

SHOW THE RULE-BY-RULE REASONING.
Walk the applicable rules in the order they apply, one step per sentence,
each step cited. The reader must be able to follow the argument and check
every link in it.

WHEN THE EVIDENCE IS NOT ENOUGH.
Reply exactly `{REFUSAL}` followed by one sentence naming what is missing.
This is a correct answer, not a failure — the honest limit of the retrieved
context. Do not fill a gap with plausible reasoning.

WHEN THE CONTEXT IS MARKED INCOMPLETE.
If the context ends with a NOTICE that it was trimmed, and your answer
depends on what might be missing, say so in the answer.
"""


def build_prompt(question: str, subgraph: Subgraph, *, notice: bool = True) -> str:
    """Assemble the user-side prompt: the context, then the question.

    Args:
        question: The question, verbatim.
        subgraph: What retrieval produced.
        notice: Passed to `serialize`. E-001 suppresses the incompleteness
            notice on every arm so that no arm is handed an invitation to
            hedge that another cannot receive.
    """
    return f"## CONTEXT\n{serialize(subgraph, notice=notice)}\n\n## QUESTION\n{question}\n"


def prompt_digest(system: str, prompt: str) -> str:
    """SHA-256 of exactly what the model was sent, system prompt included.

    Recorded so a later reconstruction can be *verified* instead of assumed.
    Rebuilding a prompt from the same frozen inputs usually reproduces it, and
    a rebuild that quietly differs looks identical to one that does not — the
    failure this project keeps paying for.
    """
    return hashlib.sha256(f"{system}\n\n{prompt}".encode()).hexdigest()


@dataclass
class Answer:
    """One generated answer and everything the audit needs about it.

    Attributes:
        question: The question, verbatim.
        text: What the model wrote, with bare handles.
        rendered: The same answer with citations expanded to the reader
            format. Empty when the answer was refused before generation.
        refused: True when no substantive answer was produced — whether the
            model declined or retrieval never gave it anything.
        generated: False when the refusal was decided by the pipeline and
            the model was never called. The distinction matters to E-007:
            one is the retrieval layer's honesty, the other the prompt's.
        unknown: Handles cited that the subgraph does not contain. Any
            entry here is a fabricated citation — the `evidence_absent`
            code in E-007's taxonomy, detected mechanically.
        handles: Every handle cited, in order.
        outcome: The retrieval outcome this answer was built on.
        context_incomplete: Whether the subgraph was trimmed or capped.
        prompt_version: Recorded per the E-007 configuration.
    """

    question: str
    text: str = ""
    rendered: str = ""
    refused: bool = False
    generated: bool = True
    unknown: list[str] = field(default_factory=list)
    handles: list[str] = field(default_factory=list)
    outcome: Outcome = Outcome.RESOLVED
    context_incomplete: bool = False
    prompt_version: str = PROMPT_VERSION

    @property
    def prose(self) -> str:
        """The answer without citation markers — what E-007 segments."""
        return strip_citations(self.text)

    def with_notice(self) -> str:
        """The rendered answer plus the Fan Content notice, for display."""
        return f"{self.rendered}\n\n---\n{FAN_CONTENT_NOTICE}"


def is_refusal(text: str) -> bool:
    """Whether the model declined. Leading prose is tolerated, as in Phase 4."""
    return REFUSAL.lower() in text.lower()


def answer(
    question: str,
    subgraph: Subgraph,
    generate: Callable[[str, str], str],
    *,
    system: str = SYSTEM,
    notice: bool = True,
    model: str | None = None,
) -> Answer:
    """Generate one grounded answer, or refuse.

    Args:
        question: The user's question, verbatim.
        subgraph: The evidence from `retrieval.pipeline.retrieve`.
        generate: ``(system, prompt) -> str``. Never called when the
            subgraph carries nothing to answer from.
        system: The grounding prompt. Overridable so an iteration round can
            be run and recorded without editing this module.
        notice: Whether the context may carry the incompleteness notice.
            E-001 suppresses it on every arm; `context_incomplete` is
            recorded either way, so the rate is still reported.

    Returns:
        An :class:`Answer`. ``refused`` with ``generated=False`` means
        retrieval produced nothing and no tokens were spent.
    """
    incomplete = bool(subgraph.dropped or subgraph.capped)

    with stage(
        spans.GENERATION,
        **{
            spans.OUTCOME: subgraph.outcome,
            spans.CONTEXT_INCOMPLETE: incomplete,
            spans.PROMPT_VERSION: PROMPT_VERSION,
            # None when the caller did not name one, and an absent
            # attribute is right: the fake generators in the smoke path and
            # in the tests are not a model, and a blank value would read as
            # a model whose name nobody recorded.
            spans.LLM_MODEL_NAME: model,
        },
    ) as span:
        if subgraph.outcome is not Outcome.RESOLVED or subgraph.is_empty:
            # Nothing to answer from. Calling the model here would be asking
            # it to write about an empty page, which is precisely when it
            # writes from memory.
            annotate(span, **{spans.GENERATED: False, spans.REFUSED: True})
            return Answer(
                question=question,
                text=f"{REFUSAL} — {refusal_reason(subgraph)}",
                refused=True,
                generated=False,
                outcome=subgraph.outcome,
                context_incomplete=incomplete,
            )

        prompt = build_prompt(question, subgraph, notice=notice)
        text = generate(system, prompt).strip()
        rendered, unknown = expand(text, subgraph)
        handles = cited_handles(text)
        annotate(
            span,
            **{
                spans.GENERATED: True,
                spans.REFUSED: is_refusal(text),
                # What the model was sent and what it returned. `generation`
                # has been an LLM span since Phase 7 — the kind Phoenix renders
                # with a prompt and a completion — and both were empty, so the
                # trace could say what an answer cited and never what the model
                # was looking at. See the 2026-09-13 amendment to E-012: a cell
                # that had been handing the model the wrong evidence for months
                # was invisible in every trace of it.
                spans.LLM_INPUT: spans.clip(f"{system}\n\n{prompt}"),
                spans.LLM_INPUT_MIME: "text/plain",
                spans.LLM_OUTPUT: spans.clip(text),
                spans.LLM_OUTPUT_MIME: "text/plain",
                # Of the whole prompt, not of the clipped attribute, so a
                # rebuilt prompt can be checked against what was sent instead
                # of being trusted because it looks right.
                spans.PROMPT_SHA256: prompt_digest(system, prompt),
                spans.CITATIONS: len(handles),
                # Which ones, not only how many. A count of 2 beside a
                # traversal that added 8 pieces of evidence says the answer
                # used a quarter of what was retrieved; the handles say
                # which quarter, which is the difference between noticing a
                # number and being able to check it against the paths on
                # the traversal spans above.
                spans.CITATION_KEYS: spans.first_n(handles),
                # Every entry is a fabricated citation, detected
                # mechanically. Non-zero here is the one number in this
                # trace that means the answer is unsound, so it goes on
                # the span rather than only into E-007's taxonomy.
                spans.UNKNOWN_HANDLES: unknown,
                spans.RULE_FAMILIES: spans.rule_families(handles),
            },
        )
        return Answer(
            question=question,
            text=text,
            rendered=rendered,
            refused=is_refusal(text),
            unknown=unknown,
            handles=handles,
            outcome=subgraph.outcome,
            context_incomplete=incomplete,
        )
