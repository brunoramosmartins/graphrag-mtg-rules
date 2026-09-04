"""Arm C's text half: arm A's retriever behind arm B's contract.

Pin 12 is the whole of this module, and it is worth restating because it
corrected a mistake in the pin before it — the earlier amendment had
registered arm C's weakness as "a known limitation of C vs B" and put it in
the wrong place.

**C is the shipped system and C vs A is the README figure.** If arm A
became a tuned hybrid while C's text half stayed TF-IDF over CR rules with
oracle-text expansion — reaching a gold rule in 2 of 8 development
`interaction_multihop` questions — then the portfolio's central table would
compare the product against a text retriever *stronger than the one inside
the product*, and the likely published sentence would be "our shipped
GraphRAG loses to a vector baseline" for a build reason rather than a
finding. Registering that as a limitation does not make the figure
readable.

So :class:`VectorRuleSearch` is a drop-in for
`retrieval/rule_search.py::RuleSearch` — same `search` and `evidence`
methods, same call site in `retrieval/pipeline.py`, no change to the
traversal, the budget, or the prompt. TF-IDF `rule_search` remains a
**registered ablation of C**, published on and off.

**One deliberate widening, and the argument for it.** `RuleSearch.evidence`
returns rule nodes only. This returns whatever arm A retrieves — rules,
rulings, cards, glossary entries — because pin 12's requirement is that C's
text half be *the same retriever* A uses, and a version that could not cite
a ruling would be weaker than A by construction. That matters most exactly
where the hypothesis is tested: on all 8 development `interaction_multihop`
questions, arm A retrieves 2 to 17 rulings on a card the answer key names,
and a rules-only adapter would throw every one of them away.
"""

from __future__ import annotations

from collections.abc import Iterable

from graphrag_mtg.evaluation.baseline_vector import VectorArm
from graphrag_mtg.extraction.cite_search import RuleHit
from graphrag_mtg.retrieval.subgraph import Evidence

#: Documents the text half offers the subgraph per question. The budget
#: and `add_evidence`'s per-kind cap decide what survives, so this is a
#: ceiling on the offer rather than on the context — set generously, since
#: withholding candidates here would be handicapping arm C in a way arm A
#: is not handicapped.
DEFAULT_K = 60

#: Distance assigned to text-retrieved evidence. 1, not 0, exactly as
#: `RuleSearch.evidence` assigns it and for the same reason: a lexically
#: or semantically retrieved node was never *named* by the question, so it
#: must lose a budget contest against a node the question actually
#: mentioned. Changing it would alter arm B's eviction order too, which is
#: not a configuration change but a different experiment.
DEFAULT_DISTANCE = 1

#: Which corpus kinds may become evidence, and the `Evidence.kind` each
#: maps to. `glossary` keeps its own kind rather than being folded into
#: `rule`: folding it produced handles like `[rule:Trample]`, which claims
#: a rule numbered "Trample" and is a citation that cannot be checked.
#: Folding it into `keyword` would be as wrong in the other direction —
#: "APNAP Order" and "Timestamp Order" are glossary entries and not
#: keywords. `serialize` renders unfamiliar kinds in a trailing group,
#: which is exactly the behaviour E-002 added for this case, and the
#: ordering cost is cosmetic against a handle that lies.
KIND_MAP = {"rule": "rule", "ruling": "ruling", "card": "card", "glossary": "glossary"}


class VectorRuleSearch:
    """Arm A's retriever, wearing `RuleSearch`'s interface.

    Args:
        arm: A built :class:`~graphrag_mtg.evaluation.baseline_vector.VectorArm`.
            Its mode — hybrid, dense or lexical — is arm C's text half, so
            an ablation of A is automatically the matching ablation of C.
        k: Documents offered per question.
        iterative: Pin 13's protocol variable, passed through so that the
            affordance granted to arm A is granted to arm C's text half as
            well. Parity is symmetric from here.
    """

    #: What `pipeline.retrieve` records in `templates_run`. A run log
    #: saying `rule_search` when this ran is a record that disagrees with
    #: what happened.
    template_name = "vector_search"

    def __init__(self, arm: VectorArm, *, k: int = DEFAULT_K, iterative: bool = False) -> None:
        self._arm = arm
        self._k = k
        self._iterative = iterative

    @property
    def mode(self) -> str:
        """Which ablation of arm A is running underneath."""
        return self._arm.mode

    def _documents(self, question: str, expansions: Iterable[str]) -> list:
        """Retrieve for the question, widened by the graph's own expansions.

        `expansions` is the oracle text of the cards the question names,
        which the graph has already resolved. `RuleSearch` uses it because
        a question is written in card names and the CR never mentions one;
        the same is true of a dense retriever, whose query embedding of
        "Does Humility turn off the counter?" carries no idea what
        *Humility* says. Passing it keeps the two text halves comparable
        rather than handing one a query the other does not get.
        """
        topic = " ".join([question, *expansions]).strip()
        if not topic:
            return []
        retrieved = self._arm.retrieve(topic, iterative=self._iterative)
        return retrieved.documents[: self._k]

    def search(self, question: str, expansions: Iterable[str] = ()) -> list[RuleHit]:
        """Rule hits only, for the rule-level comparisons that already exist.

        `scripts/eval_rule_search.py` and E-006's figures read this method
        and compare rule numbers. Returning rulings here as pseudo-rules
        would silently change what those scripts measure, so the widening
        this module argues for lives in :meth:`evidence` — which is what
        `retrieval/pipeline.py` actually calls — and `search` stays a
        rules-only view.
        """
        return [
            RuleHit(number=document.rule_number, score=0.0, snippet=document.text)
            for document in self._documents(question, expansions)
            if document.rule_number
        ]

    def evidence(
        self,
        question: str,
        expansions: Iterable[str] = (),
        *,
        distance: int = DEFAULT_DISTANCE,
    ) -> list[Evidence]:
        """Retrieved documents as subgraph evidence, citable and provenanced.

        The `path` names the retriever and its mode, so a citation in an
        arm C answer can be traced to whether it came from the graph or
        from the text half — which is what makes C vs B readable as "what
        the text contributed" rather than as one undifferentiated system.
        """
        out: list[Evidence] = []
        for document in self._documents(question, expansions):
            kind = KIND_MAP.get(document.kind)
            if kind is None:
                continue
            out.append(
                Evidence(
                    kind=kind,
                    key=document.doc_id.split(":", 1)[-1],
                    text=document.text,
                    template="vector_search",
                    path=f"{self._arm.mode} retrieval over the shared corpus",
                    distance=distance,
                )
            )
        return out
