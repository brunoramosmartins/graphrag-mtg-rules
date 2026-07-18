"""Unit tests for card-name / face / mana-cost normalization (ADR-004)."""

from __future__ import annotations

import pytest

from graphrag_mtg.etl.normalize import (
    loose_name,
    mana_value,
    normalize_name,
    parse_mana_cost,
    split_faces,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lightning Bolt", "lightning bolt"),
        ("Æther Vial", "aether vial"),          # ligature has no NFKD decomposition
        ("æther vial", "aether vial"),
        ("Lim-Dûl's Vault", "lim-dul's vault"),  # diacritic folded, hyphen kept
        ("Jötun Grunt", "jotun grunt"),
        ("Márton Stromgald", "marton stromgald"),
        ("Séance", "seance"),
        ("Lim-Dul’s Vault", "lim-dul's vault"),  # curly apostrophe -> ASCII
        ("  Sol   Ring  ", "sol ring"),          # whitespace collapsed
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_normalize_name_is_idempotent():
    once = normalize_name("Æther Vial")
    assert normalize_name(once) == once


def test_loose_name_strips_punctuation_but_keeps_words():
    assert loose_name("Lim-Dûl's Vault") == "limduls vault"
    assert loose_name("Yawgmoth, Thran Physician") == "yawgmoth thran physician"


def test_loose_name_collides_deliberately():
    assert loose_name("Lim-Dul's Vault") == loose_name("LimDuls Vault")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Fire // Ice", ["Fire", "Ice"]),
        ("Delver of Secrets // Insectile Aberration", ["Delver of Secrets", "Insectile Aberration"]),
        ("Lightning Bolt", ["Lightning Bolt"]),
        ("  Fire  //  Ice  ", ["Fire", "Ice"]),
    ],
)
def test_split_faces(raw, expected):
    assert split_faces(raw) == expected


def test_parse_mana_cost():
    assert parse_mana_cost("{2}{W}{U}") == ["2", "W", "U"]
    assert parse_mana_cost("") == []
    assert parse_mana_cost(None) == []


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        ("{2}{W}{U}", 4),
        ("{W}", 1),
        ("", 0),
        ("{X}{R}", 1),          # X counts as 0 on a card (CR 202.3d)
        ("{W/U}", 1),           # hybrid: largest component
        ("{2/W}", 2),           # monocolor hybrid: the generic side is larger
        ("{W/P}", 1),           # Phyrexian
        ("{C}", 1),             # colorless
        ("{S}", 1),             # snow
        ("{10}", 10),           # multi-digit generic
    ],
)
def test_mana_value(cost, expected):
    assert mana_value(cost) == expected
