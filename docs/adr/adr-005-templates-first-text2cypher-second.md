# ADR-005 — Templates first, text2cypher second

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Bruno Ramos Martins

## Context

Graph retrieval must turn a question into a subgraph of evidence. Two
strategies are available: **parameterized template traversals** (hand
-written Cypher for known question families) and **text2cypher**
(LLM generates Cypher from the schema for the long tail). Text2cypher is
attractive but unstable and, if it "steals the stage", it undermines
reliability and safety.

## Decision

- **Templates are the cake; text2cypher is the cherry.** Cover the
  golden-set question families with ≥ 7 tested, parameterized template
  traversals (keyword→rule→subrules, card/list legality,
  card→rulings→rules, card×card interaction, subrule chains, negative/
  temporal). Target: **~80% of the golden set answerable by templates.**
- **text2cypher handles only the long tail**, behind hard guardrails:
  **read-only clauses only**, **mandatory LIMIT**, **syntax-checked via
  EXPLAIN before execution**, and an honest **"I can't translate this"**
  fallback. It **never** executes a write (covered by adversarial tests).
- text2cypher is **timeboxed** in Phase 4; if it proves flaky, templates
  carry the project and text2cypher is documented as a bounded
  experiment.

## Rationale

- Templates are **reliable, testable, and fast** (p95 < 2 s target) and
  make the evaluation trustworthy.
- Guarded text2cypher demonstrates the skill (schema-aware generation +
  safety) without betting reliability on it.
- Safety is non-negotiable: an LLM emitting Cypher against a live DB is
  a write/destruction risk that must be closed by validation, not trust.

## Consequences

- **Positive:** reliable retrieval for the measured families; a
  demonstrable, safe text2cypher layer for the tail; graceful, honest
  failure instead of silently-wrong context.
- **Negative / accepted:** templates require up-front design per family;
  some genuinely novel questions may hit the "can't translate" fallback
  — acceptable and surfaced to the user.
- **Cut order:** if effort runs short, text2cypher is the first thing
  cut (templates remain) — consistent with the roadmap's critical-path
  guidance.
