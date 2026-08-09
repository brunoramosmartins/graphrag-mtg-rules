# Architecture Decision Records

Each ADR captures one significant decision: its context, the decision,
and its consequences. Status values: Proposed · Accepted · Superseded.

| ADR | Title | Status |
|---|---|---|
| [001](./adr-001-domain-choice-magic.md) | Domain choice: Magic: The Gathering rules | Accepted |
| [002](./adr-002-graph-db-neo4j.md) | Graph database: Neo4j Community | Accepted |
| [003](./adr-003-deterministic-parse-plus-llm-extraction.md) | Deterministic parse first, LLM extraction second | Accepted (the `APPLIES_RULE` clause superseded by 006) |
| [004](./adr-004-card-name-linking-strategy.md) | Card-name linking strategy (cascade) | Accepted |
| [005](./adr-005-templates-first-text2cypher-second.md) | Templates first, text2cypher second | Accepted |
| [006](./adr-006-cites-rule-reduced-to-explicit.md) | `CITES_RULE` reduced to explicit citations | Accepted |
