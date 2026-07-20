"""Comprehensive Rules text to a numbered tree (fully deterministic).

The CR is the densest, most self-referential corpus in the project, and the
whole graph thesis rests on its structure being *derived*, not guessed. No LLM
touches this module: the tree and the explicit cross-references come from the
numbering and from "see rule N" alone. The LLM only adds what this parser
cannot reach (implicit relations, Phase 3).

Structure, measured against the February 27, 2026 CR rather than assumed:

* The file is UTF-8 **with a BOM** (``utf-8-sig``) and uses bare LF endings.
* A table of contents repeats all 9 section and 146 chapter headings before the
  body starts. Parsing it as rules would duplicate every chapter, so the body
  boundary is found explicitly: the last single-digit section heading before
  the first numbered rule. Front matter then holds 0 rules, by construction.
* Rule text does **not** wrap: each rule is one line. Of 3,551 non-blank body
  lines, only 2 are indented continuations, and 276 are ``Example:`` lines that
  belong to the preceding rule.
* Numbered rules carry a trailing period (``613.4.``); lettered subrules do not
  (``613.4b``).
* The glossary (726 terms) follows the body and has no rule numbers, so its
  entries become :class:`GlossaryEntry` rather than ``Rule`` nodes; 206 of them
  cite a ``702.x`` keyword rule, which is what feeds ``Keyword-[:DEFINED_BY]->``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CR_TXT_PATH = Path("data/raw/comprehensive_rules.txt")

# "613.4." (numbered, trailing period) or "613.4b" (lettered, none).
_RULE_LINE = re.compile(r"^(\d{3})\.(\d+)([a-z]?)\.?\s+(.*)$")
# "613. Interaction of Continuous Effects"
_CHAPTER_LINE = re.compile(r"^(\d{3})\.\s+(\S.*)$")
# "1. Game Concepts"
_SECTION_LINE = re.compile(r"^(\d)\.\s+(\S.*)$")

_EXAMPLE_PREFIX = "Example:"
_GLOSSARY_HEADING = "Glossary"
_CREDITS_HEADING = "Credits"

_EFFECTIVE_DATE = re.compile(r"These rules are effective as of (.+?)\.")

# "see rule 704.5", "rules 602.2a and 603.3", "rule 603.7 and rule 603.12".
# The trailing group collects the extra targets of a multi-reference phrase.
_REFERENCE_PHRASE = re.compile(
    r"\brules?\s+"
    r"((?:\d{3}(?:\.\d+[a-z]?)?)"
    r"(?:\s*(?:,|and)\s*(?:rule\s+)?\d{3}(?:\.\d+[a-z]?)?)*)"
)
_REFERENCE_NUMBER = re.compile(r"\d{3}(?:\.\d+[a-z]?)?")


@dataclass
class Rule:
    """One node of the CR tree.

    Attributes:
        number: The rule number, e.g. ``613``, ``613.4`` or ``613.4b``.
        level: 1 for a chapter, 2 for a numbered rule, 3 for a lettered subrule.
        text: The rule's own text (the chapter's is its title).
        parent: The parent rule's number, or None for a chapter.
        examples: ``Example:`` lines attached to this rule, verbatim.
        section: The containing section's title, e.g. ``Game Concepts``.
        references: Rule numbers this rule points at, validated to exist.
    """

    number: str
    level: int
    text: str
    parent: str | None
    section: str
    examples: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass
class GlossaryEntry:
    """A glossary term and its definition.

    The glossary has no rule numbers, so entries cannot key on ``number`` like
    ``Rule`` does. They become ``Keyword`` nodes plus ``DEFINED_BY`` edges to
    the rules they cite — the deterministic source of the ``definition_1hop``
    stratum.
    """

    term: str
    definition: str
    references: list[str] = field(default_factory=list)


@dataclass
class CRDocument:
    """The parsed Comprehensive Rules."""

    effective_date: str | None
    rules: list[Rule]
    glossary: list[GlossaryEntry]

    @property
    def by_number(self) -> dict[str, Rule]:
        """Index the rules by number (numbers are unique — verified: 0 duplicates)."""
        return {rule.number: rule for rule in self.rules}

    def subtree(self, number: str) -> list[Rule]:
        """Return ``number`` and every rule beneath it, in document order.

        Walks the parent chain rather than matching number prefixes. Prefixes
        are wrong twice over here: lettered subrules append their letter with
        no separator ("613.4" -> "613.4b", which does not start with "613.4."),
        while a plain prefix would wrongly pull "613.41" into "613.4"'s
        subtree. Rules are emitted in document order, so a parent is always
        seen before its children.
        """
        members = {number}
        found: list[Rule] = []
        for rule in self.rules:
            if rule.number == number or rule.parent in members:
                members.add(rule.number)
                found.append(rule)
        return found


def parent_of(number: str) -> str | None:
    """Return a rule number's parent, or None for a chapter.

    >>> parent_of("613.4b")
    '613.4'
    >>> parent_of("613.4")
    '613'
    >>> parent_of("613") is None
    True
    """
    if number[-1].isalpha():
        return number[:-1]
    if "." in number:
        return number.split(".", 1)[0]
    return None


def level_of(number: str) -> int:
    """Return 1 for a chapter, 2 for a numbered rule, 3 for a lettered subrule."""
    if number[-1].isalpha():
        return 3
    return 2 if "." in number else 1


def _find_body_bounds(lines: list[str]) -> tuple[int, int, int]:
    """Locate the body, glossary and credits boundaries.

    The table of contents repeats every heading, so the body is taken to start
    at the last single-digit section heading that precedes the first numbered
    rule. Verified against the real document: front matter then contains 0
    rules and the body contains exactly 9 sections and 146 chapters.

    Returns:
        ``(body_start, glossary_start, credits_start)`` line indices.

    Raises:
        ValueError: if any boundary is missing — a restructured CR must fail
            loudly rather than parse into a plausible-looking wrong tree.
    """
    first_rule = next((i for i, ln in enumerate(lines) if _RULE_LINE.match(ln)), None)
    if first_rule is None:
        msg = "No numbered rule found; the CR layout changed."
        raise ValueError(msg)

    sections_before = [i for i in range(first_rule) if _SECTION_LINE.match(lines[i])]
    if not sections_before:
        msg = "No section heading precedes the first rule; the CR layout changed."
        raise ValueError(msg)
    body_start = max(sections_before)

    glossary = [i for i, ln in enumerate(lines) if ln.strip() == _GLOSSARY_HEADING]
    credits = [i for i, ln in enumerate(lines) if ln.strip() == _CREDITS_HEADING]
    if not glossary or not credits:
        msg = "Missing Glossary or Credits heading; the CR layout changed."
        raise ValueError(msg)
    return body_start, max(glossary), max(credits)


def _parse_rules(lines: list[str]) -> list[Rule]:
    """Parse the body lines into the rule tree, in document order."""
    rules: list[Rule] = []
    current: Rule | None = None
    section = ""

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if section_match := _SECTION_LINE.match(line):
            section = section_match.group(2).strip()
            current = None
            continue

        if rule_match := _RULE_LINE.match(line):
            chapter, number, letter, text = rule_match.groups()
            full = f"{chapter}.{number}{letter}"
            current = Rule(
                number=full,
                level=level_of(full),
                text=text.strip(),
                parent=parent_of(full),
                section=section,
            )
            rules.append(current)
            continue

        # Checked after _RULE_LINE: "613.4. text" also matches the chapter shape.
        if chapter_match := _CHAPTER_LINE.match(line):
            number, title = chapter_match.groups()
            current = Rule(
                number=number,
                level=1,
                text=title.strip(),
                parent=None,
                section=section,
            )
            rules.append(current)
            continue

        if current is None:
            continue
        if line.strip().startswith(_EXAMPLE_PREFIX):
            current.examples.append(line.strip())
        else:
            # One of the two indented continuation lines in the current CR.
            current.text = f"{current.text} {line.strip()}"

    return rules


def _parse_glossary(lines: list[str]) -> list[GlossaryEntry]:
    """Parse glossary entries.

    Entries are blank-line separated: the first non-blank line is the term and
    the following lines are its definition (some terms have numbered senses).
    """
    entries: list[GlossaryEntry] = []
    term: str | None = None
    definition: list[str] = []

    def flush() -> None:
        if term is not None:
            entries.append(GlossaryEntry(term=term, definition=" ".join(definition).strip()))

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush()
            term, definition = None, []
            continue
        if term is None:
            term = line
        else:
            definition.append(line)
    flush()
    return [entry for entry in entries if entry.definition]


def extract_references(text: str, known: set[str]) -> list[str]:
    """Return the rule numbers ``text`` explicitly references.

    Handles the multi-target phrasings the CR actually uses ("see rules 602.2a
    and 603.3", "rule 603.7 and rule 603.12"). Targets are validated against
    ``known``, so a number that does not name a real rule is dropped rather
    than becoming a dangling edge.
    """
    found: list[str] = []
    for phrase in _REFERENCE_PHRASE.finditer(text):
        for number in _REFERENCE_NUMBER.findall(phrase.group(1)):
            if number in known and number not in found:
                found.append(number)
    return found


def parse_cr(path: Path = CR_TXT_PATH) -> CRDocument:
    """Parse the Comprehensive Rules text into a :class:`CRDocument`.

    Args:
        path: The downloaded CR text (UTF-8 with BOM).

    Returns:
        The parsed document: rule tree, glossary, and effective date.

    Raises:
        ValueError: if the document's structural landmarks are missing.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.split("\n")

    body_start, glossary_start, credits_start = _find_body_bounds(lines)
    rules = _parse_rules(lines[body_start:glossary_start])
    glossary = _parse_glossary(lines[glossary_start + 1 : credits_start])

    known = {rule.number for rule in rules}
    for rule in rules:
        body = " ".join([rule.text, *rule.examples])
        rule.references = [ref for ref in extract_references(body, known) if ref != rule.number]
    for entry in glossary:
        entry.references = extract_references(entry.definition, known)

    date_match = _EFFECTIVE_DATE.search(text)
    return CRDocument(
        effective_date=date_match.group(1) if date_match else None,
        rules=rules,
        glossary=glossary,
    )
