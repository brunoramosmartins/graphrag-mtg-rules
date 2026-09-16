"""The one entry point a reader will point at a question of their own.

Everything else here answers from `data/golden/`, where the question, the key
and the split are fixed. This script has none of that, and the first question
asked through it hit `NO_ENTITIES` — an outcome that fired **zero** times
across E-001's 57 evaluation questions. So the things worth pinning are the
ones a frozen question never exercises: that the arm is a choice and the
default is the shipped one, that it fails before spending two minutes building
a corpus it cannot embed, and that the one recoverable refusal says how to
recover from it while the genuine limits stay quiet.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ask
from graphrag_mtg.retrieval.subgraph import Evidence, Outcome, Subgraph


def settings(*, openai: str = "", anthropic: str = "") -> SimpleNamespace:
    return SimpleNamespace(openai_api_key=openai, anthropic_api_key=anthropic)


def args(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "arm": "C",
        "text": "vector",
        "mode": "hybrid",
        "always_text": False,
        "retrieval_only": False,
        "cr": Path("data/raw/comprehensive_rules.txt"),
        "vectors": Path("data/interim/e001_vectors.bin"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def cr_file(tmp_path: Path) -> Path:
    path = tmp_path / "cr.txt"
    path.write_text("100. General", encoding="utf-8")
    return path


def item(kind: str, key: str, template: str, path: str) -> Evidence:
    return Evidence(
        kind=kind, key=key, text="what the node says", template=template, path=path
    )


class TestWhichConfigurationsSpendOnEmbeddings:
    """One embedding call per ask, or none — decided without any I/O.

    The documents are cached and the question is not, so the cost follows the
    retriever the arm plans for rather than the flag a reader happened to pass.
    """

    def test_the_vector_baseline_embeds_the_question(self) -> None:
        assert ask.needs_encoder(args(arm="A")) is True

    def test_the_lexical_half_embeds_nothing(self) -> None:
        assert ask.needs_encoder(args(arm="A", mode="lexical")) is False

    def test_the_shipped_hybrid_embeds_through_its_text_half(self) -> None:
        assert ask.needs_encoder(args(arm="C")) is True

    def test_the_tfidf_ablation_embeds_nothing(self) -> None:
        assert ask.needs_encoder(args(arm="C", text="tfidf")) is False

    def test_the_graph_only_arm_has_no_retriever_to_pay_for(self) -> None:
        # Arm B is defined as having no text half, so `--text vector` on it is
        # a flag with nothing behind it — and charging for it would be paying
        # for a retriever that never runs.
        assert ask.needs_encoder(args(arm="B")) is False


class TestPreflightFailsBeforeTheExpensivePart:
    def test_a_configuration_that_embeds_needs_the_encoder_key(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k"))
        with pytest.raises(SystemExit) as exit_info:
            ask.preflight(args(cr=cr_file(tmp_path)))
        assert "OPENAI_API_KEY" in str(exit_info.value)

    def test_it_names_both_ways_out_rather_than_only_the_problem(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k"))
        with pytest.raises(SystemExit) as exit_info:
            ask.preflight(args(cr=cr_file(tmp_path)))
        assert "--mode lexical" in str(exit_info.value)
        assert "--text tfidf" in str(exit_info.value)

    def test_a_configuration_that_embeds_nothing_passes_without_that_key(
        self, monkeypatch, tmp_path
    ) -> None:
        # Refusing here would be a guard firing for a reason that does not
        # apply, which is as wrong as one that cannot fire.
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k"))
        ask.preflight(args(text="tfidf", cr=cr_file(tmp_path)))
        ask.preflight(args(arm="A", mode="lexical", cr=cr_file(tmp_path)))

    def test_retrieval_only_needs_no_llm_key_at_all(self, monkeypatch, tmp_path) -> None:
        # The claim the usage text makes: the evidence half costs nothing and
        # needs no credentials. If that stops holding, the script is
        # advertising something it cannot do.
        monkeypatch.setattr(ask, "get_settings", lambda: settings())
        ask.preflight(args(text="tfidf", retrieval_only=True, cr=cr_file(tmp_path)))

    def test_generating_without_any_key_is_refused_with_the_free_option(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(ask, "get_settings", lambda: settings())
        with pytest.raises(SystemExit) as exit_info:
            ask.preflight(args(text="tfidf", cr=cr_file(tmp_path)))
        assert "--retrieval-only" in str(exit_info.value)

    def test_a_missing_corpus_is_named_before_anything_is_built(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k", openai="k"))
        with pytest.raises(SystemExit) as exit_info:
            ask.preflight(args(cr=tmp_path / "absent.txt"))
        assert "bootstrap" in str(exit_info.value)

    def test_a_missing_vector_index_is_named_before_the_corpus_is_built(
        self, monkeypatch, tmp_path
    ) -> None:
        """The default configuration is the one a fresh clone cannot run yet.

        `bootstrap.py` builds the graph and says the vector index is a separate
        paid build, so this is the likeliest first failure a reader meets —
        and without this check it arrives after two minutes of corpus loading.
        """
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k", openai="k"))
        with pytest.raises(SystemExit) as exit_info:
            ask.preflight(args(cr=cr_file(tmp_path), vectors=tmp_path / "absent.bin"))
        message = str(exit_info.value)
        assert "run_eval.py index" in message
        assert "--mode lexical" in message

    def test_a_configuration_that_reads_no_index_does_not_check_for_one(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(ask, "get_settings", lambda: settings(anthropic="k", openai="k"))
        ask.preflight(args(text="tfidf", cr=cr_file(tmp_path), vectors=tmp_path / "absent.bin"))
        ask.preflight(
            args(arm="A", mode="lexical", cr=cr_file(tmp_path), vectors=tmp_path / "absent.bin")
        )


class TestTheDefaultsNameTheShippedSystem:
    """Pin 12, at the one place a reader forms an impression of the product.

    TF-IDF over CR rules is a *registered ablation* of arm C, published on and
    off. Defaulting to it would demonstrate a system nobody shipped, and the
    demonstration would be indistinguishable from the real one.
    """

    def test_the_default_arm_is_the_shipped_hybrid(self) -> None:
        parsed = ask.build_parser().parse_args(["does deathtouch stack?"])
        assert parsed.arm == "C"
        assert parsed.text == "vector"
        assert parsed.mode == "hybrid"

    def test_the_router_ablation_is_off_by_default(self) -> None:
        # `always_text_search` off is the shipped system; E-001 publishes both
        # states, and the flag exists so the choice is visible rather than
        # enjoyed quietly.
        assert ask.build_parser().parse_args(["q"]).always_text is False

    def test_every_registered_arm_is_offered(self) -> None:
        parsed = [ask.build_parser().parse_args(["q", "--arm", arm]).arm for arm in ask.ARMS]
        assert sorted(parsed) == sorted(ask.ARMS)

    def test_the_smoke_generator_is_not_reachable_from_here(self) -> None:
        """`--smoke` answers with a fake that cites the first handle it is handed.

        `build_retrieval_stack` reads the flag, so it has to be set; a person
        asking a real question must not be able to get the fixture's answer
        back and read it as the system's.
        """
        parsed = ask.build_parser().parse_args(["q"])
        assert parsed.smoke is False
        assert parsed.cards is None
        with pytest.raises(SystemExit):
            ask.build_parser().parse_args(["q", "--smoke"])


def seedless(question: str = "q") -> Subgraph:
    return Subgraph(question=question, outcome=Outcome.NO_ENTITIES)


class TestTheOnlyRefusalThatComesWithAdvice:
    """Zero of 57 evaluation questions, and the first two asked outside them.

    A golden set drawn from a card-question site cannot contain a question that
    names no card, so `NO_ENTITIES` was unreachable by construction and looked
    like a branch that could not fire. It fires, and for two different reasons
    that want two different answers.
    """

    def test_a_question_naming_nothing_is_pointed_at_the_arm_that_can_take_it(self) -> None:
        hint = ask.hint_for(seedless("does damage wear off between turns?"), "C")
        assert hint is not None
        assert "--arm A" in hint

    def test_the_advice_says_which_flag_does_not_help(self) -> None:
        # `--always-text` is the obvious thing to reach for and it cannot work:
        # the planner returns before the text-search branch. A reader who tries
        # it and sees the same output learns nothing about why.
        assert "--always-text" in (ask.hint_for(seedless(), "C") or "")

    def test_arm_a_gets_no_advice_because_there_is_none_to_give(self) -> None:
        assert ask.hint_for(seedless(), "A") is None

    def test_a_genuine_limit_is_reported_without_a_flag_to_try(self) -> None:
        # `no_seed` and `no_match` are the system's honest edge, not a
        # configuration mistake. Offering a re-roll on them would teach a reader
        # to keep asking until the output looks better.
        for outcome in (Outcome.NO_SEED, Outcome.NO_MATCH, Outcome.AMBIGUOUS):
            assert ask.hint_for(Subgraph(question="q", outcome=outcome), "C") is None


class TestThePossessiveIsADefectAndNotALimit:
    """A named card that is in the graph, and does not resolve.

    `QueryLinker` matches surfaces against a lexicon of exact card names, so
    "Gollum, Riddle Master's ability" contains no match while "the ability of
    Gollum, Riddle Master" does — and the second phrasing retrieves the ruling
    that answers the question. Sending that reader to arm A would move them off
    the arm that answers them, which is why the two cases do not share advice.
    """

    def test_a_possessive_is_named_before_the_arm_is_suggested(self) -> None:
        hint = ask.hint_for(seedless("What does Gollum, Riddle Master's ability do?"), "C")
        assert hint is not None
        assert hint.startswith(ask.POSSESSIVE_HINT)

    def test_the_reader_is_still_told_about_arm_a(self) -> None:
        # The rephrasing is worth trying first and is not guaranteed to work;
        # dropping the fallback would leave a reader with one suggestion and no
        # second move.
        hint = ask.hint_for(seedless("Is Gollum, Riddle Master's ability optional?"), "C")
        assert "--arm A" in (hint or "")

    def test_a_question_with_no_apostrophe_gets_only_the_arm_advice(self) -> None:
        assert ask.hint_for(seedless("does damage wear off?"), "C") == ask.SEEDLESS_HINT

    def test_the_pattern_matches_a_possessive_and_not_a_contraction_of_is(self) -> None:
        # "what's" and "it's" are the same three characters doing different
        # work. Both would be flagged, and the advice would be wrong on one of
        # them — so the pattern is pinned to what it actually detects rather
        # than to what the message claims.
        assert ask.POSSESSIVE.search("Gollum, Riddle Master's ability")
        assert not ask.POSSESSIVE.search("the ability of Gollum, Riddle Master")
        assert not ask.POSSESSIVE.search("Whenever an opponent casts a spell")

    def test_an_apostrophe_on_a_resolved_question_changes_nothing(self) -> None:
        # The hint is keyed on the outcome first. A question that linked fine
        # and happens to contain an apostrophe must not be told its phrasing
        # was the problem.
        resolved = Subgraph(
            question="What does Gollum, Riddle Master's ability do?",
            evidence=[item("card", "Gollum, Riddle Master", "card_core", "(:Card)")],
        )
        assert ask.hint_for(resolved, "C") is None

    def test_the_question_is_read_off_the_subgraph_and_not_passed_beside_it(self) -> None:
        """One source for the question, because two can disagree.

        The first version took the question as a second argument, and a caller
        that passed only the subgraph silently got its advice chosen from an
        empty string — a wrong branch with nothing to announce it.
        """
        assert ask.hint_for(seedless("Is Humility's effect an ability?"), "C") != ask.SEEDLESS_HINT


class TestWhatTheReaderIsShown:
    def test_every_item_is_printed_with_the_edge_that_produced_it(self, capsys) -> None:
        """E-029's finding, made visible at the point of use.

        The vector baseline's provenance is one constant string across 2,215
        items; the graph arm's names which edge was walked. Printing an item
        without its path throws away the only part a reader can check.
        """
        subgraph = Subgraph(
            question="q",
            evidence=[
                item("rule", "702.2b", "keyword_definition", "(:Keyword)-[:DEFINED_BY]->(:Rule)")
            ],
            templates_run=["keyword_definition"],
        )
        ask.report_retrieval(subgraph, show_context=False)
        printed = capsys.readouterr().out
        assert "[rule:702.2b]" in printed
        assert "[:DEFINED_BY]" in printed

    def test_a_trimmed_context_says_so(self, capsys) -> None:
        subgraph = Subgraph(question="q", evidence=[item("rule", "1", "t", "p")])
        subgraph.capped["ruling"] = 27
        ask.report_retrieval(subgraph, show_context=False)
        assert "capped {'ruling': 27}" in capsys.readouterr().out

    def test_the_preview_says_how_much_it_is_not_showing(self, capsys) -> None:
        # A truncation a reader cannot see is the failure this repository has
        # paid for most often.
        subgraph = Subgraph(
            question="q",
            evidence=[item("ruling", str(i), "card_rulings", "p") for i in range(ask.PREVIEW + 5)],
        )
        ask.report_retrieval(subgraph, show_context=False)
        assert "... 5 more" in capsys.readouterr().out

    def test_show_context_prints_what_the_model_receives(self, capsys) -> None:
        """Standing rule 8 wants the final prompt as sent, not a paraphrase."""
        subgraph = Subgraph(
            question="q", evidence=[item("rule", "702.2b", "keyword_definition", "(:Rule)")]
        )
        ask.report_retrieval(subgraph, show_context=True)
        printed = capsys.readouterr().out
        assert "## rule" in printed
        assert "context as sent" in printed

    def test_a_template_that_never_ran_is_distinguishable_from_one_that_found_nothing(
        self, capsys
    ) -> None:
        # Two different diagnoses, and the line must not collapse them: the
        # question that prompted this script had "none ran", and reading it as
        # "ran and found nothing" points at the wrong half of the pipeline.
        ask.report_retrieval(Subgraph(question="q", outcome=Outcome.NO_ENTITIES), show_context=False)
        assert "none ran" in capsys.readouterr().out
