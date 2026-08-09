# ADR-003 — Deterministic parse first, LLM extraction second

- **Status:** Accepted — the `APPLIES_RULE` clause superseded by
  [ADR-006](./adr-006-cites-rule-reduced-to-explicit.md) (2026-08-09),
  which measured that edge at F1 0.125 and made it deterministic. The
  deterministic-first principle, the gate, and the linking decision all
  stand.
- **Date:** 2026-07-17
- **Deciders:** Bruno Ramos Martins

## Context

The graph has two kinds of edges: those derivable **deterministically**
from structured data or regular text patterns (the CR numbering tree,
explicit "see rule 704.5" references, Scryfall legalities and layouts),
and those requiring **inference** (linking a ruling to the card it
mentions when the card is named "Opt"/"Fear"/"Terror" or referred to
as "this creature"; the rule a ruling applies; implicit CR
cross-references). A single "throw the text at an LLM" approach would
be unmeasurable and would fabricate structure that the source already
encodes precisely.

## Decision

- **Parse deterministically wherever the structure is explicit.** The
  CR tree (`SUBRULE_OF`), explicit `REFERENCES` ("see rule X"), and all
  Scryfall-derived facts (cards, faces, sets, legalities) are built by
  tested, deterministic code — **no LLM**.
- **Use an LLM only for what determinism cannot reach:** ruling→card
  linking, ruling→rule (`APPLIES_RULE`), and *implicit* CR
  cross-references.
- **Every LLM-produced triple passes `extraction/gate.py`** before it
  enters the graph: schema-valid, carries a mandatory **evidence span**,
  meets a confidence threshold, deduped, and linked to an existing node.
  A rule number cited by the LLM must **exist in the graph** and be
  **present in the evidence span**.
- **Quantify it.** Extraction/linking are validated against ~100–120
  manually annotated rulings (Phase 3), reported as P/R/F1 stratified by
  difficulty (Phase 6).

## LLM provider

Default provider is **Anthropic Claude** via API (`anthropic` optional
dependency; model configurable via `LLM_MODEL`). The extraction and
generation code is written provider-agnostically so the client can be
swapped. Build-vs-use note: `LangChain LLMGraphTransformer` and
`LlamaIndex PropertyGraphIndex` were studied as references; we **build**
the extraction layer to own the evidence-span gate and the metrics,
which those abstractions do not expose the way this project needs.

## Rationale

- The differentiator of GraphRAG over "load JSON into Neo4j" is exactly
  the **measured** inference layer; determinism must not be faked by an
  LLM, and inference must not be trusted without metrics.
- The evidence-span gate is the guard against the failure mode where an
  LLM invents a plausible rule number (601.2c when it is 601.2b).

## Consequences

- **Positive:** the CR tree is 100% reproducible and test-covered; the
  LLM layer is auditable and quantified; hallucinated structure cannot
  enter the graph.
- **Negative / accepted:** manual annotation of ~100–120 rulings is the
  most important — and most tedious — manual work of the project
  (mitigated by a written guideline and timeboxed sessions).
- **Thresholds (adjustable with justification):** linking
  ruling→card F1 ≥ 0.9; `APPLIES_RULE` F1 ≥ 0.75. See gate **G3**.
