"""BM25 over the E-001 corpus — the lexical half of arm A.

Pin 2 makes arm A a hybrid rather than a dense-only retriever, and the
reason is specific to this corpus rather than general good practice. The
Comprehensive Rules have **exact-token semantics**: `613.4b` is not
approximately `613.4a`, and a rule that cites one does not mean the other.
And Magic's terms of art are ordinary English words whose ordinary-English
embedding is actively misleading — `flying`, `protection`, `regenerate`,
*Humility*. A dense retriever is built to collapse exactly the distinctions
this corpus depends on.

`extraction/cite_search.py` already has a TF-IDF index and is deliberately
not reused: it scores 3,308 CR rules for an annotation aid, while arm A
indexes 115k documents whose lengths span two orders of magnitude — an
eight-word rule beside a 300-word card. Without length normalisation those
two score **identically** on a term each mentions once, so the one-line
rule that answers the question has no advantage over a card that merely
contains the word. BM25's `b` parameter is what separates them, and it is
the thing missing rather than a preference.

What `b` does **not** do, stated because the first draft of this docstring
claimed otherwise and a test caught it: it does not overturn term
frequency. A 300-word card saying "trample" forty times still outranks an
eight-word rule saying it once, because BM25 saturates term frequency
rather than discarding it, and forty mentions genuinely are evidence.
Length normalisation decides between documents of comparable term
frequency; it is not a preference for short documents.

Parameters are the standard `k1=1.2`, `b=0.75`. They are **not** tuned
here: pin 7 allows tuning on the 20 development questions and requires the
sweep to be published, so any change to these arrives as a swept artefact
and not as a constant someone adjusted.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Terms are lowercase words **or rule numbers**. A tokenizer that split
#: `613.4b` into `613` and `4b` would destroy the one thing lexical
#: retrieval is here to preserve, so rule-shaped tokens are matched first
#: and kept whole.
_RULE_NUMBER = re.compile(r"\b\d{3}\.\d+[a-z]?\b")
_WORD = re.compile(r"[a-z][a-z0-9'\-]*")

#: Words carrying no retrieval signal in questions phrased as questions.
#: Deliberately short: an aggressive list would remove `may`, `must` and
#: `can`, which are the modal verbs the rules turn on.
STOPWORDS = frozenset(
    (
        # articles, conjunctions, prepositions
        "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for",
        "with", "as", "by", "from", "if", "then", "than", "but", "so",
        "about", "into", "over", "under",
        # copulas
        "is", "are", "was", "were", "be", "been", "being",
        # pronouns and determiners
        "it", "its", "this", "that", "these", "those", "there", "their",
        "they", "them", "he", "she", "his", "her", "you", "your", "i", "we",
        "our",
        # interrogative scaffolding
        "what", "does", "do", "did",
    )
)

#: Standard BM25. Registered as untuned; pin 7 governs any change.
K1 = 1.2
B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase words plus whole rule numbers, stopwords removed.

    Rule numbers are extracted before the text is word-split, so `613.4b`
    survives as one term instead of becoming `613` and `4b`.
    """
    lowered = text.lower()
    numbers = _RULE_NUMBER.findall(lowered)
    without = _RULE_NUMBER.sub(" ", lowered)
    words = [w for w in _WORD.findall(without) if w not in STOPWORDS and len(w) > 1]
    return numbers + words


@dataclass(frozen=True)
class Hit:
    """One scored document.

    Attributes:
        doc_id: The corpus handle.
        score: BM25 score. Comparable within one query only — never
            across queries, and never against a dense similarity, which
            is why fusion is by rank rather than by score.
    """

    doc_id: str
    score: float


class Bm25Index:
    """An inverted index with BM25 scoring.

    Built in memory from the corpus. 115k documents of Magic text is
    roughly 7M postings, which fits comfortably and takes about a minute
    to build — small enough that persisting it would add a staleness bug
    for no gain.
    """

    def __init__(self, doc_ids: Sequence[str], texts: Iterable[str]) -> None:
        """Index the documents.

        Args:
            doc_ids: Handles, positionally aligned with `texts`.
            texts: The text to index, one per id.
        """
        self.doc_ids = list(doc_ids)
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._lengths: list[int] = []
        for index, text in enumerate(texts):
            terms = Counter(tokenize(text))
            self._lengths.append(sum(terms.values()))
            for term, count in terms.items():
                self._postings[term].append((index, count))
        if len(self._lengths) != len(self.doc_ids):
            raise ValueError(
                f"{len(self._lengths)} texts against {len(self.doc_ids)} ids — "
                "the index would score documents under the wrong handles."
            )
        self.average_length = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0

    def __len__(self) -> int:
        return len(self.doc_ids)

    def _idf(self, term: str) -> float:
        """Robertson-Sparck-Jones IDF, floored at zero.

        The unfloored form goes negative for a term in more than half the
        documents, which would make a common word actively *lower* a
        document's score — a card containing `creature` ranking below one
        that does not. Floored, such a term simply stops contributing.
        """
        document_frequency = len(self._postings.get(term, ()))
        if not document_frequency:
            return 0.0
        total = len(self._lengths)
        return max(
            0.0, math.log((total - document_frequency + 0.5) / (document_frequency + 0.5) + 1.0)
        )

    def search(self, query: str, *, k: int = 20, k1: float = K1, b: float = B) -> list[Hit]:
        """The `k` best-scoring documents for `query`.

        Args:
            query: The question, or the question plus its expansions.
            k: How many hits to return.
            k1: Term-frequency saturation. Passed per call rather than
                read from the module, because pin 7 permits a good-faith
                tuning sweep on the development split and these two are
                what a baseline would tune. Scoring parameters do not
                touch the postings, so a sweep re-scores a single index
                instead of rebuilding one per cell — the difference
                between a two-minute sweep and a two-hour one.
            b: Length normalisation.

        Ties are broken by `doc_id`, so a run is reproducible rather than
        dependent on dict ordering.
        """
        scores: dict[int, float] = defaultdict(float)
        for term, query_count in Counter(tokenize(query)).items():
            idf = self._idf(term)
            if not idf:
                continue
            for index, count in self._postings[term]:
                length_ratio = self._lengths[index] / self.average_length
                denominator = count + k1 * (1 - b + b * length_ratio)
                scores[index] += query_count * idf * (count * (k1 + 1)) / denominator
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], self.doc_ids[kv[0]]))
        return [Hit(doc_id=self.doc_ids[i], score=score) for i, score in ranked[:k]]
