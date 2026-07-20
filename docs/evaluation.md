# Evaluation — pre-registration

Source of truth for how this project is measured. Written **before any
retrieval or generation exists**, which is the point: predictions recorded
after seeing results are not predictions.

Results land here in Phase 6. Until then this document fixes what will be
measured, on which questions, and what each stratum is expected to show.

## The claim being tested

From [`hypothesis.md`](hypothesis.md): judge-level Magic rules questions are
not answerable by vector RAG, because the answer is not contained in any one
passage — it is a path between cards, numbered rules and rulings.

That claim is only meaningful if it can fail. Two guards make failure possible:

1. **Strata where the vector baseline should tie or win.** If every stratum
   predicted a graph win, any result would confirm the hypothesis and the
   comparison would be worthless.
2. **A good-faith baseline.** The vector arm reuses Project 1's real pipeline
   over the same corpus, tuned as if we were defending it. A strawman baseline
   would invalidate the comparison more thoroughly than a negative result.

## Why a `tie` stratum is required

`definition_1hop` exists to be losable.

A keyword's effect is written in one self-contained CR passage — "a creature
with flying can't be blocked except by creatures with flying and/or reach"
lives entirely inside rule 702.9. There is no traversal to perform. A passage
retriever should find it as readily as a graph edge, and if the graph somehow
"wins" here, that is evidence of a measurement artifact, not of graph
superiority.

This matters because of what the golden set looked like before it existed. The
Phase 1 annotation pass left every stratum predicting `lose` or `fail`: a
uniform prediction that the graph wins everywhere. Any run would have
"confirmed" the hypothesis. The stratum was filled in Phase 2 from the parsed
CR glossary (issue #6) specifically to restore the possibility of being wrong.

The expected shape of the result is therefore **not** a clean sweep. It is:
parity on definitions, a modest edge on structured lookups, and a widening
margin as hops increase. A clean sweep would be a reason to distrust the
harness.

## A-priori predictions

Recorded before any run. `tie` — the answer is stated in one passage, both
retrievers should find it. `lose` — the graph edge is cleaner but text could
work. `fail` — the answer is a path no single passage states.

| Stratum | Questions | Hops | Prediction | Why |
|---|---:|---|---|---|
| `definition_1hop` | 15 | 1 | **tie** | The keyword's rule states the effect outright |
| `legality_1hop` | 20 | 1 | lose | Structured metadata; prose signal is weak and rotates |
| `keyword_rule_2hop` | 3 | 2 | lose | Keyword to rule to sub-rule; text can sometimes carry it |
| `rulings_2hop` | 0 | 2 | lose | *Deferred to Phase 3: its path runs through `CITES_RULE`, and 1 of 77,999 rulings cites a rule number, so the edge is entirely an LLM target* |
| `interaction_multihop` | 30 | 3+ | fail | Composition of two or more effects; stated nowhere |
| `negative_temporal` | 9 | 2–3 | fail | Turns on something **not** happening, or on ordering |

Current totals: **77 questions, all verified** — 39 `fail`, 23 `lose`,
15 `tie`. Every CR citation (95) resolves against the parsed rules, enforced
by `scripts/check_cr_citations.py`.

## Metrics

Layered deliberately, so "the graph retrieved the right context" and "the LLM
reasoned correctly over it" never collapse into one number. Judge-level
questions require reasoning *about* retrieved rules; conflating the two is how
a project over-claims.

**Retrieval** (per question, stratified by hops and difficulty)
- *Entity Recall* — gold entities present in the retrieved subgraph.
- *Path Recall* — is the gold path contained in the subgraph? (binary)
- *Context Precision* — fraction of the subgraph that is relevant.
- *Context Sufficiency* — could a human answer from this context alone?
  Separates retrieval failure from reasoning failure.

**Answer**
- *Answer Correctness* against the answer key, via LLM-as-judge with a
  versioned rubric plus manual audit of 20% (judge–human agreement reported).
- *Faithfulness* — claims supported by the retrieved context, including a
  parametric-leakage test with fictional cards injected into the graph. Models
  know Magic; this measures whether the answer came from the graph or from
  memory.
- *Citation Precision* — citations that actually support the sentence.

**Extraction** (Phase 3, reported here) — linking and relation P/R/F1 against
manual annotations, stratified by difficulty. The number that matters is the
tail (homonyms, implicit references), not the easy majority.

**Calibration** (Phase 6) — the same machinery run on MetaQA, so "the pipeline
works" is separable from "the domain is hard".

**Operational** — p50/p95 latency per stage from OTel spans, and token cost per
question, for both systems.

## Reporting rules

- Results are published **including where the graph loses**. The limitations
  section is mandatory, not optional.
- Any stratum whose outcome contradicts its prediction gets a written analysis,
  not a quiet edit to the prediction.
- The whole report must be reproducible with one command.
