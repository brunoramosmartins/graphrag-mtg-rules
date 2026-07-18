# Ontology v1

The graph schema, derived **from the golden-set strata** (see
[`golden-set.md`](golden-set.md)) — not from the game at large. The
governing rule, inherited from the roadmap: **only what some golden-set
question needs enters the schema.** Everything else stays as CR *text*
on `Rule` nodes.

Versioning: v0 was the sketch in the roadmap; v1 (this document) is the
first schema-as-code, applied by [`graph/schema.py`](../src/graphrag_mtg/graph/schema.py).

## Nodes

| Label | Key | Key properties | Source |
|---|---|---|---|
| `Card` | `oracle_id` | `name`, `oracle_text`, `mana_cost`, `cmc`, `type_line`, `colors`, `keywords`, `layout` | Scryfall oracle |
| `CardFace` | `face_key` (`<oracle_id>#<i>`) | `name`, `oracle_text`, `mana_cost`, `type_line` | Scryfall (multi-face layouts) |
| `Format` | `name` | — (`standard`, `modern`, `commander`, …) | Scryfall `legalities` |
| `Rule` | `number` (`613.7c`) | `level`, `text`, `is_glossary` | CR (deterministic parse) |
| `Keyword` | `name` | `is_evergreen` | Scryfall `keywords` + CR glossary |
| `Ruling` | `ruling_id` | `source`, `published_at`, `text` | Scryfall rulings |

## Relationships

| Pattern | Meaning | Provenance |
|---|---|---|
| `(:Card)-[:HAS_FACE]->(:CardFace)` | face of a multi-face card | deterministic |
| `(:Card)-[:HAS_LEGALITY {status}]->(:Format)` | `status ∈ legal \| not_legal \| banned \| restricted` | deterministic |
| `(:Card)-[:HAS_KEYWORD]->(:Keyword)` | card has ability keyword | deterministic |
| `(:Card)-[:HAS_RULING]->(:Ruling)` | official ruling on a card | deterministic |
| `(:Keyword)-[:DEFINED_BY]->(:Rule)` | keyword's governing rule | deterministic where the glossary is explicit; else LLM-gated |
| `(:Rule)-[:HAS_SUBRULE]->(:Rule)` | CR tree parent → child | deterministic |
| `(:Rule)-[:REFERENCES]->(:Rule)` | "see rule X" cross-reference | deterministic (explicit) + LLM (implicit) |
| `(:Ruling)-[:CITES_RULE]->(:Rule)` | ruling invokes a rule | **LLM extraction (gated)** |
| `(:Ruling)-[:MENTIONS]->(:Card)` | ruling references another card | entity linking (exact→fuzzy→LLM) |

**Provenance is a first-class property.** Every edge added by the LLM
(`CITES_RULE`, `MENTIONS`, implicit `REFERENCES`/`DEFINED_BY`) carries
`source="llm"`, `confidence`, and an `evidence_span` — nothing enters the
graph without passing `extraction/gate.py`. Deterministic edges carry
`source="deterministic"`.

## Layout modeling (Card vs. Printing)

- **Printings are NOT modeled.** No golden-set question is set- or
  printing-specific; legality is per *format* and Scryfall provides it
  per oracle card. We model the **oracle (gameplay) identity** only. This
  is a deliberate scope cut, revisited only if a question demands it.
- **Multi-face layouts** (`split`, `adventure`, `flip`, `transform`,
  `modal_dfc`) → one `Card` with a `HAS_FACE` per `CardFace`; `layout`
  is stored on the `Card`. Single-face `normal` cards carry their text
  on the `Card` directly (no face node).
- **Meld** is recorded as a decision but **deferred**: it would use
  `(:Card)-[:MELDS_WITH]->(:Card)` (the two halves) and
  `(:Card)-[:MELDS_INTO]->(:Card)` (the result). Not created until a
  golden-set question needs it — per the no-inflation rule.

## Explicitly excluded (anti-inflation)

These stay as **CR text** on `Rule` nodes, never as node types: the
**stack**, **turn structure** (turns/phases/steps), **zones**,
**players**, and the **mana pool**. Modeling the whole game engine is the
classic GraphRAG failure mode; the layer/timestamp *interactions* we care
about are answered by traversing `Rule` + `Ruling`, not by simulating
the game.

## Coverage — every stratum maps to a path

The DoD is that the ontology answers 100% of the golden-set strata. It does:

| Stratum | Answering path |
|---|---|
| `legality_1hop` | `(:Card)-[:HAS_LEGALITY {status}]->(:Format)` |
| `definition_1hop` | `(:Keyword)-[:DEFINED_BY]->(:Rule)` |
| `keyword_rule_2hop` | `(:Keyword)-[:DEFINED_BY]->(:Rule)-[:HAS_SUBRULE\|REFERENCES]->(:Rule)` |
| `rulings_2hop` | `(:Card)-[:HAS_RULING]->(:Ruling)-[:CITES_RULE]->(:Rule)` |
| `interaction_multihop` | `(:Card)-[:HAS_KEYWORD]->(:Keyword)-[:DEFINED_BY]->(:Rule)-[:REFERENCES*]->(:Rule)` + `Ruling` paths (e.g. the layer system 613.x subtree) |
| `negative_temporal` | `Rule` subtree + `REFERENCES`; timing/negation resolved from rule text on the path |

The candidate pool already surfaces this: e.g. a `keyword_rule_2hop`
sample cites `613.3`/`613.7` (the layer system) with gold entities
`Inkmoth Nexus`, `Dress Down` — exactly a `Card→Keyword→Rule` traversal.

## Reconciliation

v1 is drafted from the strata and the first 20 candidates. It is
re-checked against the full golden set once curation completes (Gate G2);
any question that needs a path the schema lacks is a schema bug, tracked
against the ontology issue.
