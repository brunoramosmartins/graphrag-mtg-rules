"""LLM stage of the linking cascade: is this word being used as a card name?

The deterministic stages resolve multi-word names and refuse to guess at
single-word ones ("Opt", "Fear", "Clone", "Terror"). Those refusals are
not a gap — they are the phase's hardest and most valuable decisions,
measured on the homonym stratum (60 of 125 annotated rulings, and ~24%
of the whole corpus).

The question put to the model is deliberately closed: the candidate card
is already known, so this is a **binary judgement with a confidence**,
not open-ended linking. A yes/no keeps the failure modes bounded — the
model cannot invent a card, only misjudge a usage — and it makes the
gate's job simple: threshold the confidence, keep the span the
deterministic scanner already located.

Cost discipline: one call per pending mention, batched by ruling so a
ruling naming three homonyms costs one call, not three.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from graphrag_mtg.extraction.linker import PendingMention
from graphrag_mtg.extraction.llm import LlmClient
from graphrag_mtg.extraction.schemas import CardMention, LinkMethod

SYSTEM_PROMPT = """\
You decide whether words in official Magic: The Gathering rulings are being used \
as card names.

Many Magic cards are named after ordinary English words ("Opt", "Fear", "Clone", \
"Terror", "Shock"). A ruling that says "creatures with fear" is talking about the \
keyword ability, not the card Fear. A ruling that says "if Clone enters as a copy" \
is naming the card.

For each numbered occurrence you are given, reply with a JSON array of objects:
  {"n": <the occurrence number>, "is_card": true|false, "confidence": 0.0-1.0}

Judge each occurrence in its own context. Say false whenever the word is doing \
ordinary work in the sentence: a keyword ability, a common verb or noun, or a \
generic reference. Return the JSON array and nothing else."""


@dataclass
class DisambiguationReport:
    """Resolved mentions plus a named accounting of everything discarded."""

    resolved: list[CardMention] = field(default_factory=list)
    rejected_as_not_a_card: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def _drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def merge(self, other: DisambiguationReport) -> None:
        self.resolved.extend(other.resolved)
        self.rejected_as_not_a_card += other.rejected_as_not_a_card
        for reason, n in other.dropped.items():
            self.dropped[reason] = self.dropped.get(reason, 0) + n


def build_prompt(pending: Sequence[PendingMention], ruling_text: str) -> str:
    """One prompt covering every pending mention in a single ruling.

    Each occurrence is numbered and quoted with its offset, so repeated
    surfaces ("Clone" twice in one ruling) stay distinguishable — the
    model answers per occurrence, not per word.
    """
    lines = []
    for n, p in enumerate(pending, 1):
        names = ", ".join(f'"{oid[:8]}"' for oid in p.candidate_oracle_ids)
        lines.append(
            f'{n}. "{p.mention.surface}" at character {p.mention.span.start} '
            f"(matches {len(p.candidate_oracle_ids)} card(s): {names})"
        )
    return (
        f'Ruling: "{ruling_text}"\n\n'
        "Occurrences to judge:\n" + "\n".join(lines)
    )


def parse_response(
    pending: Sequence[PendingMention],
    raw: object,
) -> DisambiguationReport:
    """Turn a model response into resolved mentions.

    A mention is resolved only when the model says ``is_card`` **and** the
    candidate set holds exactly one card; an ambiguous surface matching
    several cards is left for the gate to reject rather than guessed at.
    Occurrences the model failed to answer are counted, never assumed.
    """
    report = DisambiguationReport()
    if not isinstance(raw, list):
        report._drop("response_not_a_list")
        return report

    answers: dict[int, dict] = {}
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("n"), int):
            answers[item["n"]] = item

    for n, p in enumerate(pending, 1):
        answer = answers.get(n)
        if answer is None:
            report._drop("no_answer_for_occurrence")
            continue
        if not answer.get("is_card"):
            report.rejected_as_not_a_card += 1
            continue
        if len(p.candidate_oracle_ids) != 1:
            report._drop("ambiguous_candidate_set")
            continue
        try:
            confidence = float(answer.get("confidence", 0.0))
        except (TypeError, ValueError):
            report._drop("unparseable_confidence")
            continue
        report.resolved.append(
            CardMention(
                ruling_id=p.mention.ruling_id,
                surface=p.mention.surface,
                oracle_id=p.candidate_oracle_ids[0],
                span=p.mention.span,
                method=LinkMethod.LLM,
                confidence=min(max(confidence, 0.0), 1.0),
            )
        )
    return report


def disambiguate_ruling(
    pending: Sequence[PendingMention],
    ruling_text: str,
    client: LlmClient,
) -> DisambiguationReport:
    """Resolve one ruling's pending mentions (one API call)."""
    if not pending:
        return DisambiguationReport()
    try:
        raw = client.complete_json(build_prompt(pending, ruling_text), system=SYSTEM_PROMPT)
    except ValueError:
        report = DisambiguationReport()
        report._drop("unparseable_response")
        return report
    return parse_response(pending, raw)


def prompts_for_estimate(
    by_ruling: Iterable[tuple[Sequence[PendingMention], str]],
) -> list[str]:
    """Prompts a run would send, for :func:`~.llm.estimate_cost`."""
    return [build_prompt(pending, text) for pending, text in by_ruling if pending]


def to_json_line(mention: CardMention) -> str:
    """Serialize a resolved mention for the candidates file."""
    return json.dumps(mention.model_dump(), ensure_ascii=False)
