"""The one-command run, the smoke, and the figures.

Two properties carry most of this file. A smoke run must be **impossible
to mistake for a measurement** — its files, its rows and its report all
have to say so from the inside, because the console banner is the one
thing that scrolls away. And arm A must run with **no database**, which
`plan_arm` has always claimed and the harness did not honour until now.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_eval
from graphrag_mtg.evaluation.metrics import wilson_interval

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "smoke"


@pytest.fixture
def at_repo_root(monkeypatch: pytest.MonkeyPatch):
    """`smoke_paths` writes repo-relative paths, so anchor the cwd.

    The harness is a script run from the repo root and its defaults are
    relative on purpose — a test that passes only because pytest happened
    to be invoked from the right directory is a test that fails on someone
    else's machine for a reason that has nothing to do with the code.
    """
    monkeypatch.chdir(ROOT)


def namespace(**kw) -> argparse.Namespace:
    defaults = {
        "arm": "A",
        "mode": "lexical",
        "text": "vector",
        "always_text": False,
        "iterative": False,
        "smoke": True,
        "token_budget": 6000,
        "kind_cap": 25,
        "vectors": Path("data/interim/e001_vectors.bin"),
        "embedding_model": "text-embedding-3-small",
        "split_side": "dev",
        "open_the_evaluation_split": False,
    }
    return argparse.Namespace(**{**defaults, **kw})


class TestArtefactNaming:
    """`runs/` is gitignored, so a run file is the only copy of its prose."""

    def test_a_smoke_file_never_lands_where_a_real_one_is_looked_for(self) -> None:
        real = run_eval.artefact(run_eval.ANSWERS, namespace(smoke=False), slug="A", split="dev")
        smoke = run_eval.artefact(run_eval.ANSWERS, namespace(smoke=True), slug="A", split="dev")
        assert real != smoke
        assert real.name.startswith("e001_")
        assert smoke.name.startswith("smoke_")
        assert "e001" not in smoke.name

    def test_the_real_path_is_untouched(self) -> None:
        # The existing runs are pointed at by finished labels; renaming
        # them would orphan E-011a's batch 2.
        path = run_eval.artefact(run_eval.VERDICTS, namespace(smoke=False), slug="C-vector-routed",
                                 split="dev")
        assert str(path).replace("\\", "/") == "runs/e001_C-vector-routed_verdicts_dev.jsonl"

    def test_both_stay_under_runs(self) -> None:
        for smoke in (True, False):
            path = run_eval.artefact(run_eval.RETRIEVAL, namespace(smoke=smoke), slug="A",
                                     split="dev")
            assert path.parts[0] == "runs"


class TestSmokeFakes:
    def test_the_generator_cites_what_it_was_handed(self) -> None:
        # Citation expansion and the unknown-handle check both have to
        # receive something structurally real, or the smoke skips the two
        # stages most worth exercising.
        text = run_eval.smoke_generate("sys", "## CONTEXT\n[rule:702.9] Flying...\n")
        assert "[rule:702.9]" in text

    def test_the_generator_invents_no_handle_when_there_is_none(self) -> None:
        # A fabricated handle would make `unknown_handles` non-empty and
        # the smoke would report an unsound answer on every run.
        assert "[" not in run_eval.smoke_generate("sys", "## CONTEXT\nNO EVIDENCE\n")

    def test_the_generator_never_refuses(self) -> None:
        # A refusal is scored by rule with no judge call, so a refusing
        # fake would leave the judging path untested.
        from graphrag_mtg.generation.answerer import is_refusal

        assert not is_refusal(run_eval.smoke_generate("sys", "[rule:1.1]"))

    def test_the_judge_answers_in_the_judge_s_own_format(self) -> None:
        # Parsed by the real parser, not compared as a string: the fake
        # exists to exercise the format, so a fake the parser rejects
        # would be worse than no fake at all.
        from graphrag_mtg.evaluation.judge import parse_label

        label, why = parse_label(run_eval.smoke_score("sys", "prompt"))
        assert label.value == run_eval.SMOKE_LABEL
        assert "no judge was called" in why

    def test_the_fake_label_is_fixed_rather_than_varied(self) -> None:
        # A varied fake would produce a distribution, and a distribution
        # invites being read as a finding.
        outputs = {run_eval.smoke_score("sys", f"prompt {i}") for i in range(5)}
        assert len(outputs) == 1


class TestSmokeSaysSoFromInsideTheData:
    def test_an_answer_row_carries_the_flag_and_the_fake_model(self) -> None:
        row = run_eval.answer_row(
            {"question_id": "sm-1", "stratum": "definition_1hop"},
            type("R", (), {"text": "t", "rendered": "t", "refused": False, "generated": True,
                           "unknown": [], "context_incomplete": False, "prompt_version": "p5-a3"})(),
            namespace(smoke=True),
            "dev",
            run_eval.SMOKE_MODEL,
        )
        assert row["smoke"] is True
        assert row["model"] == run_eval.SMOKE_MODEL

    def test_a_real_row_says_it_is_not_a_smoke(self) -> None:
        row = run_eval.answer_row(
            {"question_id": "rg-1", "stratum": "definition_1hop"},
            type("R", (), {"text": "t", "rendered": "t", "refused": False, "generated": True,
                           "unknown": [], "context_incomplete": False, "prompt_version": "p5-a3"})(),
            namespace(smoke=False),
            "dev",
            "claude-opus-4-8",
        )
        assert row["smoke"] is False

    def test_the_banner_says_what_ci_does_not_test(self) -> None:
        # The sentence that has to survive editing: a green badge is a
        # claim about the wiring and never about the answers.
        banner = run_eval.SMOKE_BANNER.lower()
        assert "wiring, not" in banner and "quality" in banner
        assert "not a measurement" in banner


class TestSmokePaths:
    def test_every_source_points_at_the_fixture(self) -> None:
        args = namespace(smoke=True)
        run_eval.smoke_paths(args)
        for path in (args.cr, args.cards, args.rulings, args.golden, args.split):
            assert "fixtures" in str(path)

    def test_every_named_source_exists(self, at_repo_root) -> None:
        # A fixture path that drifted from the file it names fails at the
        # first question rather than here, in the middle of a CI run whose
        # subject is something else entirely.
        args = namespace(smoke=True)
        run_eval.smoke_paths(args)
        for path in (args.cr, args.cards, args.rulings, args.split):
            assert Path(path).exists(), path

    def test_the_development_side_is_forced(self) -> None:
        # `--smoke --split-side eval` must not be a way to reach the
        # evaluation guard and think the split moved.
        args = namespace(smoke=True, split_side="eval")
        run_eval.smoke_paths(args)
        assert args.split_side == "dev"

    def test_the_cache_is_the_fixture_not_the_real_one(self) -> None:
        # A developer's machine has gitignored RulesGuru files; a smoke
        # that read one would put licensed text into a fixture run.
        args = namespace(smoke=True)
        run_eval.smoke_paths(args)
        assert args.cache_dir != run_eval.CACHE_DIR


class TestArmATouchesNoDatabase:
    """The claim `plan_arm` makes, asserted of the harness for once.

    `test_run_eval.py` asserts arm A's *plan* uses no graph and always
    has. The harness opened a Neo4j session and read the Scryfall bulk
    before every run regardless, arm A included, and nothing said so
    until CI needed arm A with no database at all.
    """

    def test_the_stack_holds_no_runner_and_no_linker(self, at_repo_root) -> None:
        args = namespace(arm="A", smoke=True)
        run_eval.smoke_paths(args)
        with ExitStack() as resources:
            stack = run_eval.build_retrieval_stack(args, resources)
        assert stack.run is None
        assert stack.linker is None
        assert stack.searcher is not None

    def test_a_fixture_question_retrieves_citable_evidence(self, at_repo_root) -> None:
        args = namespace(arm="A", smoke=True)
        run_eval.smoke_paths(args)
        with ExitStack() as resources:
            stack = run_eval.build_retrieval_stack(args, resources)
            subgraph = run_eval.retrieve_one(
                "What does deathtouch do to combat damage?", stack, args
            )
        assert subgraph.citations()
        assert any(c.startswith("rule:702.2") for c in subgraph.citations())


class TestLoadCards:
    def test_a_named_file_is_read_instead_of_the_bulk(self) -> None:
        cards = run_eval.load_cards(namespace(cards=FIXTURE / "cards.json"))
        assert {c["oracle_id"] for c in cards} == {"smoke-0001", "smoke-0002", "smoke-0003"}

    def test_the_fixture_cards_survive_the_playability_filter(self) -> None:
        # `is_playable` is the predicate pin 8 shares between the graph
        # loader and arm A's index. A fixture card it rejected would give
        # the smoke an empty card half and hide that.
        from graphrag_mtg.etl.cards import is_playable

        assert all(is_playable(c) for c in run_eval.load_cards(namespace(cards=FIXTURE / "cards.json")))


class TestCorrectnessTable:
    def rows(self) -> dict[str, dict]:
        return {
            "q1": {"stratum": "definition_1hop"},
            "q2": {"stratum": "definition_1hop"},
            "q3": {"stratum": "legality_1hop"},
        }

    def test_every_stratum_plus_an_overall_row(self) -> None:
        arms = {"A": {"q1": "correct", "q2": "incorrect", "q3": "correct"}}
        table = run_eval.correctness_table(self.rows(), arms, ["q1", "q2", "q3"], ["A"])
        assert [stratum for stratum, _, _ in table] == [
            "definition_1hop",
            "legality_1hop",
            "ALL",
        ]
        assert [n for _, n, _ in table] == [2, 1, 3]

    def test_partial_does_not_count_as_correct(self) -> None:
        # E-007c found a middle category absorbs uncertainty; letting it
        # count would let the headline move with how generously it was
        # applied.
        arms = {"A": {"q1": "partial", "q2": "partial", "q3": "correct"}}
        table = run_eval.correctness_table(self.rows(), arms, ["q1", "q2", "q3"], ["A"])
        overall = table[-1][2][0]
        assert overall.point == pytest.approx(1 / 3)

    def test_an_empty_intersection_is_refused(self) -> None:
        with pytest.raises(SystemExit, match="empty intersection"):
            run_eval.correctness_table(self.rows(), {"A": {}}, [], ["A"])

    def test_the_table_is_returned_not_printed(self) -> None:
        # The console table and the figure must be the same numbers by
        # construction; two renderers computing their own is how a chart
        # comes to disagree with the table above it.
        arms = {"A": {"q1": "correct", "q2": "correct", "q3": "correct"}}
        table = run_eval.correctness_table(self.rows(), arms, ["q1", "q2", "q3"], ["A"])
        assert all(hasattr(interval, "low") for _, _, cells in table for interval in cells)


def cells() -> list[tuple[str, int, list]]:
    return [
        ("definition_1hop", 4, [wilson_interval(3, 4), wilson_interval(2, 4)]),
        ("ALL", 4, [wilson_interval(3, 4), wilson_interval(2, 4)]),
    ]


class TestForestPlot:
    def test_the_svg_parses(self) -> None:
        root = ET.fromstring(run_eval.forest_svg(cells(), ["A", "B"], "dev", smoke=False))
        assert root.tag.endswith("svg")

    def test_one_mark_per_arm_per_row(self) -> None:
        root = ET.fromstring(run_eval.forest_svg(cells(), ["A", "B"], "dev", smoke=False))
        circles = [e for e in root.iter() if e.tag.endswith("circle")]
        # Two rows times two arms, plus one legend swatch per arm.
        assert len(circles) == 2 * 2 + 2

    def test_the_interval_is_drawn_not_just_the_point(self) -> None:
        # The project's rule is that no proportion is reported bare, and a
        # bar chart of point estimates is a bare proportion with ink on it.
        root = ET.fromstring(run_eval.forest_svg(cells(), ["A"], "dev", smoke=False))
        assert [e for e in root.iter() if e.tag.endswith("line")]

    def test_a_smoke_figure_says_so_on_its_face(self) -> None:
        svg = run_eval.forest_svg(cells(), ["A"], "dev", smoke=True)
        assert "SMOKE" in svg and "not a measurement" in svg

    def test_a_real_figure_carries_no_smoke_note(self) -> None:
        assert "SMOKE" not in run_eval.forest_svg(cells(), ["A"], "dev", smoke=False)

    def test_the_axis_labels_its_own_gridlines_exactly(self) -> None:
        # `:.1f` rendered the quarter ticks as 0.2 and 0.8 — an axis
        # misreporting its own gridlines by a fortieth of the range.
        svg = run_eval.forest_svg(cells(), ["A"], "dev", smoke=False)
        assert ">0.25<" in svg and ">0.75<" in svg

    def test_a_slug_cannot_inject_markup(self) -> None:
        svg = run_eval.forest_svg(cells(), ["<script>"], "dev", smoke=False)
        assert "<script>" not in svg and "&lt;script&gt;" in svg


class TestReportMarkdown:
    def test_the_banner_leads_a_smoke_report(self) -> None:
        assert "SMOKE RUN" in run_eval.report_markdown(cells(), ["A"], "dev", smoke=True)

    def test_a_real_report_has_no_banner(self) -> None:
        assert "SMOKE RUN" not in run_eval.report_markdown(cells(), ["A"], "dev", smoke=False)

    def test_every_figure_carries_its_interval(self) -> None:
        # Computed rather than typed: the project's rule is that no
        # proportion is reported bare, and hardcoding the bounds here
        # would test the transcription instead of the rule.
        interval = wilson_interval(3, 4)
        text = run_eval.report_markdown(cells(), ["A", "B"], "dev", smoke=False)
        assert f"{interval.point:.2f} [{interval.low:.2f}, {interval.high:.2f}]" in text

    def test_it_points_at_the_plot_beside_it(self) -> None:
        assert "correctness_dev.svg" in run_eval.report_markdown(cells(), ["A"], "dev", smoke=False)


class TestWriteFigures:
    def test_both_artefacts_are_written(self, tmp_path: Path) -> None:
        written = run_eval.write_figures(tmp_path, cells(), ["A"], "dev", smoke=False)
        assert {p.suffix for p in written} == {".svg", ".md"}
        assert all(p.exists() for p in written)


class TestCeilingEstimate:
    def test_it_bounds_a_real_prompt_of_the_same_budget(self) -> None:
        # `run` interleaves retrieval and generation so one question is one
        # trace, which means the real prompts do not exist until money
        # could already have been spent. A bound printed before the loop
        # honours the cost rule better than an exact figure printed after.
        from graphrag_mtg.extraction.llm import estimate_cost

        budget = 1000
        bound = run_eval.ceiling_estimate(
            3, model="claude-opus-4-8", budget=budget, output_tokens=200, system="sys"
        )
        actual = estimate_cost(
            ["word " * (budget // 2)] * 3,
            model="claude-opus-4-8",
            output_tokens_per_call=200,
            system="sys",
        )
        assert bound.usd >= actual.usd

    def test_it_scales_with_the_number_of_questions(self) -> None:
        one = run_eval.ceiling_estimate(1, model="claude-opus-4-8", budget=100,
                                        output_tokens=10, system="")
        ten = run_eval.ceiling_estimate(10, model="claude-opus-4-8", budget=100,
                                        output_tokens=10, system="")
        assert ten.usd > one.usd


class TestEmptyGraphIsRefused:
    """A traversal over an empty graph is a run that tested nothing.

    Every question comes back `NO_MATCH`, the run completes, writes its
    files and prints a report. In CI that is a passing smoke with no
    subject; in a real run it is the loader having silently not loaded.
    """

    def stack(self, rows) -> run_eval.Stack:
        plan = run_eval.plan_arm(namespace(arm="B"))
        return run_eval.Stack(plan=plan, searcher=None, run=lambda cypher, params: rows)

    def test_a_graph_with_no_rules_stops_the_run(self) -> None:
        with pytest.raises(SystemExit, match="no Rule nodes"):
            run_eval.require_a_populated_graph(self.stack([{"n": 0}]))

    def test_a_loaded_graph_passes(self) -> None:
        run_eval.require_a_populated_graph(self.stack([{"n": 13}]))

    def test_an_arm_with_no_runner_is_not_asked(self) -> None:
        # Arm A has no session to query, and demanding one would undo the
        # coupling this phase removed.
        plan = run_eval.plan_arm(namespace(arm="A"))
        run_eval.require_a_populated_graph(run_eval.Stack(plan=plan, searcher=object(), run=None))


class TestTheFixtureExercisesTheRouter:
    """Arm C's distinguishing half must actually fire on the fixture.

    Arm C is arm B plus a text retriever, and that retriever runs only
    where the router sends it — on questions whose entities cannot reach
    the CR rule graph. A fixture in which every question seeds the graph
    makes the two arms produce byte-identical output while both pass,
    which is the Phase 6 mislabel with a green badge on it. It very nearly
    happened here: the first five fixture questions all seeded.

    Built without `build_stack`, which opens a Neo4j session for its
    format probe. These run in `lint-and-unit`, where there is no database.
    """

    def linker(self):
        from graphrag_mtg.etl.cr_parser import parse_cr
        from graphrag_mtg.graph.loader import keyword_definition_rows
        from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon

        cards = run_eval.load_cards(namespace(cards=FIXTURE / "cards.json"))
        document = parse_cr(ROOT / "tests" / "fixtures" / "cr_excerpt.txt")
        return QueryLinker(
            build_card_lexicon(cards),
            {row["display_name"] for row in keyword_definition_rows(document)},
            {card["oracle_id"]: card.get("keywords", []) for card in cards},
        )

    def questions(self) -> list[str]:
        import json as _json

        path = FIXTURE / "golden" / "authored_v0.jsonl"
        return [
            _json.loads(line)["question"]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_at_least_one_question_cannot_reach_the_rule_graph(self) -> None:
        linker = self.linker()
        seedless = [q for q in self.questions() if not linker.link(q).has_graph_seed]
        assert seedless, "no fixture question routes to the text half; C would equal B"

    def test_at_least_one_question_does_reach_it(self) -> None:
        # The complement: a fixture that seeded nothing would exercise no
        # traversal at all and arm B would be the one testing nothing.
        linker = self.linker()
        assert any(linker.link(q).has_graph_seed for q in self.questions())

    def test_a_card_with_keywords_and_one_without_are_both_present(self) -> None:
        # `has_graph_seed` turns on exactly this distinction, so a fixture
        # whose cards were all one or all the other could not produce both
        # branches however the questions were written.
        cards = run_eval.load_cards(namespace(cards=FIXTURE / "cards.json"))
        assert any(card.get("keywords") for card in cards)
        assert any(not card.get("keywords") for card in cards)
