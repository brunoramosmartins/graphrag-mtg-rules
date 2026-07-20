"""Card-name, face, and mana-cost normalization.

These are the deterministic front of the card-name linking cascade
(ADR-004: exact -> fuzzy -> LLM). Getting the exact stage right is what
keeps the expensive stages from ever being asked: Magic names carry
ligatures (AEther), diacritics (Lim-Dul), curly apostrophes, and
multi-face "A // B" forms that must all collapse to one key.
"""

from __future__ import annotations

import re
import unicodedata

# Characters with no canonical decomposition, so NFKD alone will not fold them.
_LIGATURES = {
    "Æ": "AE",  # AE ligature
    "æ": "ae",
    "Œ": "OE",  # OE ligature
    "œ": "oe",
    "Ø": "O",
    "ø": "o",
    "ß": "ss",
}

# Typographic punctuation -> ASCII, so "Lim-Dul's" matches whichever quote a
# source used.
_PUNCTUATION = {
    "‘": "'",  # noqa: RUF001 - left single quote; the ambiguity IS the data here
    "’": "'",  # noqa: RUF001 - right single quote (the apostrophe in card names)
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "–": "-",  # noqa: RUF001 - en dash
    "—": "-",  # em dash
    "−": "-",  # noqa: RUF001 - minus sign
}

FACE_SEPARATOR = "//"

_WHITESPACE = re.compile(r"\s+")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9 ]+")
_MANA_SYMBOL = re.compile(r"\{([^}]+)\}")


def _fold(text: str) -> str:
    """Replace ligatures/typographic punctuation, then strip diacritics."""
    for source, target in {**_LIGATURES, **_PUNCTUATION}.items():
        text = text.replace(source, target)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(name: str) -> str:
    """Return the canonical matching key for a card name.

    Folds ligatures and diacritics, normalizes quotes/dashes, lowercases,
    and collapses whitespace. Hyphens, apostrophes and commas are kept, so
    distinct names stay distinct.

    >>> normalize_name("AEther Vial")
    'aether vial'
    """
    return _WHITESPACE.sub(" ", _fold(name).lower()).strip()


def loose_name(name: str) -> str:
    """Return a punctuation-free key for the fuzzy stage of the cascade.

    Strips every non-alphanumeric character after :func:`normalize_name`, so
    "Lim-Dul's Vault" and "Lim Duls Vault" collide deliberately.
    """
    return _WHITESPACE.sub(" ", _NON_ALPHANUMERIC.sub("", normalize_name(name))).strip()


def split_faces(name: str) -> list[str]:
    """Split a Scryfall combined name ("Fire // Ice") into its faces.

    Single-face names come back as a one-element list.
    """
    if FACE_SEPARATOR not in name:
        return [name.strip()]
    return [part.strip() for part in name.split(FACE_SEPARATOR) if part.strip()]


def parse_mana_cost(cost: str) -> list[str]:
    """Return the symbols in a mana cost string, e.g. ``{2}{W}{U}`` -> 2, W, U."""
    return _MANA_SYMBOL.findall(cost or "")


def _symbol_value(symbol: str) -> int:
    """Mana value of a single symbol (CR 202.3).

    Generic numbers count as themselves; X/Y/Z count as 0; hybrids use their
    largest component; every other symbol counts as 1.
    """
    if symbol.isdigit():
        return int(symbol)
    if symbol.upper() in {"X", "Y", "Z"}:
        return 0
    if "/" in symbol:
        return max(_symbol_value(part) for part in symbol.split("/"))
    if symbol.upper() == "P":  # bare Phyrexian marker inside a hybrid split
        return 1
    return 1


def mana_value(cost: str) -> int:
    """Return a *single* mana cost's mana value (CR 202.3).

    Only accepts one face's cost. A combined multi-face cost ("{2}{B} // {B}")
    is rejected rather than summed, because the correct answer depends on the
    layout and cannot be derived from the string alone: an adventure card's
    mana value is that of its creature half, while a split card's is taken
    from the combined cost (CR 712.12a). Summing the symbols silently returns
    the wrong number for every adventure card — 209 of them in the current
    bulk. Use Scryfall's ``cmc``, which already encodes those rules, or split
    with :func:`split_faces` and pick the face you mean.

    Raises:
        ValueError: if ``cost`` holds more than one face's cost.

    >>> mana_value("{2}{W}{U}")
    4
    >>> mana_value("{2/W}")
    2
    """
    if FACE_SEPARATOR in (cost or ""):
        msg = (
            f"mana_value() takes one face's cost, got a combined cost {cost!r}. "
            "Use Card.cmc from Scryfall, or split_faces() and pick a face."
        )
        raise ValueError(msg)
    return sum(_symbol_value(symbol) for symbol in parse_mana_cost(cost))
