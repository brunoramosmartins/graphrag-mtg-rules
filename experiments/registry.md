# Experiment Registry

Every experiment is registered **before** it runs: ID, objective,
hypothesis, configuration, decision rule, expected result. The actual
result is filled in afterwards and never edits the prediction. Entries
for work that predates this registry carry an explicit
`registered: retrospectively` field; the registry is forward-looking
from 2026-07-19 on.

Metric reporting rules (binding, see [../docs/evaluation.md](../docs/evaluation.md)):
confidence intervals always, paired tests for paired comparisons, a
multiple-comparison correction when strata are tested jointly.

---

## E-001 — Graph traversal vs. vector baseline on the golden set

- **Registered:** 2026-07-19 (a priori — predictions were recorded in
  [../docs/evaluation.md](../docs/evaluation.md) and
  `data/golden/*.jsonl` before any retrieval system existed).
- **Objective:** test the central hypothesis
  ([../docs/hypothesis.md](../docs/hypothesis.md)) that judge-level
  questions are path-shaped and measurably out of reach of vector
  retrieval.
- **Hypothesis / predictions:** per-question `vector_should` labels —
  39 fail / 23 lose / 15 tie across 77 questions. The `tie` stratum
  (`definition_1hop`) is the falsifier: if the graph "wins" there too,
  distrust the harness before celebrating.
- **Configuration:** frozen golden set v0 (77 questions, all
  verified); graph pipeline (Phases 4–5) vs. the Project 1 vector
  pipeline over the same textual corpus. Details to be pinned in this
  entry before the first run.
- **Decision rule:** per-stratum comparison with CIs and paired
  tests; the hypothesis survives only if the observed pattern matches
  the predicted stratification, not merely if the aggregate favors
  the graph.
- **Expected result:** graph ≫ vector on `fail`, graph > vector on
  `lose`, no significant difference on `tie`.
- **Actual result:** _pending (Phase 8)._

## E-002 — MetaQA calibration

- **Registered:** _not yet — to be registered with full configuration
  before the first calibration run (Phase 6)._
- **Objective (declared intent only):** run the same machinery on an
  academic multi-hop benchmark with an answer key, to separate "the
  pipeline works" from "the domain is hard" before any claim on MTG.

## E-003 — Extraction gate quality (Phase 3)

- **Registered:** _not yet — to be registered together with the
  annotation of ~100–120 rulings, before `extractor.py` runs on
  them._
- **Objective (declared intent only):** measure precision/recall of
  LLM-extracted relations against manual annotations; only
  gate-passing edges enter the graph.
