"""Lexical search over the Comprehensive Rules — a faster grep, not an oracle.

The citation pass asks a human to name the CR rule a ruling invokes. Doing
that by hand means grepping the CR for likely terms and reading candidates.
This module automates the grep-and-rank, and nothing more: it returns CR
rules ordered by lexical overlap with the ruling, so a person scans ten
candidates instead of three thousand — then reads the actual rule and
decides.

**Why this does not contaminate the gold.** It is deterministic TF-IDF over
rule text, not the LLM extractor's mechanism and not the semantic retrieval
the vector baseline will use, so gold citations found with its help do not
correlate with either system under evaluation. It ranks; the human judges.
The distinction that keeps it honest: a search tool surfaces candidates, it
never asserts the answer (see the decision journal, 2026-07-21).

No embeddings, no network, no LLM — the CR is small enough that a plain
inverted-document-frequency score is instant and transparent.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from graphrag_mtg.etl.cr_parser import CRDocument

_WORD = re.compile(r"[a-z][a-z']+")

# Words too common in rules text to carry signal — English function words plus
# Magic's ever-present vocabulary. A shared "creature" means nothing; a shared
# "regenerate" means a lot.
_STOPWORDS = frozenset({
    # English function words
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "as",
    "if", "then", "that", "this", "these", "those", "is", "are", "be", "it",
    "its", "it's", "they", "them", "their", "there", "when", "while", "any",
    "all", "each", "no", "not", "only", "also", "may", "can", "will", "would",
    "could", "must", "has", "have", "had", "do", "does", "can't", "by", "at",
    "up", "out", "from", "onto", "into", "one", "two", "number", "put",
    # Magic's ever-present vocabulary
    "rule", "rules", "see", "player", "players", "card", "cards", "permanent",
    "permanents", "object", "objects", "creature", "creatures", "spell",
    "spells", "ability", "abilities", "effect", "effects", "game", "turn",
    "control", "controls", "controlled", "battlefield",
})


@dataclass(frozen=True)
class RuleHit:
    """A candidate rule with its lexical score and a text snippet."""

    number: str
    score: float
    snippet: str


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]


def _fold(word: str) -> str:
    """Fold a trailing plural / third-person ``-s`` off ``word``.

    Rulings and rule text disagree constantly on inflection — a ruling says
    "the creature connives", the rule says "to connive" — and without this the
    two share no term at all and the rule never surfaces. Deliberately limited
    to ``-s``/``-es``/``-ies``: it is the inflection that actually differs
    across the two registers, and a fuller stemmer would start conflating
    distinct rules vocabulary ("counter" and "countered" are not the same
    concept in Magic) for no gain.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _folded_terms(text: str) -> list[str]:
    """Indexable terms: distinctive words, inflection folded."""
    return [_fold(w) for w in _terms(text)]


class CiteSearch:
    """A TF-IDF index over CR rule text (levels 2 and 3, the ones with content)."""

    def __init__(self, doc: CRDocument, snippet_chars: int = 160) -> None:
        self._rules = [
            r for r in doc.rules if r.level in (2, 3) and r.text.strip()
        ]
        self._snippet_chars = snippet_chars
        self._doc_terms: list[Counter[str]] = [Counter(_folded_terms(r.text)) for r in self._rules]
        n = len(self._rules)
        df: Counter[str] = Counter()
        for counts in self._doc_terms:
            df.update(counts.keys())
        self._idf = {term: math.log(n / freq) for term, freq in df.items()}

    def search(self, text: str, *, k: int = 8) -> list[RuleHit]:
        """Return the ``k`` rules whose text shares the most distinctive terms.

        Score is the summed IDF of terms shared with ``text`` — rules that
        share rare vocabulary (a keyword name, "regenerate", "protection")
        rank above rules sharing only common words.
        """
        query = set(_folded_terms(text))
        if not query:
            return []
        scored: list[RuleHit] = []
        for rule, counts in zip(self._rules, self._doc_terms, strict=True):
            shared = query & counts.keys()
            if not shared:
                continue
            score = sum(self._idf.get(term, 0.0) for term in shared)
            snippet = rule.text[: self._snippet_chars]
            scored.append(RuleHit(number=rule.number, score=score, snippet=snippet))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]
