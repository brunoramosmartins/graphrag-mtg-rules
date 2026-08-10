"""Query-time linking: what nodes does this question talk about?

Feeds the template traversals their parameters. It reuses the ingestion
lexicon — pure name tables, nothing tuned to ruling prose — but not the
ingestion *policy*, because a question is not a ruling:

- **Rulings are edited English; questions are typed.** The ingestion
  linker requires a capitalized word before accepting a multi-word name,
  which is what stops the card *Card Draw* from matching the phrase "card
  draw" (Phase 3, measured). A user typing "how does humility interact
  with opalescence" capitalizes nothing, and that gate would resolve
  nothing at all.
- **A question names rules and keywords directly.** "What does rule 613.4b
  say?" and "how does deathtouch work" need no card lookup, and both are
  exact, deterministic resolutions.
- **Ambiguity must surface, not be guessed.** At ingestion an unresolved
  homonym went to an LLM. Here it goes back to the caller as *ambiguous*,
  because the Phase 4 DoD forbids silently wrong context and a question is
  a live conversation where asking is cheap.

One policy governs the open card vocabulary. When the question
capitalizes, the ingestion gate applies and a multi-word surface with no
capital is the phrase, not the card. When the question capitalizes
nothing, the signal does not exist, and **nothing is asserted** — matches
come back as ambiguous with their candidates for the caller to confirm.
That costs recall on lowercase questions, and it is the right side to err
on: resolving anyway is how "extra card draw each turn" puts the card
*Card Draw* into a subgraph and then into a citation.

:meth:`QueryEntities.has_graph_seed` is the routing signal ADR-007 rests
on: whether this question's entities reach the rule graph at all. It is
the same test `scripts/reachability.py` measured, computed per question
and deterministically, and it is what a future agentic router (Project 3)
would ask before choosing a retrieval route.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from graphrag_mtg.etl.normalize import loose_name, normalize_name
from graphrag_mtg.extraction.linker import Lexicon
from graphrag_mtg.extraction.schemas import LinkMethod

#: Dotted rule numbers stand alone ("613.4b"); a bare chapter needs a cue
#: word, or "I have 100 life" would cite chapter 100.
DOTTED_RULE = re.compile(r"\b\d{3}\.\d+[a-z]?\b")
CUED_CHAPTER = re.compile(r"\b(?:rule|cr|comprehensive rules?)\s+(\d{3})\b", re.IGNORECASE)

#: Longest first, so "first strike" wins over "strike" and "double strike"
#: over "first strike".
MAX_KEYWORD_TOKENS = 4
MAX_NAME_TOKENS = 8

#: Typographic apostrophe, spelled by codepoint: a literal one in a pattern
#: is flagged as an ambiguous character (RUF001) and is invisible in review.
RIGHT_SINGLE_QUOTE = chr(0x2019)

_WORD = re.compile("[A-Za-z0-9'" + RIGHT_SINGLE_QUOTE + "/,.-]+")


class EntityKind(StrEnum):
    """Which node label a resolved mention points at."""

    CARD = "card"
    KEYWORD = "keyword"
    RULE = "rule"
    FORMAT = "format"


@dataclass(frozen=True)
class EntityRef:
    """One resolved (or ambiguous) mention in the question.

    Attributes:
        kind: Node label the reference points at.
        key: ``oracle_id`` / keyword name / rule number — the template
            parameter value.
        surface: Exactly what the question said, for the answer's citation.
        start: Character offset of ``surface`` in the question.
        end: Offset one past the last character.
        method: Which stage resolved it.
        candidates: Every candidate when the surface is ambiguous. Empty
            for a clean resolution; a resolved ``key`` is never guessed
            from a non-empty ``candidates``.
        has_keywords: Cards only — whether this card carries keyword
            abilities, which is what decides if it can seed the rule graph.
    """

    kind: EntityKind
    key: str
    surface: str
    start: int
    end: int
    method: LinkMethod
    candidates: tuple[str, ...] = ()
    has_keywords: bool = False


@dataclass(frozen=True)
class QueryEntities:
    """Everything a question resolved to, plus what it could not."""

    question: str
    cards: tuple[EntityRef, ...] = ()
    keywords: tuple[EntityRef, ...] = ()
    rules: tuple[EntityRef, ...] = ()
    formats: tuple[EntityRef, ...] = ()
    ambiguous: tuple[EntityRef, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> tuple[EntityRef, ...]:
        """Every unambiguous reference, in question order."""
        found = self.cards + self.keywords + self.rules + self.formats
        return tuple(sorted(found, key=lambda e: e.start))

    @property
    def has_graph_seed(self) -> bool:
        """Whether these entities reach the CR rule graph deterministically.

        True when the question names a rule, names a keyword, or names a
        card that *has* keywords. False for a question whose only entities
        are cards with no keyword abilities — *Humility*, *Opalescence* —
        which `scripts/reachability.py` found for 15 of the 30
        `interaction_multihop` questions. Those cannot be answered by
        traversal at any depth and are ADR-007's text-retrieval route.
        """
        return bool(self.rules or self.keywords or any(c.has_keywords for c in self.cards))


def carries_capitalization(text: str) -> bool:
    """Whether capitalization is informative in this text.

    A question with no capitalized word past the first is one where the
    writer is not capitalizing at all, so the absence of a capital is
    evidence of nothing. Sentence-initial words are excluded for the same
    reason — every sentence has one.
    """
    words = _WORD.findall(text)
    return any(word[:1].isupper() for word in words[1:])


def _spans_free(claimed: list[tuple[int, int]], start: int, end: int) -> bool:
    return all(end <= s or start >= e for s, e in claimed)


def find_rules(question: str) -> list[EntityRef]:
    """Rule numbers the question states, dotted or cued by "rule"/"CR"."""
    found = []
    for match in DOTTED_RULE.finditer(question):
        found.append(
            EntityRef(
                kind=EntityKind.RULE,
                key=match.group(),
                surface=match.group(),
                start=match.start(),
                end=match.end(),
                method=LinkMethod.EXPLICIT,
            )
        )
    for match in CUED_CHAPTER.finditer(question):
        start, end = match.span(1)
        if _spans_free([(f.start, f.end) for f in found], start, end):
            found.append(
                EntityRef(
                    kind=EntityKind.RULE,
                    key=match.group(1),
                    surface=match.group(1),
                    start=start,
                    end=end,
                    method=LinkMethod.EXPLICIT,
                )
            )
    return found


class QueryLinker:
    """Resolves a question's mentions against the graph's vocabularies.

    Args:
        lexicon: Card-name tables (`Lexicon.build`), optionally carrying
            community aliases so "Bolt" reaches *Lightning Bolt*.
        keywords: Known keyword names, in any casing.
        keywords_by_oracle: ``oracle_id -> [keyword, ...]``, used only to
            decide :attr:`EntityRef.has_keywords`. Absent means every card
            is treated as seedless, which routes conservatively.
    """

    def __init__(
        self,
        lexicon: Lexicon,
        keywords: Iterable[str] = (),
        keywords_by_oracle: Mapping[str, list[str]] | None = None,
        formats: Iterable[str] = (),
    ) -> None:
        self.lexicon = lexicon
        self.keywords = {normalize_name(k): k for k in keywords if normalize_name(k)}
        self.keywords_by_oracle = keywords_by_oracle or {}
        # Another closed vocabulary: "Modern" in a question is the format,
        # never anything else, so it resolves exactly like a keyword does.
        self.formats = {normalize_name(f): f for f in formats if normalize_name(f)}

    def link(self, question: str) -> QueryEntities:
        """Resolve every mention, longest span first, without overlaps.

        Order is rules, then keywords, then cards. Rules and keywords are
        closed vocabularies and cannot be wrong about themselves; card
        names are the open, ambiguous set and get what is left.
        """
        claimed: list[tuple[int, int]] = []
        rules = find_rules(question)
        claimed += [(r.start, r.end) for r in rules]

        formats = self._scan(question, claimed, self._match_format, 2)
        claimed += [(f.start, f.end) for f in formats]

        keywords = self._scan(question, claimed, self._match_keyword, MAX_KEYWORD_TOKENS)
        claimed += [(k.start, k.end) for k in keywords]

        gate = carries_capitalization(question)
        cards = self._scan(
            question, claimed, lambda s: self._match_card(s, gate), MAX_NAME_TOKENS
        )
        resolved_cards = tuple(c for c in cards if not c.candidates)
        ambiguous = tuple(c for c in cards if c.candidates)
        return QueryEntities(
            question=question,
            cards=resolved_cards,
            keywords=tuple(keywords),
            rules=tuple(rules),
            formats=tuple(formats),
            ambiguous=ambiguous,
        )

    def _scan(self, text, claimed, matcher, max_tokens) -> list[EntityRef]:
        """Greedy longest-match left to right, skipping claimed spans."""
        words = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(text)]
        found: list[EntityRef] = []
        i = 0
        while i < len(words):
            hit = None
            for width in range(min(max_tokens, len(words) - i), 0, -1):
                start, end = words[i][1], words[i + width - 1][2]
                if not _spans_free(claimed + [(f.start, f.end) for f in found], start, end):
                    continue
                hit = matcher(text[start:end])
                if hit is not None:
                    kind, key, method, candidates = hit
                    found.append(
                        EntityRef(
                            kind=kind,
                            key=key,
                            surface=text[start:end],
                            start=start,
                            end=end,
                            method=method,
                            candidates=candidates,
                            has_keywords=bool(self.keywords_by_oracle.get(key)),
                        )
                    )
                    i += width
                    break
            if hit is None:
                i += 1
        return found

    def _match_format(self, surface: str):
        name = self.formats.get(normalize_name(surface))
        if name is None:
            return None
        return EntityKind.FORMAT, name, LinkMethod.EXACT, ()

    def _match_keyword(self, surface: str):
        name = self.keywords.get(normalize_name(surface))
        if name is None:
            return None
        return EntityKind.KEYWORD, name, LinkMethod.EXACT, ()

    def _match_card(self, surface: str, gate: bool):
        """Exact then loose, under one policy about capitalization.

        Card names are the *open* vocabulary, and English is full of them:
        *Card Draw*, *Deal Damage*, *Fear*, *Opt*, *Humility*. The only
        deterministic signal separating "the card" from "the words" is that
        a writer capitalizes a name. So:

        - **The question capitalizes** — apply the ingestion gate. A
          multi-word surface with no capital is the phrase, not the card,
          and is rejected outright.
        - **The question capitalizes nothing** — the signal does not exist,
          and nothing from the open vocabulary is *asserted*. Matches are
          returned as ambiguous with their candidates, for the caller to
          confirm.

        The second branch is the honest one and it costs recall on
        lowercase questions. The alternative — resolving anyway — is how
        "extra card draw each turn" puts the card *Card Draw* into a
        subgraph that then gets cited, which is exactly the silently-wrong
        context the Phase 4 DoD forbids. A single candidate in
        ``candidates`` means "confirm this is a card"; several mean "pick
        which one".
        """
        norm = normalize_name(surface)
        if not norm:
            return None
        multiword = len(norm.split()) > 1
        if gate and multiword and not any(w[:1].isupper() for w in _WORD.findall(surface)):
            return None

        hits = self.lexicon.exact.get(norm)
        method = LinkMethod.EXACT
        if not hits:
            hits = self.lexicon.loose.get(loose_name(surface))
            method = LinkMethod.LOOSE
        if not hits and not multiword:
            hits = self.lexicon.single_word.get(norm)
            method = LinkMethod.SURFACE
        if not hits:
            return None
        return self._decide(hits, method, force_ambiguous=not gate)

    def _decide(self, hits: set[str], method: LinkMethod, *, force_ambiguous: bool = False):
        ordered = tuple(sorted(hits))
        if len(ordered) == 1 and not force_ambiguous:
            return EntityKind.CARD, ordered[0], method, ()
        return EntityKind.CARD, "", method, ordered
