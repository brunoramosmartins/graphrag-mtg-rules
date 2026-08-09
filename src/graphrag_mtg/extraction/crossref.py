"""Few-shot extraction of implicit (:Rule)-[:REFERENCES]->(:Rule) edges.

The deterministic CR parser already extracts **explicit** cross-references
— a rule that literally says "see rule 601.2e". This stage adds only the
**implicit** ones: a rule that depends on another's concept without naming
its number ("a spell with no legal targets doesn't resolve" leans on the
targeting/resolution rules it never cites). Those are exactly the edges
the roadmap reserves for the LLM, and the G3 gate's fallback if
`CITES_RULE` turns out trivial.

Same contract as every LLM edge (`extraction/schemas.py`): each candidate
carries a verbatim quote from the **source rule's** text, located to an
offset span the gate re-checks. A candidate whose target is already an
explicit reference is dropped here — this stage never re-proposes what the
parser found deterministically.

Because a rule's text is short and self-contained, extraction is grounded
in a candidate list (the chapter map plus the rule's own section), so the
model cites real numbers rather than inventing them — the same lesson the
citation extractor learned (see `notes/phase3-extraction.md`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from graphrag_mtg.extraction.llm import LlmClient
from graphrag_mtg.extraction.schemas import EvidenceSpan, LinkMethod, RuleCrossRef

CROSSREF_VERSION = "v1"

SYSTEM_PROMPT = """\
You find IMPLICIT cross-references between Magic: The Gathering Comprehensive \
Rules — a rule that depends on another rule's concept WITHOUT stating its number.

You are given one source rule and a list of candidate target rules. Return a JSON \
array (possibly empty) of objects:
  {"target_rule": "<a number from the candidate list>",
   "quote": "<verbatim substring of the SOURCE rule that leans on the target>",
   "rationale": "<one sentence: why this passage depends on that rule>",
   "confidence": <0.0-1.0>}

Hard requirements:
- Do NOT report a reference the source rule already states by number — those are \
found deterministically. Only implicit dependencies.
- "quote" must be copied character-for-character from the source rule's text.
- "target_rule" must be one of the candidate numbers given.
- An empty array is the right answer for a self-contained rule.
Return the JSON array and nothing else."""

FEW_SHOTS = """\
Example source rule 509.1 (a made-up excerpt about declaring blockers):
"A blocking creature must be able to block the attacker legally."
Candidates: 509.1b Evasion abilities, 702.9 Flying, 509.4 Ordering blockers
Example output: [{"target_rule": "702.9", "quote": "must be able to block the \
attacker legally", "rationale": "Legality of a block turns on evasion abilities \
like flying.", "confidence": 0.7}]

Example source rule with no implicit dependency:
"A player who has lost the game leaves the game."
Candidates: 104.3a Concession, 800.4 Leaving the game
Example output: []"""


@dataclass
class CrossRefReport:
    """Implicit-reference candidates plus a named accounting of drops."""

    candidates: list[RuleCrossRef] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)

    def merge(self, other: CrossRefReport) -> None:
        self.candidates.extend(other.candidates)
        self.dropped.update(other.dropped)


def build_prompt(rule_number: str, rule_text: str, candidate_rules: list[tuple[str, str]]) -> str:
    """Assemble the per-rule prompt with its candidate targets."""
    listing = "\n".join(f"- {number}: {snippet}" for number, snippet in candidate_rules)
    return (
        f"{FEW_SHOTS}\n\n"
        f"Source rule {rule_number}: \"{rule_text}\"\n\n"
        f"Candidate target rules (cite ONLY from this list):\n{listing}"
    )


def parse_response(
    source_rule: str,
    source_text: str,
    raw: Any,
    *,
    explicit_refs: set[str] | frozenset[str] = frozenset(),
    candidate_numbers: set[str] | frozenset[str] = frozenset(),
) -> CrossRefReport:
    """Turn a model response into schema-valid, deduplicated candidates.

    Drops, each counted: quote missing from the source rule, target absent
    from the candidate list, target already an explicit reference, a
    self-reference, or a schema failure.
    """
    report = CrossRefReport()
    if not isinstance(raw, list):
        report.dropped["response_not_a_list"] += 1
        return report
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            report.dropped["item_not_an_object"] += 1
            continue
        target = str(item.get("target_rule", ""))
        if candidate_numbers and target not in candidate_numbers:
            report.dropped["target_not_a_candidate"] += 1
            continue
        if target in explicit_refs:
            report.dropped["already_explicit"] += 1
            continue
        if target == source_rule:
            report.dropped["self_reference"] += 1
            continue
        if target in seen:
            report.dropped["duplicate_in_response"] += 1
            continue
        quote = str(item.get("quote", ""))
        start = source_text.find(quote) if quote else -1
        if start < 0:
            report.dropped["quote_not_in_source"] += 1
            continue
        try:
            crossref = RuleCrossRef(
                source_rule=source_rule,
                target_rule=target,
                span=EvidenceSpan(start=start, end=start + len(quote), text=quote),
                rationale=str(item.get("rationale", "")) or "(none given)",
                method=LinkMethod.LLM,
                confidence=float(item.get("confidence", 0.0)),
            )
        except (ValidationError, TypeError, ValueError):
            report.dropped["schema_invalid"] += 1
            continue
        seen.add(target)
        report.candidates.append(crossref)
    return report


def extract_crossrefs(
    rule_number: str,
    rule_text: str,
    candidate_rules: list[tuple[str, str]],
    client: LlmClient,
    *,
    explicit_refs: set[str] | frozenset[str] = frozenset(),
) -> CrossRefReport:
    """Run one rule through the implicit-reference extractor (one API call)."""
    if not candidate_rules:
        return CrossRefReport()
    prompt = build_prompt(rule_number, rule_text, candidate_rules)
    try:
        raw = client.complete_json(prompt, system=SYSTEM_PROMPT)
    except ValueError:
        report = CrossRefReport()
        report.dropped["unparseable_response"] += 1
        return report
    return parse_response(
        rule_number,
        rule_text,
        raw,
        explicit_refs=explicit_refs,
        candidate_numbers={number for number, _ in candidate_rules},
    )
