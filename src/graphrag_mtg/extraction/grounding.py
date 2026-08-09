"""Grounding context for extraction round 2: real rule numbers in the prompt.

Round 1 (open mode) measured the failure precisely: 7 of 31 candidates
cited *plausible but nonexistent* keyword subrules — the model knows the
concept ("connive") and invents the number (702.74b instead of 702.131).
The fix is not a closed citation list (round 1's good citations included
non-keyword rules like 601.2c, which a closed list would forbid) but
giving the model the numbers it keeps guessing at:

- a **keyword directory** — every level-2 rule under 701 (keyword
  actions) and 702 (keyword abilities), number + name, ~1k tokens,
  appended to the system prompt once per call;
- **host-card candidates** — the rules behind the host card's own
  keywords (via the CR glossary), quoted with a text snippet in the
  per-ruling prompt.

Round 2 then measured the cost of that fix: invented numbers fell to
~0, but **every** citation became a 701/702 keyword rule — the correct
procedural citations round 1 produced (601.2c, 608.2, 613.x) vanished.
A directory of only keyword names is a prompt that says "cite keywords".
So the grounding block also carries the **chapter map**: all 146 level-1
CR chapters with their titles (~700 tokens), which gives the model the
document's whole skeleton instead of one wing of it.

Everything here is derived deterministically from the parsed CR
(`etl.cr_parser`); no LLM, no network.
"""

from __future__ import annotations

from graphrag_mtg.etl.cr_parser import CRDocument
from graphrag_mtg.etl.normalize import normalize_name

# Chapters whose children form the keyword directory.
KEYWORD_CHAPTERS = ("701", "702")

# Candidate snippets stay short: the model needs enough text to recognize
# relevance, not the whole rule.
SNIPPET_CHARS = 240

# A directory entry is a keyword NAME ("Connive"), never prose. Chapters 701
# and 702 open with prose rules ("701.1 Most actions described...") that a
# pure level filter would let in; names are short, prose is not.
MAX_NAME_CHARS = 40


def keyword_directory(doc: CRDocument) -> list[tuple[str, str]]:
    """Return (number, name) for every keyword action/ability rule.

    Level-2 rules under 701/702 carry the keyword's name as their text
    ("702.2. Deathtouch"), which is exactly the number-to-name mapping the
    model hallucinates.
    """
    return [
        (rule.number, rule.text.strip())
        for rule in doc.rules
        if rule.level == 2
        and rule.parent in KEYWORD_CHAPTERS
        and len(rule.text.strip()) <= MAX_NAME_CHARS
    ]


def directory_block(directory: list[tuple[str, str]]) -> str:
    """Render the directory for the system prompt, one entry per line."""
    lines = "\n".join(f"{number} {name}" for number, name in directory)
    return (
        "Keyword rule directory (the ONLY valid rule numbers under 701/702 — "
        "when citing a keyword's rule, use its number or a lettered subrule "
        "of it; never invent 701/702 numbers not derived from this list):\n" + lines
    )


def chapter_map(doc: CRDocument) -> list[tuple[str, str]]:
    """Return (number, title) for every CR chapter (level-1 rule)."""
    return [(rule.number, rule.text.strip()) for rule in doc.rules if rule.level == 1]


def grounding_block(doc: CRDocument, *, include_keywords: bool = True) -> str:
    """The system-prompt grounding: chapter map, optionally + keyword directory.

    Order matters. The chapter map comes first so the model reads the CR
    as a whole document before it reaches the keyword names — round 2
    showed that leading with keywords collapses every citation onto
    701/702.

    Ordering alone did not cure that collapse. The first E-003 dev run still
    put 7 of its citations in 702 and 6 in 608 while the gold spread across
    509, 707, 616 and 614, so ``include_keywords=False`` drops the directory
    entirely and leaves only the chapter map. Per-ruling candidates from
    :func:`candidate_rules_for_keywords` are unaffected — those exist to stop
    invented numbers, which is a different job.

    Args:
        doc: The parsed CR.
        include_keywords: Append the keyword rule directory.

    Returns:
        The grounding text for the system prompt.
    """
    chapters = "\n".join(f"{number} {title}" for number, title in chapter_map(doc))
    block = (
        "Comprehensive Rules chapter map (the document's full structure — many "
        "rulings are governed by procedural chapters such as 601 casting, 608 "
        "resolving spells, 613 layers, or 704 state-based actions, NOT by a "
        "keyword rule; cite whichever chapter actually governs the ruling):\n"
        + chapters
    )
    if include_keywords:
        block += "\n\n" + directory_block(keyword_directory(doc))
    return block


def candidate_rules_for_keywords(
    keywords: list[str],
    doc: CRDocument,
    *,
    max_subrules: int = 6,
) -> list[tuple[str, str]]:
    """Rules behind a card's keywords, as (number, snippet) prompt candidates.

    Resolution goes through the CR glossary (term -> referenced rules),
    which is the same deterministic source the graph's ``DEFINED_BY``
    edges come from; each referenced rule brings its first subrules so the
    model can cite the lettered leaf instead of the parent.
    """
    glossary = {normalize_name(entry.term): entry for entry in doc.glossary}
    by_number = doc.by_number
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for keyword in keywords:
        entry = glossary.get(normalize_name(keyword))
        if entry is None:
            continue
        for number in entry.references:
            for rule in doc.subtree(number)[: max_subrules + 1]:
                if rule.number in seen or rule.number not in by_number:
                    continue
                seen.add(rule.number)
                candidates.append((rule.number, rule.text[:SNIPPET_CHARS]))
    return candidates
