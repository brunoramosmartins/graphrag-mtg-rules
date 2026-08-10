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
- **Amendment 2026-08-09 (before Phase 4 writes a single traversal, no
  retrieval result seen) — development split.** Phase 4 would otherwise write
  its templates against the same 77 questions E-001 measures on, which is
  fitting the retriever to the test set. **20 questions** (seed `20260809`,
  stratified proportionally) are frozen as the Phase 4 development subset in
  `data/golden/phase4_dev_ids.json`; the remaining **57** are the evaluation
  set and are touched once, in Phase 6. `scripts/split_golden.py` refuses to
  redraw. Consequence stated rather than hidden: `keyword_rule_2hop` holds 3
  questions in total, so the split leaves 1 dev and 2 evaluation and **no
  per-stratum claim about it is reportable from either side**.
- **Amendment 2026-08-09 (same, before any run) — three arms.** ADR-006
  removed the ruling→rule bridge and ADR-007 answers with a hybrid, so the
  "graph pipeline" of the original design no longer names one thing. A hybrid
  measured only against the vector baseline could win entirely on its text
  component — the Project 1 pipeline wearing a different hat — and be
  presented as evidence about the graph. E-001 therefore runs:
  | arm | what it is | what it tests |
  |---|---|---|
  | **A** | vector baseline (Project 1 pipeline, same corpus) | control |
  | **B** | graph-only traversal | the thesis in `docs/hypothesis.md` |
  | **C** | hybrid (ADR-007) | the shipped system |
  **B vs A is the registered prediction above and is not renegotiated.**
  C vs A is the product; C vs B isolates the text contribution. Three arms
  across five strata require the multiple-comparison correction this registry
  already mandates, and paired tests over the shared question set.
- **Interim evidence recorded 2026-08-09, no decision taken from it:**
  `scripts/reachability.py` measured deterministic reachability of gold rules
  from gold entities — 100% at k=2 on `definition_1hop` and
  `keyword_rule_2hop`; 38% only at k=6 on `interaction_multihop`, where the
  ball holds 1515 of 3308 rules, and 15 of those 30 questions produce no seed
  at all (their cards have no keyword abilities). This makes prediction 2
  look unlikely **for arm B**. The prediction stands as written and is scored
  as written in Phase 6; it is not amended to match evidence that arrived
  after it.
- **Actual result:** _pending (Phase 8)._

## E-002 — MetaQA calibration

- **Registered:** _not yet — to be registered with full configuration
  before the first calibration run (Phase 6)._
- **Objective (declared intent only):** run the same machinery on an
  academic multi-hop benchmark with an answer key, to separate "the
  pipeline works" from "the domain is hard" before any claim on MTG.

## E-003 — Linking and extraction quality against manual annotations

- **Registered:** 2026-07-20 (a priori — the sample froze first at seed
  `20260720` in `data/golden/extraction_sample_ids.json`; no extractor
  has run on either split, and the annotation labels do not exist yet).
- **Objective:** measure card-mention linking and `CITES_RULE`
  extraction P/R/F1 against 125 manually annotated rulings; only
  gate-passing edges ever enter the graph.
- **Configuration:** frozen sample 30 dev / 125 annotation (strata:
  homonym 60, multiword 50, plain 40, explicit 5); linker cascade v1
  (exact → loose → surface + LLM disambiguation); extractor v1 (open
  and grounded modes); gate `min_confidence = 0.7`; metrics = micro
  P/R/F1 with per-document bootstrap CIs (`evaluation/metrics.py`),
  stratified by sampling stratum. Model pinned in the run log at run
  time.
- **Blinding rule:** annotation labels are written without ever running
  the extractor on the annotation split; prompt iteration happens on
  the dev split only. The annotation split is touched by the system
  exactly once, after `check_extraction_annotations.py --publish`.
- **Hypothesis / predictions:** deterministic stages near ceiling on
  the multiword stratum (F1 ≥ 0.95); the homonym stratum is the open
  question and predicted hardest; `CITES_RULE` F1 predicted below
  linking F1. Pass thresholds (roadmap DoD): linking F1 ≥ 0.9 overall,
  `CITES_RULE` F1 ≥ 0.75.
- **Decision rule (gate G3, week 1, on the dev split):** trivial
  (F1 > 0.95 with no prompt effort) → shift Phase 3 weight to implicit
  CR cross-references; infeasible (F1 < 0.5 after 3 documented prompt
  iterations) → reduce the schema and report the negative result.
  Threshold changes after seeing annotation-split results are not
  permitted; any adjustment needs a dated decision-journal entry
  *before* the run it applies to.
- **Amendment 2026-08-08 (before the run, no results seen):** the CR
  corpus moved from the 2026-02-27 release to 2026-08-07, because the
  rulings snapshot (2026-07-17) was newer than the CR and some rulings
  cited rules absent from it. Labels were migrated by rule text via
  `scripts/cr_migrate.py` (71 of 79 cited rules unchanged, 4 relocated,
  4 edited without semantic change, 0 orphaned) and every row now carries
  `cr_version`. No threshold, sample, cascade, or metric changed; the
  annotation split still has not been touched by the extractor. Rationale
  in `docs/decision-journal.md` (2026-08-08).
- **Secondary metric added 2026-08-08, after the first dev run, before the
  annotation split was touched:** citations are also scored on
  `(ruling_id, rule_family)`, where `rule_family` drops the trailing subrule
  letter (`702.33d` → `702.33`). The first dev run showed the extractor
  routinely naming the right rule at the wrong depth — gold `608.2b`, predicted
  `608.2` — which exact match counts twice against, as a false positive and a
  false negative. `(ruling_id, rule_number)` **remains the primary metric and
  the one the E-003 threshold of 0.75 applies to**; the family score is
  reported beside it as diagnosis, never in place of it. Loosening the primary
  key after seeing that the errors are depth errors would be fitting the ruler
  to the result.
- **Prompt-iteration budget, fixed 2026-08-08 (before any run):** citation
  extraction gets at most 3 documented prompt iterations, judged against a
  **15-ruling subset of the dev split** — 5 per dev stratum, chosen with seed
  `20260808` and frozen in `data/golden/dev_citation_subset.json`. The dev split
  carries verified `mentions` for all 30 rulings, so linking iteration is
  unaffected. The subset was drawn before any citation was annotated on it, and
  the annotation split remains untouched. Deliberately a subset, not the whole
  dev split: enough signal to tell two prompts apart, at half the manual cost.
- **Adjudication rule, pre-registered 2026-08-08 (before any run, no results
  seen):** after the annotation-split run, the annotator may inspect the rows
  where the system and the gold disagree. A gold label may be changed **only**
  when it is wrong on its own terms under `docs/extraction-annotation-guide.md`
  — the rule number does not exist, does not govern the question the ruling
  answers, or contradicts the annotator's own note. It may never be changed
  because the model disagrees with it, and never to move a metric. Every change
  is logged in `docs/decision-journal.md` with ruling id, before, after, and
  reason. `docs/evaluation.md` reports **both** the pre-adjudication and the
  post-adjudication figures, and the pre-adjudication figure is the headline.
  If adjudication would touch more than **10% of the gold**, the gold is not
  reliable enough to measure against: the run is void and the sample is
  re-annotated rather than patched.
- **Known limitation, recorded 2026-08-08:** intra-annotator agreement has not
  been measured — the annotator has not blind-re-annotated a subsample. The
  reliability of the gold is therefore unquantified and the attainable ceiling
  on F1 is unknown. `docs/evaluation.md` must state this beside the results.
  Deferred by the author, not overlooked.
- **Iterations spent (dev only, 2026-08-08):** 3 of 3. (1) removed the "cite the
  parent you are sure of" fallback: 0.054 → 0.118. (2) dropped the keyword
  directory and added three-step reasoning: 0.118 → 0.000. (3) restored the
  directory, kept the reasoning: **0.167 [0.000, 0.333]** primary, 0.312
  [0.121, 0.529] family. Best configuration: prompt `v3` with the keyword
  directory. Linking unchanged throughout at 0.706 [0.444, 0.868].
- **Gate G3, decided 2026-08-08 on the dev split:** citation F1 0.167 after three
  documented iterations is below the 0.5 infeasibility line, so the registered
  rule applies — reduce the schema and report the negative result. The
  annotation-split run still happens, to report that negative with the sample
  and intervals it was registered for, and to measure linking.
- **Amendment 2026-08-09 (dev only; annotation split still untouched):** two
  defects found while diagnosing linking. (1) `LlmClient` set no `temperature`,
  so no run was reproducible — the same configuration scored citation F1 0.167
  and 0.114 on consecutive runs, a spread the size of the iteration effects.
  Temperature is now pinned to 0 and **the three prompt iterations are retired
  as unattributable**; the reproducible figure for the best configuration is
  citation F1 **0.057 [0.000, 0.176]** primary, **0.250 [0.067, 0.437]** family.
  G3's infeasibility call stands and is firmer. (2) Linker cascade v1 → **v2**:
  a match strictly inside a longer occurrence of the host card's name is
  dropped ("Legion" inside "Kemba's Legion"), lifting linking F1 to **0.727
  [0.476, 0.889]**, tp=12 fp=6 fn=3. Broader forms of the rule, and a
  type/keyword stoplist, were measured against the dev gold and rejected — both
  cost as many true positives as they won. The annotation-split run will use
  cascade v2, prompt v3 with the keyword directory, temperature 0.
- **Actual result (2026-08-09, annotation split, single run, pre-adjudication):**
  linking F1 **0.634 [0.491, 0.750]** (tp=26 fp=26 fn=4) against a 0.90
  threshold — **fail**; citation F1 **0.125 [0.073, 0.180]** (tp=19 fp=121
  fn=146) against 0.75 — **fail**; citation family F1 0.252 [0.188, 0.323].
  Predictions: multiword-at-ceiling **falsified** (0.760, upper bound 0.871
  below the predicted 0.95 floor); homonym-hardest **confirmed** (0.438, and 16
  of 26 linking false positives); citations-below-linking **confirmed** (0.125
  vs 0.634). G3 fires: reduce the schema, report the negative. Full write-up
  with limitations in `docs/evaluation.md`.

### E-003a — intra-annotator agreement (the ceiling)

- **Registered:** 2026-08-09, before the second pass is written. Closes the
  known limitation recorded 2026-08-08.
- **Objective:** measure how much the annotator agrees with themself, so the
  E-003 citation F1 can be read against a ceiling instead of against 1.0. If a
  second blind pass over the same rulings cites different rules, the task is
  ambiguous and no system could have scored higher.
- **Configuration:** 20 rulings drawn from the citation-reviewed rows of the
  annotation split, stratified proportionally, seed `20260809`, frozen in
  `data/golden/reannotation_sample_ids.json`. Pass 2 is written into a blinded
  copy (`scripts/reannotate.py draw`) carrying the ruling text and mentions but
  no `cited_rules`, using the same tools as pass 1 (`cite_search.py`,
  `annotation_worksheet.py --citation-pass`, `cite.py`) — a different tool would
  measure the tool, not the annotator. Metric: the E-003 citation metric
  unchanged, micro P/R/F1 on `(ruling_id, rule_number)` with per-document
  bootstrap CIs, pass 1 as reference; family score reported beside it. Micro F1
  is symmetric, so the direction is presentational only.
- **Ordering constraint (binding):** pass 2 must be written **before** the
  annotator inspects any E-003 disagreement (E-003b). Re-reading rulings that
  were just re-litigated against the model's output is recall, not an
  independent second pass.
- **Hypothesis / prediction:** agreement F1 well below 1.0 and well above the
  measured 0.125 — the author's stated reason is that two rules can both
  support a ruling. No threshold: this is a measurement, not a test.
- **Use and non-use:** the figure is reported in `docs/evaluation.md` beside the
  E-003 result and replaces the "agreement unmeasured" limitation. It does
  **not** license changing any gold label, does not change the E-003 thresholds,
  and is not used to rescale any reported score.
- **Known limitation:** the rulings were annotated in the days before the draw,
  so memory inflates agreement; the figure is an optimistic bound on the
  ceiling. `reannotate.py compare` prints the elapsed days and says so.
- **Actual result (2026-08-09, 20 rulings, same-day second pass):** citation
  agreement F1 **0.815 [0.679, 0.938]** primary, **0.902 [0.800, 0.980]**
  family; tp=22 fp=5 fn=5; 14 of 20 rulings cited identically (0.70 [0.48,
  0.85], Wilson). No decision rule applies — E-003a was registered as a
  measurement, not a test, so this section is descriptive by construction and
  no branch is taken. Reproducible from `scripts/reannotate.py compare`, which
  refuses to report on a partial second pass.
  **What it settles:** the gold is not the explanation for E-003's citation
  score. For annotator unreliability to account for F1 0.125, the annotator
  would have to agree with themself at roughly that rate; the measured
  agreement is 0.815, and the same-day inflation would have to be worth ~0.69
  of F1 for the two to meet. Per the registration, the ceiling is reported
  beside the result and is **not** used to rescale it.
  **Structure of the disagreement** (all 6 divergent rulings, read from the
  compare output): 3 are granularity — parent versus child (`303.4a`/`303.4`,
  `706.2b` dropped with `706.2` kept) or sibling leaves (`603.7b`/`603.7c`);
  2 are completeness — the second pass adds a rule the first did not cite
  (`601.2c`, `702.174a`) without contradicting it; 1 is a genuine conflict with
  no overlap (`709.4` vs `202.3d`). This is what the 0.815/0.902 gap is made
  of, and it is the same failure the family metric was added to separate.

### E-003 — schema reduction executed (2026-08-09)

G3's registered consequence is done. `CITES_RULE` is deterministic:
`extraction/explicit_citations.py` reads rule numbers the ruling states, and
`gate.gate_candidates(require_explicit_citations=True)` — the ship default —
rejects everything inferred as `citation_not_explicit`. The rule lives in the
gate rather than in the prompt or the caller, so it holds for future callers
too; E-003 is the measurement of what the same guarantee is worth in a prompt.
E-003 stays reproducible via `--llm-citations --legacy-citation-gate`, which
the CLI refuses to combine with `--load`.

Measured consequences on the same 125 annotated rulings, **descriptive, not a
new test** — the reduction was mandated by a rule fixed on 2026-07-20 and the
figures below are worse, not better:

- citations overall F1 **0.047** (tp=4 fp=2 fn=161), down from 0.125;
- on the `explicit` stratum P 0.667 / R 0.800 / F1 **0.727 [0.222, 1.000]**;
- 6 gated citation edges over 125 rulings.

**New limitation the reduction introduces:** ruling text carries rule numbers
that go stale and cannot be migrated. One `explicit` false positive is a ruling
stating "(704.5w)" where the August 2026 CR moved that state-based action to
`704.5x` and reused `704.5w`. The number still resolves, so no existence check
catches it. `scripts/cr_migrate.py` can migrate the gold; it cannot migrate a
historical document.

### E-006 — retrieval reach on the Phase 4 development split

- **Registered:** 2026-08-09, before the first end-to-end run. The Phase 4
  DoD carries a threshold, and a threshold recorded after the number exists
  is not a threshold.
- **Objective:** does the shipped retrieval stack put the things a question
  needs into the subgraph? Preliminary only — the official comparison is
  E-001 in Phase 6, and this never touches its 57 evaluation questions.
- **Two metrics, kept apart because they are different claims:**
  - **Entity recall** — the share of a question's `gold_entities` that
    appear as evidence keys in the retrieved subgraph, matched on
    normalized name. This is what the DoD's threshold applies to.
  - **Rule recall** — the share of its `gold_cr_rules` that appear.
    Reported beside it, never merged into it: reaching *Humility* and
    reaching *613.4b* are not interchangeable achievements, and averaging
    them would let the easy one hide the hard one.
- **Configuration:** the 20 questions of `data/golden/phase4_dev_ids.json`;
  `QueryLinker` -> `router.plan` -> template traversals -> `rule_search`
  where the plan says so -> `Subgraph` with its default budget and caps;
  live Neo4j with the full corpus loaded. Reported per stratum with
  bootstrap intervals over questions.
- **Decision rule (from the roadmap DoD, not invented here):** entity
  recall **≥ 0.9 on the 1–2 hop strata** (`definition_1hop`,
  `keyword_rule_2hop`, `legality_1hop`). Below that, the templates are
  wrong before anything downstream is worth building. `interaction_multihop`
  is **excluded from the threshold** — the roadmap scoped it to 1–2 hops,
  and reachability plus `eval_rule_search` have already measured that
  stratum as out of reach for both halves.
- **Prediction, recorded before the run:** the 1–2 hop strata clear 0.9,
  because reachability found 100% of their gold rules at two hops inside
  small balls, and the traversals for them are a single typed edge or a
  single `DEFINED_BY` hop. `interaction_multihop` entity recall is high
  (its cards resolve) while its **rule** recall stays near the 2 of 8 that
  `eval_rule_search.py` measured. If entity recall on the 1–2 hop strata
  comes back low, suspect the harness before the templates.
- **Also collected, not a criterion:** wall-clock per question, to check
  the DoD's p95 < 2 s. Informal timing of the eight traversals already
  ranged 9–685 ms.
- **Actual result (2026-08-09, 20 development questions):**

  | stratum | entity recall | rule recall | n |
  |---|---|---|---|
  | `definition_1hop` | 1.00 | 1.00 | 4 |
  | `legality_1hop` | 1.00 | n/a | 5 |
  | `keyword_rule_2hop` | 0.67 | 1.00 | 1 |
  | `negative_temporal` | 1.00 | 0.25 | 2 |
  | `interaction_multihop` | 0.69 | **0.06** | 8 |

  **1–2 hop entity recall 0.967** over 10 questions against the 0.9 floor —
  **PASS**. Outcomes: 19 resolved, 1 ambiguous, **0 silent**; every question
  produced a subgraph or a named failure. Latency median 0.12 s, p95 0.57 s
  against the 2 s criterion. n=10 on the threshold, so this is a smoke test
  and not E-001.

  **The registered prediction held, including its warning.** It said to
  suspect the harness before the templates if the 1–2 hop strata came back
  low. The first run returned **0.067**, and both causes were harness bugs
  found only because that instruction was written down:
  1. the router passed `Keyword.display_name` ("Trample") where the graph
     keys on the normalized `name` ("trample"), so every `definition_1hop`
     question returned `NO_MATCH`;
  2. `card_legality` was never wired into the router at all, and no
     traversal emitted the *card* as evidence, so `legality_1hop` scored 0
     on questions the graph answers with one typed edge.

  Both were fixed and the measurement re-run; the 0.067 figure belongs to
  a broken harness and is recorded here rather than quietly discarded.

  `interaction_multihop` rule recall of **0.06** is consistent with the two
  independent measurements that preceded it — `reachability.py` (graph) and
  `eval_rule_search.py` (text, 2 of 8). Three methods now agree that this
  stratum is out of reach, which is the Phase 4 finding rather than a
  defect left to fix.

- **Third run, 2026-08-09, after a lexicon fix.** All three runs are kept:
  a number that moved because a defect was fixed says more than the final
  number alone.

  | run | 1–2 hop entity recall | what changed |
  |---|---|---|
  | 1 | 0.067 — FAIL | broken harness (keyword casing, legality unwired) |
  | 2 | 0.967 — PASS | both harness bugs fixed |
  | 3 | **1.000 — PASS** | query lexicon excludes non-rules layouts |

  Run 3, full: `definition_1hop` 1.00/1.00, `legality_1hop` 1.00/n/a,
  `keyword_rule_2hop` 1.00/1.00, `negative_temporal` 1.00/0.25,
  `interaction_multihop` **0.88 entity / 0.12 rule**. All 20 questions
  resolved, none ambiguous, latency p95 0.53 s.

  The fix: 2,196 multi-word card names resolved to more than one
  `oracle_id`, and **2,116 of those collisions are `art_series` prints**
  (collectible cards named "X // X" whose faces normalize onto the real
  card) with 80 more from tokens. Neither is a rules entity. Filtering
  those layouts out of the query lexicon drops collisions to 25 of 33,448,
  and the ambiguous question disappears. `build_card_lexicon` does the
  filtering at the retrieval call site, **not** inside `Lexicon.build`,
  because that constructor is what E-003 measured.

- **Hypothesis for E-005, generated here and not acted on:** the Phase 3
  ingestion linker used the *unfiltered* lexicon, so those same 2,196
  collisions would have pushed real multi-word card names into the pending
  homonym path and on to LLM disambiguation. That is a plausible
  contributor to multiword linking F1 landing at 0.760 against a predicted
  0.95, and to the precision of the LLM stage. It is **not** a correction
  to E-003: that split is spent, its figure stands as reported, and this
  belongs to E-005 with a fresh sample.

### E-005 — linking precision (registered 2026-08-09, not yet run)

- **Objective:** E-003 measured linking F1 0.634 [0.491, 0.750] against a 0.90
  threshold — fail — with precision 0.500 and 16 of 26 false positives in the
  homonym stratum. E-005 asks what to change.
- **Hypotheses, generated post hoc from the annotation split and therefore
  requiring a fresh sample:**
  1. *The LLM homonym disambiguation costs more than it earns.* Observed in
     passing while dry-running the reduced pipeline: deterministic stages alone
     score linking F1 0.677 (tp=22 fp=13 fn=8) where the full cascade scored
     0.634 (tp=26 fp=26 fn=4) — the LLM stage bought 4 true positives for 13
     false ones. **This must not be acted on from this observation.** The split
     is spent; choosing a cascade because it scores better on the data that
     measured it is fitting to the test set, which is the failure this registry
     exists to prevent.
  2. *The reported figure is optimistic for the corpus.* The sample fixes
     homonym 50 / multiword 40 / plain 30 / explicit 5, while the corpus counts
     are homonym 17,808 / multiword 6,166 / plain 53,850 / explicit 25
     (`data/golden/extraction_sample_ids.json`). The corpus over-weights the
     stratum that scores worst, so a reweighted estimate should read *below*
     0.634. The registered figure remains 0.634; a reweighted estimate is a
     separate, labelled quantity and needs its bootstrap redone under the
     weights.
- **Design requirement:** a fresh annotation sample with its own seed. Neither
  hypothesis may be tested on the E-003 annotation split.
- **Actual result:** _not run._

### E-003b — composition of the E-003 disagreements

- **Registered:** 2026-08-09, before any disagreement is inspected.
- **Objective:** decompose the citation F1 gap. Exact match scores a wrong rule
  and a *differently defensible* rule identically, so 0.125 is consistent with
  several different worlds and by itself names none of them.
- **Configuration:** a seeded random sample of the annotation-split
  disagreements (false positives and false negatives) from the recorded E-003
  run, sized so each proportion below carries a usable interval. Each sampled
  disagreement is classified into exactly one bucket:
  - `gold_right` — the gold is correct and the prediction is wrong: model error.
  - `both_defensible` — the predicted rule also governs the interaction: an
    artifact of exact match, neither a model error nor a gold error.
  - `gold_wrong` — the gold is wrong on its own terms under
    `docs/extraction-annotation-guide.md`: adjudicable.
  - `unclear` — parked, and counted, rather than forced into a bucket.
- **Reported as:** the four proportions with confidence intervals. Not an F1,
  and not a correction to one.
- **Relation to adjudication (important):** this is measurement, not repair. It
  changes no gold label. A sample cannot patch the gold — a partly-patched gold
  makes both the pre- and post-adjudication figures meaningless — so the
  pre-registered adjudication rule (2026-08-08) continues to govern any change,
  including its 10% cap and its requirement that a label be wrong on its own
  terms. If `gold_wrong` comes back high, the honest response is the one that
  rule already names: void and re-annotate, not patch.
- **Hypothesis / prediction:** `both_defensible` is the largest bucket after
  `gold_right`, and `gold_wrong` is small. Recorded before any case is read.
- **Note 2026-08-09, prediction deliberately NOT amended:** E-003a landed first
  and is weak evidence against the prediction above — of the annotator's own 6
  divergences, only 1 was a genuine conflict between two different rules, the
  rest being granularity or completeness. That is evidence about one person
  disagreeing with themself, not about a model disagreeing with a person, and
  in any case a prediction edited after seeing adjacent data is not a
  prediction. It stands as written and will be scored as written.
- **Actual result (2026-08-09, 40 cases over 33 rulings, seed `20260810`):**
  `gold_right` **40/40**; `both_defensible` 0; `gold_wrong` 0; `unclear` 0.
  Composition by direction: 16 false positives and 24 false negatives, all
  `gold_right`. **The registered prediction is falsified** — `both_defensible`
  was predicted to be the largest bucket after `gold_right` and is empty.
  - **Interval:** the cluster bootstrap prints `[1.000, 1.000]`, which is
    degenerate, not certain — a percentile bootstrap on a sample with no
    variation resamples to itself. The reportable bound is rule-of-three over
    33 clusters: everything other than `gold_right` is at most **0.091** (95%).
    `report` now detects unanimity and prints this instead of the false
    interval; `metrics.rule_of_three_upper` is the shared implementation.
  - **What it settles:** the citation gap is model error. It is not a metric
    artifact (`both_defensible` = 0) and not gold error (`gold_wrong` = 0, so
    the 10% adjudication cap is not approached and no label changes). Together
    with E-003a's ceiling of 0.815, both alternative explanations for F1 0.125
    are now measured and excluded.
- **Threat to validity, recorded because it is not resolved by more sampling:**
  the judge wrote the gold. Unanimity in one's own favour is exactly what a
  lenient self-judge produces, and it cannot be distinguished from correctness
  by this design. A concrete asymmetry is measurable and is now printed by
  `report`: **9 of the 40 cases are a wrong leaf rather than a wrong rule**
  (`608.2` against gold `608.2b`, `704.5g` against gold `704.5d`/`704.5f`,
  sibling subrules of `702.131`, `702.33`, `702.179`, `701.54`), and E-003a
  found precisely this to be the annotator's commonest disagreement with
  themself (3 of 6). All 9 were judged model error. That is defensible —
  sibling subrules can be genuinely different rules — but it is one standard
  applied to the model and another absorbed as ceiling.
  **It is bounded and does not change the conclusion:** the family score
  already prices depth leniency in full, and there the model reads 0.252
  against a family ceiling of 0.902. Removing the leniency question entirely
  still leaves the model at roughly a quarter of the attainable score. What
  would resolve it is an independent judge, not a bigger sample; registered as
  future work, not attempted here.
- **Sample coverage gap:** 13 of 125 rulings produced no citation at all,
  contributing 13 of the 267 disagreements (4.9%); none were drawn into the 40.
  That failure mode — the extractor returning nothing — is therefore
  unmeasured by E-003b.
- **CR-version check (asked 2026-08-09, answered from the data):** the CR
  upgrade did not contaminate this analysis. All 125 annotation rows carry
  `cr_version = "August 7, 2026"`, the same release the extractor was grounded
  on, so gold and system were scored against one document. **0 of the 267
  disagreements cite a rule number absent from the current CR** — a
  version-skew artifact would show up here first, and does not. Of the 4
  citations the migration remapped, exactly one falls inside the 40 sampled
  cases (`310.10` -> `310.11`, ruling `41f59f3c34ff`) and it was judged with
  the current rule text on screen.

---

## E-007 — do the generated answers cite what they claim?

- **Registered:** 2026-08-09, at Phase 5 kickoff, before `answerer.py` exists.
  The Phase 5 DoD is a verdict, and a verdict whose criteria are written after
  the answers are read is not a verdict.
- **Objective:** the Phase 5 DoD, made measurable. Two questions that are
  routinely conflated and are kept apart here:
  - **Coverage** — what share of a generated answer's factual claims carry a
    citation at all?
  - **Support** — of the claims that do carry one, what share are actually
    supported by the cited evidence? A citation that points at a real rule
    which does not say what the sentence says is worse than no citation,
    because it survives inspection.
- **Sample, and why it is not the golden set:** 30 RulesGuru questions drawn
  fresh by `build_golden_pool.py`, **disjoint from all 77 golden-set
  questions** — from both the 20-question development split and the 57
  evaluation questions frozen for E-001. Auditing generation on the
  evaluation split would spend the split that Phase 4 froze specifically to
  protect E-001; auditing on the development split would measure a prompt on
  the same 20 questions it was tuned against. The RulesGuru answer key is the
  asset here, and it exists for questions we have never touched. IDs are
  versioned, text is cached and gitignored, per the licence posture already
  applied to the golden set.
- **Configuration:** each question goes through the Phase 4 stack
  (`retrieve()` with its default budget and caps) and then through
  `generation/answerer.py`. The audit is manual, one worksheet row per
  **claim**, not per answer — an answer is not a unit of truth. Recorded per
  claim: whether a citation is present; whether the cited evidence supports
  it; and whether the claim is correct against the RulesGuru answer key,
  which is a *third* thing and reported separately.
- **Decision rule (from the roadmap DoD, not invented here):** **100% of
  factual claims carry a citation**. Below 100%, the prompt is iterated and
  the run repeats — this is a build criterion, not a research finding.
  Support is reported with a cluster-bootstrap interval over questions and
  carries **no threshold**, because no threshold for it was pre-registered
  and inventing one after seeing the number is how a target becomes a
  rationalisation.
- **Refusals count as correct, and this is the subtle part.** Phase 4 measured
  `interaction_multihop` rule recall at 0.12: for those questions the rule the
  answer needs is *not in the subgraph*, and the honest output is a refusal.
  An audit that scores refusals as failures would push the prompt toward
  answering from parametric knowledge — it would reward exactly the failure
  E-008 exists to detect. A refusal is scored as correct behaviour whenever
  the subgraph lacks the evidence, and the refusal rate is reported beside
  the coverage figure rather than folded into it.
- **Prediction, recorded before the run:** coverage reaches 100% only after
  iteration, with the first round failing on *connective* sentences — the
  bridging clauses a model writes between two cited facts ("so the creature
  is still a 1/1"), which feel like reasoning rather than claims and are
  where uncited assertions hide. Support lands lower than coverage, and its
  commonest failure is a citation to the right *chapter* and the wrong
  subrule, which is the same wrong-leaf error E-003a found the annotator
  making against themself.
- **Threat to validity, recorded up front:** the author writes the prompt and
  audits the answers, which is the same single-judge design flagged in E-003b.
  It is not resolvable by a bigger sample. What bounds it here is that
  coverage is nearly mechanical — a sentence either carries a citation
  marker or it does not — while *support* carries the judgement, and support
  is the figure without a threshold.
- **Actual result:** _(to be filled after the run)_

## E-008 — does the model answer from the graph or from what it already knows?

- **Registered:** 2026-08-09, at Phase 5 kickoff, before any prompt exists.
- **Objective:** every grounding claim in this project rests on an assumption
  that is false by default — that the model's answer came from the retrieved
  subgraph. Magic is a 30-year-old game with an enormous public corpus, and
  the model knows it. A correct answer is therefore **not evidence of
  grounding**, and E-007 cannot separate the two: a well-cited answer that
  the model actually produced from memory passes every check E-007 makes.
- **Design — fictional cards, which is the only way to tell the two apart:**
  a small set of cards that do not exist is loaded into a **disposable graph
  namespace**, each built to make parametric knowledge actively wrong:
  - a fictional card whose oracle text contradicts what a similarly-named
    real card does;
  - a fictional keyword with a glossary entry and a governing rule, so the
    correct answer is only derivable from the subgraph;
  - a real card given a fictional ruling that changes the outcome.
  The measurement is whether the answer follows the graph or the world. Test
  fixtures only — nothing fictional touches the production database, and
  nothing about this ships in the corpus.
- **Decision rule:** any answer that contradicts the loaded subgraph in favour
  of real-world Magic knowledge is a **leak**, and a single leak blocks the
  Phase 5 DoD claim that answers are grounded. Not a proportion with an
  interval: the claim being tested is "grounded", and one counterexample
  falsifies it. If leaks occur, the prompt is iterated and the finding is
  reported either way — a phase that reports "we found parametric leakage and
  here is what fixed it" is worth more than one that never looked.
- **Prediction, recorded before the run:** leakage happens, and it happens
  most on the *contradiction* case rather than the invented-keyword case. An
  invented keyword leaves the model nothing to fall back on, so it either
  uses the subgraph or refuses; a card that resembles a known one gives it
  something confidently wrong to say. Second prediction: leakage shows up in
  the uncited connective sentences before it shows up in a cited claim —
  the same seam E-007 predicts for coverage.
- **Actual result:** _(to be filled after the run)_
