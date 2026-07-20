"""Deterministic golden-set generators (reliable keys from ground-truth data).

`legality_1hop` questions are generated from a Scryfall oracle card's
``legalities`` field: the answer *is* the data, so these rows are our own
content (committable in full) and auto-verified.

`definition_1hop` is built from the CR glossary parsed in Phase 2. The
*selection* and the *citation* are derived from the real document — the
keyword must exist in the glossary and its cited rule must exist in the tree —
but the answer prose is **ours**, deliberately. Copying glossary text into a
committed file would redistribute CR text, which the project's IP rules forbid;
paraphrasing keeps the row fully ours, the same posture as the authored set.
"""

from __future__ import annotations

from graphrag_mtg.etl.normalize import normalize_name
from graphrag_mtg.evaluation.golden import (
    GoldenQuestion,
    Source,
    Stratum,
    VectorExpectation,
    content_sha256,
)

# Why this stratum predicts a tie, recorded a priori. The evaluation needs
# strata where the vector baseline should draw: without them a reported graph
# win cannot be falsified.
_TIE_REASON = (
    "The CR states this keyword's effect in one self-contained passage (its "
    "701.x/702.x rule), so a passage retriever should find it as readily as the "
    "graph edge does. No traversal is required, and claiming a graph advantage "
    "here would be over-claiming."
)

# Scryfall format keys -> display names for the question stem.
FORMAT_DISPLAY: dict[str, str] = {
    "standard": "Standard",
    "pioneer": "Pioneer",
    "modern": "Modern",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
    "commander": "Commander",
    "brawl": "Brawl",
    "historic": "Historic",
    "explorer": "Explorer",
    "oathbreaker": "Oathbreaker",
}

# Scryfall legality status -> answer template (a reliable, mechanical key).
STATUS_ANSWER: dict[str, str] = {
    "legal": "Yes - {name} is legal in {fmt}.",
    "not_legal": "No - {name} is not legal in {fmt}.",
    "banned": "No - {name} is banned in {fmt}.",
    "restricted": "{name} is restricted in {fmt}: legal, but limited to one copy per deck.",
}


def build_legality_question(card: dict, fmt: str) -> GoldenQuestion | None:
    """Build a ``legality_1hop`` question for one card + format, or None.

    Returns None if the card lacks a name/oracle_id or has no legality entry
    for ``fmt``, or the status is unrecognized.
    """
    name = card.get("name")
    oracle_id = card.get("oracle_id")
    status = card.get("legalities", {}).get(fmt)
    if not name or not oracle_id or status not in STATUS_ANSWER:
        return None

    fmt_display = FORMAT_DISPLAY.get(fmt, fmt.title())
    return GoldenQuestion(
        id=f"scry-leg-{oracle_id}-{fmt}",
        source=Source.scryfall,
        stratum=Stratum.legality_1hop,
        hops=1,
        question=f"Is {name} legal in {fmt_display}?",
        answer=STATUS_ANSWER[status].format(name=name, fmt=fmt_display),
        gold_entities=[name],
        gold_path=(
            f"(:Card {{oracle_id:'{oracle_id}'}})"
            f"-[:HAS_LEGALITY {{status:'{status}'}}]->(:Format {{name:'{fmt}'}})"
        ),
        # Format legality is structured card metadata; the graph answers it
        # with a first-class edge, while the vector baseline over prose has
        # weak, unreliable signal. Conservative a-priori: lose, not fail.
        vector_should=VectorExpectation.lose,
        snapshot_sha256=content_sha256(f"{oracle_id}|{fmt}|{status}"),
        verified=True,  # answer is mechanically derived from ground-truth data
    )


def build_definition_question(keyword: str, rule_number: str, answer: str) -> GoldenQuestion:
    """Build a ``definition_1hop`` question for one keyword.

    Args:
        keyword: Display spelling, e.g. ``First strike``.
        rule_number: The CR rule that defines it, e.g. ``702.7``. The caller is
            responsible for having validated it against the parsed CR.
        answer: Our paraphrase of the rule's effect — never CR text verbatim.

    Returns:
        A ``tie``-predicted, verified question keyed on the normalized keyword,
        matching how :mod:`graphrag_mtg.graph.loader` merges ``Keyword`` nodes.
    """
    key = normalize_name(keyword)
    return GoldenQuestion(
        id=f"hand-def-{key.replace(' ', '-')}",
        source=Source.authored,
        stratum=Stratum.definition_1hop,
        hops=1,
        question=f"What does {key} do?",
        answer=answer,
        gold_entities=[keyword],
        gold_cr_rules=[rule_number],
        gold_path=f"(:Keyword {{name:'{key}'}})-[:DEFINED_BY]->(:Rule {{number:'{rule_number}'}})",
        vector_should=VectorExpectation.tie,
        vector_should_reason=_TIE_REASON,
        snapshot_sha256=content_sha256(f"{key}|{rule_number}|{answer}"),
        # Verified as: the keyword and its rule are checked to exist in the
        # parsed CR by the generating script, and the paraphrase is the
        # author's, reviewed against the rule text.
        verified=True,
    )
