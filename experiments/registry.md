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

- **Registered:** 2026-08-10, at Phase 5 kickoff, before `answerer.py` exists.
  Red-teamed the same day, before any generation; what the review changed is
  listed at the end of this entry rather than silently folded in.
- **Objective:** the Phase 5 DoD, made measurable. Three constructs that are
  routinely collapsed into one number, kept apart here:
  - **Coverage** — what share of an answer's factual claims carry a citation?
  - **Support** — of the claims that carry one, what share are actually
    supported by the cited evidence? A citation pointing at a real rule that
    does not say what the sentence says is worse than no citation, because it
    survives inspection.
  - **Correctness** against the RulesGuru answer key — a third thing, reported
    separately, and **not part of the Phase 5 DoD**. It may not be traded
    against coverage in the write-up.

### Sample

- **Target 40 fresh RulesGuru questions; 42 achieved** (drawn 2026-08-10,
  `data/golden/e007_audit_pool.jsonl`), **disjoint from all 77 golden-set
  questions** — from the 20-question development split and from the 57 frozen
  for E-001 alike. Auditing on the evaluation split would spend the split
  Phase 4 froze to protect E-001; auditing on the development split would
  measure a prompt against the 20 questions it was tuned on.
- **10 are the prompt-development subset. 32 are the audit.** The 32 are
  touched by `answerer.py` exactly once, after the prompt is frozen and its
  version string recorded. **The rule-of-three bound follows from 32, not
  from the round number this entry first named: 3/32 = 0.094.**
- **Achieved content overlap: 9 of the 42 questions touch a card name the
  golden set also uses** — Blood Moon, Dress Down, Glass Golem, Hardened
  Scales, Ral's Outburst, Magus of the Moon, Strionic Resonator, Yixlid
  Jailer. Reported rather than dropped: a second question about Blood Moon is
  not the same question. The one place it could bite is indirect — prompt
  iteration on the 10 development questions could in principle fit a card
  E-001 will later evaluate on — and it is bounded by the fact that E-007
  tunes a *prompt*, never retrieval, and never sees an E-001 answer.
- **The drawn labels are the source filter, not the strata**, and are
  reclassified by hand (`scripts/classify_pool.py`) **before** the 10/32
  split, because the split draws proportionally by stratum. Splitting on
  seeded labels would be nominally stratified and substantively hollow, and
  if the true `interaction_multihop` questions landed mostly on the
  development side the audit would lose the stratum this pool was redrawn to
  recover. Seeded mix as drawn: `keyword_rule_2hop` 16, `rulings_2hop` 14,
  `interaction_multihop` 12.
- **Achieved mix, 2026-08-10, before the split was drawn:**
  `interaction_multihop` **26**, `negative_temporal` **15**,
  `keyword_rule_2hop` **1**, `rulings_2hop` **0**. The hand pass **changed 31
  of 42 labels**, so the complexity-seeded value was noise rather than a
  weak signal — the second independent demonstration of that, after Phase 1.
- **`rulings_2hop` came back empty again**, exactly as it did in the golden
  set. Two independent annotation passes now agree that judge questions are
  not answered by "a card's official ruling citing a rule", which is the
  same conclusion ADR-006 reached from the corpus side when it reduced
  `CITES_RULE` to explicit citations. Recorded as a replication, not
  re-litigated here.
- **`keyword_rule_2hop` holds exactly one question**, so **no per-stratum
  claim about it is reportable from this sample** — the same disclosure the
  Phase 4 split carries for the same stratum, and for the same reason.
- **Consequence to face before generating, not after:** 41 of the 42 sit in
  the two strata where Phase 4 measured retrieval weakest
  (`interaction_multihop` rule recall 0.12). Most subgraphs are therefore
  expected to be labelled `insufficient`, the refusal machinery will be
  exercised heavily — which is what this pool was redrawn for — and
  **coverage and support will rest on whatever small number of questions can
  actually be answered.** That is a real risk of a figure over fewer than 10
  clusters, which this entry already requires to be labelled a description
  rather than an estimate.
  **Pre-registered contingency, decided now rather than after seeing the
  number:** once sufficiency is labelled and before any answer is generated,
  if `sufficient` + `partial` over the 32 audit questions is **below 12**,
  the pool is topped up by a further draw under the same filters and
  exclusions, the top-up is recorded here with its own date, and sufficiency
  is labelled for the new questions before generation. Below 12 there is no
  coverage figure worth reporting, and discovering that after generating
  would leave only bad options.
- **Stratified proportionally to the golden set's strata**, assigned before
  generation. Unstratified, the refusal rate is close to a function of the
  draw: rule recall on `interaction_multihop` is 0.12, so a draw light on
  that stratum reports a system that rarely needs to refuse and a heavier one
  reports the opposite, from the same pool.
- **Disjoint by id is not disjoint in content.** RulesGuru carries
  near-duplicate questions about the same interaction; a card-set overlap
  check against the 77 runs before the draw is frozen, and the achieved
  overlap is reported.
- **Amendment 2026-08-10, before the draw is frozen and before any
  generation — the source filter widens.** The first dry run against the
  registered filter (`complexity: Complicated`, judge levels 0–2) returned
  **23 new questions, none of them `interaction_multihop`**: that filter
  matched three questions and the golden set already holds all three. It
  holds 22 `interaction_multihop` questions from RulesGuru in total, so the
  bucket is exhausted rather than unlucky.
  Sampling around it is not an option. `interaction_multihop` is where Phase
  4 measured rule recall **0.12**, which makes it the only stratum that
  exercises the machinery this experiment was rebuilt around — `insufficient`
  subgraphs, correct refusals, over-refusal. A draw without it would report
  citation behaviour on the easy half and say nothing about the hard one,
  which is the failure mode the stratification requirement above exists to
  prevent.
  The filter therefore widens, with the stratum **assigned by hand from the
  question text**, as this entry already requires and as the golden set
  itself was built ([../docs/golden-set.md](../docs/golden-set.md) records
  that the complexity-seeded stratum was wrong and left two strata empty).
  The filter used is passed on the command line and printed with the draw, so
  what the sample represents is recorded rather than remembered.
  **Which axis, measured rather than assumed (two dry runs, 2026-08-10):**
  judge level is not it — `Complicated` at levels 0–3 returned the same three
  questions and zero new. Complexity is — `Intermediate` + `Complicated` at
  levels 0–2 returned **14 new of 20**, with 3 of the 14 touching a card name
  the golden set also uses.
- **What the three `STRATUM_PLAN` entries actually are, corrected here:**
  three **source filters**, not strata. `data/golden/ids_v0.jsonl` contains no
  `rulings_2hop` question at all — its 30 RulesGuru rows are 22
  `interaction_multihop`, 6 `negative_temporal`, 2 `keyword_rule_2hop` —
  because the seeded stratum was reclassified by hand during annotation. The
  achieved stratum mix of this pool is therefore unknowable until the manual
  pass is done, and is reported as **achieved**, never as planned.
- **Two golden-set strata are out of E-007's reach, stated before the draw:**
  `definition_1hop` and `legality_1hop` were generated from Scryfall, not
  drawn from RulesGuru, so no RulesGuru filter can produce them. Together they
  are 35 of the golden set's 77 questions. Nothing E-007 reports speaks to
  citation behaviour on those two strata. The limitation runs in the
  conservative direction — they are the easiest questions in the set, where
  coverage would be highest — so the reported figure is a floor rather than a
  flattering slice, and the write-up says which strata it covers instead of
  implying all of them.
  **The achieved n and stratum mix are registered here before generation.**
  If the widened draw cannot reach 40, the registered n changes and the
  rule-of-three bound is recomputed from it — 3/30 = 0.10 is a property of
  the sample size, not a target to be reported regardless.

### Configuration, pinned before the run

An unpinned temperature already cost this project three prompt iterations
(journal, 2026-08-09): the same configuration scored citation F1 0.167 and
then 0.114, a spread as wide as the differences it was meant to measure.

Pinned 2026-08-10, before the first generation:

- **Model `gpt-4o-mini`, temperature 0.** The same model E-003 used, chosen
  for cost; temperature 0 because nothing here wants variation — a rules
  answer has a right shape, and sampling would make two runs of one
  configuration disagree. Recorded per answer in the run log, not only in
  this entry.
- **Prompt version `p5-a1`**, incremented per iteration round and written
  into every answer row.
- **`max_tokens` 700 per answer** — generous for a rule-by-rule walk, small
  enough that a runaway answer cannot quietly multiply the bill.
- **`retrieve()` with `token_budget=6000`, `kind_cap=25`** (the
  `subgraph.py` defaults, stated rather than inherited).
- **`rule_search` on. `oracle_text` expansions on. `text2cypher` OFF.**
  These are optional injections and each moves the refusal rate, which is
  the denominator of everything measured here. The first two match how
  E-006 ran, so the retrieval half is unchanged between the phases.
  `text2cypher` is off on principle: it would put a *generated Cypher
  query* underneath a *generated answer*, and a failure could then belong
  to either model. E-007 measures whether answers cite what they claim, not
  whether two models compose.
- **Retrieval defect found and fixed before any label was frozen
  (2026-08-10).** The first hand-read sufficiency case exposed three linking
  bugs — the router deriving its query parameter from the raw surface, a
  single-word name failing to resolve when clause punctuation was attached,
  and *Who // What // When // Where // Why* matching the word "What". The
  pool's retrieval went from 32 resolved / 10 `no_match` to **42 resolved /
  0 `no_match`**, with cards in the subgraph rising 51 -> 164. **E-006 was
  re-run and is unchanged**, so the Phase 4 figures stand as published; the
  defect was invisible from the golden set, whose development questions name
  cards without clause punctuation. Sufficiency is labelled against the
  corrected dump, and this entry records that the dump was regenerated once,
  before labelling, for a stated reason.
- **Generation replays the retrieval dump rather than re-querying**, and
  `run_e007.py` refuses to proceed if the rebuilt context differs by one
  byte from what was dumped. The sufficiency labels describe the dumped
  context; letting the graph move underneath a frozen label would
  invalidate them silently.
- A rerun of the same configuration must reproduce byte-identically. One that
  does not is a bug report before it is a result.

### The claim unit, fixed before the first answer is generated

Segmentation is the most judgement-laden step in this design and it sits
under the only threshold, so it is mechanical and it is frozen first:

1. `scripts/audit_answers.py segment` strips every citation marker, splits
   the remaining text into sentences deterministically, writes one worksheet
   row per sentence, and **freezes the file with its sha-256 in the run log
   before any citation is re-attached or any judgement is entered**.
2. Each row is labelled `factual` / `non_factual` under
   [../docs/claim-annotation-guide.md](../docs/claim-annotation-guide.md),
   written before the run. A sentence asserting anything about a card, rule,
   ruling or game outcome is `factual` **including connective and inferential
   sentences** — an inference drawn from two cited facts is still a claim
   about the game, and is in the denominator.
3. The `non_factual` **exclusion rate is reported beside coverage** with its
   own interval. Above 20%, the coverage figure is void: at that point the
   metric is measuring the segmentation.
4. **Mean factual claims per answer and mean answer length are reported for
   every iteration round.** Coverage is monotonically improved by brevity and
   hedging, and the iteration loop optimises it; a gain bought by shortening
   answers must be visible rather than invisible.

### Sufficiency is labelled before any answer is read

Binding ordering, the same shape as E-003a's ceiling-before-adjudication rule
and enforced the same way. After `retrieve()` runs on all 40 questions and
**before** `answerer.py` is invoked, each retrieved subgraph is labelled
`sufficient` / `partial` / `insufficient` against the RulesGuru answer key —
could a human derive the key's answer from this evidence alone? Labels are
frozen in `data/golden/e007_sufficiency.json` with the file's hash in the run
log. **Reading a generated answer before that file is frozen voids the run.**

`partial` is a real category, not a hedge: `subgraph.serialize()` appends a
NOTICE when the context is incomplete, so the system itself produces hedged
partial answers and refusal-vs-answer is not binary here.

Without this, the refusal rule below is circular — the author would look at a
refusal, look at the subgraph, and agree it was thin. The 30 fresh questions
carry no `gold_cr_rules` annotations, so nothing else on this sample can
supply the ground truth.

### Achieved sufficiency, and what it does to the gates (2026-08-10, before generation)

Labelled and frozen before any answer existed. **Audit side: 5
`sufficient`, 20 `partial`, 7 `insufficient`** (development side 3 / 5 / 2).
By stratum: `interaction_multihop` 3 / 19 / 4, `negative_temporal` 5 / 6 / 4,
`keyword_rule_2hop` 0 / 0 / 1.

The registered contingency does **not** fire — `sufficient` + `partial` is
25 against a floor of 12 — and no new threshold is invented here, because
the criterion was chosen before the labels existed and moving it now
because the composition disappoints is exactly what pre-registration
forbids. What follows is therefore a **limitation, not a revised gate**:

- **The over-refusal gate rests on 5 questions.** It is the only condition
  that blocks the Phase 5 DoD, and it is defined only on `sufficient`.
  Zero over-refusals over 5 bounds the over-refusal rate at **3/5 = 0.60**
  by rule of three. The write-up says that bound; it does not say "the
  system does not over-refuse".
- **Unsupported answering rests on 7**, bounded at 3/7 = 0.43 on a clean
  run. Same treatment.
- **`partial` is the majority of the audit at 20 of 32**, and `partial`
  carries no threshold in either direction by design. So most of the audit
  exercises coverage and support while contributing nothing to the refusal
  gates. Coverage and support keep a healthy denominator — up to 25
  answering questions — which is the half this sample can actually speak to.

### Reopened after a retrieval defect, and re-labelled (2026-08-10, still before generation)

The section above is **superseded on the audit side** and kept as written,
because a pre-registration that edits its own record of what it found is
worth nothing.

A defect found while hand-reading one case: a card with no rulings and no
keywords never entered any subgraph, since every card traversal reached the
node through a relationship. `card_core` fixed it (164 → 195 cards over the
pool) and the evidence changed on **42 of 42** questions — so the frozen
labels no longer described the subgraphs they were labelled against.

- **Reopened: the 32 audit labels only.** The 10 development labels are kept
  and marked `stale_labels`. Their answers had already been read, and
  re-labelling a question whose answer the annotator has seen is the
  contamination the ordering in this experiment exists to prevent. The
  development side therefore carries a stated limitation — its labels
  describe weaker evidence than the run they will score — and no repair.
- **Re-labelled composition (audit, n=32): 4 `sufficient`, 19 `partial`,
  9 `insufficient`** (before: 5 / 20 / 7). The contingency is re-checked
  against the same floor and still does not fire: `sufficient` + `partial`
  is 23 against 12.
- **The gates got thinner, not fatter.** Over-refusal now rests on **4**
  audit questions, bounded at 3/4 = 0.75 by rule of three; unsupported
  answering on 9, bounded at 3/9 = 0.33. The prediction that oracle text
  would convert `partial` into `sufficient` was **wrong**: 21 of 32 labels
  are unchanged and 7 of the 11 that moved went away from sufficiency. The
  evidence these questions lack is rules and rulings, not card text.
- **The 11 changes are not an agreement measurement.** Evidence changed and
  the annotator judged twice; the two are confounded by construction and
  nothing here isolates either. E-007c is unaffected and still required.

### Amendment — how the shuffled-citation control is administered (2026-08-10)

The control was registered above before any answer existed; what was *not*
registered is how a human judges it. Written down now, before the audit
answers exist, and an amendment rather than an edit to the text above.

- **Permutation is within an answer**, by a derangement — no row may draw
  its own citation. Across answers the evidence would come from a different
  subgraph and every control row would be trivially unsupported, which
  measures the sampling, not the judge.
- **An answer holding a single cited factual claim is excluded** and
  enumerated in the output. It cannot be deranged against itself.
- **Both arms are judged in one blind pass.** Each cited factual claim
  appears twice — once with its real citation, once with another claim's —
  in a seeded random order over the whole file, addressed by an opaque slot
  number. The arm is in the file and is never printed, and per-arm counts
  are withheld until the last row is judged.
- **The seed is recorded in the run log.** Without it the pairing cannot be
  reproduced and the control cannot be re-derived by a reader.
- **`compare` refuses while any row is unjudged**, so the remaining
  judgements cannot be aimed at a verdict already half visible.

**Amended the same day, before any support label existed: the control is
capped at two cited claims per answer.** The audit worksheet came back at
411 rows, which puts the full control near 240 blind slots on top of the
real support pass, and a control that does not get finished measures
nothing at all. The cap is sampled with the recorded seed, and **every
answer that contributes a pair still contributes one** — the cluster
bootstrap resamples questions, so the interval depends on the number of
clusters far more than on claims within a cluster.

The deviation runs in the conservative direction and that is why it is
acceptable here: a smaller control sample widens **both** arms' intervals,
and the clause requires the real arm's lower bound to clear the control
arm's upper bound. Less data makes this harder to satisfy, never easier.
It was chosen from the row count, before a single support judgement
existed, and the alternative — starting a 240-slot pass and abandoning it
part-way — would leave the arms judged under different levels of fatigue.

**Threat this does not remove.** The same sentence is shown twice to the
same annotator, and a distinctive sentence is recognisable however far
apart the two slots fall. Blinding here bounds rubber-stamping; it does not
achieve independence. The honest reading is that the control detects a
judge who accepts any plausible-looking citation, and does not rule out a
judge who remembers giving this sentence a different verdict earlier. A
second annotator would fix it and this project has one.

### E-007d — does the claim unit survive a list? (registered 2026-08-10, not yet run)

- **Registered mid-labelling of E-007's audit side, before its exclusion
  rate is final**, and prompted by a row count rather than by a result: 49
  of 411 worksheet rows are a bare list marker (`2.`), because the
  registered segmenter splits on punctuation + whitespace + a sentence
  opener and a numbered list matches that. It changes nothing about E-007,
  whose worksheet stays frozen and whose void rule stands as written.
- **Objective:** whether a claim unit aware of list structure measures the
  same thing as the sentence unit. Two failure modes are in play and pull
  opposite ways: bare markers inflate the exclusion rate toward the void,
  and a citation at the end of a bullet spanning four sentences reads as
  three uncited claims plus one cited.
- **Design:** re-segment E-007's audit answers under a unit that treats a
  list item as one claim, label from scratch under the same guide, and
  report coverage under **both** units side by side. The frozen E-007
  worksheet is the comparison, not the thing corrected.
- **Pre-committed reading:** if the two coverage figures agree within their
  intervals, the sentence unit was sound and the artefact was cosmetic. If
  they disagree, E-007's coverage is reported as unit-dependent and the
  successor's number does **not** retroactively become E-007's result.
- **Threat, stated now:** the answers are already read, so this is not a
  blind pass and cannot be one. It is a measurement of the instrument, not
  of the system, and the write-up says so.
- **Actual result:** _(to be filled after the run)_

### E-007c — is `partial` a judgement or a shrug? (registered 2026-08-10, not yet run)

- **Registered before the first generation**, and before any disagreement is
  inspected. Prompted by the composition above rather than by a result:
  `partial` was applied to 25 of 42 subgraphs by one annotator on a label
  invented for this experiment, and a category that absorbs the majority of
  a sample is the category most likely to be absorbing uncertainty.
- **Objective:** the ceiling for the sufficiency label, the same M2 the
  project applies to every hand-made gold
  ([../docs/annotation-methodology.md](../docs/annotation-methodology.md)).
  E-003a measured this annotator at **0.815 against themself**; a label with
  no ceiling is reported against a 1.0 that does not exist.
- **Design:** a blind re-label of **10 of the 42** subgraphs — fresh
  worksheet, original labels hidden, days elapsed printed — scored as exact
  agreement and as agreement collapsed to answerable / not
  (`sufficient`+`partial` vs `insufficient`), because the second is what the
  refusal gates actually use.
- **Decision rule:** none, and deliberately. This measures the instrument;
  it changes no frozen label and licenses no re-labelling. If collapsed
  agreement is materially below exact agreement, the reported refusal
  figures carry that ceiling beside them.
- **Prediction, recorded before the run:** exact agreement is the weaker of
  the two, with the disagreement concentrated on the `sufficient` /
  `partial` boundary rather than on `insufficient` — deciding whether the
  missing rule mattered is the judgement, and deciding whether anything was
  retrieved is not.
- **Actual result:** _(to be filled after the run)_

### Decision rules

- **Coverage: 100% of factual claims carry a citation** (from the roadmap
  DoD, not invented here). Below 100% on the *development* subset, the prompt
  is iterated.
- **Iteration budget: at most 3 documented rounds**, each judged on the
  10-question development subset only, each recorded with its coverage,
  support and refusal figures. If coverage has not reached 100% there within
  3 rounds, the audit runs anyway and the DoD is reported **not met** with
  the measured figure — the same shape as E-003's G3. Calling this "a build
  criterion, not a research finding" does not exempt it: the number goes into
  `docs/evaluation.md` and the README as evidence that answers are grounded,
  which makes it a finding the moment it is published.
- **Support: no numeric pass threshold** — none was pre-registered and one
  invented now would be fitted to the data. It carries a **pre-committed
  reading**, registered here before any number exists. The roadmap DoD has
  two clauses — *"100% das afirmações factuais têm citação; citações
  sustentam a frase"* — and the second is satisfied only if the **lower
  bound** of support's cluster-bootstrap interval exceeds the **upper bound**
  of a same-run **shuffled-citation control**: the same answers re-scored
  with citation handles permuted across claims within each answer. That
  control is the only thing separating "the citations support the sentences"
  from "any citation looked plausible to this judge". If the intervals
  overlap, Phase 5 reports the DoD **not met on its second clause**, whatever
  coverage reads.
- **Refusals count as correct behaviour when the subgraph lacks the
  evidence.** Phase 4 measured `interaction_multihop` rule recall at 0.12; for
  those questions there is nothing to answer from, and an audit that scored
  refusals as failures would push the prompt toward answering from parametric
  knowledge — rewarding exactly the failure E-008 exists to detect.
- **The two error directions that rule creates are both measured**, because
  without them a system that refuses everything scores coverage 100% (0/0)
  with an unbounded refusal rate and passes:
  - **Over-refusal** — refusing on a `sufficient` subgraph. A grounding
    failure, not correct behaviour. **Non-zero over-refusal blocks the Phase 5
    DoD regardless of coverage.** The frozen sufficiency file is what makes
    that threshold un-gameable after the fact.
  - **Unsupported answering** — answering on an `insufficient` subgraph. The
    parametric-leak surface, which E-008 tests directly.
- **`partial` subgraphs, scored separately and under no threshold.** The
  three-way sufficiency label creates a middle case that the two error
  directions above do not cover, and leaving it uncovered would let the
  judgement drift to wherever the result needed it. Registered before the
  labels exist: on a `partial` subgraph **both a refusal and a partial answer
  that states what is missing are correct behaviour**; only a partial answer
  that asserts the missing part *without* flagging it is a failure, and it is
  counted as **unsupported answering**, not as over-refusal. Partial answers
  are audited for coverage and support exactly like full ones — a claim
  inside a hedged answer is still a claim.
  Rationale: `subgraph.serialize()` itself appends a NOTICE inviting the
  model to say the context is incomplete, so refusing and hedging are both
  behaviours the system asks for, and neither can be scored as an error
  without penalising the design. The DoD-blocking threshold therefore applies
  **only** to over-refusal on `sufficient`, where the evidence was
  demonstrably there. The rate of each `partial` outcome is reported.
- **Every figure is published as counts, never as a bare percentage:**
  `covered / factual claims`, with `n answering questions`, `n refusals`,
  `n sufficient`, `n partial`, `n insufficient`.

### Reporting plan

- **Coverage at 100% is reported as a rule-of-three bound over question
  clusters, not as a bootstrap interval.** A percentile bootstrap on a
  unanimous sample resamples to itself and prints `[1.000, 1.000]`; E-003b
  already walked into this and `metrics.rule_of_three_upper` exists because of
  it. Over 30 questions the bound is **3/30 = 0.10** — n=30 can only bound the
  per-question uncited-claim rate at 10%, and the write-up says that rather
  than "100% of claims carry a citation".
- **Clusters are questions, and the count is printed.** Claims inside one
  answer share a prompt, a subgraph and an error mode. Refusals contribute
  zero claims, so support's effective cluster count is the number of
  *answering* questions and may be 12–18. Every figure prints `n_clusters` and
  `n_claims`; a figure over fewer than 10 clusters is labelled as such rather
  than reported as an estimate.
- **Round-over-round is paired.** Rounds 1 and 2 run on the same development
  questions: McNemar over claims with a question-level cluster bootstrap. If
  that is not run, round-over-round differences are **descriptive only** and
  no claim of improvement is made.
- **Multiple comparisons:** if coverage or support are broken out by stratum,
  the correction the registry mandates applies and is named in the result.
- **Support failure taxonomy**, mandatory per-claim field, without which this
  entry's own prediction is unfalsifiable: `wrong_leaf` (right rule family,
  wrong subrule), `right_evidence_wrong_reading`, `unrelated_evidence`,
  `evidence_absent` (cites a handle absent from the subgraph),
  `claim_not_in_evidence`.
- **`key_stale`** — a claim correct under CR 2026-08-07 that disagrees with
  the RulesGuru key. Counted separately and excluded from the correctness
  denominator, with the exclusion stated. The key was written against whatever
  CR was current when authored, and this project has already been displaced
  twice this way (`704.5w` -> `704.5x`; initiative off 725.1). An answer key
  is a historical document and cannot be migrated any more than a ruling can.

### Ceiling (M2), registered before the score exists

E-007 builds a new hand-made gold — every claim label, every support
judgement, every sufficiency label — produced by one person. The project's
own default ([../docs/annotation-methodology.md](../docs/annotation-methodology.md))
is M1 score, M2 ceiling, M3 composition, and E-003a showed why: the ceiling
came back at **0.815, not 1.0**, and the disagreement lived exactly where
this entry predicts its commonest support failure — choosing the leaf.

**Blind re-audit of 8 of the 30 answers**: fresh worksheet, segmentation
regenerated from the citation-stripped text, original labels hidden, days
elapsed printed, scored with the same metric — and **written before any
support disagreement is inspected**. If the second pass disagrees with the
first at a rate comparable to the support gap being reported, the support
figure has no ceiling and must say so.

### Predictions, recorded before the run

- **Round 1 coverage is below 1.0**, failing on *connective* sentences — the
  bridging clauses between two cited facts ("so the creature is still a
  1/1"), which feel like reasoning rather than claims and are where uncited
  assertions hide. Scoreable now that connectives are explicitly inside the
  denominator and the iteration budget is fixed.
- **The commonest support failure is `wrong_leaf`** — right chapter, wrong
  subrule — matching what E-003a found the annotator doing against themself
  (3 of 6 disagreements).
- **Refusal is the first round's dominant failure on `partial` subgraphs** —
  the NOTICE invites a refusal the evidence did not require. Scored as a
  `partial` outcome rate, not as over-refusal, which is defined only on
  `sufficient`. Over-refusal on `sufficient` is predicted to be **zero**, and
  a non-zero one blocks the DoD.

### Threats to validity, recorded before the run

- **Single judge, again.** The author writes the prompt, segments the answers,
  labels sufficiency and judges support. Not resolvable by a bigger sample —
  E-003b recorded the same threat. What bounds it here is the ordering
  (segmentation frozen before scoring, sufficiency frozen before any answer is
  read), the shuffled-citation control, and the M2 ceiling — **not**, as first
  registered, the claim that "coverage is nearly mechanical". Coverage is
  mechanical only *given* a segmentation, and the segmentation is the
  judgement-laden step.
- **The audit sample has no hop annotations**, so stratum labels are assigned
  by the author from the question text rather than inherited from a verified
  golden set.

### What the red-team pass changed

Recorded because the first version would have passed while measuring little:
the degenerate 0/0 route to coverage 100% via universal refusal; "factual
claim" left undefined with the denominator chosen by the interested party; no
iteration budget and no held-out split on the sample that produces the
verdict; the roadmap DoD's second clause quoted away; and no ceiling on a
brand-new hand-made gold.

- **Actual result:** _(to be filled after the run)_

## E-008 — does the model answer from the graph or from what it already knows?

- **Registered:** 2026-08-10, at Phase 5 kickoff, before any prompt exists.
  Red-teamed the same day, before any probe ran.
- **Objective:** every grounding claim in this project rests on an assumption
  that is false by default — that the answer came from the retrieved
  subgraph. Magic is a 30-year-old game with an enormous public corpus, and
  the model knows it. A correct answer is therefore **not evidence of
  grounding**, and E-007 cannot separate the two: a well-cited answer the
  model produced from memory passes every check E-007 makes.

### Design — fictional cards, in a disposable namespace

Three constructs, each built so that parametric knowledge is actively wrong:

1. a fictional card whose oracle text contradicts what a similarly-named real
   card does;
2. a fictional keyword with a glossary entry and a governing rule, so the
   correct answer is derivable only from the subgraph;
3. a real card given a fictional ruling that changes the outcome.

Test fixtures only. Nothing fictional touches the production database and
nothing here ships in the corpus.

**Probe count, fixed before the first generation:** 3 constructs × 4 probe
questions = **12 held-out probes**, plus a **6-probe development set** for the
iteration rounds. Temperature 0, one generation per probe; if the shipped
answerer samples, the sample count is registered here and a leak in any
sample is a leak.

**Namespace hygiene, verified rather than asserted.** Node counts before
load, after load and after teardown are recorded. E-007's 30 answers are
generated against a graph verified to hold zero fictional nodes, and the two
experiments never share a database session.

**Evidence presence is verified per probe before any answer is judged.** For
each probe the retrieved `Subgraph` is recorded with its `outcome`,
`templates_run`, `evidence` keys, `dropped` and `capped` counters. A probe
whose subgraph does not contain the fictional evidence the question needs is
**excluded from the leak denominator and reported as a retrieval miss**, not
scored as a leak. Fictional entities load through the same path as production
data and `build_card_lexicon` is rebuilt against the fixture graph so the
linker can resolve them; if it cannot, that is a fixture defect to fix before
generating, not a result. Without this check a leak would be scored — and the
prompt iterated — against a *retrieval* defect, collapsing the two numbers
`docs/evaluation.md` exists to keep apart. E-006's first run read 0.067 and
both causes were harness bugs.

### Outcome coding — four categories, all reported

A refusal is not a leak, and neither is a hedge. Without this coding, a model
that recognises the fakes and refuses everything records zero leaks, and the
experiment measures its fiction detector rather than its grounding. Combined
with E-007's refusal rule, refusing would otherwise be the dominant strategy
across both Phase 5 experiments with nothing penalising it.

- `followed_graph` — the answer follows the loaded fiction.
- `leak` — the answer contradicts the loaded subgraph in favour of real-world
  Magic knowledge.
- `refused` — refusal or hedge on a probe whose subgraph was **verified** to
  contain the needed evidence. A grounding failure, not a pass.
- `intra_context_conflict` — the answer follows one loaded item against
  another. The fictional-ruling construct puts oracle text and injected ruling
  in conflict, and a model siding with the oracle text is following the
  subgraph, not leaking. Coded, reported, never counted as a leak.

### Decision rule

**Both conditions, or the grounded claim does not hold:** zero `leak`, **and**
`followed_graph` on at least 80% of probes whose evidence was verified
present. An all-`refused` run is a **fail**, recorded as such — that is the
outcome this second condition exists to make impossible to report as success.

One leak on the held-out probes blocks the grounded claim for Phase 5, and the
response is **to report it, not to re-iterate and re-run the held-out
probes**. Iteration happens on the 6 development probes only, within E-007's
3-round budget. A phase reporting "we found parametric leakage and here is
what fixed it" is worth more than one that never looked.

**What a clean run may claim.** Zero leaks over 12 held-out probes bounds the
per-probe leak rate at **0.25 (95%, rule of three)**. The write-up states that
bound and does **not** state "no parametric leakage".

### Predictions, recorded before the run

- **Leakage happens**, and most on the *contradiction* construct rather than
  the invented-keyword one. An invented keyword leaves nothing to fall back
  on, so the model either uses the subgraph or refuses; a card resembling a
  known one gives it something confidently wrong to say. Compared across 3
  constructs × 4 probes with the mandated multiple-comparison correction.
- **Leakage appears more often in uncited connective sentences than in cited
  claims**, scored as a frequency over E-007's support taxonomy — the same
  seam where E-007 predicts coverage fails.

### Threats to validity, recorded before the run

- **Single judge**: the author authors the fictional cards and judges the
  answers, the same threat E-003b recorded.
- **The constructs are conspicuously artificial** and may cue the model that
  it is being tested. The measured leak rate is therefore a **lower bound** on
  deployment leakage over real cards the model knows well.
- **A leak on a fictional card licenses no quantitative claim about real
  ones.** The construct differs from the deployment condition in exactly the
  dimension being measured, and the write-up says so rather than
  extrapolating.

- **Actual result:** _(to be filled after the run)_
