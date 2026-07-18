"""Deterministic golden-set generators (reliable keys from ground-truth data).

`legality_1hop` questions are generated from a Scryfall oracle card's
``legalities`` field: the answer *is* the data, so these rows are our own
content (committable in full) and auto-verified. `definition_1hop` is
deferred to Phase 2, where the CR glossary parse provides the answer key.
"""

from __future__ import annotations

from graphrag_mtg.evaluation.golden import (
    GoldenQuestion,
    Source,
    Stratum,
    VectorExpectation,
    content_sha256,
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
