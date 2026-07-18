# ADR-002 — Graph database: Neo4j Community

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Bruno Ramos Martins

## Context

The project needs a graph database to store the ontology (cards,
printings, sets, formats, rules, keywords, rulings, documents,
questions) and to serve traversal queries at query time. It runs on a
personal 16 GB laptop, must be reproducible via Docker, and must
support both hand-written template traversals and LLM-generated queries
(text2cypher).

## Decision

Use **Neo4j Community Edition** in Docker as the primary graph store,
accessed through the official `neo4j` Python driver.

## Rationale

- **Cypher is the market standard** — the most transferable graph query
  skill for a portfolio; the text2cypher literature and datasets
  (Neo4j on HuggingFace) target Cypher.
- **Mature GraphRAG ecosystem** — `neo4j-graphrag-python` to be
  evaluated in Phase 4; abundant reference material.
- **Neo4j Browser** aids the demo and debugging (visual subgraphs).
- **Operational fit** — modest memory footprint tunable for a laptop;
  first-class Docker image with healthchecks and a service-container
  story for CI.

## Alternatives considered

- **Kùzu** — embedded, serverless; great for **test fixtures** without a
  server. Kept as an **optional** dependency for offline unit tests, not
  the primary store.
- **Memgraph** — Cypher-compatible, in-memory; less ubiquitous
  ecosystem for the GraphRAG tooling targeted here.
- **FalkorDB** — promising, smaller community; higher ecosystem risk for
  a portfolio piece meant to read as "industry standard".

## Consequences

- **Positive:** standard Cypher skill on the résumé; strong tooling and
  demo affordances; straightforward CI via a Neo4j service container.
- **Negative / accepted:** must operate Neo4j (memory, indexes,
  constraints) — captured as explicit new learning in the roadmap;
  Community Edition lacks some enterprise features (not needed here).
- **Mitigation:** memory tuned in `docker-compose.yml`; constraints and
  indexes defined as code in `graph/schema.py` (Phase 1); Kùzu available
  for server-free fixtures.
