"""Entity linking: ruling text -> (:Ruling)-[:MENTIONS]->(:Card) candidates.

Cascade (ADR-004), cheapest stage first, each stage only seeing what the
previous one could not resolve:

1. **exact** — normalized multi-word name match (`normalize_name`),
   gated on capitalization: at least one word of the match must be
   capitalized. Multi-word names are *not* automatically unambiguous —
   "card draw", "deal damage", "too many" are real card names and
   ordinary phrases both, so an all-lowercase match is a phrase, not a
   mention (measured on the dev annotations, 5 false positives).
2. **loose** — punctuation-insensitive match (`loose_name`), so
   "Lim-Dul's Vault" is found even typed "Lim Duls Vault".
3. **surface** — single-word card names ("Opt", "Fear", "Terror") are
   ordinary English words; a capitalized occurrence is only a *candidate*
   and is handed to the LLM stage unresolved. This tail is where the
   linking F1 that matters lives.
4. **llm** — disambiguation of surface candidates (see
   :func:`build_disambiguation_prompt`; calls go through
   `extraction/llm.py` and results through `extraction/gate.py`).

The roadmap sketches an embedding stage (BGE-M3) between 2 and 4. It is
deliberately absent here: official rulings quote card names verbatim —
paraphrased nicknames ("Bolt", "Sad Robot") occur in *user questions*,
which is query-time linking (Phase 4, `retrieval/linking.py`). If Phase 3
error analysis finds paraphrases in rulings, that decision gets revisited
in `notes/phase3-extraction.md` rather than silently patched.

CLI (deterministic stages only — no API cost):

    python -m graphrag_mtg.extraction.linker --limit 1000
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, RULINGS_STEM, bulk_path, iter_bulk
from graphrag_mtg.etl.normalize import loose_name, normalize_name, split_faces
from graphrag_mtg.extraction.schemas import CardMention, EvidenceSpan, LinkMethod

# Longest real card name is well under this many tokens; bounds the scan window.
MAX_NAME_TOKENS = 12

# Tokens as they appear in ruling text, offsets preserved. Apostrophes and
# hyphens stay inside a token so "Lim-Dul's" is one token.
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")

# First-token prefilter key: normalized, punctuation stripped, so the text
# token "Nissa" meets the name token "nissa," and "LimDuls" meets "lim-dul's".
_STRIP = re.compile(r"[^a-z0-9]+")

MENTIONS_CANDIDATES_PATH = Path("data/interim/mentions_candidates.jsonl")


@dataclass(frozen=True)
class PendingMention:
    """A surface-stage candidate awaiting LLM disambiguation.

    Attributes:
        mention: The unresolved mention (``oracle_id is None``).
        candidate_oracle_ids: Cards whose name matches the surface. Usually
            one (there is exactly one card named "Opt") — the open question
            for the LLM is whether the *word* is being used as that card's
            name at all.
    """

    mention: CardMention
    candidate_oracle_ids: tuple[str, ...]


@dataclass
class Lexicon:
    """Card-name lookup tables for the deterministic stages.

    Multi-word names key the exact/loose tables; single-word names go to
    their own table because matching them is a *decision*, not a lookup.
    ``first_tokens`` maps a name's stripped first token to the widest
    window it can start — the prefilter that keeps a corpus-scale scan
    from normalizing every window of every ruling.
    """

    exact: dict[str, set[str]] = field(default_factory=dict)
    loose: dict[str, set[str]] = field(default_factory=dict)
    single_word: dict[str, set[str]] = field(default_factory=dict)
    first_tokens: dict[str, int] = field(default_factory=dict)
    #: oracle_id -> combined name, so a scan can recognise the host card by
    #: name and not only by id. Dropping self-mentions by id alone missed
    #: "Soul Shatter" on a Soul Shatter ruling, because the name resolved to a
    #: different printing's oracle_id than the one the ruling hangs on.
    name_by_oracle: dict[str, str] = field(default_factory=dict)
    #: Lookup key -> oracle_ids indexed there because the key is a *face* of
    #: a multi-face name rather than a whole name. Recorded, never acted on
    #: here: the ingestion linker's behaviour was measured in E-003 and this
    #: field adds nothing to it. The query-time linker consults it, because
    #: at query time "what" matching a face of *Who // What // When // Where
    #: // Why* is a defect and "Lightning Bolt" losing to a face of another
    #: card is a worse one.
    faces: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        names: Iterable[tuple[str, str]],
        aliases: Iterable[tuple[str, str]] = (),
    ) -> Lexicon:
        """Build the tables from ``(name, oracle_id)`` pairs.

        Multi-face combined names ("Fire // Ice") index under the combined
        name *and* each face. ``aliases`` (community nicknames) join the
        loose table only — an alias is never an exact match.
        """
        lex = cls()
        for name, oracle_id in names:
            lex.name_by_oracle.setdefault(oracle_id, name)
            for form in {name, *split_faces(name)}:
                lex._add(form, oracle_id)
                if form != name:
                    lex.faces.setdefault(normalize_name(form), set()).add(oracle_id)
                    lex.faces.setdefault(loose_name(form), set()).add(oracle_id)
        for alias, oracle_id in aliases:
            lex.loose.setdefault(loose_name(alias), set()).add(oracle_id)
        return lex

    def _add(self, name: str, oracle_id: str) -> None:
        norm = normalize_name(name)
        n_tokens = len(norm.split())
        if n_tokens == 1:
            self.single_word.setdefault(norm, set()).add(oracle_id)
            return
        self.exact.setdefault(norm, set()).add(oracle_id)
        self.loose.setdefault(loose_name(name), set()).add(oracle_id)
        first = _STRIP.sub("", norm.split()[0])
        width = min(n_tokens, MAX_NAME_TOKENS)
        self.first_tokens[first] = max(self.first_tokens.get(first, 0), width)


def _tokens_with_offsets(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def scan_ruling(
    ruling_id: str,
    text: str,
    lexicon: Lexicon,
    *,
    host_oracle_id: str | None = None,
) -> tuple[list[CardMention], list[PendingMention]]:
    """Find card-name mentions in one ruling's text.

    Greedy longest-match, left to right: once a window matches, its tokens
    are consumed, so "Nissa, Who Shakes the World" never also yields a
    match for a shorter name inside it.

    Args:
        ruling_id: The graph's Ruling key (provenance on every candidate).
        text: Ruling text exactly as stored on the node — spans index into
            this string and the gate will re-check them against it.
        lexicon: Prebuilt name tables.
        host_oracle_id: Card the ruling hangs on. MENTIONS means
            "references *another* card", so pure self-mentions are dropped.

    Returns:
        ``(resolved, pending)`` — exact/loose mentions with an oracle_id,
        and surface-stage candidates for the LLM.
    """
    tokens = _tokens_with_offsets(text)
    resolved: list[CardMention] = []
    pending: list[PendingMention] = []
    host_faces = _host_faces(lexicon, host_oracle_id)
    i = 0
    while i < len(tokens):
        match = _longest_match_at(tokens, i, text, lexicon, ruling_id, host_oracle_id)
        if match is None:
            i += 1
            continue
        mention_or_pending, consumed = match
        candidate = (
            mention_or_pending.mention
            if isinstance(mention_or_pending, PendingMention)
            else mention_or_pending
        )
        span = candidate.span
        if names_the_host(span.text, span.start, span.end, text, host_faces):
            i += consumed
            continue
        if isinstance(mention_or_pending, PendingMention):
            pending.append(mention_or_pending)
        else:
            resolved.append(mention_or_pending)
        i += consumed
    return resolved, pending


def _host_faces(lexicon: Lexicon, host_oracle_id: str | None) -> list[str]:
    """Face names of the card a ruling hangs on, or empty when unknown."""
    if not host_oracle_id:
        return []
    name = lexicon.name_by_oracle.get(host_oracle_id)
    return split_faces(name) if name else []


def names_the_host(
    surface: str, start: int, end: int, text: str, host_faces: list[str]
) -> bool:
    """True when a match is a fragment of the host card's name in the text.

    Only one shape qualifies: the match sits **inside a full occurrence of the
    host's name in the ruling text** — "Legion" matched inside "Kemba's Legion".
    That is a tokenization error with no judgement in it, and the greedy scan
    should have consumed the longer name.

    Everything broader was tried on dev and rejected by the annotations:

    * A plain substring test is wrong — "The Ring" is a substring of the host
      *Call of the Ring* and is nonetheless a real mention of the card
      **The Ring**.
    * Suppressing a surface that merely *prefixes* a host face is also wrong.
      It would catch "Nicol Bolas" on *Nicol Bolas, the Ravager*, which the
      gold does treat as a non-mention — but it equally catches "Brutal Cathar"
      and "Moonrage Brute" on the host *Brutal Cathar // Moonrage Brute*, which
      the gold records as genuine mentions. Two won, two lost, so the rule
      encodes a judgement the annotations do not share and is left out.
    """
    if not normalize_name(surface):
        return False
    lowered = text.lower()
    for face in host_faces:
        needle = face.lower()
        position = lowered.find(needle)
        while position != -1:
            finish = position + len(needle)
            # Strictly inside: the occurrence has to extend past the match on at
            # least one side. Equality means the ruling names the host in full,
            # and the gold records that as a real mention — "Brutal Cathar" on
            # the host *Brutal Cathar // Moonrage Brute* is a true positive.
            if position <= start and end <= finish and (position < start or end < finish):
                return True
            position = lowered.find(needle, position + 1)
    return False


def _longest_match_at(
    tokens: list[tuple[str, int, int]],
    i: int,
    text: str,
    lexicon: Lexicon,
    ruling_id: str,
    host_oracle_id: str | None,
) -> tuple[CardMention | PendingMention, int] | None:
    """Try windows ending furthest-right first; return (candidate, n_tokens)."""
    first_key = _STRIP.sub("", normalize_name(tokens[i][0]))
    limit = min(lexicon.first_tokens.get(first_key, 0), len(tokens) - i)
    for width in range(limit, 1, -1):
        start, end = tokens[i][1], tokens[i + width - 1][2]
        surface = text[start:end]
        # A card name is a proper noun: at least one of its words is
        # capitalized wherever it appears. An all-lowercase multi-word match
        # is a generic English phrase that merely collides with a card name
        # ("card draw", "deal damage", "too many") — real cards, but not what
        # the ruling names. Requiring one capitalized word (not the initial,
        # so "the Ring" survives its lowercase article) killed 5 such false
        # positives at the cost of none, measured on the dev annotations.
        if not any(word[:1].isupper() for word in surface.split()):
            continue
        targets, method = _lookup_multiword(surface, lexicon)
        targets = targets - ({host_oracle_id} if host_oracle_id else set())
        if len(targets) == 1:
            span = EvidenceSpan(start=start, end=end, text=surface)
            mention = CardMention(
                ruling_id=ruling_id,
                surface=surface,
                oracle_id=next(iter(targets)),
                span=span,
                method=method,
                confidence=1.0,
            )
            return mention, width
    return _single_word_match(tokens[i], text, lexicon, ruling_id, host_oracle_id)


def _lookup_multiword(surface: str, lexicon: Lexicon) -> tuple[set[str], LinkMethod]:
    exact = lexicon.exact.get(normalize_name(surface))
    if exact:
        return set(exact), LinkMethod.EXACT
    loose = lexicon.loose.get(loose_name(surface))
    if loose:
        return set(loose), LinkMethod.LOOSE
    return set(), LinkMethod.EXACT


def _single_word_match(
    token: tuple[str, int, int],
    text: str,
    lexicon: Lexicon,
    ruling_id: str,
    host_oracle_id: str | None,
) -> tuple[PendingMention, int] | None:
    """Single-word names: capitalized occurrence -> pending, never resolved.

    "Opt" as a card name and "opt" as a verb are the same normalized token;
    capitalization is the only deterministic signal and it is weak (sentence
    starts capitalize everything). So the stage *nominates* and the LLM
    decides — confidence here is explicitly not asserted (0.0).
    """
    surface, start, end = token
    if not surface[0].isupper():
        return None
    candidates = lexicon.single_word.get(normalize_name(surface), set())
    candidates = candidates - ({host_oracle_id} if host_oracle_id else set())
    if not candidates:
        return None
    mention = CardMention(
        ruling_id=ruling_id,
        surface=surface,
        oracle_id=None,
        span=EvidenceSpan(start=start, end=end, text=surface),
        method=LinkMethod.SURFACE,
        confidence=0.0,
    )
    return PendingMention(mention=mention, candidate_oracle_ids=tuple(sorted(candidates))), 1


def build_disambiguation_prompt(pending: PendingMention, ruling_text: str) -> str:
    """Prompt for the LLM stage: is this word being used as the card's name?

    The answer format is consumed by `extraction/llm.py` and validated by
    the gate; the model is asked for a yes/no plus confidence, never for
    free-form linking (the candidate set is closed).
    """
    return (
        "In the Magic: The Gathering ruling below, the word "
        f'"{pending.mention.surface}" may or may not refer to the card of that name.\n\n'
        f"Ruling: {ruling_text}\n\n"
        'Does this occurrence name the card? Reply with JSON: {"is_card": true|false, '
        '"confidence": 0.0-1.0}. is_card is true only when the sentence treats the word '
        "as a proper noun naming that specific card."
    )


# ── CLI: deterministic pass over the raw rulings, stats + candidates file ──


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulings", type=Path, default=bulk_path(RULINGS_STEM))
    parser.add_argument("--cards", type=Path, default=bulk_path(ORACLE_CARDS_STEM))
    parser.add_argument("--limit", type=int, default=None, help="scan at most N rulings")
    parser.add_argument("--out", type=Path, default=MENTIONS_CANDIDATES_PATH)
    args = parser.parse_args()

    # Local imports keep module import safe without the raw data present.
    from graphrag_mtg.graph.loader import ruling_id as make_ruling_id

    lexicon = Lexicon.build(
        (c["name"], c["oracle_id"]) for c in iter_bulk(args.cards)
    )

    stats: Counter[str] = Counter()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for n, raw in enumerate(iter_bulk(args.rulings)):
            if args.limit is not None and n >= args.limit:
                break
            rid = make_ruling_id(raw)
            resolved, pending = scan_ruling(
                rid, raw.get("comment", ""), lexicon, host_oracle_id=raw.get("oracle_id")
            )
            stats["rulings"] += 1
            stats["resolved"] += len(resolved)
            stats["pending_llm"] += len(pending)
            for m in resolved:
                out.write(m.model_dump_json() + "\n")
            for p in pending:
                row = p.mention.model_dump()
                row["candidate_oracle_ids"] = list(p.candidate_oracle_ids)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"Scanned {stats['rulings']:,} rulings: {stats['resolved']:,} resolved "
        f"deterministically, {stats['pending_llm']:,} single-word candidates for the "
        f"LLM stage. Candidates written to {args.out}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
