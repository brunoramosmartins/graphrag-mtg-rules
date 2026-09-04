"""Arm C's text half: a drop-in for RuleSearch, widened on purpose.

Pin 12 redefines arm C as graph retrieval plus *the same* retriever arm A
uses, because C is the shipped system and C vs A is the README figure. If
C's text half were weaker than A's, that table would compare the product
against a retriever stronger than the one inside the product.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.evaluation.arm_c import DEFAULT_DISTANCE, VectorRuleSearch
from graphrag_mtg.evaluation.baseline_vector import build_arm
from graphrag_mtg.evaluation.corpus import Document

CORPUS = [
    Document(
        doc_id="rule:702.19",
        kind="rule",
        title="CR 702.19",
        text="702.19. Trample lets excess combat damage through to the player.",
        rule_number="702.19",
    ),
    Document(
        doc_id="ruling:abc123",
        kind="ruling",
        title="Ruling: Humility",
        text="Humility: With Humility and Opalescence, timestamps decide the outcome.",
        oracle_id="o1",
    ),
    Document(
        doc_id="card:o1",
        kind="card",
        title="Humility",
        text="Humility Enchantment All creatures lose all abilities.",
        oracle_id="o1",
    ),
    Document(
        doc_id="glossary:Trample",
        kind="glossary",
        title="Glossary: Trample",
        text="Trample. A keyword ability modifying combat damage assignment.",
    ),
]


@pytest.fixture
def searcher() -> VectorRuleSearch:
    return VectorRuleSearch(build_arm(CORPUS, mode="lexical", token_budget=10_000))


class TestContract:
    def test_exposes_the_methods_the_pipeline_calls(self, searcher: VectorRuleSearch) -> None:
        # A drop-in for RuleSearch: same call site, no change to the
        # traversal, the budget or the prompt.
        assert callable(searcher.search) and callable(searcher.evidence)

    def test_names_itself_in_the_run_log(self, searcher: VectorRuleSearch) -> None:
        # A run log saying `rule_search` when `vector_search` ran is a
        # record that disagrees with what happened.
        assert searcher.template_name == "vector_search"

    def test_reports_which_ablation_is_underneath(self, searcher: VectorRuleSearch) -> None:
        # An ablation of arm A is automatically the matching ablation of C.
        assert searcher.mode == "lexical"


class TestEvidence:
    def test_returns_rulings_and_cards_not_only_rules(
        self, searcher: VectorRuleSearch
    ) -> None:
        # The deliberate widening. On all 8 development interaction_multihop
        # questions arm A retrieves rulings on a card the answer key names;
        # a rules-only adapter would throw every one of them away and be
        # weaker than arm A by construction.
        kinds = {item.kind for item in searcher.evidence("Humility and Opalescence")}
        assert "ruling" in kinds

    def test_a_glossary_entry_keeps_its_own_kind(self, searcher: VectorRuleSearch) -> None:
        # Folded into `rule` it produced `[rule:Trample]`, a handle
        # claiming a rule numbered "Trample" — a citation that cannot be
        # checked. Folding it into `keyword` would be as wrong the other
        # way: "APNAP Order" is a glossary entry and not a keyword.
        items = searcher.evidence("What does trample do?")
        assert any(item.kind == "glossary" and item.key == "Trample" for item in items)
        assert all(item.kind in {"rule", "ruling", "card", "glossary"} for item in items)

    def test_evidence_lands_at_distance_one(self, searcher: VectorRuleSearch) -> None:
        # Exactly as RuleSearch.evidence assigns it: a retrieved node was
        # never *named* by the question, so it must lose a budget contest
        # against one the question actually mentioned.
        items = searcher.evidence("trample")
        assert items and all(item.distance == DEFAULT_DISTANCE for item in items)

    def test_the_path_names_the_retriever_and_its_mode(
        self, searcher: VectorRuleSearch
    ) -> None:
        # What makes C vs B readable as "what the text contributed" rather
        # than as one undifferentiated system.
        [first, *_] = searcher.evidence("trample")
        assert first.template == "vector_search" and "lexical" in first.path

    def test_the_key_drops_the_kind_prefix(self, searcher: VectorRuleSearch) -> None:
        # Citation handles are `kind:key`; carrying `rule:` inside the key
        # would render as `[rule:rule:702.19]`.
        rules = [i for i in searcher.evidence("trample") if i.kind == "rule"]
        assert any(item.key == "702.19" for item in rules)

    def test_an_empty_question_retrieves_nothing(self, searcher: VectorRuleSearch) -> None:
        assert searcher.evidence("  ") == []


class TestSearch:
    def test_stays_a_rules_only_view(self, searcher: VectorRuleSearch) -> None:
        # eval_rule_search.py and E-006's figures read this method and
        # compare rule numbers. Returning rulings as pseudo-rules would
        # silently change what those scripts measure.
        hits = searcher.search("Humility and Opalescence and trample")
        assert all(hit.number for hit in hits)
        assert all(not hit.number.startswith("ruling") for hit in hits)

    def test_expansions_widen_the_query(self, searcher: VectorRuleSearch) -> None:
        # A question is written in card names and the CR never mentions
        # one. A dense retriever has the same problem as a lexical one:
        # the embedding of the question carries no idea what the card says.
        assert not searcher.search("Does it work?")
        assert searcher.search("Does it work?", ["excess combat damage trample"])
