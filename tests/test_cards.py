"""Tests for the Scryfall oracle card models.

Pure unit tests: fixtures are trimmed copies of real Scryfall records, so the
suite never needs the gitignored bulk in ``data/raw/``. The shapes here mirror
what the real corpus actually contains — notably that multi-face cards carry
no top-level ``mana_cost``/``oracle_text``/``colors``.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from graphrag_mtg.etl.cards import (
    SKIP_LAYOUTS,
    Card,
    LegalityStatus,
    face_key,
    is_playable,
    legality_edges,
    load_oracle_cards,
    parse_card,
)

# A single-face card: text and cost live at the top level.
NORMAL_CARD = {
    "object": "card",
    "oracle_id": "00037840-6089-42ec-8c5c-281f9f474504",
    "name": "Nissa, Worldsoul Speaker",
    "layout": "normal",
    "mana_cost": "{3}{G}",
    "cmc": 4.0,
    "type_line": "Legendary Creature — Elf Druid",
    "oracle_text": "Landfall — Whenever a land you control enters, you get {E}{E}.",
    "colors": ["G"],
    "color_identity": ["G"],
    "keywords": ["Landfall"],
    "legalities": {"standard": "not_legal", "modern": "legal", "vintage": "restricted"},
    # Fields we never consume must be ignored, not rejected.
    "prices": {"usd": "1.23"},
    "artist": "Someone",
}

# A transform card: no top-level cost/text/colors — they are on the faces.
TRANSFORM_CARD = {
    "object": "card",
    "oracle_id": "aaaaaaaa-0000-0000-0000-000000000000",
    "name": "Ulvenwald Captive // Ulvenwald Abomination",
    "layout": "transform",
    "cmc": 2.0,
    "type_line": "Creature — Werewolf // Creature — Eldrazi Werewolf",
    "keywords": [],
    "legalities": {"modern": "legal"},
    "card_faces": [
        {
            "name": "Ulvenwald Captive",
            "mana_cost": "{1}{G}",
            "oracle_text": "Defender. {T}: Add {G}.",
            "type_line": "Creature — Werewolf",
            "colors": ["G"],
        },
        {
            "name": "Ulvenwald Abomination",
            "mana_cost": "",
            "oracle_text": "{T}: Add {C}{C}.",
            "type_line": "Creature — Eldrazi Werewolf",
            "colors": ["G"],
        },
    ],
}


def test_parses_a_single_face_card():
    card = parse_card(NORMAL_CARD)
    assert card.oracle_id == NORMAL_CARD["oracle_id"]
    assert card.name == "Nissa, Worldsoul Speaker"
    assert card.cmc == 4.0
    assert card.keywords == ["Landfall"]
    assert card.faces == []
    assert card.is_multi_face is False


def test_unused_scryfall_fields_are_ignored_not_rejected():
    # ~50 top-level fields we do not model; forbidding extras would fail on
    # every card, so the strictness lives in required fields and enums.
    card = parse_card(NORMAL_CARD)
    assert not hasattr(card, "prices")


def test_multi_face_card_expands_to_faces_with_derived_keys():
    card = parse_card(TRANSFORM_CARD)
    assert card.is_multi_face is True
    assert [f.name for f in card.faces] == ["Ulvenwald Captive", "Ulvenwald Abomination"]
    assert [f.face_key for f in card.faces] == [
        face_key(TRANSFORM_CARD["oracle_id"], 0),
        face_key(TRANSFORM_CARD["oracle_id"], 1),
    ]
    assert [f.index for f in card.faces] == [0, 1]


def test_multi_face_card_has_no_top_level_cost_or_text():
    # This is the real shape: asserting it guards against a model that wrongly
    # marks these required and would then reject every transform card.
    card = parse_card(TRANSFORM_CARD)
    assert card.mana_cost is None
    assert card.oracle_text is None
    assert card.colors == []
    assert card.faces[0].mana_cost == "{1}{G}"


def test_face_key_must_belong_to_its_card():
    card = parse_card(TRANSFORM_CARD)
    bad = card.model_dump()
    bad["faces"][0]["face_key"] = "someone-elses-id#0"
    with pytest.raises(ValidationError):
        Card(**bad)


def test_legality_statuses_are_an_enum():
    card = parse_card(NORMAL_CARD)
    assert card.legality("modern") is LegalityStatus.legal
    assert card.legality("vintage") is LegalityStatus.restricted
    assert card.legality("nonexistent-format") is None


def test_unknown_legality_status_raises_loudly():
    # The point of the enum: a Scryfall schema change must break, not coerce.
    raw = {**NORMAL_CARD, "legalities": {"modern": "sometimes"}}
    with pytest.raises(ValidationError):
        parse_card(raw)


@pytest.mark.parametrize("field", ["oracle_id", "name", "layout", "cmc", "type_line", "legalities"])
def test_missing_required_field_raises(field):
    raw = {k: v for k, v in NORMAL_CARD.items() if k != field}
    with pytest.raises(ValidationError):
        parse_card(raw)


def test_legality_edges_yields_every_format():
    edges = dict(legality_edges(parse_card(NORMAL_CARD)))
    assert edges == {
        "standard": LegalityStatus.not_legal,
        "modern": LegalityStatus.legal,
        "vintage": LegalityStatus.restricted,
    }


def test_normalized_name_folds_ligatures():
    raw = {**NORMAL_CARD, "name": "Æther Vial"}
    assert parse_card(raw).normalized_name == "aether vial"


@pytest.mark.parametrize("layout", sorted(SKIP_LAYOUTS))
def test_non_playable_layouts_are_filtered(layout):
    assert is_playable({**NORMAL_CARD, "layout": layout}) is False


def test_token_type_line_is_filtered_even_on_a_normal_layout():
    assert is_playable({**NORMAL_CARD, "type_line": "Token Creature — Elf"}) is False


def test_playable_requires_the_fields_the_graph_keys_on():
    assert is_playable(NORMAL_CARD) is True
    assert is_playable({**NORMAL_CARD, "oracle_id": ""}) is False
    assert is_playable({**NORMAL_CARD, "legalities": {}}) is False


def test_load_oracle_cards_filters_and_limits(tmp_path):
    bulk = tmp_path / "oracle.json"
    token = {**NORMAL_CARD, "layout": "token", "oracle_id": "tok", "name": "A Token"}
    bulk.write_text(json.dumps([NORMAL_CARD, token, TRANSFORM_CARD]), encoding="utf-8")

    playable = list(load_oracle_cards(bulk))
    assert [c.name for c in playable] == [NORMAL_CARD["name"], TRANSFORM_CARD["name"]]

    assert len(list(load_oracle_cards(bulk, limit=1))) == 1
    assert len(list(load_oracle_cards(bulk, playable_only=False))) == 3
