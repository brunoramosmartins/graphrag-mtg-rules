# Golden Set v0 — design, strata, and Gate G2

The golden set is the project's ground truth for the head-to-head
comparison of graph traversal against a vector baseline. This document
is the plan of record for **Gate G2** (Phase 1): 60–80 stratified
questions with a reliable answer key, each annotated with hops and gold
entities.

> **Honesty is the point.** The value of this project is *not* "the
> graph wins everywhere" — it is a layered result that shows **where**
> the graph wins (multi-hop interaction) and **where it ties** (1-hop
> lookup). So the golden set deliberately includes strata where the
> vector baseline is *expected to tie or win*. Hiding those would make
> the evaluation dishonest and worthless.

## Strata

Each question belongs to exactly one stratum. The `vector_should` column
is our **a-priori** prediction (recorded before running anything), per
`docs/hypothesis.md`.

| Stratum | Hops | What it tests | Primary source | `vector_should` |
|---|---|---|---|---|
| `legality_1hop` | 1 | "Is *card* legal in *format*?" | Scryfall `legalities` (auto) | lose |
| `definition_1hop` | 1 | "What does *keyword* do?" | CR keyword glossary (auto, Phase 2) | tie |
| `keyword_rule_2hop` | 2 | keyword → governing rule → sub-rules | RulesGuru / CR | lose |
| `rulings_2hop` | 2 | card → ruling → rule cited | RulesGuru + Scryfall rulings | lose |
| `interaction_multihop` | 3+ | layer / replacement / timestamp interaction | RulesGuru + authored | fail |
| `negative_temporal` | 2–3 | "does **not**" / timing-dependent | authored + RulesGuru | fail |

`vector_should` values: **tie** (answer is written in one passage, both
retrievers find it), **lose** (graph edge is cleaner but text can work),
**fail** (answer is a *path* that no single passage states).

## Sources — depth over breadth

Three origins, each playing to its strength:

1. **Scryfall-derived (auto-generated, reliable key).** `legality_1hop`
   and part of `definition_1hop` are generated from structured data
   whose ground truth *is* the data: card `legalities`, evergreen
   keyword lists. These are our own generated questions (committable in
   full) and give the honest 1-hop baseline where the vector should tie.
2. **RulesGuru (judge-curated).** The 2-hop and interaction strata,
   where judge-written questions with expert answers are the asset.
   **License-bound:** eval-only, non-commercial, no training; we version
   **question IDs + a fetch script, never the question text** (see
   [`data-sources.md`](data-sources.md)). Full text is materialized to
   `data/interim/` (gitignored) on demand.
3. **Hand-authored (our content, grounded in CR).** ~10–15 hard
   interaction and negative/temporal questions written against the
   Comprehensive Rules — the "hard core" that the whole graph thesis
   exists to answer (e.g. Humility + Opalescence layer interaction).
   Fully committable; zero third-party license exposure.

## Record schema

One JSON object per line (`data/golden/ids_v0.jsonl`), validated by
`evaluation/golden.py` (`GoldenQuestion`). Fields:

| Field | Meaning |
|---|---|
| `id` | Stable id: `rg-<n>` (RulesGuru), `scry-<n>` (generated), `hand-<n>` (authored) |
| `source` | `rulesguru` \| `scryfall` \| `authored` |
| `stratum` | one of the six above |
| `hops` | integer ≥ 1 |
| `question` / `answer` | inline text — **only** for `scryfall`/`authored`; **must be null** for `rulesguru` |
| `gold_entities` | card names / keywords the answer depends on |
| `gold_cr_rules` | CR rule numbers on the gold path, e.g. `["613.1", "613.7c"]` |
| `gold_path` | prose description of the traversal |
| `vector_should` | `tie` \| `lose` \| `fail` (a-priori prediction) |
| `vector_should_reason` | required when `stratum` is interaction/negative or `vector_should == fail` |
| `rulesguru_url` | canonical link (attribution) — for `rulesguru` rows |
| `snapshot_sha256` | hash of the resolved content at curation time (drift detection) |
| `verified` | `true` once a human has reviewed the annotation |

On **`verified`** — it means something different per origin, deliberately:

- **Generated (`scryfall`)** — `true` on creation. The answer is derived
  mechanically from ground-truth data; there is no judgment to review.
- **Authored** — `true`. Every CR citation is machine-checked to exist in
  the downloaded rules (`scripts/check_cr_citations.py`; that check caught
  and fixed four wrong citations — the layer-7 sublayers are 613.4a–d, not
  613.7), and the author has signed off on the rulings. Citation
  *existence* is proven mechanically; the *correctness* of each ruling
  rests on that sign-off, not on a machine.
- **RulesGuru** — `false` until a human confirms **our annotations**
  (stratum, hops, gold path). The answer key itself needs no review; it is
  judge-curated. What is unverified is our classification of it.

The **snapshot hash** addresses the RulesGuru procedural-variation risk
(interchangeable cards can change a fetched question): we freeze the
content hash per id at curation time and can detect upstream drift on
re-fetch.

## Workflow

```
# 1. Pull a stratified candidate pool from RulesGuru (IDs + our annotations;
#    full text cached to data/interim/, never committed).
python scripts/build_golden_pool.py --per-stratum 15

# 2. Human review: fix stratum/hops, fill gold_entities/gold_cr_rules/gold_path,
#    write vector_should_reason for interaction/negative rows, set verified=true.
#    Procedure + worked examples: docs/annotation-guide.md

# 3. Re-materialize full text at eval time (by id) and check snapshot drift.
```

## Gate G2 status

**In progress — path is clear, no blocker.**

- Framework, schema, and loader: **done** (this document + `golden.py`).
- `legality_1hop`: **done** — generated from Scryfall `legalities`
  (`scripts/generate_legality_questions.py`), reliable key, auto-verified.
  Marked `vector_should=lose`: format legality is structured metadata, so
  the graph edge should beat prose retrieval (conservative, not `fail`).
- `definition_1hop`: **deferred to Phase 2** — its answer key is the CR
  keyword glossary (702.x), which the `cr_parser` provides.
- 2-hop / interaction strata: candidate pool pulled from RulesGuru;
  **human annotation of hops/gold-entities is the remaining work** — the
  answer key itself is judge-reliable (that is RulesGuru's asset).
- Hard-interaction authored set: **done** — 12 questions in
  `authored_v0.jsonl` (`scripts/build_authored_set.py`), all
  `verified=false` pending a judge's review of the rulings/CR citations.

**Current count: 62, all verified** — by origin: 30 RulesGuru, 20
generated, 12 authored.

| Stratum | Count | `vector_should` |
|---|---|---|
| `interaction_multihop` | 30 | fail |
| `legality_1hop` | 20 | lose |
| `negative_temporal` | 9 | fail |
| `keyword_rule_2hop` | 3 | lose |
| `rulings_2hop` | **0** | — |
| `definition_1hop` | **0** | — |

### Known gap: two empty strata, and no `tie` stratum

The annotation pass (`scripts/annotate_rulesguru_pass1.py`) revealed that
**RulesGuru is an interaction-puzzle corpus, not a rulings-lookup one**.
Every one of its 30 rows is a multi-permanent scenario; none is a
"card → official ruling → rule" question. The seeded classification hid
this because it was derived from `complexity`.

Consequences to fix before the evaluation is credible:

- **`rulings_2hop` is empty.** Its real source is the Scryfall rulings
  corpus (77,999 rulings already downloaded), not RulesGuru — a generator
  like the legality one can build it.
- **`definition_1hop` is empty**, pending the Phase 2 CR glossary parse.
- **No stratum currently predicts `tie`.** The roadmap deliberately wants
  strata where the vector baseline should *draw*; without them a reported
  graph win is not falsifiable. `definition_1hop` is the natural `tie`
  stratum (the answer is written in one CR passage), so filling it is what
  restores that balance.

Gate G2's count and verification bars are met; this is a **composition**
gap, tracked rather than papered over.

## Files (shards)

The golden set is sharded by origin; `load_golden_dir("data/golden")`
loads and concatenates them (rejecting duplicate ids):

- `ids_v0.jsonl` — RulesGuru skeletons (IDs, no text) + generated legality.
- `authored_v0.jsonl` — hand-authored hard-interaction questions.

G2 passes when ≥ 60 questions are `verified` across the strata. If
RulesGuru coverage of a stratum proves thin, the fallback is to lean
harder on the authored set (per [`contingency.md`](contingency.md)); the
scaffold does not change.
