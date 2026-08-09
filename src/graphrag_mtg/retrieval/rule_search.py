"""Text retrieval over CR rule text — the half of ADR-007 the graph cannot do.

`scripts/reachability.py` found that 15 of the 30 `interaction_multihop`
questions produce **no graph seed at all**: their cards carry no keyword
abilities, so nothing deterministic connects *Humility* to the layer
system. Traversal depth cannot help a node with no edge. This module is
how those questions reach a rule.

It wraps :class:`~graphrag_mtg.extraction.cite_search.CiteSearch`, the
lexical TF-IDF index already built and tested for the annotation pass,
rather than introducing a second implementation of the same idea. Two
things make that reuse legitimate rather than lazy:

- **No contamination.** `cite_search` helped the annotator choose
  `cited_rules` for the *extraction* gold (E-003). The 77-question golden
  set's `gold_cr_rules` come from RulesGuru and authored questions and
  never passed through it, so E-001 is measuring a tool that did not help
  build its answer key. The same tool was *refused* inside E-003 for
  exactly the opposite reason, and the distinction is the point.
- **It is matched to what it is good at.** E-003a measured where lexical
  overlap works: the annotator's own passes agreed at F1 0.815 on the
  exact rule but 0.902 on the rule *family*, and the disagreements were
  overwhelmingly parent-versus-child. Bag-of-words is structurally blind
  to depth — a rule and its subrule share nearly the same bag — and good
  at area.

So this module deliberately retrieves the **area** and leaves the depth
to the graph: hits are returned as rule numbers that the
``rule_subtree`` traversal then expands. Neither half is asked to do what
it was measured to be bad at.

Question text is filtered before searching, and expanded with the oracle
text of the cards the question names — a question is written in card
names, and the Comprehensive Rules never mention one.

**What this does not fix, measured on the development split.** With
expansions, retrieval reaches a gold rule for 8 of 15 dev questions — but
only **2 of the 8 `interaction_multihop` ones**. ADR-007 assumed text
retrieval would cover the stratum the graph cannot seed; on this
evidence it does not. Questions like *Humility* and *Opalescence* need the
layer system (613.x), and reaching it requires knowing that two
continuous effects must be ordered, which is not a vocabulary overlap
with anything either card says. The boundary the project ends up
reporting is sharper than expected: **neither half reaches that
stratum**, and the honest response is to measure it in Phase 6 rather
than to keep adding mechanisms until something scores.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from graphrag_mtg.etl.cr_parser import CRDocument
from graphrag_mtg.extraction.cite_search import CiteSearch, RuleHit
from graphrag_mtg.retrieval.subgraph import Evidence

#: Interrogative scaffolding. Distinct from `cite_search`'s stopwords,
#: which cover rules prose; these are the words questions add and rulings
#: never contain.
QUESTION_WORDS = frozenset({
    "what", "why", "how", "when", "where", "which", "who", "whom", "whose",
    "does", "do", "did", "is", "are", "was", "were", "can", "could", "should",
    "would", "will", "happens", "happen", "work", "works", "mean", "means",
    "explain", "tell", "me", "my", "i", "you", "your", "please", "about",
    "still", "instead", "anything", "something", "someone", "everything",
    # Pronouns: a question that says "it" has named its topic elsewhere.
    "it", "its", "they", "them", "their", "he", "she", "him", "her", "this",
    "that", "these", "those", "there",
})

#: Rules retrieved per question by default. Small on purpose: this layer
#: proposes an area, and the graph expands it. A wide net here would
#: reproduce the k=6 ball that reachability showed holds half the CR.
DEFAULT_K = 8

#: Below this share of the top hit's score, a rule is noise riding on one
#: shared common term. Relative rather than absolute because IDF sums are
#: not comparable between questions of different lengths.
MIN_SCORE_RATIO = 0.25

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")


def question_terms(question: str) -> str:
    """Strip interrogative scaffolding, keeping what the question is *about*.

    Returns the remaining words joined by spaces, or the original text when
    filtering would leave nothing — a question made entirely of question
    words has no topic, and searching the empty string is worse than
    searching the noise.
    """
    words = [w for w in _WORD.findall(question) if w.lower() not in QUESTION_WORDS]
    return " ".join(words) if words else question


def significant(hits: Iterable[RuleHit], min_ratio: float = MIN_SCORE_RATIO) -> list[RuleHit]:
    """Drop hits far below the best one.

    Lexical search always returns *something*; a ranked list is not
    evidence that any member is relevant. Cutting relative to the top hit
    is what keeps a question with no lexical match in the CR from
    producing eight confident-looking citations.
    """
    ranked = sorted(hits, key=lambda h: h.score, reverse=True)
    if not ranked:
        return []
    floor = ranked[0].score * min_ratio
    return [hit for hit in ranked if hit.score >= floor]


class RuleSearch:
    """Lexical retrieval of CR rules for a question.

    Args:
        doc: The parsed Comprehensive Rules.
        k: Candidates to consider before the significance cut.
        min_ratio: See :func:`significant`.
    """

    def __init__(self, doc: CRDocument, k: int = DEFAULT_K, min_ratio: float = MIN_SCORE_RATIO):
        self._index = CiteSearch(doc)
        self._k = k
        self._min_ratio = min_ratio

    def search(self, question: str, expansions: Iterable[str] = ()) -> list[RuleHit]:
        """Rules whose text shares distinctive vocabulary with the question.

        Args:
            question: The user's question. Interrogative scaffolding is
                stripped by :func:`question_terms`.
            expansions: Extra text to search with — in practice the oracle
                text of the cards the question names, which the graph
                already resolved. A question is written in *card names*
                and the Comprehensive Rules never mention one, so on its
                own it can share no vocabulary with the rule that governs
                it. *Humility* contributes "lose all abilities" and "base
                power and toughness", which the CR does talk about.

                Measured on the Phase 4 development split (15 questions
                with gold rules): retrieval reaches a gold rule in 8 of 15
                with expansions against 6 of 15 without, the gain landing
                on `keyword_rule_2hop` (0/1 -> 1/1) and
                `interaction_multihop` (1/8 -> 2/8).
        """
        topic = " ".join([question_terms(question), *expansions]).strip()
        if not topic:
            return []
        return significant(self._index.search(topic, k=self._k), self._min_ratio)

    def evidence(
        self, question: str, expansions: Iterable[str] = (), *, distance: int = 1
    ) -> list[Evidence]:
        """Hits as subgraph evidence, citable and provenanced.

        ``distance`` is 1 by default, not 0: a lexically retrieved rule was
        never *named* by the question, so it must lose a budget contest
        against a node the question actually mentioned. The subgraph's
        eviction order does the rest.
        """
        return [
            Evidence(
                kind="rule",
                key=hit.number,
                text=hit.snippet,
                template="rule_search",
                path=f"lexical match on CR text (score {hit.score:.1f})",
                distance=distance,
            )
            for hit in self.search(question, expansions)
        ]
