# ADR-001 — Domain choice: Magic: The Gathering rules

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Bruno Ramos Martins
- **Supersedes:** the v1 domain recommendation (corporate ownership /
  sanctions network), retained as the Plan-B roadmap (gate G4).

## Context

Project 2 of a three-part RAG trilogy must **attest technical depth in
GraphRAG** (explicit ontology, metrics-validated extraction, traversal
retrieval, cited generation) while surviving the #1 risk of a
free-time project: **abandonment**. The v1 roadmap recommended a
corporate ownership + sanctions graph (aligned with a
compliance/fraud brand). Additional author context re-weighted the
criteria: the goal is to demonstrate engineering, with a domain that
motivates outside of work; thematic continuity with Project 1 is not a
requirement.

## Decision

Build the GraphRAG system over the **official Magic: The Gathering
rules corpus**: Scryfall oracle data, the Comprehensive Rules (parsed
as a numbered tree with cross-references), official rulings, and the
tournament documents (MTR/IPG), evaluated against a **judge-curated
golden set (RulesGuru)** and **calibrated on MetaQA**.

## Rationale (re-weighted criteria)

1. **Motivation is an engineering criterion.** In a free-time project,
   the domain that sustains engagement reduces the dominant risk.
2. **The author must be able to judge the answer key.** Solved by a
   pre-existing golden set curated by judges (RulesGuru + official
   rulings + the Cranial Insertion archive) — the author is *curator of
   the key, not author of it*.
3. **A hard textual layer for LLM extraction.** The Comprehensive Rules
   are exceptional: hierarchical numbering (601.2b), cross-references,
   exceptions overriding general rules, quarterly updates — a
   legitimate proxy for dense regulatory text.
4. **Objective ground truth.** Rules questions have a right answer.

## Alternatives considered (and rejected)

- **Pokémon TCG** — thin textual corpus; author never played; grey IP
  zone with no explicit policy.
- **Game lore** — interpretive answer key destroys evaluation.
- **Popular-science books** — corpus copyright is a blocker.
- **ML-concept graph** — contestable edges without a public golden set.
  Preserved as a **Project 4** candidate.
- **v1 corporate ownership network** — still valid and detailed; kept
  as the **G4 last-resort** plan (~90% of structure portable).

## Contingency gates (registered here, detailed in `contingency.md`)

- **G1 — Licensing** (Phase 0), **G2 — Golden set** (Phase 1),
  **G3 — Extraction** (Phase 3 wk 1), **G4 — Last resort** (any time).
  Failing a gate triggers a pre-registered exit plan, not project
  failure.

## Consequences

- **Positive:** high author motivation; an expert-validated key at
  scale; a genuinely hard extraction layer; a defensible
  "measure-the-truth" portfolio narrative.
- **Negative / accepted:** must confront the "but it's a game"
  objection head-on in the README; must manage WotC/Scryfall IP
  compliance (handled by G1 and the Fan Content notice).
- **Prior art** (MTG AI assistants, the Forge rules engine) exists; the
  differentiator is the **documented engineering** — explicit ontology,
  measured extraction F1, stratified honest evaluation against a real
  baseline, observability — which none of them publish.
