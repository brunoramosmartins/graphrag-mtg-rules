"""What a trace of this pipeline must contain, and what it must not.

The phase before this one lost a run to a mislabel: the harness handed a
text retriever to what it recorded as the graph-only arm, and every
summary number still looked exactly as that arm should look, because the
routed branch fires on 2 of 20 questions. A viewer reproduces that
failure the moment two arms name their stages the same way, so the tests
here are mostly about **telling the arms apart from the trace alone**.
"""

from __future__ import annotations

import pytest

from graphrag_mtg.evaluation.baseline_vector import VectorArm
from graphrag_mtg.evaluation.bm25 import Bm25Index
from graphrag_mtg.evaluation.corpus import Document
from graphrag_mtg.evaluation.dense import DenseIndex, normalise
from graphrag_mtg.generation.answerer import answer
from graphrag_mtg.observability import spans
from graphrag_mtg.retrieval.linking import QueryLinker, build_card_lexicon
from graphrag_mtg.retrieval.pipeline import retrieve
from graphrag_mtg.retrieval.subgraph import Evidence

# ── Fakes ────────────────────────────────────────────────────────────────────

CARDS = [
    {"name": "Serra Angel", "oracle_id": "serra", "layout": "normal"},
    {"name": "Humility", "oracle_id": "hum", "layout": "normal"},
]
KEYWORD_ROWS = {
    "keyword_definition": [
        {
            "keyword": "Flying",
            "glossary": "A keyword ability.",
            "rule_number": "702.9",
            "rule_text": "Flying is a static ability.",
            "subrules": [],
        }
    ]
}


def linker() -> QueryLinker:
    return QueryLinker(
        build_card_lexicon(CARDS),
        keywords=["Flying"],
        keywords_by_oracle={"serra": ["Flying"], "hum": []},
    )


def runner(table: dict[str, list[dict]] | None = None):
    rows_by_marker = KEYWORD_ROWS if table is None else table

    def run(cypher: str, params):
        for marker, rows in rows_by_marker.items():
            if marker == "keyword_definition" and "DEFINED_BY" in cypher and "HAS_KEYWORD" not in cypher:
                return rows
            if marker in cypher:
                return rows
        return []

    return run


class FakeRuleSearch:
    """Arm C's text half, under the name arm C actually reports."""

    template_name = "vector_search"

    def evidence(self, question: str, expansions=()) -> list[Evidence]:
        return [
            Evidence(
                kind="rule",
                key="613.7",
                text="Timestamp order decides which effect applies first.",
                template=self.template_name,
                path=self.template_name,
                distance=1,
            )
        ]


class FakeEncoder:
    def encode(self, texts):
        return [normalise([1.0, 0.0]) for _ in texts]


def vector_arm() -> VectorArm:
    documents = [
        Document(
            doc_id="rule:702.19",
            kind="rule",
            title="702.19",
            text="Trample lets excess combat damage through.",
            rule_number="702.19",
        ),
        Document(
            doc_id="rule:613.7",
            kind="rule",
            title="613.7",
            text="Timestamp order decides which effect applies first.",
            rule_number="613.7",
        ),
    ]
    ids = [document.doc_id for document in documents]
    return VectorArm(
        documents=documents,
        lexical=Bm25Index(ids, [document.text for document in documents]),
        dense=DenseIndex(ids, [normalise([1.0, 0.0]), normalise([0.0, 1.0])]),
        encoder=FakeEncoder(),
    )


def names(recorded) -> list[str]:
    return [span.name for span in recorded.get_finished_spans()]


def by_name(recorded, name: str):
    return [span for span in recorded.get_finished_spans() if span.name == name]


# ── The vocabulary itself ────────────────────────────────────────────────────


class TestStageSets:
    def test_the_arms_share_exactly_the_two_stages_that_are_the_same_work(self) -> None:
        # Budget and generation genuinely are one operation on every arm.
        # Anything else in the intersection is a stage named for symmetry
        # rather than for what it does, and it is the point at which a
        # trace stops identifying its arm.
        assert spans.GRAPH_STAGES & spans.VECTOR_STAGES == spans.SHARED_STAGES

    def test_each_arm_has_stages_no_other_arm_emits(self) -> None:
        assert spans.GRAPH_STAGES - spans.SHARED_STAGES
        assert spans.VECTOR_STAGES - spans.SHARED_STAGES

    def test_the_vector_arm_has_no_traversal_and_the_graph_arms_no_fusion(self) -> None:
        # Arm A walks nothing; arms B and C fuse nothing. Naming either of
        # those after the other's step is the mislabel in visual form.
        assert spans.TRAVERSAL not in spans.VECTOR_STAGES
        assert spans.FUSION not in spans.GRAPH_STAGES


def attribute_constants() -> dict[str, str]:
    stage_names = spans.GRAPH_STAGES | spans.VECTOR_STAGES | {spans.QUERY}
    return {
        name: value
        for name, value in vars(spans).items()
        if name.isupper() and isinstance(value, str) and value not in stage_names
    }


class TestAttributeNames:
    def test_every_attribute_lives_in_one_namespace(self) -> None:
        # Phoenix filters on the attribute key. One prefix is what makes
        # "show me everything this project recorded" a single query.
        assert all(value.startswith("graphrag.") for value in attribute_constants().values())

    def test_no_two_constants_name_the_same_attribute(self) -> None:
        # A copy-paste that leaves two meanings on one key does not fail
        # anywhere: the second write silently overwrites the first.
        values = list(attribute_constants().values())
        assert len(values) == len(set(values))


class TestRuleFamilies:
    def test_a_subrule_reports_its_chapter(self) -> None:
        assert spans.rule_family("702.9b") == "700"

    def test_a_non_rule_key_is_not_forced_into_a_family(self) -> None:
        assert spans.rule_family("serra-angel") is None

    def test_only_rule_handles_contribute(self) -> None:
        found = spans.rule_families(["rule:613.7", "card:o1", "ruling:9", "rule:702.19"])
        assert found == ["600", "700"]

    def test_families_are_deduplicated_and_sorted(self) -> None:
        assert spans.rule_families(["rule:702.9", "rule:702.19", "rule:104.3a"]) == ["100", "700"]


# ── What a real run emits ────────────────────────────────────────────────────


class TestGraphTrace:
    def test_a_keyword_question_walks_and_does_not_fuse(self, recorded) -> None:
        retrieve("What does Flying do?", linker=linker(), run=runner())
        emitted = set(names(recorded))
        assert emitted <= spans.GRAPH_STAGES
        assert emitted & (spans.VECTOR_STAGES - spans.SHARED_STAGES) == set()
        assert spans.TRAVERSAL in emitted

    def test_the_traversal_span_names_its_template(self, recorded) -> None:
        retrieve("What does Flying do?", linker=linker(), run=runner())
        (traversal,) = by_name(recorded, spans.TRAVERSAL)
        assert traversal.attributes[spans.TEMPLATE] == "keyword_definition"
        assert traversal.attributes[spans.ROWS] == 1

    def test_the_routing_span_records_what_it_chose(self, recorded) -> None:
        retrieve("What does Flying do?", linker=linker(), run=runner())
        (routing,) = by_name(recorded, spans.ROUTING)
        assert list(routing.attributes[spans.PLAN_TEMPLATES]) == ["keyword_definition"]
        assert routing.attributes[spans.PLAN_TEXT_SEARCH] is False

    def test_the_budget_span_reports_the_rule_families_that_survived(self, recorded) -> None:
        retrieve("What does Flying do?", linker=linker(), run=runner())
        (budget,) = by_name(recorded, spans.BUDGET)
        assert list(budget.attributes[spans.RULE_FAMILIES]) == ["700"]
        assert budget.attributes[spans.TOKENS] <= budget.attributes[spans.TOKEN_BUDGET]

    def test_a_seedless_question_says_so_on_the_linking_span(self, recorded) -> None:
        # The one attribute that explains an otherwise puzzling trace:
        # *Humility* has no keyword abilities, so no traversal can reach a
        # CR rule and the text half is not a fallback but the route.
        retrieve(
            "How does Humility work?",
            linker=linker(),
            run=runner({}),
            rule_search=FakeRuleSearch(),
        )
        (linking,) = by_name(recorded, spans.LINKING)
        assert linking.attributes[spans.HAS_GRAPH_SEED] is False
        assert list(linking.attributes[spans.CARDS_LINKED]) == ["Humility"]

    def test_the_text_search_span_names_the_retriever_that_ran(self, recorded) -> None:
        # `rule_search` recorded when `vector_search` ran is a trace that
        # disagrees with the run it describes — the same defect the
        # `templates_run` entry beside it already guards against.
        retrieve(
            "How does Humility work?",
            linker=linker(),
            run=runner({}),
            rule_search=FakeRuleSearch(),
        )
        (text_search,) = by_name(recorded, spans.TEXT_SEARCH)
        assert text_search.attributes[spans.RETRIEVER] == "vector_search"
        assert text_search.attributes[spans.EVIDENCE_ADDED] == 1

    def test_a_question_naming_nothing_emits_the_two_cheap_stages_and_stops(
        self, recorded
    ) -> None:
        # The plan is inspected before the database is touched, and the
        # trace has to show that rather than an empty traversal.
        retrieve("what about the weather", linker=linker(), run=runner())
        assert names(recorded) == [spans.LINKING, spans.ROUTING]


class TestVectorTrace:
    def test_arm_a_fuses_and_does_not_walk(self, recorded) -> None:
        vector_arm().retrieve("trample damage", depth=2)
        emitted = set(names(recorded))
        assert emitted <= spans.VECTOR_STAGES
        assert emitted & (spans.GRAPH_STAGES - spans.SHARED_STAGES) == set()
        assert {spans.LEXICAL, spans.DENSE, spans.FUSION} <= emitted

    def test_the_lexical_span_carries_the_scoring_parameters(self, recorded) -> None:
        # Pin 7's sweep varies k1 and b per call. A trace that omits them
        # cannot say which cell it came from.
        vector_arm().retrieve("trample damage", depth=2, k1=1.6, b=0.4)
        (lexical,) = by_name(recorded, spans.LEXICAL)
        assert lexical.attributes[spans.BM25_K1] == 1.6
        assert lexical.attributes[spans.BM25_B] == 0.4

    def test_a_cached_query_vector_is_visible_as_not_embedding(self, recorded) -> None:
        # 588 sweep cells over one question must not read as 588 paid
        # embeddings, and the only place that distinction survives is here.
        vector_arm().retrieve("trample damage", depth=2, query_vector=normalise([1.0, 0.0]))
        (dense,) = by_name(recorded, spans.DENSE)
        assert dense.attributes[spans.EMBEDDED] is False

    def test_a_second_round_is_counted_not_hidden(self, recorded) -> None:
        # Iterative retrieval is pin 13's protocol variable: both states
        # are published, so the trace has to say which one ran.
        vector_arm().retrieve("timestamp order", depth=2, iterative=True)
        (fusion,) = by_name(recorded, spans.FUSION)
        assert fusion.attributes[spans.ROUNDS] == 2
        assert len(by_name(recorded, spans.LEXICAL)) == 2


class TestGenerationTrace:
    def test_a_refusal_records_that_no_model_was_called(self, recorded) -> None:
        subgraph = retrieve("what about the weather", linker=linker(), run=runner())
        answer(subgraph.question, subgraph, lambda system, prompt: "never reached")
        (generation,) = by_name(recorded, spans.GENERATION)
        assert generation.attributes[spans.GENERATED] is False
        assert generation.attributes[spans.REFUSED] is True

    def test_a_fabricated_citation_reaches_the_span(self, recorded) -> None:
        # Non-zero here means the answer is unsound. It is detected
        # mechanically, so there is no reason for a reader of the trace to
        # have to open E-007's taxonomy to find out.
        subgraph = retrieve("What does Flying do?", linker=linker(), run=runner())
        answer(subgraph.question, subgraph, lambda system, prompt: "See [rule:999.9].")
        (generation,) = by_name(recorded, spans.GENERATION)
        assert list(generation.attributes[spans.UNKNOWN_HANDLES]) == ["rule:999.9"]


class TestRootSpan:
    def test_the_arm_is_on_the_trace(self, recorded) -> None:
        with spans.query_span("What does Flying do?", arm="C"):
            pass
        (root,) = by_name(recorded, spans.QUERY)
        assert root.attributes[spans.ARM] == "C"

    def test_the_question_text_is_withheld_by_default(self, recorded) -> None:
        # A trace is a thing that gets screenshotted into a README, and
        # the golden set's RulesGuru questions are kept out of this repo
        # on purpose — ids plus a gitignored fetch, never the text.
        with spans.query_span("What does Flying do?", arm="C"):
            pass
        (root,) = by_name(recorded, spans.QUERY)
        assert spans.QUESTION not in root.attributes
        assert root.attributes[spans.QUESTION_CHARS] == len("What does Flying do?")

    def test_the_id_names_the_question_without_quoting_it(self, recorded) -> None:
        # A screenshotted trace whose caption claims which question it
        # shows should let the reader check that inside the image. The id
        # is the handle the repo already versions publicly; the text is
        # the part the licence keeps out, and it stays out.
        with spans.query_span("What does Flying do?", arm="C", question_id="hand-flying") as _:
            pass
        (root,) = by_name(recorded, spans.QUERY)
        assert root.attributes[spans.QUESTION_ID] == "hand-flying"
        assert spans.QUESTION not in root.attributes

    def test_a_question_with_no_id_records_none(self, recorded) -> None:
        # The demo app answers free-typed questions, which have no golden
        # id. An absent attribute is right; an empty string would read as
        # an id that exists and is blank.
        with spans.query_span("What does Flying do?", arm="demo"):
            pass
        (root,) = by_name(recorded, spans.QUERY)
        assert spans.QUESTION_ID not in root.attributes

    def test_the_question_can_be_recorded_when_the_caller_owns_it(self, recorded) -> None:
        with spans.query_span("What does Flying do?", arm="demo", record_question=True):
            pass
        (root,) = by_name(recorded, spans.QUERY)
        assert root.attributes[spans.QUESTION] == "What does Flying do?"

    def test_every_stage_hangs_under_the_root(self, recorded) -> None:
        # A stage that is not a child of the query span shows up in
        # Phoenix as its own trace, which is how one question turns into
        # five unrelated rows nobody can correlate.
        with spans.query_span("What does Flying do?", arm="C"):
            retrieve("What does Flying do?", linker=linker(), run=runner())
        finished = recorded.get_finished_spans()
        (root,) = [span for span in finished if span.name == spans.QUERY]
        children = [span for span in finished if span.name != spans.QUERY]
        assert children
        assert {span.parent.trace_id for span in children} == {root.context.trace_id}


@pytest.mark.parametrize("arm", ["A", "B", "C"])
def test_every_registered_arm_can_open_a_trace(recorded, arm: str) -> None:
    with spans.query_span("q", arm=arm):
        pass
    (root,) = by_name(recorded, spans.QUERY)
    assert root.attributes[spans.ARM] == arm
