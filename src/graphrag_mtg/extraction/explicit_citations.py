"""Deterministic ``CITES_RULE``: the ruling states the rule number itself.

What is left of the citation edge after the E-003 schema reduction. The
LLM path aimed at the *governing* rule — the rule a ruling turns on
without naming — and measured citation F1 0.125 [0.073, 0.180] over 125
annotated rulings, with a sampled decomposition (E-003b) putting the gap
on the model rather than on the metric or the gold. Gate G3's registered
rule fired: reduce the schema, report the negative.

So this module claims far less, and can prove what it claims. A citation
exists when the ruling text contains the rule number, and the evidence
span *is* that occurrence — a claim the gate re-checks by re-reading the
source. Coverage is 25 of 77,999 rulings (0.03%, concentrated on 3 cards
whose rulings enumerate the 704.5 state-based actions).

The claim being exact does **not** make the edge right, and the measured
numbers say so: against the E-003 gold this path scores P 0.667, R 0.800
on the `explicit` stratum (tp=4 fp=2 fn=1), not 1.0. Two distinct
reasons, both worth knowing:

- **Ruling text goes stale and cannot be migrated.** One ruling writes
  "(704.5w)"; the August 2026 CR shifted that state-based action to
  `704.5x` and reused `704.5w` for something else. The gold moved with
  the text (`scripts/cr_migrate.py`); the ruling, being a historical
  document, did not. The number still resolves, so the gate cannot catch
  it — the same silent displacement that moved `initiative` off 725.1
  while leaving 725.1 valid. This is the reduced schema's own version
  hazard and it is not fixable by parsing harder.
- **The gold answers a different question.** It records the rule that
  *governs* a ruling, which is not always the rule the ruling names.

What is exact is the narrow claim in the edge: the ruling states this
number. Anything beyond that is measurement, and it is above.

Trading 99.97% of the coverage for a guarantee is only worth it because
the coverage was not real: at F1 0.125 roughly seven of every eight
inferred edges were wrong, and a graph that cites wrongly is worse than
one that stays silent — it looks grounded.

Deliberately narrow in two ways:

- **Only the dotted form** (``704.5g``, ``601.2c``). A bare three-digit
  chapter number would match "100 life" and every other quantity in the
  corpus; the false positives would cost more than the chapter edges are
  worth.
- **No normalisation of near-misses.** A number that does not exist in the
  CR is dropped by the gate's ``rule_not_in_graph`` check rather than
  repaired here. Repairing it would be inference again, wearing a regex.
"""

from __future__ import annotations

import re

from graphrag_mtg.extraction.schemas import EvidenceSpan, LinkMethod, RuleCitation

# Dotted rule numbers only. `\b` on both sides so "(704.5g)" is found —
# the parenthesized form is how the corpus actually writes them, and the
# Phase 2 pattern that missed it undercounted the stratum by 24 rulings
# (docs/decision-journal.md, 2026-07-20).
RULE_NUMBER = re.compile(r"\b\d{3}\.\d+[a-z]?\b")

# Enough of the ruling around the number for a human audit trail, without
# putting a second sentence in the rationale.
RATIONALE_CONTEXT = 60


def _context(text: str, start: int, end: int) -> str:
    """The ruling around a match, for the audit note."""
    left = max(0, start - RATIONALE_CONTEXT)
    right = min(len(text), end + RATIONALE_CONTEXT)
    return " ".join(text[left:right].split())


def explicit_citations(ruling_id: str, text: str) -> list[RuleCitation]:
    """Every rule number the ruling states, as gate-ready candidates.

    The span is the number occurrence itself rather than the enclosing
    sentence: it is the smallest claim that supports the edge, and the
    tightest one for the gate to verify. Repeated numbers yield repeated
    candidates — the gate dedupes on (type, source, target), keeping the
    accounting of what was proposed honest.

    Args:
        ruling_id: The graph's Ruling key for this ruling.
        text: The ruling's text, exactly as the gate will re-read it.

    Returns:
        One :class:`RuleCitation` per occurrence, in document order, each
        with ``method = LinkMethod.EXPLICIT`` and confidence 1.0. Whether
        the number names a real rule is the gate's question, not this
        function's.
    """
    citations: list[RuleCitation] = []
    for match in RULE_NUMBER.finditer(text):
        start, end = match.span()
        citations.append(
            RuleCitation(
                ruling_id=ruling_id,
                rule_number=match.group(),
                span=EvidenceSpan(start=start, end=end, text=match.group()),
                rationale=f"the ruling states this rule number: ...{_context(text, start, end)}...",
                method=LinkMethod.EXPLICIT,
                confidence=1.0,
            )
        )
    return citations
