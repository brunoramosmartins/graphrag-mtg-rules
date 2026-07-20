# Decision Journal

Dated entries, written the day the decision is made. Entries
reconstructed from git history after the fact are marked
*(retrospective, written 2026-07-19)*. Architectural decisions get a
full ADR in [docs/adr/](adr/); the journal records the smaller,
dated calls that an ADR would be too heavy for — and points at the
evidence that forced each one.

---

## 2026-07-17 — Domain choice gated by motivation and licensing *(retrospective, written 2026-07-19)*

MTG rules chosen as the domain (ADR-001) with an explicit licensing
gate before any data touched the repo: Fan Content Policy compliance,
no bulk data committed, Scryfall attribution. Contingency gates
defined up front so an abandoned phase fails loudly instead of
lingering. Embodied in `9cd111d`.

## 2026-07-17 — Neo4j property graph over RDF *(retrospective, written 2026-07-19)*

Property graph (ADR-002): the ontology is small and typed, queries are
path-shaped, and Cypher templates are auditable. A written comparison
with RDF/OWL was not produced at decision time — parked as a possible
TIL, not re-litigated.

## 2026-07-18 — Curate, don't author, the golden set *(retrospective, written 2026-07-19)*

Golden set sourced from judge-curated RulesGuru questions rather than
self-authored ones, with `vector_should` predictions (fail/lose/tie)
recorded per question **before** any system runs. The `tie` stratum is
deliberate: a hypothesis that cannot lose anywhere is not a
hypothesis. Embodied in `ddca2bf`; source of truth in
[evaluation.md](evaluation.md).

## 2026-07-19 — Deterministic backbone; LLM only for the residual *(retrospective, written 2026-07-19)*

Phase 2 build decisions, each forced by measurement rather than taste:

- `subtree()` walks parent links, not number prefixes — `613.4b` does
  not start with `613.4.` (caught by a failing test).
- `mana_value()` refuses combined multi-face costs — 209 adventure
  cards would silently get a wrong value (caught by cross-checking
  against Scryfall `cmc`).
- Keywords keyed on normalized names — Scryfall's `"First strike"` vs
  the CR glossary's `"First Strike"` silently split every keyword into
  two nodes, leaving `Card → Keyword → Rule` empty while node counts
  looked healthy.
- Load reports use Neo4j result counters, not row counts — `0 created`
  on a reload is direct idempotency evidence.
- `PRUNE_STALE_RULES` keyed on `source_sha256` — `MERGE` never
  deletes, so withdrawn rules survived a CR update until pruned.

## 2026-07-19 — `rulings_2hop` deferred to Phase 3 on evidence *(written same day; measurement corrected 2026-07-20, see below)*

Measured: 1 of 77,999 rulings contains a CR rule number (and it is
about a store locator). `CITES_RULE` therefore has no deterministic
component — the edge can only come from validated LLM extraction,
which is exactly Phase 3's job. The stratum moves there instead of
being faked here.

## 2026-07-20 — G3 assessed on the dev split: proceed, iterate to grounded mode

First extraction run (open mode, gpt-4o-mini, 30 dev rulings, ~$0.01):
31 candidates, 2 fabricated quotes killed by the parser, 7 of 31
(23%) citing **plausible but nonexistent** rule numbers — all caught by
the gate's existence check. Spans and concepts look right; the numbers
are invented (e.g. 702.74b for connive, which is 701.50). Neither
trivial nor infeasible under E-003's decision rule, so Phase 3 proceeds
as designed: round 2 grounds the prompt in candidate rules retrieved
from the graph. What the gate cannot catch — existing-but-wrong numbers
— is exactly what the manual annotations will measure.

## 2026-07-20 — Grounding fixed hallucinated numbers and induced a topical bias

Round 2 (keyword directory in the system prompt) did what it was
designed to do: nonexistent rule numbers fell from 7 of 31 to 1 of 21.
It also did something it was not designed to do: **all 21 citations
became 701/702 keyword rules**, losing the correct procedural citations
round 1 produced (601.2c, 608.2, 613.1). A prompt whose only rule
inventory is keyword names is a prompt that asks for keywords.

Decision: keep grounding, but lead the block with the full CR chapter
map (146 chapters) and name the procedural chapters explicitly, so the
model sees the whole document rather than one wing of it. Recorded
because the lesson generalizes past this prompt: the metric that
improved (gate rejection rate) was not the metric that mattered, and
only inspecting the *shape* of the output caught it. Every prompt round
now reports the distribution of cited rule families, not just error
rates.

## 2026-07-20 — Correction: 25 rulings (3 cards) cite rule numbers, not 1

The Phase 3 sampling stratifier re-measured with the pattern
`\b\d{3}\.\d+[a-z]?\b` and found **25 of 77,999** rulings carrying an
explicit CR number — all from 3 cards whose rulings enumerate the
704.5x state-based actions in the form "(704.5g)". The Phase 2 pattern
missed parenthesized citations and undercounted by 24. The decision
stands unchanged — 0.03% coverage concentrated on 3 cards is not a
deterministic component worth building on — but the number in
[golden-set.md](golden-set.md) and [evaluation.md](evaluation.md) was
wrong and is now corrected. Lesson recorded: a measurement that feeds a
decision gets its pattern reviewed like code, because the number
outlives the script that produced it.

## 2026-07-19 — Literature reading anchored to decisions

Adopted a research scaffold: every source must name the project
decision it informs before getting a full reading note; otherwise it
goes to an ideas parking lot. Reading order is decision order (survey
→ what *not* to build → closest published design → extraction
roadmap), not textbook order. Experiments pre-register in
[../experiments/registry.md](../experiments/registry.md) before
running.
