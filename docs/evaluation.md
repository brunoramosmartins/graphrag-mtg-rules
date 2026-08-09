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
| `rulings_2hop` | 0 | 2 | lose | *Deferred to Phase 3: its path runs through `CITES_RULE`, and only 25 of 77,999 rulings (3 cards) cite a rule number, so the edge is in practice an LLM target* |
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

## Extraction cost model (Phase 3)

Nothing runs on the full corpus before its cost is projected from a sample
(`scripts/extraction_cost_report.py`, `--sample N`, chars/4 token heuristic).
The pipeline is up to two LLM calls per ruling: **disambiguation** (only for the
24.8% of rulings carrying a single-word homonym) and **citation** (every
ruling). Projected over all 77,999 rulings, seed 20260720:

| Mode | $/1000 rulings | Full corpus (gpt-4o-mini) | Full corpus (Opus 4.8) |
|---|---|---|---|
| open | $0.29 | ~$23 | ~$2,700 |
| grounded | $0.59 | ~$46 | ~$5,000 |

Two decisions fall out of the numbers, not taste:

1. **Model choice is ~100×.** The corpus run uses `gpt-4o-mini`; a frontier
   model is reserved for spot re-runs where the annotation shows it is needed.
2. **Grounded mode costs ~2×** — the CR chapter map + keyword directory in the
   system prompt is ~2,375 input tokens/call versus ~364 open. That premium is
   only spent if the annotation-measured F1 justifies it (see the round-by-round
   log in `notes/phase3-extraction.md`); grounding is not assumed to win, it has
   to earn its cost.

Numbers are budgeting ceilings, refreshed against measured token counts once a
full run exists.

## Reporting rules

- Results are published **including where the graph loses**. The limitations
  section is mandatory, not optional.
- Any stratum whose outcome contradicts its prediction gets a written analysis,
  not a quiet edit to the prediction.
- The whole report must be reproducible with one command.

---

# Results — E-003, extraction quality (2026-08-09)

Reproduce with:

```bash
python -m graphrag_mtg.extraction.pipeline --ids data/golden/extraction_sample_ids.json --split annotation --grounded --yes --out data/interim/gated_triples.annotation.jsonl
```

```bash
python scripts/eval_extraction.py --split annotation --gated data/interim/gated_triples.annotation.jsonl
```

Configuration: linker cascade v2, citation prompt v3 with the keyword
directory, grounded mode, gate `min_confidence = 0.7`, temperature 0,
`gpt-4o-mini`. Gold: 125 rulings, hand-annotated, CR 2026-08-07. Scored on
gate-passing edges only — what would actually enter the graph. Micro P/R/F1
with per-document bootstrap CIs. **Figures below are pre-adjudication**, which
is the headline figure under the E-003 adjudication rule.

## Both thresholds fail

| Task | F1 | 95% CI | Threshold | Verdict |
|---|---|---|---|---|
| Card-mention linking | **0.634** | [0.491, 0.750] | ≥ 0.90 | **fail** |
| Rule citations (primary) | **0.125** | [0.073, 0.180] | ≥ 0.75 | **fail** |
| Rule citations (family, secondary) | 0.252 | [0.188, 0.323] | — | diagnosis |

Linking: tp=26, fp=26, fn=4. Citations: tp=19, fp=121, fn=146.

The two failures are not the same kind. Linking **finds** what it should —
recall 0.867 [0.737, 0.973] — and emits an equal quantity of things it should
not: precision 0.500. Citations fail on both sides at once, and the interval
does not come within 0.5 of the threshold. No amount of tuning closes that gap;
it is the wrong instrument for the task.

## By stratum

| Stratum | Linking F1 | Citation F1 |
|---|---|---|
| multiword (40) | 0.760 [0.611, 0.871] | 0.140 [0.042, 0.246] |
| homonym (50) | 0.438 [0.138, 0.667] | 0.132 [0.053, 0.226] |
| plain (30) | — (no gold mentions) | 0.054 [0.000, 0.137] |
| explicit (5) | — (no gold mentions) | 0.400 [0.000, 0.727] |

## Against the a-priori predictions

- **"Deterministic stages near ceiling on multiword (F1 ≥ 0.95)" — falsified.**
  Multiword linking reached 0.760, and the interval's upper bound (0.871) sits
  below the predicted floor. Exact name matching is not the solved problem the
  prediction assumed: the failures are card names used as ordinary words and
  names embedded in longer names, neither of which a lexicon settles.
- **"The homonym stratum is the open question and predicted hardest" —
  confirmed.** Homonym linking F1 0.438 against multiword's 0.760, and its
  precision (0.304) carries 16 of the 26 false positives.
- **"`CITES_RULE` F1 below linking F1" — confirmed**, by a wider margin than
  anticipated: 0.125 against 0.634.
- The `explicit` stratum is the one place citations work at all (F1 0.400 on 5
  rulings, interval far too wide to lean on). Those are the rulings that state
  a rule number in their own text, so the model is reading rather than
  inferring — which is precisely the distinction the whole task turns on.

## What this means, and what it does not

Gate **G3 fires on the pre-registered rule**: citation F1 is below the 0.5
infeasibility line after three documented prompt iterations, so the schema is
reduced and the negative result reported rather than tuned toward. `CITES_RULE`
by a single grounded LLM call does not reach production quality and should not
be loaded into the graph as though it did.

This is a result about **one mechanism**, not about the thesis. The CR tree,
its explicit cross-references, and the card–ruling backbone remain
deterministic and unaffected. What Phase 3 establishes is the boundary: the
deterministic parser reaches further than expected, and LLM inference of a
*governing* rule — a rule the ruling never names — reaches much less far.

## Limitations, stated because they bound every number above

- **The ceiling is measured, and it does not explain the result (E-003a).** A
  single annotator produced all 125 rulings, so the reliability of the gold
  bounds every citation number above. Measured 2026-08-09: 20 rulings drawn at
  seed `20260809`, re-cited into a blinded copy with the same tools, scored
  with the same metric (`scripts/reannotate.py`). Agreement **F1 0.815 [0.679,
  0.938]** primary, **0.902 [0.800, 0.980]** family; 14 of 20 rulings cited
  identically (0.70 [0.48, 0.85]). The citation F1 of 0.125 is therefore not
  attributable to an unreliable gold — that would require the annotator to
  disagree with themself about seven times out of eight. Reported beside the
  result, **not** used to rescale it. Two caveats bound the ceiling itself: the
  second pass was written the same day, so memory inflates it, and 20 rulings
  give a wide interval. Neither is close to large enough to change the reading.
- **The ceiling is not 1.0, and the gap between 0.815 and 0.902 says where it
  goes.** Of the 6 rulings the two passes cited differently, 3 differ only in
  granularity (parent versus child, or sibling subrules), 2 differ by one pass
  citing an additional rule without contradicting the other, and 1 is a genuine
  conflict. Choosing the leaf is the interpretive part of this task; choosing
  the area is not.
- **The gap is model error, not a metric artifact and not gold error
  (E-003b).** Exact match scores a wrong rule and a differently defensible rule
  identically, so 0.125 was consistent with several different failures. A
  seeded sample of 40 disagreements over 33 rulings (seed `20260810`) was
  classified by the annotator: **40/40 `gold_right`**, 0 `both_defensible`, 0
  `gold_wrong`, 0 `unclear`. The registered prediction — that
  `both_defensible` would be the largest bucket after `gold_right` — is
  falsified. The bound is rule-of-three, not the bootstrap interval, which is
  degenerate on a unanimous sample: everything other than model error is at
  most **0.091** (95%, over 33 clusters). No gold label changed, and the 10%
  adjudication cap was never approached.
- **E-003b's judge wrote the gold, and that bounds it.** Unanimity in one's own
  favour is what a lenient self-judge produces, and this design cannot tell
  that apart from correctness. The measurable asymmetry: 9 of the 40 cases are
  a wrong *leaf* rather than a wrong rule (`608.2` for gold `608.2b`, `704.5g`
  for `704.5d`/`704.5f`, sibling subrules of `702.131`, `702.33`, `702.179`,
  `701.54`), and E-003a found exactly that to be the annotator's commonest
  disagreement with themself — yet all 9 were judged model error. The family
  score already prices full depth leniency, and reads 0.252 against a family
  ceiling of 0.902, so the conclusion survives the objection; an independent
  judge, not a larger sample, is what would settle it.
- **One failure mode is unsampled.** 13 of 125 rulings produced no citation at
  all (13 of the 267 disagreements); none were drawn into the 40.
- **The CR upgrade is not a confound.** All 125 annotation rows carry
  `cr_version = "August 7, 2026"`, the release the extractor was grounded on,
  and 0 of the 267 disagreements cite a rule absent from that CR — the first
  place version skew would surface.
- **No retrieval was given to the citation extractor.** The obvious remedy —
  feeding it candidate rules, as `cite_search.py` does for the annotator — was
  refused deliberately: that tool helped build the gold, so using it inside the
  system under measurement would make agreement a family resemblance. It is
  registered as future work with its own pre-registration, not folded in here.
- **The dev estimates were optimistic and noisy.** Dev linking read 0.727
  against 0.634 here, and dev citations swung between 0.057 and 0.167 across
  runs of the same configuration before temperature was pinned. Fifteen
  citation-annotated dev rulings cannot separate a treatment from noise; the
  125-ruling intervals above are the ones to read.
- **The three prompt iterations are unattributable** and are not claimed as
  improvements — they ran before temperature was pinned.
