# Changelog

Phase tags mark the roadmap's checkpoints; `v1.0.0` is the release. Dates are
the day the work was finished, not the day it was tagged.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project versions by roadmap phase rather than by semantic API surface —
it is a study, not a library, and nothing here is imported by anyone else.

## [1.0.0] — 2026-09-12

The evaluation split was opened once and the study answered its own question.
**The hypothesis was not confirmed**, and the release ships that finding with
the machinery that makes it trustworthy.

### The result

- E-001 on the 57-question evaluation split: judge-scored correctness
  **0.60 / 0.61 / 0.65** for vector / graph / hybrid.
- The registered primary analysis — B vs A, exact McNemar, Holm-corrected over
  the four strata with n ≥ 7 — returns **`inconclusive` on all four**, adjusted
  *p* = 1.0000 throughout.
- The direction runs against the thesis: the graph leads on the one-hop
  strata and the **vector baseline leads on `interaction_multihop`**, the
  stratum the hypothesis was written about.
- The distance to significance was computed in August and confirmed in
  September: the test needs 6 discordant pairs one way, the largest
  discordance observed is 5.

### Added

- Live Streamlit demo (`app/`) against Neo4j: a question, the grounded answer,
  and the subgraph that produced it. Hierarchical left-to-right layout, nodes
  ringed when the question named them, Scryfall card images by URL, and a
  report of how much of the retrieved evidence the answer actually cited.
- `scripts/e001_analysis.py` — applies E-001's registered decision rule
  (Holm-corrected exact McNemar, three-valued per-stratum verdict, TOST on the
  declared falsifier) with validity guards that hard-fail before printing.
- `scripts/e010_analysis.py` — E-010 part (a) under its registered rule, with
  a paired cluster bootstrap over questions.
- `scripts/verify_legality_keys.py` — E-001 pin 10, which had been registered
  as mandatory and never implemented: re-verifies every legality answer key
  against the Scryfall bulk the run will read, exiting non-zero on drift.
- `scripts/run_e009.py`, `scripts/run_e010.py`, `scripts/run_e013.py`,
  `scripts/error_taxonomy.py`, `scripts/audit_key_fidelity.py` — the Phase 8
  measurement harnesses.
- README: the result above the fold, an architecture diagram, a limitations
  section, and a three-command reproduction path that spends nothing.

### Changed

- `run_eval.py` accepts the evaluation split behind `--open-the-evaluation-split`
  and a dated journal entry, and its report footers now read from the side
  actually run rather than claiming the development split.
- E-010 part (b) runs on the evaluation split, where it was always registered
  to run, and applies its own 3× budget gate rather than leaving it to be
  remembered.
- Judge published **ungated** (0.727 [0.598, 0.827] against a 0.720 threshold)
  under the registered `sufficiency` precedent, with its ceiling beside it.
- Precision published **unblinded**: the pre-registered blinding check failed
  at 0.778, and a classifier seeing only the *kind* of each evidence item
  reaches 0.722 on held-out slots. The arms return different kinds of
  evidence and that difference is the treatment, so item-level blinding is
  withdrawn as achievable rather than retried.

### Fixed

- `--help` crashed on a cp1252 console; a test now pins every CLI docstring.
- Phoenix's healthcheck used `CMD-SHELL` against a distroless image with no
  `/bin/sh`, which reported identically to the service being down.
- Span `paths` and `evidence.keys` were not index-aligned.
- An arithmetic mismatch in E-010 part (b)'s first write-up: item counts over
  20 questions quoted beside a total over 15.

### Known limitations

Carried deliberately, each with its reason in
[`docs/evaluation.md`](docs/evaluation.md): n = 57 cannot reach the registered
threshold at these effect sizes; the judge is not validated; the retrieval
comparison is budget-confounded at 3.38×; precision was judged by one
annotator, unblinded; `legality_1hop` is unmeasured for precision; E-010's
reliability ceiling has not run.

## [0.8.0] — 2026-09-10 — `v0.8-observability-ci`

OpenTelemetry spans on every pipeline stage with OpenInference span kinds,
Phoenix as viewer, Docker Compose profiles, and CI exercising all three arms
with no API key.

## [0.7.0] — 2026-09-09 — `v0.7-evaluation`

Three-arm evaluation harness, judge, rubric frozen by hash, confidence
intervals, paired tests, and the correctness ceiling.

## [0.6.0] — 2026-08-15 — `v0.6-grounded-generation`

Grounded answering with mandatory citations, refusal when the subgraph carries
nothing, and mechanical detection of fabricated citations.

## [0.5.0] — 2026-08-09 — `v0.5-graph-retrieval`

Named Cypher templates, entity linking, routing, token and per-kind budgets,
and validated Text2Cypher as the long-tail layer.

## [0.4.0] — 2026-08-09 — `v0.4-llm-extraction`

LLM relation extraction behind `extraction/gate.py` — schema, evidence span,
confidence, dedupe — with the metrics that validated it.

## [0.3.0] — 2026-07-19 — `v0.3-graph-backbone`

Neo4j schema, constraints, and idempotent loaders with SHA-256 change
detection.

## [0.2.0] — 2026-07-18 — `v0.2-ontology-and-golden-set`

The explicit ontology and the judge-curated golden set, split 20/57 and
frozen.

## [0.1.0] — untagged

Scaffold, licensing gate G1, and the Comprehensive Rules parser with
golden-file tests.
