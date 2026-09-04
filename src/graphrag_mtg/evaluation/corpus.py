"""The document set every arm of E-001 retrieves over.

Pin 8 is the reason this module exists and is worth restating, because it
is the roadmap's own **critical** credibility risk arriving through the one
door the earlier pins left open. Protocol parity — same chunking,
embeddings, generator, budget, judge — governs *affordances*. The asymmetry
that would have decided the experiment lives in the *source data*: all 20
`legality_1hop` questions carry an empty `gold_cr_rules`, because their
answer is "is X legal in Modern?", which lives in Scryfall's structured
legality field and in **no document** of CR + rulings + MTR. Fifteen of
them are in the evaluation split — 26% of the 57. A vector arm indexing
only prose could not answer one of them, the graph arms would sweep the
stratum, and the per-stratum table would read "graph wins" for a reason
that has nothing to do with graphs.

So: **every fact any arm may cite is in every arm's index.** One document
per CR rule and subrule, one per glossary entry, one per ruling, one per
card carrying its oracle text *and its format-legality lines*.

Chunking follows the CR's own hierarchy — the parsed numbered node — per
pin 3. :func:`window_chunks` is the registered fixed-size ablation, not a
default. Semantic chunking is deliberately not built: the published
evidence for it is a negative result.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from graphrag_mtg.etl.cards import is_playable
from graphrag_mtg.etl.cr_parser import CRDocument
from graphrag_mtg.graph.loader import ruling_id

#: Formats a card document spells out. Scryfall reports far more, most of
#: which no golden question asks about, and every extra line dilutes the
#: card's own text in an embedding. These are the five the golden set's
#: `legality_1hop` stratum uses plus the two commonly asked beside them.
LEGALITY_FORMATS = (
    "standard",
    "pioneer",
    "modern",
    "legacy",
    "vintage",
    "pauper",
    "commander",
)

#: Kinds a document can have. `card` is the one pin 8 added.
KINDS = ("rule", "glossary", "ruling", "card")

_WHITESPACE = re.compile(r"\s+")

#: Field separator inside the corpus hash. A byte that `_clean` guarantees
#: is absent from any document text, so two different corpora cannot
#: collide by one document's text running into the next one's id.
SEPARATOR = b"\n"


@dataclass(frozen=True)
class Document:
    """One retrievable unit, identical for every arm.

    Attributes:
        doc_id: Stable, kind-prefixed handle — `rule:613.7`, `card:<oracle
            id>`. What an arm cites, and what a run log can be replayed
            against.
        kind: One of :data:`KINDS`.
        title: A short label for the reader. Never embedded on its own.
        text: What is indexed and what reaches the generator.
        rule_number: Set only on rule documents. Pin 6 grades retrieval at
            rule-number granularity, and this is the field that makes that
            computable without parsing the text back out.
        oracle_id: Set on card and ruling documents, so a ruling can be
            traced to the card it belongs to.
        legalities: Set on card documents. Pin 9 scores `legality_1hop` by
            the presence of the correct `(card, format, status)` fact,
            judged deterministically — not by rule-number recall, which is
            undefined where `gold_cr_rules` is empty.
    """

    doc_id: str
    kind: str
    title: str
    text: str
    rule_number: str | None = None
    oracle_id: str | None = None
    legalities: Mapping[str, str] = field(default_factory=dict)


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text or "").strip()


def rule_documents(doc: CRDocument) -> list[Document]:
    """One document per numbered rule or subrule, plus its examples.

    Examples are kept with their rule rather than split off. They are the
    CR's own worked cases and carry the card names a question is written
    in — splitting them would hand the lexical half a document with the
    vocabulary and the dense half a document with the semantics, and
    neither with both.
    """
    out: list[Document] = []
    for rule in doc.rules:
        body = _clean(rule.text)
        if not body:
            continue
        examples = " ".join(_clean(e) for e in rule.examples)
        out.append(
            Document(
                doc_id=f"rule:{rule.number}",
                kind="rule",
                title=f"CR {rule.number}",
                text=f"{rule.number}. {body}" + (f" {examples}" if examples else ""),
                rule_number=rule.number,
            )
        )
    return out


def glossary_documents(doc: CRDocument) -> list[Document]:
    """One document per glossary entry.

    The graph models only the 701/702 keyword entries — the ontology's rule
    is that only what a question uses enters the schema. Text retrieval has
    no such constraint and no such cost, so the whole glossary is indexed:
    withholding entries here would be handing arm A a smaller corpus than
    the one it is being compared against.
    """
    return [
        Document(
            doc_id=f"glossary:{entry.term}",
            kind="glossary",
            title=f"Glossary: {entry.term}",
            text=f"{entry.term}. {_clean(entry.definition)}",
        )
        for entry in doc.glossary
        if _clean(entry.definition)
    ]


def ruling_documents(
    raw_rulings: Iterable[dict[str, Any]], names: Mapping[str, str]
) -> list[Document]:
    """One document per ruling, prefixed with the card it belongs to.

    Scryfall's rulings are written as if the card name were already on
    screen — "This ability triggers only once each turn." Indexed bare,
    such a document matches nothing a question asks, because a question
    names the card. The name is prepended rather than stored beside the
    text so that both halves of the hybrid see it.
    """
    out: list[Document] = []
    for raw in raw_rulings:
        oracle_id = raw.get("oracle_id")
        comment = _clean(raw.get("comment", ""))
        if not oracle_id or not comment:
            continue
        name = names.get(oracle_id, "")
        out.append(
            Document(
                doc_id=f"ruling:{ruling_id(raw)}",
                kind="ruling",
                title=f"Ruling: {name}" if name else "Ruling",
                text=f"{name}: {comment}" if name else comment,
                oracle_id=oracle_id,
            )
        )
    return out


def legality_sentences(name: str, legalities: Mapping[str, str]) -> list[str]:
    """The legality facts, written as prose an embedding can match.

    `{"modern": "not_legal"}` is a fact no retriever can match against
    "Is Mindsparker legal in Modern?" — the question is a sentence and the
    field is an enum. Pin 8 requires the fact to be *in* arm A's index, and
    a fact only counts as indexed if the arm can actually retrieve it, so
    each one is spelled out both ways round: legal and not legal both get a
    sentence, because a stratum that is half unanswerable is not parity.
    """
    out: list[str] = []
    for fmt in LEGALITY_FORMATS:
        status = legalities.get(fmt)
        if not status:
            continue
        pretty = fmt.capitalize()
        if status == "legal":
            out.append(f"{name} is legal in {pretty}.")
        elif status == "banned":
            out.append(f"{name} is banned in {pretty}, and so is not legal in {pretty}.")
        elif status == "restricted":
            out.append(f"{name} is restricted in {pretty}, and is legal in {pretty}.")
        else:
            out.append(f"{name} is not legal in {pretty}.")
    return out


def card_documents(cards: Iterable[dict[str, Any]]) -> list[Document]:
    """One document per playable card: name, type line, oracle text, legalities.

    This is the document pin 8 added, and without it 26% of the evaluation
    split is unanswerable for arm A alone.

    `is_playable` is applied here for the same reason pin 8 exists, running
    the other way. The graph loads 34,236 of the bulk's 38,262 records —
    tokens, art series and non-playable layouts are filtered by
    `etl/cards.py`. Indexing them for arm A only would give one arm four
    thousand documents the others cannot cite, which is the asymmetry pin 8
    forbids and not the direction it was written to catch. Reusing the same
    predicate is what keeps the two indexes describing one corpus.
    """
    out: list[Document] = []
    for card in cards:
        if not is_playable(card):
            continue
        oracle_id = card.get("oracle_id")
        name = card.get("name", "")
        if not oracle_id or not name:
            continue
        legalities = card.get("legalities") or {}
        parts = [name]
        if type_line := _clean(card.get("type_line", "")):
            parts.append(type_line)
        if oracle_text := _clean(card.get("oracle_text", "")):
            parts.append(oracle_text)
        parts.extend(legality_sentences(name, legalities))
        out.append(
            Document(
                doc_id=f"card:{oracle_id}",
                kind="card",
                title=name,
                text=" ".join(parts),
                oracle_id=oracle_id,
                legalities={f: s for f, s in legalities.items() if f in LEGALITY_FORMATS},
            )
        )
    return out


def build_corpus(
    cr: CRDocument,
    cards: Iterable[dict[str, Any]],
    raw_rulings: Iterable[dict[str, Any]],
) -> list[Document]:
    """Every document arm A indexes, in a deterministic order.

    Args:
        cr: The parsed Comprehensive Rules.
        cards: Scryfall oracle-card records.
        raw_rulings: Scryfall ruling records.

    Returns:
        Documents sorted by `doc_id`, so two builds of the same sources
        produce the same list and :func:`corpus_sha256` means something.
    """
    card_list = [c for c in cards if is_playable(c)]
    names = {c["oracle_id"]: c.get("name", "") for c in card_list}
    # Rulings for cards no arm holds are dropped for the same parity
    # reason: the graph attaches rulings to loaded cards, so indexing a
    # ruling whose card is not in the corpus would give arm A a document
    # with no counterpart and no card name to be found by.
    kept_rulings = [r for r in raw_rulings if r.get("oracle_id") in names]
    documents = [
        *rule_documents(cr),
        *glossary_documents(cr),
        *card_documents(card_list),
        *ruling_documents(kept_rulings, names),
    ]
    return sorted(documents, key=lambda d: d.doc_id)


def corpus_sha256(documents: Iterable[Document]) -> str:
    """Hash of the indexed text, so a run can name the corpus it saw.

    Hashes `doc_id` and `text` only. A change to a title is a presentation
    change; a change to the text is a different index, and an arm's scores
    are not comparable across the two.
    """
    digest = hashlib.sha256()
    for document in documents:
        digest.update(document.doc_id.encode())
        digest.update(SEPARATOR)
        digest.update(document.text.encode())
        digest.update(SEPARATOR)
    return digest.hexdigest()


def counts_by_kind(documents: Iterable[Document]) -> dict[str, int]:
    """How many documents of each kind, for the run log."""
    out = dict.fromkeys(KINDS, 0)
    for document in documents:
        out[document.kind] = out.get(document.kind, 0) + 1
    return out


def window_chunks(
    documents: Iterable[Document], *, size: int = 120, overlap: int = 30
) -> Iterator[Document]:
    """Fixed-size word windows — pin 3's registered ablation, not a default.

    Structure-aware chunking is the pinned configuration because the CR
    already carries a hierarchy written by the people who wrote the rules.
    This exists so that "we chose the structural chunker" is a published
    comparison rather than an assertion.

    Args:
        documents: The structural documents to re-cut.
        size: Words per window.
        overlap: Words shared with the previous window.

    Yields:
        Documents whose `doc_id` carries a `#n` window suffix. The rule
        number and legality fields ride along on every window, so grading
        stays computable when a window lands on the half of a rule that
        does not repeat its own number.
    """
    if overlap >= size:
        raise ValueError(f"overlap {overlap} must be smaller than size {size}")
    for document in documents:
        words = document.text.split()
        if len(words) <= size:
            yield document
            continue
        step = size - overlap
        for index, start in enumerate(range(0, len(words), step)):
            window = words[start : start + size]
            if not window:
                break
            yield Document(
                doc_id=f"{document.doc_id}#{index}",
                kind=document.kind,
                title=document.title,
                text=" ".join(window),
                rule_number=document.rule_number,
                oracle_id=document.oracle_id,
                legalities=document.legalities,
            )
            if start + size >= len(words):
                break
