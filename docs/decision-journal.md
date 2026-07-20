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

## 2026-07-19 — `rulings_2hop` deferred to Phase 3 on evidence *(written same day)*

Measured: 1 of 77,999 rulings contains a CR rule number (and it is
about a store locator). `CITES_RULE` therefore has no deterministic
component — the edge can only come from validated LLM extraction,
which is exactly Phase 3's job. The stratum moves there instead of
being faked here.

## 2026-07-19 — Literature reading anchored to decisions

Adopted a research scaffold: every source must name the project
decision it informs before getting a full reading note; otherwise it
goes to an ideas parking lot. Reading order is decision order (survey
→ what *not* to build → closest published design → extraction
roadmap), not textbook order. Experiments pre-register in
[../experiments/registry.md](../experiments/registry.md) before
running.
