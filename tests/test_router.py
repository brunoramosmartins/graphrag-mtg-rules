"""Routing: which layer answers, and whether the plan admits its weakness."""

from __future__ import annotations

from graphrag_mtg.extraction.linker import Lexicon
from graphrag_mtg.retrieval.linking import QueryLinker
from graphrag_mtg.retrieval.router import Plan, describe, plan
from graphrag_mtg.retrieval.subgraph import Outcome
from graphrag_mtg.retrieval.templates import BY_NAME

CARDS = [("Humility", "hum"), ("Opalescence", "opa"), ("Serra Angel", "serra")]
ORACLE = {
    "hum": "All creatures lose all abilities and have base power and toughness 1/1.",
    "opa": "Each other non-Aura enchantment is a creature.",
}


def linker() -> QueryLinker:
    return QueryLinker(
        Lexicon.build(CARDS),
        keywords=["Flying", "Deathtouch"],
        keywords_by_oracle={"serra": ["Flying"], "hum": [], "opa": []},
    )


def route(question: str) -> Plan:
    return plan(linker().link(question), oracle_text=ORACLE)


class TestExplicitFailures:
    def test_a_question_naming_nothing_fails_by_name(self) -> None:
        result = route("what about the weather")
        assert result.outcome is Outcome.NO_ENTITIES
        assert not result.runnable

    def test_unconfirmed_surfaces_fail_rather_than_guess(self) -> None:
        """Lowercase 'humility' may be the card or the English word."""
        result = route("how does humility work")
        assert result.outcome is Outcome.AMBIGUOUS
        assert "humility" in result.reason

    def test_a_failed_plan_runs_nothing(self) -> None:
        assert not route("what about the weather").calls


class TestSeededRoute:
    def test_a_keyword_answers_from_the_graph(self) -> None:
        result = route("What does deathtouch do?")
        assert result.outcome is Outcome.RESOLVED
        assert [c.template for c in result.calls] == ["keyword_definition"]
        assert not result.text_search

    def test_a_rule_number_expands_its_subtree_and_neighbourhood(self) -> None:
        result = route("What does rule 613.4b say?")
        assert {c.template for c in result.calls} == {"rule_subtree", "rule_neighbourhood"}
        assert not result.text_search

    def test_a_card_with_keywords_needs_no_text_retrieval(self) -> None:
        result = route("Does Serra Angel have Flying?")
        assert not result.text_search


class TestSeedlessRoute:
    def test_cards_without_keywords_fall_back_to_text(self) -> None:
        """The interaction_multihop route: 15 of 30 such questions."""
        result = route("How does Humility interact with Opalescence?")
        assert result.text_search

    def test_traversals_still_supply_cards_and_rulings(self) -> None:
        result = route("How does Humility interact with Opalescence?")
        assert "card_rulings" in {c.template for c in result.calls}

    def test_two_cards_get_the_interaction_traversal(self) -> None:
        result = route("How does Humility interact with Opalescence?")
        assert "card_interaction" in {c.template for c in result.calls}

    def test_oracle_text_is_carried_for_expansion(self) -> None:
        """A question is written in card names; the CR never mentions one."""
        result = route("How does Humility interact with Opalescence?")
        assert any("lose all abilities" in text for text in result.expansions)

    def test_the_plan_says_this_evidence_is_weaker(self) -> None:
        """A route taken because the graph could not seed must not read as coverage."""
        result = route("How does Humility interact with Opalescence?")
        assert any("weaker evidence" in note for note in result.notes)


class TestCalls:
    def test_every_call_names_a_real_template(self) -> None:
        result = route("Does Serra Angel have Flying?")
        assert all(c.template in BY_NAME for c in result.calls)

    def test_every_call_binds_the_template_parameters(self) -> None:
        for question in ("What does deathtouch do?", "Does Serra Angel have Flying?"):
            for call in route(question).calls:
                declared = set(BY_NAME[call.template].params)
                assert declared <= set(call.params)

    def test_every_call_carries_a_row_limit(self) -> None:
        assert all("limit" in c.params for c in route("Does Serra Angel have Flying?").calls)


class TestDescribe:
    def test_it_states_the_route_and_its_notes(self) -> None:
        entities = linker().link("How does Humility interact with Opalescence?")
        text = describe(entities, plan(entities, oracle_text=ORACLE))
        assert "text retrieval: yes" in text
        assert "note:" in text

    def test_a_failure_is_described_as_one(self) -> None:
        entities = linker().link("what about the weather")
        assert "no_entities" in describe(entities, plan(entities))


class TestCardParameterIsTheResolvedName:
    """The bug that emptied 194 of 245 card traversals in E-007's first run.

    The tokenizer keeps commas and periods because card names contain them
    (*Omnath, Locus of Creation*), so a mention written mid-sentence carries
    its punctuation into the surface. The linker resolves that correctly
    through the loose table; the router used to throw the resolution away and
    re-normalize the raw surface, producing a query for `humility,` — an
    empty traversal indistinguishable, from outside, from a card the graph
    does not hold.
    """

    def params(self, question: str, template: str) -> list[dict]:
        return [dict(c.params) for c in route(question).calls if c.template == template]

    def test_a_trailing_comma_does_not_reach_the_query(self) -> None:
        (call,) = self.params("Nico casts Humility, then passes.", "card_rulings")
        assert call["normalized_name"] == "humility"

    def test_a_sentence_initial_capital_is_still_not_an_assertion(self) -> None:
        """Trimming punctuation must not weaken the capitalization gate.

        "Humility, and then…" capitalizes only because a sentence starts
        there, which is no evidence of a proper noun — so it stays
        ambiguous and routes to nothing, exactly as before this fix.
        """
        assert route("Humility, and then what happens?").outcome is Outcome.AMBIGUOUS

    def test_a_trailing_period_does_not_either(self) -> None:
        (call,) = self.params("Nico casts Opalescence. What resolves?", "card_rulings")
        assert call["normalized_name"] == "opalescence"

    def test_a_clean_mention_is_unchanged(self) -> None:
        (call,) = self.params("What does Serra Angel do", "card_rulings")
        assert call["normalized_name"] == "serra angel"

    def test_the_interaction_pair_uses_resolved_names_too(self) -> None:
        (call,) = self.params("Humility, Opalescence, what happens?", "card_interaction")
        assert (call["left"], call["right"]) == ("humility", "opalescence")
