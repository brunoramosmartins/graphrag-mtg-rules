"""Scryfall oracle cards to validated models (the structured backbone).

Parses the daily Scryfall oracle bulk into the node shapes of ontology v1:
``Card``, its ``CardFace`` children for multi-face layouts, and the legality
edges to ``Format``. Printings are deliberately not modeled — no golden-set
question is printing-specific (see ``docs/ontology.md``).

**On strictness.** The roadmap requires that a silent Scryfall schema change
break loudly. Scryfall ships ~50 top-level fields we have no use for, so
``extra="forbid"`` would fail on every card and is the wrong tool. Instead:
extra fields are ignored, the fields we *do* consume are genuinely required,
and legality statuses are an enum — so a removed field or a newly-invented
status raises instead of silently becoming ``None``.

Field optionality is measured against the real bulk, not assumed: on
multi-face cards ``mana_cost``, ``oracle_text`` and ``colors`` are absent at
the top level because they live on the faces (~92% top-level presence).
``cmc``, ``oracle_id``, ``name``, ``layout``, ``type_line``, ``keywords`` and
``legalities`` are present on 100% of the 38,262 cards, so they are required.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.normalize import normalize_name

ORACLE_CARDS_PATH = bulk_path(ORACLE_CARDS_STEM)

# Layouts that are not deck-legal objects: tokens, emblems, and the assorted
# oversized/supplementary card types. Canonical definition — scripts import
# this rather than keeping their own copy.
SKIP_LAYOUTS = frozenset(
    {"token", "double_faced_token", "emblem", "art_series", "vanguard", "scheme", "planar"}
)

FACE_KEY_SEPARATOR = "#"


class LegalityStatus(StrEnum):
    """The four statuses Scryfall emits in ``legalities`` (verified against the bulk)."""

    legal = "legal"
    not_legal = "not_legal"
    banned = "banned"
    restricted = "restricted"


class CardFace(BaseModel):
    """One face of a multi-face card, keyed ``<oracle_id>#<index>``.

    Only ``name`` is required: ``type_line`` is missing on a handful of faces
    (99.8% presence) and the rest vary by layout.
    """

    model_config = ConfigDict(extra="ignore")

    face_key: str
    index: int = Field(ge=0)
    name: str
    mana_cost: str | None = None
    oracle_text: str | None = None
    type_line: str | None = None
    colors: list[str] = Field(default_factory=list)

    @property
    def normalized_name(self) -> str:
        """The face name's canonical linking key."""
        return normalize_name(self.name)


class Card(BaseModel):
    """A Magic card's oracle (gameplay) identity — one node per ``oracle_id``."""

    model_config = ConfigDict(extra="ignore")

    oracle_id: str
    name: str
    layout: str
    cmc: float
    type_line: str
    keywords: list[str] = Field(default_factory=list)
    # Absent at the top level on multi-face cards; the faces carry them.
    mana_cost: str | None = None
    oracle_text: str | None = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list)
    legalities: dict[str, LegalityStatus]
    faces: list[CardFace] = Field(default_factory=list)

    @model_validator(mode="after")
    def _faces_belong_to_this_card(self) -> Card:
        """Every face key must be derived from this card's oracle_id."""
        for face in self.faces:
            expected = face_key(self.oracle_id, face.index)
            if face.face_key != expected:
                msg = f"face_key {face.face_key!r} does not match {expected!r}"
                raise ValueError(msg)
        return self

    @property
    def normalized_name(self) -> str:
        """The card name's canonical linking key (``AEther Vial`` -> ``aether vial``)."""
        return normalize_name(self.name)

    @property
    def is_multi_face(self) -> bool:
        """True when the card carries face nodes rather than top-level text."""
        return bool(self.faces)

    def legality(self, format_name: str) -> LegalityStatus | None:
        """Return the status in ``format_name``, or None if the format is absent."""
        return self.legalities.get(format_name)


def face_key(oracle_id: str, index: int) -> str:
    """Build the stable key for a face: ``<oracle_id>#<index>``."""
    return f"{oracle_id}{FACE_KEY_SEPARATOR}{index}"


def is_playable(raw: dict[str, Any]) -> bool:
    """Whether a raw Scryfall record is a deck-legal card worth modeling.

    Filters non-playable layouts and token type lines, and requires the fields
    the graph keys on. Roughly 3.9k of the 38.3k records are excluded.
    """
    if raw.get("layout") in SKIP_LAYOUTS or "Token" in raw.get("type_line", ""):
        return False
    return bool(raw.get("oracle_id") and raw.get("legalities") and raw.get("name"))


def parse_card(raw: dict[str, Any]) -> Card:
    """Build a :class:`Card` from one raw Scryfall oracle record.

    Raises:
        pydantic.ValidationError: if a required field is missing or a legality
            status is not one of the four known values — i.e. if Scryfall's
            schema moved under us.
    """
    faces = [
        CardFace(face_key=face_key(raw["oracle_id"], i), index=i, **raw_face)
        for i, raw_face in enumerate(raw.get("card_faces") or [])
    ]
    return Card(**{**raw, "faces": faces})


def load_oracle_cards(
    path: Path = ORACLE_CARDS_PATH,
    *,
    playable_only: bool = True,
    limit: int | None = None,
) -> Iterator[Card]:
    """Stream validated cards from the Scryfall oracle bulk.

    Records are yielded one at a time so callers can batch without holding
    models for the whole corpus. Gzipped JSONL (Scryfall's current format) is
    also read record by record; a legacy JSON array still has to be parsed in
    one ~180 MB read, since an array cannot be streamed.

    Args:
        path: The downloaded oracle bulk, in any format `iter_bulk` accepts.
        playable_only: Skip tokens, emblems and other non-deck objects.
        limit: Stop after this many cards — cost discipline for dry runs.

    Yields:
        One validated :class:`Card` per record.
    """
    yielded = 0
    for raw in iter_bulk(path):
        if playable_only and not is_playable(raw):
            continue
        yield parse_card(raw)
        yielded += 1
        if limit is not None and yielded >= limit:
            return


def legality_edges(card: Card) -> Iterator[tuple[str, LegalityStatus]]:
    """Yield ``(format_name, status)`` for each of the card's legality edges."""
    yield from card.legalities.items()
