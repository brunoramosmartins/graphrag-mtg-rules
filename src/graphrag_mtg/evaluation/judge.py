"""The LLM judge, built from the same rubric constant the human reads.

E-011's amendments are the specification, and three of them are load-bearing
here rather than in the harness:

**One rubric, not two.** The threshold this judge is measured against is the
lower bound of a human self-agreement interval "scored on the same
correctness rubric the judge uses". That sentence means nothing unless there
is a single object. :data:`~graphrag_mtg.evaluation.rubric.RUBRIC` is that
object; the system prompt is built from it, the worksheet prints it, and
:func:`~graphrag_mtg.evaluation.rubric.rubric_hash` travels with every
verdict. A rubric drift becomes a hash mismatch instead of a silent change
of instrument.

**Domain blindness is controlled, not instructed.** Telling a model to score
only against the supplied key asserts by prompt exactly the property E-008
had to build a control to establish. A judge that silently corrects from its
own Magic knowledge is not noise: it systematically favours whichever arm's
answers resemble what it already believes, and agreement figures cannot
detect it, because a judge and a human who share the same knowledge agree
beautifully. So the prompt says it *and* :func:`perturbed_key` builds the
fixture that measures whether it held.

**Both orderings, because position bias is real.** The pairwise comparison
runs A-then-B and B-then-A. A pair the two orderings disagree about is
counted a **tie**, registered before any pair exists, and above a
disagreement rate of 0.20 the pairwise win rate is not published as the
head-to-head at all — the per-stratum correctness comparison becomes the
headline instead.

Nothing here decides anything on its own. Every verdict carries the rubric
hash, the prompt version and the model, so a figure can always name what
produced it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from graphrag_mtg.evaluation.rubric import (
    RUBRIC,
    RUBRIC_VERSION,
    Correctness,
    render_for_judgement,
    rubric_hash,
)

#: Bumped whenever the prompt scaffolding around the rubric changes. The
#: rubric has its own version; this one covers everything else the model
#: sees, so a figure can name both.
JUDGE_PROMPT_VERSION = "p6-j1"

#: What a refusal scores. Registered in E-011a: a refusal is excluded from
#: the *ceiling*, because both human passes would agree on it without
#: judging anything, but downstream a refusal to an answerable question is
#: not the key's answer. Scored here without a model call — it is a rule,
#: not a judgement, and paying for it would invite the model to disagree.
REFUSAL_LABEL = Correctness.INCORRECT

CORRECTNESS_SYSTEM = f"""\
You grade one answer against one answer key.

{RUBRIC}
OUTPUT FORMAT, exactly two lines and nothing else:

LABEL: <correct|partial|incorrect|void>
WHY: <one sentence, naming the specific thing that decided it>
"""

PREFERENCE_SYSTEM = f"""\
You compare two answers to the same question against one answer key.

The key is the only authority. You are not being asked which answer you
prefer, nor which is better written, nor which agrees with what you know
about the game. You are being asked which one says what the key says.

{RUBRIC}
Apply those labels to each answer, then choose. If both would earn the same
label, that is a tie — say so rather than breaking it on style, length, or
which one reads more confidently.

OUTPUT FORMAT, exactly two lines and nothing else:

WINNER: <left|right|tie>
WHY: <one sentence, naming the specific thing that decided it>
"""

_LABEL = re.compile(r"^\s*LABEL:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_WINNER = re.compile(r"^\s*WINNER:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_WHY = re.compile(r"^\s*WHY:\s*(.+)", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class Verdict:
    """One judged answer, with everything needed to name what produced it."""

    question_id: str
    label: Correctness
    rationale: str
    model: str
    rubric_version: str = RUBRIC_VERSION
    rubric_hash: str = ""
    prompt_version: str = JUDGE_PROMPT_VERSION
    #: True when no model was called — a refusal, or an empty answer.
    by_rule: bool = False


@dataclass(frozen=True)
class Preference:
    """One pairwise comparison in one ordering."""

    question_id: str
    winner: str
    rationale: str
    #: Which arm sat on the left in this ordering, so `winner` can be
    #: mapped back to an arm without the caller remembering.
    left_arm: str
    right_arm: str

    def choice(self) -> str:
        """The arm this ordering chose, or `tie`."""
        return {"left": self.left_arm, "right": self.right_arm}.get(self.winner, "tie")


class JudgeFormatError(ValueError):
    """The model did not answer in the required two-line format."""


def parse_label(text: str) -> tuple[Correctness, str]:
    """Read the label and rationale from a judge reply.

    The **last** LABEL line wins. A model that reasons aloud before
    committing writes the word "incorrect" several times on the way to
    "correct", and reading the first match would score the reasoning
    rather than the verdict — the same failure `metaqa.parse_prediction`
    was rewritten to avoid.

    Raises:
        JudgeFormatError: when no line carries a recognised label. A run
            that cannot read a verdict must stop and say so rather than
            record a default, because the default would be a score.
    """
    matches = _LABEL.findall(text or "")
    for raw in reversed(matches):
        try:
            label = Correctness(raw.strip().lower())
        except ValueError:
            continue
        why = _WHY.findall(text)
        return label, (why[-1].strip() if why else "")
    raise JudgeFormatError(f"no LABEL line in judge output: {text[:200]!r}")


def parse_winner(text: str) -> tuple[str, str]:
    """Read the winner and rationale from a comparison reply."""
    matches = _WINNER.findall(text or "")
    for raw in reversed(matches):
        candidate = raw.strip().lower()
        if candidate in {"left", "right", "tie"}:
            why = _WHY.findall(text)
            return candidate, (why[-1].strip() if why else "")
    raise JudgeFormatError(f"no WINNER line in judge output: {text[:200]!r}")


def correctness_prompt(question: str, answer: str, key: str) -> str:
    """The user-side prompt. The answer arrives blinded, as the human's does."""
    return (
        f"## QUESTION\n{question}\n\n"
        f"## ANSWER\n{render_for_judgement(answer)}\n\n"
        f"## KEY\n{key}\n"
    )


def preference_prompt(question: str, left: str, right: str, key: str) -> str:
    return (
        f"## QUESTION\n{question}\n\n"
        f"## LEFT ANSWER\n{render_for_judgement(left)}\n\n"
        f"## RIGHT ANSWER\n{render_for_judgement(right)}\n\n"
        f"## KEY\n{key}\n"
    )


def score(
    question_id: str,
    question: str,
    answer: str,
    key: str,
    generate: Callable[[str, str], str],
    *,
    model: str = "",
    refused: bool = False,
) -> Verdict:
    """Judge one answer against one key.

    Args:
        question_id: For the record.
        question: The question, verbatim.
        answer: What an arm wrote. Citation handles are stripped before
            the model sees it, by the same function that blinds the human.
        key: The answer key. The only authority.
        generate: ``(system, prompt) -> str``, at temperature 0.
        model: Recorded on the verdict.
        refused: Whether the arm declined. Scored by rule, without a call.

    Returns:
        A :class:`Verdict` carrying the rubric hash it was produced under.
    """
    if refused or not render_for_judgement(answer):
        return Verdict(
            question_id=question_id,
            label=REFUSAL_LABEL,
            rationale="refused or empty; the key gives an answer and this does not",
            model=model,
            rubric_hash=rubric_hash(),
            by_rule=True,
        )
    label, why = parse_label(generate(CORRECTNESS_SYSTEM, correctness_prompt(question, answer, key)))
    return Verdict(
        question_id=question_id,
        label=label,
        rationale=why,
        model=model,
        rubric_hash=rubric_hash(),
    )


def compare(
    question_id: str,
    question: str,
    left: str,
    right: str,
    key: str,
    generate: Callable[[str, str], str],
    *,
    left_arm: str,
    right_arm: str,
) -> Preference:
    """One pairwise comparison, in the ordering given."""
    winner, why = parse_winner(
        generate(PREFERENCE_SYSTEM, preference_prompt(question, left, right, key))
    )
    return Preference(
        question_id=question_id,
        winner=winner,
        rationale=why,
        left_arm=left_arm,
        right_arm=right_arm,
    )


def resolve_pair(first: Preference, second: Preference) -> str:
    """The arm a pair chose across both orderings, or `tie`.

    Registered before any pair exists: **an order-disagreeing pair is a
    tie.** Not a coin flip, not the first ordering, not the one that
    matches the correctness labels. A model that answers differently when
    the same two answers swap places has told us it is reading position,
    and the honest record of that is no preference.

    Args:
        first: The A-then-B ordering.
        second: The B-then-A ordering, over the same two answers.

    Returns:
        The winning arm's name, or ``"tie"``.
    """
    if first.question_id != second.question_id:
        raise ValueError(
            f"{first.question_id} paired with {second.question_id} — the two orderings "
            "must be of the same question."
        )
    if {first.left_arm, first.right_arm} != {second.left_arm, second.right_arm}:
        raise ValueError("the two orderings compare different arms")
    return first.choice() if first.choice() == second.choice() else "tie"


def order_disagreement_rate(pairs: list[tuple[Preference, Preference]]) -> float:
    """Share of pairs whose two orderings disagreed.

    Above 0.20 the pairwise win rate is **not** published as the
    head-to-head — the per-stratum correctness comparison becomes the
    headline instead. That threshold is registered in E-011, not chosen
    here.
    """
    if not pairs:
        return 0.0
    disagreed = sum(1 for first, second in pairs if first.choice() != second.choice())
    return disagreed / len(pairs)


#: How a perturbed key is marked in a fixture file, so a perturbed item can
#: never be counted into a reported correctness denominator by accident.
PERTURBED = "perturbed"


def perturbed_key(key: str, replacement: str) -> str:
    """A key altered so that following it disagrees with real Magic.

    E-008's pattern, applied to the judge. A judge told to score only
    against the supplied key either does so or does not, and the only way
    to find out is to supply a key that a domain-knowledgeable reader
    would want to overrule. The judge passes domain blindness only if it
    follows the supplied key on **at least 0.90** of perturbed items, and
    that rate is published beside the agreement figures.

    Args:
        key: The real answer key.
        replacement: The altered key, written by hand in the fixture.

    Returns:
        The replacement. A function rather than a bare field so the call
        site reads as an intentional perturbation and greps as one.
    """
    if not replacement.strip():
        raise ValueError("a perturbed key must actually say something different")
    if replacement.strip() == key.strip():
        raise ValueError("the perturbed key is identical to the real one")
    return replacement


def follows_key(verdict: Verdict, expected: Correctness) -> bool:
    """Whether a perturbed item was scored per the supplied key.

    `expected` is what the *perturbed* key implies, recorded in the
    fixture before the judge runs. A judge scoring from its own Magic
    knowledge disagrees here and agrees everywhere else, which is exactly
    why the control exists.
    """
    return verdict.label is expected
