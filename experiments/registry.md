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
- **Amendment 2026-08-15 — the configuration pinned, before arm A exists.**
  The entry has said "details to be pinned in this entry before the first
  run" since 2026-07-19. Pinning them now, with no arm-A code written and no
  arm-A output seen. Each item below is a decision the literature does not
  make for us (see [../notes/phase6-vector-baseline.md](../notes/phase6-vector-baseline.md));
  each is registered so that it cannot be chosen after a number exists.

  **1. One protocol, three arms.** Chunking, embeddings, generator, context
  budget and judge are fixed once and shared. Anything granted to B or C is
  offered to A, and a declined offer is recorded with its reason. Three
  independently-built systems are not a comparison.

  **2. Arm A is a hybrid, and its ablations are reported.** Lexical plus
  dense with a fusion step, because this corpus has exact-token semantics
  (`613.4b`) and terms of art whose ordinary-English embedding is actively
  misleading (`flying`, `protection`, *Humility*). Dense-only and
  lexical-only run as ablations and are published whatever they say.

  **3. Chunking follows the CR's own hierarchy** — the parsed numbered
  rule/subrule node — with fixed-size windows as a **registered ablation**.
  Semantic chunking is not built: the published evidence for it is a
  negative result, and structure-aware chunking is a different thing with
  better support.

  **4. A reranker is built behind a flag and swept on the development
  split, reported on and off.** Its absence would not make the baseline
  dismissible; the absence of the experiment would.

  **5. Arm A gets a multi-hop affordance — iterative retrieval — or the
  multi-hop claim is bounded in writing.** The hypothesis is that judge
  questions are *path-shaped*; a single-shot retriever is a system denied
  the ability to walk a path, and beating it on `interaction_multihop` is
  then close to uninformative. **This is registered knowing it may weaken
  the result**, since an iterative retriever may reach `613.x` from an
  intermediate reasoning step where a single-shot one cannot. That is the
  reason to decide it now rather than after. Cost is projected with
  `--limit` before any full run, per the cost-discipline rule.

  **6. Both arms are graded at rule-number granularity** against
  `gold_cr_rules`, not passage overlap, or A and B are not scored on the
  same target.

  **7. Tuning happens on the 20 frozen development questions only, and the
  sweep is published** as an artefact `run_eval.py` emits. The claim this
  experiment is allowed to make is not "the graph beat the vector arm" but
  "the graph beat a vector arm tuned on the development split, and here is
  the sweep". The 57 evaluation questions are opened once.

  **Two problems this amendment records without solving**, because
  inventing an answer now would be worse than naming the gap:

  - **Context-budget parity.** Matching *k chunks* against a subgraph by
    token count and by item count give different comparisons, and nothing
    read adjudicates. **Decision rule: match on token budget**, since that
    is the constraint both arms actually face at generation, with item
    counts reported beside it. Registered now so it is not chosen later.
  - **Three-arm asymmetry.** Arm C's text half is TF-IDF over CR text with
    oracle-text query expansion (`retrieval/rule_search.py`), reaching a
    gold rule in 2 of 8 development `interaction_multihop` questions. If
    arm A becomes a tuned hybrid and C's text half does not, then **C vs B
    measures a handicapped text component** and cannot be read as isolating
    the text contribution. Registered as a known limitation of C vs B; A vs
    B, the registered prediction, is unaffected.

  **Dress rehearsal, binding.** The full pipeline — all three arms, the
  judge and the report — runs end to end on the 20 development questions
  before the evaluation set is opened. E-006's first run read 0.067 from
  two harness bugs and was re-runnable only because it was the development
  split. There is no second draw here.

- **Amendment 2026-08-15b — what the morning's amendment left open.** The
  pins above were red-teamed the same day they were written, before any
  arm-A code existed and with nothing measured. Four of the objections
  landed. Recorded as additions; nothing above is rewritten.

  **8. Corpus parity, and it is not implied by protocol parity.** Pin 1
  fixed chunking, embeddings, generator, budget and judge — that governs
  *affordances*, and the asymmetry lives in the *source data*. All 20
  `legality_1hop` questions carry an **empty `gold_cr_rules`**: their answer
  is *"Is X legal in Modern?"*, which lives in Scryfall's structured
  legality field and in **no document of CR + rulings + MTR**. 15 of those
  20 are in the evaluation split — **26% of the 57**. As pinned this
  morning, arm A could not answer them at all, arms B and C would sweep the
  stratum, and the per-stratum table would read "graph wins" for a reason
  that has nothing to do with graphs. That is the roadmap's own
  **critical** credibility risk arriving through the one door left open.

  Therefore: **every fact any arm may cite is in every arm's index.** Arm A
  indexes, as text, the same sources the graph holds — one document per CR
  rule/subrule node, one per ruling, MTR/IPG sections, **and one per card
  carrying its oracle text plus its format-legality lines**. A stratum whose
  answer is reachable by one arm from a source the other does not index is
  not a comparison; it is a data-availability result and is reported under
  that name.

  **9. Pin 6 is undefined on `legality_1hop` and needs its own metric.**
  Rule-number granularity against `gold_cr_rules` cannot be computed where
  that field is empty — E-006 already prints `n/a` for the row. The
  retrieval metric for that stratum is **presence of the correct
  `(card, format, status)` fact in the arm's context**, judged
  deterministically, reported under its own name and never pooled into
  rule-number recall.

  **10. The legality answer key decays, so the snapshot is pinned.**
  Ingestion is a daily Scryfall bulk and bans move. The run uses the
  snapshot whose `snapshot_sha256` the golden rows were verified against;
  if a newer bulk is used, the 20 legality answers are re-verified against
  it **before** the run, and any changed answer is marked `key_stale` and
  excluded with the exclusion stated — the category E-007 already
  registered for exactly this and E-001 lacked.

  **11. Budget parity has to cover the NOTICE, or it is not parity.**
  `retrieval/subgraph.serialize` appends, whenever `dropped` or `capped` is
  non-empty: *"NOTICE: this context is incomplete … Say so if the answer
  depends on what is missing."* Arms B and C reach `enforce_budget` and can
  receive that string; arm A truncates at *k* and tells the model nothing.
  A shared token budget would therefore hand two arms out of three an
  explicit invitation to hedge or refuse — and E-007 measured that the
  invitation gets used (3 of 19 `partial` subgraphs refused). Refusals score
  as incorrect against the answer key, so token parity as pinned this
  morning would have handed B and C a correctness penalty A cannot incur,
  in the experiment predicting B beats A.

  Therefore: for E-001 **all arms run with the incompleteness notice
  suppressed**, and the per-arm NOTICE/truncation rate is recorded anyway.
  `kind_cap` firings are reported per arm per question. The alternative
  parity — matching by item count — runs as a published ablation on the
  development split, since nothing read adjudicates between the two and the
  token choice biases the two headline metrics in opposite directions
  (token parity favours the small-unit arm on recall; item-level precision
  penalises the same arm — see E-010).

  **12. Arm C's text half is arm A's retriever.** This morning's amendment
  registered the three-arm asymmetry as "a known limitation of C vs B" and
  put it in the wrong place. **C is the shipped system and C vs A is the
  README figure.** If A is a tuned hybrid and C's text half stays TF-IDF
  with oracle-text expansion — reaching a gold rule in 2 of 8 development
  `interaction_multihop` questions — then the portfolio's central table
  compares the product against a text retriever *stronger than the one
  inside the product*, and the likely published sentence is "our shipped
  GraphRAG loses to a vector baseline" for a build reason rather than a
  finding. Registering that as a limitation does not make the figure
  readable.

  Therefore: arm C is redefined as graph entity/structure retrieval **plus
  the same tuned text retriever arm A uses**, behind the existing
  `RuleSearch.search` / `.evidence` contract — a configuration change, not a
  rebuild. Then C vs A isolates what the graph adds on top of the best text
  retriever the project has, and C vs B isolates the text contribution at
  full strength. TF-IDF `rule_search` remains as a **registered ablation of
  C**, published on and off. The "one protocol" principle covers
  *components*, not only hyper-parameters.

  **13. Item 5's dichotomy was false, and the parity clause ran one way.**
  Multi-hop affordance was registered as "arm A gets iterative retrieval **or**
  the multi-hop claim is bounded in writing". Item 4 already contains the
  right pattern for this shape of question — build it behind a flag, sweep
  it, publish both states. Iterative retrieval is the same object.
  Restated: it is a **protocol variable ablated on every arm that can
  accept it**. Arm A runs single-shot and iterative, both published, and the
  graph's margin is reported against the **stronger** of the two. Arm B's
  equivalent — a second traversal round seeded from the first round's rules
  — runs on and off if it can be built inside the phase, and is declared
  not built with a reason if it cannot; **arm B is single-shot by
  construction today**, so granting iteration to A alone would deny the
  path-walking affordance to the *graph* arm in the experiment whose
  hypothesis is that questions are path-shaped. The multi-hop claim is
  bounded in writing **regardless**, naming which arms had the affordance.
  Parity is symmetric from here: anything granted to any arm is offered to
  every arm, and each declined offer is recorded with its reason.

- **Amendment 2026-08-15c — how the prediction is scored, fixed before any
  arm runs.** The decision rule registered in 2026-07-19 says the hypothesis
  survives "only if the observed pattern matches the predicted
  stratification". That sentence is *"comparable to the support gap"*
  wearing a different coat — it has at least two defensible readings with
  opposite verdicts, and the M2 ceiling already showed what happens when
  such a sentence meets its data. Pinning the reading now.

  **Primary family:** B vs A on the four strata with n ≥ 7, Holm-corrected
  at α = 0.05; test = **exact McNemar** over paired questions; unit =
  judge-scored answer correctness. Everything else — C vs A, C vs B, all
  ablations, and `keyword_rule_2hop` — is **exploratory**, reported with
  uncorrected intervals, labelled as such, and cannot confirm or falsify the
  hypothesis.

  **Per stratum the verdict has three values, not two:** *confirmed*
  (corrected p < 0.05 in the predicted direction), *falsified* (corrected
  p < 0.05 in the opposite direction), *inconclusive* (otherwise). A
  predicted-inconclusive stratum counts as inconclusive and never as
  confirmation.

  **What the split can actually support**, computed now rather than
  discovered later. Evaluation strata are `interaction_multihop` 22,
  `legality_1hop` 15, `definition_1hop` 11, `negative_temporal` 7,
  `keyword_rule_2hop` 2. Exact McNemar two-sided needs at least 6 discordant
  pairs one way for p < 0.05 (6:0 → p = 0.031); Holm's strictest step here
  is α/4 = 0.0125, which 7:0 (p = 0.0156) does **not** clear and 8:0
  (p = 0.0078) does.

  Consequence, registered before the run: **`negative_temporal` (n = 7)
  cannot reach the strictest Holm step at all** — even 7 of 7 pairs
  discordant one way gives p = 0.0156 — so it can only ever be confirmed if
  it happens to fall at a looser step of the procedure. It is a `fail`
  stratum carrying the central claim, and it is **registered in advance as
  underpowered**. That is a fact about the golden set's stratum sizes, and
  it is written here rather than discovered in the write-up.

  **The `tie` stratum is scored by equivalence, not by a failed test.**
  `definition_1hop` is the declared falsifier and its predicted outcome is
  "no significant difference" at n = 11 — which is the default outcome of
  the test whatever is true, so "tie confirmed" would be unearned. Tie is
  confirmed only if the 90% CI of the paired accuracy difference lies inside
  ±0.15 (TOST). At n = 11 that is attainable only with near-zero
  discordance, so the stratum is registered **in advance as unpowered for
  equivalence**, and the write-up must state that the falsifier could only
  ever have fired in the "graph wins here too" direction.

- **Amendment 2026-08-15d — what may change after the dress rehearsal.** The
  rehearsal hands the author per-arm, per-stratum scores before the
  evaluation split opens, and this morning's amendment registered no
  constraint on the response. Only defects of a **named class** may be fixed
  afterwards: a crash, an empty or silent output, an unresolved link, or a
  verifiable code defect of the E-006 class (a value passed in the wrong
  case, a template never wired). **No change may be made because an arm's
  score disappoints.** Every change is logged in
  [../docs/decision-journal.md](../docs/decision-journal.md) with its class
  and reason, and the rehearsal is re-run in full after the last one. The
  rehearsal's per-arm development scores are **published beside** the
  evaluation scores, so a reader can see whether the evaluation result was a
  surprise.

- **Amendment 2026-08-15e — arm A is reported twice, because a sweep over 20
  questions is heavy selection.** Chunking × embedding × fusion weight × k ×
  reranker × iterative, selected on 20 items whose per-stratum n is
  4/5/1/2/8, will fit development noise; the resulting gap goes straight
  into the graph's reported margin. That is the "additivity is not free"
  failure arriving through the tuning set rather than through laziness.

  The sweep is bounded and published as a grid, selection by a **single**
  pre-registered metric — rule-number recall at matched token budget — with
  ties broken by the literature-default configuration rather than by the
  development score. **Arm A is then reported at two configurations:** its
  development-tuned one, and a fixed default chosen without reference to any
  development number. If the graph's margin over default-A and over tuned-A
  differ by more than the CI width, the tuning is doing the work and the
  write-up says so.

  **Generator parity is checked, not assumed.** `p5-a3` was iterated over
  three rounds against *graph* serializations and asks for `kind:key`
  handles. On the dress rehearsal it runs over both arms' serializations and
  the malformed-citation rate, refusal rate and mean answer length are
  compared per arm; a material difference means an arm-A serialization
  adapter is built, registered and published **before** the evaluation run.

- **Amendment 2026-09-04 — the error taxonomy is fixed before the run.**
  The roadmap's DoD requires an error analysis, and an error analysis whose
  categories are invented after seeing which ones each arm loses on is a
  story fitted to the data. The categories are therefore fixed now, with no
  E-001 output in existence. They were drafted by an external LLM asked to
  read a set of dress-rehearsal answers, and the provenance is recorded
  because the categories are the usable part of that reading while its
  conclusion was not: it was built on 9 rows that happened to be visible, a
  slice containing no `correct` label when the full 36 hold 9 — a
  composition a random draw would produce about 5% of the time.

  | code | failure |
  |---|---|
  | `retrieval-miss` | the governing rule never reached the context |
  | `linking` | the wrong card, keyword or format was resolved from the question |
  | `event-order` | the sequence of events is wrong (stack order, resolution order, multiple triggers) |
  | `state-time` | the right rule read at the wrong moment — state at resolution against state when the ability triggered, delayed triggers |
  | `layer` | continuous effects composed wrongly (P/T from several effects, ability removal against an effect still applying) |
  | `verdict-only` | every step right, final answer wrong |
  | `key-mismatch` | the answer is defensible and the key disagrees |

  Every judged answer in the rehearsal and in the evaluation run gets
  exactly one code, assigned from the answer and the key alone. The
  distribution is published **per arm and per stratum** — that is the point:
  a taxonomy applied to one arm describes a system, and applied to both it
  says where a graph buys something a passage retriever cannot. `key-mismatch`
  exists so that disagreeing with the key has somewhere to go other than a
  category that blames the system.

- **Amendment 2026-09-04 — the dense encoder, changed before a single
  vector exists.** The roadmap names BGE-M3 "reuse from Project 1". Arm A
  uses **OpenAI `text-embedding-3-small`** instead. Recorded here, with the
  argument, before anything was embedded.

  **The measured reason.** The corpus under pin 8 is 115,547 documents and
  ~8.6M tokens. BGE-M3 on a CPU laptop is hours of compute and a 2.5 GB
  dependency; the API is ~US$ 0.17 and minutes, through a provider the
  project already authenticates to.

  **The reason that trade is admissible rather than merely convenient is
  the direction it moves the result.** `text-embedding-3-small` is a
  stronger English retrieval model than BGE-M3, so the substitution makes
  **arm A stronger** — and arm A is the control this experiment predicts
  losing to the graph. A change that strengthens the control cannot
  manufacture the predicted outcome; it can only make it harder to reach.
  Had the substitution weakened arm A it would not have been admissible at
  any price, and that asymmetry is the whole test being applied.

  **What it costs.** The README may not claim arm A *is* the Project 1
  pipeline. The claim it may make is the one that matters — same protocol,
  a current embedding model, tuned in good faith on the development split
  with the sweep published. `evaluation/dense.py` puts the encoder behind
  a `Encoder` protocol, so a local BGE-M3 implementing it drops in without
  touching the retriever, the fusion or the harness.

- **Amendment 2026-09-04 — pin 8 runs in both directions.** The pin was
  written to stop arm A being unable to answer a stratum the graph sweeps.
  Building the corpus surfaced the mirror: the Scryfall bulk holds 38,262
  card records and the graph loads **34,236**, because `etl/cards.py`
  filters tokens, art series and non-playable layouts. Indexed as-is, arm A
  would have held 4,026 documents no other arm can cite. `corpus.py` reuses
  `is_playable` rather than re-deciding it, and the card counts now match
  exactly; rulings whose card is not in the corpus are dropped for the same
  reason. Parity is a property of the corpus, not a favour granted to one
  arm.

- **Amendment 2026-09-04 — pin 12 fixed the wrong half of arm C's problem,
  and the routing is the other half.** Pin 12 assumed arm C's text
  retriever was too *weak*. Measured on the 20 development questions before
  any arm C answer exists: the router takes the text branch on **2 of 20**
  — 1 of 8 `interaction_multihop`, 0 of 4 `definition_1hop`, 0 of 5
  `legality_1hop`. Text retrieval is not weak in arm C so much as **rarely
  invoked**.

  Consequence for the registered readings, stated before the rehearsal:
  "C vs B isolates the text contribution" would compare two configurations
  that differ on **a tenth of the split**, which is close to a null
  comparison by construction rather than by finding. And the README figure,
  C vs A, would put a system whose text half fires twice against a hybrid
  that retrieves on every question.

  Registered, using the pattern pins 4 and 13 already established for the
  reranker and for iterative retrieval rather than inventing a new one:
  **arm C runs in two states, both published** — `routed`, which is the
  shipped system and stays the default, and `always-on`, where text
  retrieval fires on every question. `retrieval/pipeline.py` gains
  `always_text_search`, defaulting to False, because off *is* the shipped
  behaviour and this is a measurement of the routing decision, not a change
  to the product. Which state the README figure quotes is fixed here: the
  **shipped** one, with the always-on state published beside it.

- **Arm C built 2026-09-04 (`evaluation/arm_c.py`), development split,
  nothing judged.** `VectorRuleSearch` is a drop-in for `RuleSearch` — same
  `search` and `evidence` methods, same call site, no change to the
  traversal, the budget or the prompt, exactly the "configuration change,
  not a rebuild" pin 12 asked for.

  | configuration | gold-rule recall | text fired |
  |---|---|---|
  | B, graph only | 7/26 | 0/20 |
  | C routed, TF-IDF (shipped today) | 8/26 | 2/20 |
  | C routed, vector (pin 12) | 9/26 | 2/20 |
  | C always-on, vector | 9/26 | 20/20 |

  Always-on adds no gold rule over routed **on this metric** while taking
  the evidence pool from 157 to 522 rulings — which is precisely the
  blindness the amendment above records, and the reason the two states are
  compared on Context Sufficiency rather than on rule recall.

  **One deliberate widening beyond a literal reading of pin 12.**
  `RuleSearch.evidence` returns rule nodes only; `VectorRuleSearch.evidence`
  returns rules, rulings, cards and glossary entries, because the pin's
  requirement is that C's text half be *the same retriever* A uses, and a
  rules-only adapter would be weaker than A by construction — throwing away
  exactly the rulings that all 8 development `interaction_multihop`
  questions retrieve. `search` stays a rules-only view, so
  `scripts/eval_rule_search.py` and E-006's figures keep measuring what
  they measured.

- **Dress rehearsal, all three arms generated and judged (2026-09-04,
  development split, US$ 0.04 + US$ 0.01).** Nothing here is a result: the
  judge is unaudited above the registered floor, and the correctness
  ceiling's second pass is not due until 2026-09-09.

  **Run files are now named by configuration, not by arm**, which is a fix
  and not tidiness. `runs/` is gitignored, so a generated answers file is
  the only copy of the prose a label describes; E-007 lost ten answers to a
  shared default path, and E-011a's batch 2 points at one of these files
  with 19 finished labels behind it. Arm C's ablations differ only in
  flags, so an arm-only name would have let the vector run overwrite the
  TF-IDF run the ceiling is measured on. Existing files migrated;
  `require_same_prose` re-verified against the renamed batch-2 source.

  **Pin 1's generator-parity check, run as registered, before any
  comparison.** `p5-a3` was iterated against *graph* serializations and
  asks for `kind:key` handles, so the pin requires the malformed-citation
  rate, refusal rate and mean answer length to be compared per arm on the
  rehearsal, with a material difference triggering an arm-A serialization
  adapter built and published before the evaluation run.

  | configuration | answered | refused | unknown handles | mean chars |
  |---|---|---|---|---|
  | A, hybrid | 18 | 2 | 1 | 838 |
  | B | 17 | 3 | 1 | 819 |
  | C, vector, routed | 17 | 3 | 0 | 964 |
  | C, TF-IDF, routed | 19 | 1 | 1 | 947 |

  **No material difference. The adapter is therefore not built**, and that
  is recorded as a check that passed rather than a step that was skipped.

  Judge verdicts on the same 20 questions, `gpt-4o-mini` at temperature 0
  under `p6-j1` and rubric `p6-c1 @ dfcfb0851c8c`: A 10/3/7, B 9/2/9,
  C-vector 9/3/8, C-tfidf 8/3/9 (correct/partial/incorrect). **These are
  not scores.** They are unaudited verdicts on a development split, and no
  arm comparison may be drawn from them.

- **First judge-versus-human agreement (2026-09-04, 19 answers, below the
  floor, descriptive only).** `scripts/audit_judge.py` reads a frozen
  correctness worksheet as the human side and a verdicts file as the judge
  side, rather than building a second worksheet format that would drift
  from the first.

  **The blindness E-011 point 5 requires is satisfied structurally here
  rather than by a tool.** Batch 2's 19 labels were entered on 2026-09-04
  *before* `judge.py` existed, so the human could not have seen a verdict.
  That is luck, not design, and it is written down as luck.

      exact agreement 17/19 = 0.895 [0.686, 0.971]   n_clusters 19
      correct    8/9 = 0.889     partial 2/3 = 0.667     incorrect 7/7 = 1.000
      disagreements: partial -> incorrect, correct -> partial

  **Both disagreements sit on the `partial` boundary** — which is where
  E-011a's registered prediction said the *human's* second pass would
  disagree with its first, on tie-break 3, the right verdict by reasoning
  the key contradicts. That is a different comparison (inter-rater, not
  intra-rater) and it is suggestive rather than confirmatory; the
  prediction is scored against the second human pass on 2026-09-09 and not
  against this.

  19 answers and 19 clusters is below the registered floor of 30, so this
  **gates nothing** and no correctness figure may be published as validated
  on it. It is recorded because it is the first evidence the judge and the
  rubric produce compatible readings at all.

- **Amendment 2026-09-04 — arm A's good-faith tuning sweep, registered
  before it runs.** Pin 7 permits tuning on the 20 development questions
  and requires the sweep to be published as an artefact `run_eval.py`
  emits. The claim this experiment may make is not "the graph beat the
  vector arm" but "the graph beat a vector arm tuned on the development
  split, and here is the sweep". Arm A currently sits at published
  defaults, and `docs/evaluation.md` lists that as a limitation of the
  baseline rather than a virtue of the graph. This closes it.

  **Grid, fixed here.** BM25 `k1` ∈ {0.9, 1.2, 1.6, 2.0}, BM25 `b` ∈
  {0.4, 0.75, 1.0}, RRF `k` ∈ {10, 30, 60}, fusion depth ∈ {50, 100, 200},
  retriever mode ∈ {hybrid, dense, lexical}, iterative ∈ {off, on}. The
  published defaults (1.2 / 0.75 / 60 / 100 / hybrid / off) are a cell in
  the grid, not the centre it is measured against.

  **Objective, and its known defect.** Gold-rule recall, pin 6's registered
  retrieval metric, over the **15** development questions carrying a
  non-empty `gold_cr_rules` — `legality_1hop`'s five are excluded because
  the metric is undefined there, and pin 9 gives that stratum its own.
  The defect is already recorded above: rule recall is close to blind on
  `interaction_multihop`, where the answer-bearing evidence is a ruling
  carrying no CR number. So this sweep is driven mostly by the other
  strata, and that is stated rather than discovered. **No second objective
  is invented to fix it** — choosing a metric after watching the registered
  one read low is what pin 7 forbids, and it would be the same move whether
  it favours arm A or not.

  **Adoption rule, fixed before any cell is scored.** The adopted
  configuration is the one maximising the objective; **ties break toward
  the published defaults**, because 15 questions cannot separate two cells
  that differ by one gold rule and drifting away from a default on noise is
  overfitting with extra steps. If the best cell beats the defaults by
  **fewer than 2 gold rules of 26**, the defaults are kept and the sweep is
  published as having found nothing — a sweep that must produce a change to
  count is not a sweep.

  **What the sweep costs, and why it is free.** BM25's `k1`/`b` and RRF's
  `k` are scoring parameters: they do not touch the postings, so one index
  is built and re-scored. Query embeddings are computed once for the 15
  questions and passed into every cell. No LLM call, no spend.

  **Grid size, corrected before the run.** 4 × 3 × 3 × 3 × 3 × 2 = 648 raw
  combinations, of which **294 are distinct**: `k1` and `b` do nothing in
  `dense` mode, and `rrf_k` does nothing when only one ranking exists.
  Those cells are collapsed rather than left in — an inflated grid is
  cosmetic, but a duplicate cell could win a tie against the defaults on
  nothing, which is not.

- **Sweep result (2026-09-04, 294 cells, 48 min, no spend).** Artefact:
  [../docs/sweeps/e001-arm-a.md](../docs/sweeps/e001-arm-a.md).

      published defaults   9/26
      best cell           11/26   k1=1.6 b=1.0 rrf_k=10 depth=200 mode=hybrid iterative=True
      margin              +2

  **Adopted, and the margin is exactly the registered threshold.** The rule
  said adopt at ≥ 2 and the sweep returned 2. Had 3 been registered,
  nothing would have been adopted. That is not an argument for changing the
  threshold — it is the reason a threshold is fixed in advance — but a
  decision that lands on its own boundary is weaker evidence than one that
  clears it, and it is reported as such.

  **What actually won.** Every cell at 11/26 has `depth=200` and
  `iterative=True`; `rrf_k` at 10, 30 and 60 all tie at the top, so fusion
  damping does nothing measurable here, and `k1`/`b` move the result by at
  most one rule. The gain is **structural — read deeper, run a second
  round — not a BM25 tuning gain.** Reporting the winning cell as "tuned
  BM25 parameters" would be reading a table wrong.

  **Best cell per mode:** hybrid 11/26, dense 10/26, lexical 8/26. Pin 2's
  hybrid claim survives its own ablations, which is the first evidence for
  it that is not an argument from the corpus's properties.

- **Sweep adjudication (2026-09-04) — nothing is adopted, and the finding
  is about the objective.** Index and full argument:
  [../docs/sweeps/README.md](../docs/sweeps/README.md).

      depth <= 200      11/26
      depth <= 1600     16/26
      depth <= 12800    19/26

  The curve does not saturate. At 12,800 candidates arm A reads **11% of a
  115,547-document corpus per query**. The stopping rule registered before
  the curve existed therefore fires on its second branch: nothing is
  adopted and the objective is degenerate.

  **The registered rule was ambiguous on this curve's shape, and that is
  recorded rather than resolved in whichever direction suited.** It said
  "saturation adopts, monotone rise to 12800 refutes", assuming a curve
  that does one or the other. This one plateaus (1600 and 3200 both 16)
  **and** rises to the boundary, so both antecedents hold literally. The
  rule's stated purpose — "makes this a test rather than a search" — picks
  the second branch: a curve whose maximum sits at the largest value swept
  has not been swept.

  **`b = 0.4` looked like the one real tuning gain and is not.** It
  dominates every top cell of the 588-cell sweep, so it was tested at
  defensible depths on its own:

  | depth | b=0.4 | b=0.75 | b=1.0 |
  |---|---|---|---|
  | 50 | 7/26 | 7/26 | 7/26 |
  | 100 | 9/26 | 9/26 | 9/26 |
  | 200 | 9/26 | 9/26 | 9/26 |
  | 400 | 10/26 | 10/26 | 10/26 |

  Identical at every depth. `b` separates only inside the degenerate
  regime and falls with it, and so do `k1`, `rrf_k` and `iterative`.
  **Nothing in the classical BM25 or fusion tuning space moves this
  objective.**

  **Mechanism, so this is not left as a mystery.** Rule recall counts gold
  CR numbers present *after* the budget trims. A larger candidate pool
  feeds fusion more documents, the budget keeps whichever ~80 rank highest,
  and among a bigger pool more of those carry a gold rule number. The
  metric rewards **recall into a pool**, which reading deeper always
  improves, not retrieval precision, which it does not measure. This is the
  **second** pathology found in pin 6's metric by an independent route; the
  first is its blindness on `interaction_multihop`.

  **Consequence for E-001, which is the opposite of what it looks like.**
  Arm A stays at published defaults, and the standard objection to a
  baseline — "you never tuned it" — no longer applies: it was swept across
  588 cells plus three probes and the sweep declined to move it. The claim
  E-001 may make is precise: *the graph was compared against a vector arm
  swept on the development split, and the sweep found no configuration
  better than the published defaults on the registered retrieval
  objective.* What it does **not** license is "arm A is at its optimum" —
  the correct reading is that the registered objective cannot tell arm A's
  configurations apart. A sweep on **answer correctness** would be the
  informative one and is not free: 15 generations plus 15 judge calls per
  cell, and the judge is not audited above its floor. Named as future work
  with its cost, not folded in.

- **Amendment 2026-09-04 — the edge recurred, so the next probe gets a
  stopping rule instead of another extension.** Extending `depth` to 1600
  moved arm A to 16/26 and put the winner **at the boundary again**.
  Extending a second time because the result improved is the shopping this
  registry named and refused two amendments ago: "extend until arm A stops
  improving and call that tuned" is not admissible, and the argument that
  it strengthens the control does not license an unbounded search.

  So the next probe is a **depth curve with its reading fixed in advance**,
  at the winning `b` and mode: depth ∈ {1600, 3200, 6400, 12800}, and

  - if the curve **saturates** — two consecutive depths within one gold
    rule — the saturation point is adopted and depth has been swept;
  - if it **keeps rising to 12800**, nothing is adopted from it, and the
    finding is that **the objective is degenerate**: a metric that rewards
    reading a larger and larger share of a 115,547-document corpus is not
    measuring retrieval quality, and that is published as a limitation of
    pin 6's rule recall rather than as a configuration.

  The second branch is the one that makes this a test rather than a search.
  It is written before the curve exists.

- **Amendment 2026-09-04 — the winner sat at the edge of the grid, so the
  grid was extended.** Every top cell has `depth=200`, the **largest depth
  swept**. A parameter that wins at the boundary of its range has not been
  swept; it has been truncated, and adopting that value as "tuned" would
  publish a grid artefact as a result.

  Registered before the probe ran: `depth` extended to {200, 400, 800,
  1600} at the winning `k1=1.6`, `b=1.0`, across all modes, both iterative
  states, all `rrf_k`. Same objective, same code path, same adoption rule.

  **Why extending after seeing the result is admissible here**, by the same
  test applied to the encoder deviation: extending the depth grid makes
  **arm A stronger**, and arm A is the control this experiment predicts
  losing. A change that strengthens the control cannot manufacture the
  predicted outcome. The move that would *not* be admissible is extending
  until arm A stops improving and calling that tuned — so the extension is
  bounded to `depth` alone, declared here, and the artefact is published
  whether it moves the number or not.

- **Amendment 2026-09-04 — the pairwise gate fired on the rehearsal, and
  it fired where the arms differ most in context shape.** Registered in
  E-011 point 7 before any pair existed: order-disagreeing pairs count as
  ties, and above a disagreement rate of **0.20** the pairwise win rate is
  not published as the head-to-head. Measured on the 20 development
  questions, both orders, `gpt-4o-mini` at temperature 0:

  | comparison | order disagreement | resolved |
  |---|---|---|
  | B vs A | **0.368** | 17 tie / 3 A |
  | C-vector vs A | **0.368** | 16 tie / 2 A / 2 C |
  | C-vector vs B | 0.158 | 15 tie / 2 B / 3 C |

  **Two of three are above the gate**, so for those the pairwise win rate
  is withdrawn as the head-to-head, exactly as registered. The per-stratum
  correctness comparison is the headline, which is what the 2026-07-19
  decision rule always said and what `run_eval.py report` computes.

  **A mechanism worth stating as a hypothesis and not a finding.** The two
  comparisons above the gate both involve arm A, whose contexts hold 55 to
  100 documents against the graph arms' 8 to 40; the one below the gate
  compares two graph-shaped contexts. Position bias plausibly rises when
  the two answers differ in shape. That is a guess from three numbers on a
  development split, it is not tested, and it is written here so it cannot
  later be presented as something the experiment established.

- **Dress rehearsal complete end to end (2026-09-04): index, retrieve,
  generate, judge, compare, report.** Per-stratum judge-scored correctness,
  `correct` against everything else — `partial` counts as not-correct,
  because E-007c found a middle category absorbs uncertainty and letting it
  count as a win would let the headline move with how generously it was
  applied.

  | stratum | n | A | B | C-vector | C-tfidf |
  |---|---|---|---|---|---|
  | definition_1hop | 4 | 0.25 | 0.25 | 0.25 | 0.25 |
  | interaction_multihop | 8 | 0.38 | 0.38 | 0.25 | 0.25 |
  | keyword_rule_2hop | 1 | 0.00 | 0.00 | 0.00 | 0.00 |
  | legality_1hop | 5 | 1.00 | 1.00 | 1.00 | 1.00 |
  | negative_temporal | 2 | 0.50 | 0.00 | 0.50 | 0.00 |
  | **ALL** | 20 | 0.50 | 0.45 | 0.45 | 0.40 |

  No paired McNemar reaches p < 0.5. **Nothing separates.** At n = 20 that
  is the expected outcome whatever is true — E-001's own power analysis
  already registered that even the 57-question evaluation split cannot
  clear the strictest Holm step on `negative_temporal` — so this is a
  statement about the rehearsal's power and not about the arms.

  Two things it does establish. `legality_1hop` reads **1.00 for every
  arm**, which is pin 8 working: arm A can answer the stratum it could not
  have answered before the corpus carried card legality as prose, and the
  "graph wins" reading that would have produced does not appear. And the
  machinery runs end to end before the evaluation split is opened, which is
  what the binding rehearsal clause requires.

  What the rehearsal still lacks, so it is not yet binding: the judge is
  audited on 19 answers against a floor of 30, and the correctness ceiling
  that fixes its pass mark has no second pass until 2026-09-09.

- **Judge built 2026-09-04 (`evaluation/judge.py`), nothing judged yet.**
  Implements the E-011 amendment rather than restating it, and four of its
  clauses are properties of the code rather than promises:

  1. **One rubric.** `CORRECTNESS_SYSTEM` and `PREFERENCE_SYSTEM` are built
     from `evaluation/rubric.py::RUBRIC` — the same constant
     `audit_correctness.py` prints to the human. Every verdict carries
     `rubric_hash()`, so a drift is a hash mismatch and not a silent change
     of instrument. The threshold this judge is graded against is the lower
     bound of a ceiling measured "on the same rubric"; that sentence is now
     enforced by there being one object.
  2. **The answer reaches the judge blinded**, through the same
     `render_for_judgement` that blinds the human. Ceiling and judge are
     measured on one rendering, and the arms reach both readers looking
     alike.
  3. **Both orderings, and a disagreeing pair is a tie.** `resolve_pair`
     refuses to break it on the first ordering, on a coin, or on whichever
     matches the correctness labels: a model that answers differently when
     the answers swap places has reported position, and the honest record
     of that is no preference. `order_disagreement_rate` is what the
     registered 0.20 gate reads.
  4. **Domain blindness is controlled, not asserted.** `perturbed_key`
     builds E-008's fixture and refuses a perturbation identical to the
     real key — a control that changes nothing measures nothing while
     looking like evidence. `follows_key` scores it, and the pass mark
     stays the registered 0.90.

  **One scoring rule implemented without a model call.** A refusal, or an
  answer that is empty once the handles are stripped, scores `incorrect` by
  rule with `by_rule=True` on the verdict. Registered in E-011a and applied
  here: a refusal is excluded from the *ceiling*, because both human passes
  would agree on it without judging anything, but downstream a refusal to
  an answerable question is not the key's answer. Paying a model to decide
  it would invite it to disagree with a registered decision.

  **Parsing takes the last `LABEL:` line, not the first.** A model that
  reasons aloud writes "incorrect" on the way to "correct"; reading the
  first match scores the reasoning rather than the verdict. This is the
  E-002 defect that cost a prompt round, arriving in a new file, and the
  parser was written against it rather than into it. No label at all raises
  rather than defaulting, because a default is a score.

- **Correction 2026-09-04 — the run recorded below as "arm B" was arm C.**
  `run_eval.py` passed `rule_search` unconditionally, so the traversal ran
  with the TF-IDF text half attached. Text search fires on 2 of the 20
  development questions, so the numbers looked like a graph-only arm and
  nothing in the output disagreed; the retrieval dump's `templates_run`
  carries `rule_search` on `hand-doubling-season-planeswalker` and `rg-30`,
  which is where it was found. Corrected rather than edited in place:

  - The run below is **arm C, routed, TF-IDF** — the shipped configuration.
  - Arm B, genuinely graph-only, was re-run on 2026-09-04: 18 of 20
    `resolved` and **2 `no_seed`**, which is the correct behaviour for an
    arm defined as having no text half and is a fact the mislabelled run
    concealed.
  - **E-011a's batch 2 is arm C prose, not arm B.** Its 19 labels stand —
    the prose did not change, only the name for it — and the answers file
    is renamed `runs/e001_C_answers_dev.jsonl` with the worksheet's
    `sources` corrected. E-007's answers, which are batch 1, ran under
    "rule_search on" and are therefore **also arm C**, so the two batches
    are consistent and the earlier note that the ceiling is measured on
    "graph-arm prose" should read **shipped-hybrid prose**. That is the
    arm the README figure quotes, so the ceiling is measured on the right
    prose by accident rather than by design, which is worth saying plainly.

  **The fix is structural, not a correction of care.** Arm identity now
  determines configuration in one function, `run_eval.py::configure`, and
  every run prints the configuration it used. A mislabel would now have to
  be written there on purpose.

- **Dress rehearsal (2026-09-04, development split, nothing
  judged).** `scripts/run_eval.py` exists and runs arm B end to end over the
  20 development questions. Recorded now because the run happened, not
  because it produced a result — **no answer here has been scored**, and the
  rehearsal is binding only when all three arms and the judge have run.

  Retrieval resolved on 20 of 20. Generation: `gpt-4o-mini` at temperature
  0, prompt `p5-a3`, US$ 0.01, 19 answered and 1 refused (`rg-2569`). Strata
  present: `interaction_multihop` 8, `legality_1hop` 5, `definition_1hop` 4,
  `negative_temporal` 2, `keyword_rule_2hop` 1.

  **Pin 11's suppression changed nothing observable here, and that is worth
  writing down before it is mistaken for evidence.** `context_incomplete` is
  **0 of 20** — the budget never fired, as it did not for E-007's 42 or
  E-008's 18 probes. So no answer on this split could have carried the
  notice whether it was suppressed or not. The pin is a **parity guarantee
  against a case that has not yet occurred**, not an intervention with a
  measured effect, and if it ever does fire the rate is recorded per arm per
  question either way.

  **Still not built, named so the rehearsal does not read as complete:** arm
  C is not configured and there is no judge. `--arm` offers only B, and
  both `retrieve` and the file's own docstring say so on every run.

- **Arm A's retriever built 2026-09-04, lexical ablation run, no vectors
  yet.** `evaluation/corpus.py`, `bm25.py`, `dense.py` and
  `baseline_vector.py`. The corpus is 115,547 documents — 3,308 rules, 739
  glossary entries, 34,236 cards, 77,264 rulings — at `sha256 9a6fecc2`.
  BM25 indexes it in 9 s and answers in 5–233 ms. Fusion is reciprocal rank
  fusion at the published `k = 60`: BM25 scores and cosine similarities
  live on incomparable scales, and any weighted sum needs a normalisation
  constant, which is precisely the constant pin 7 exists to stop being
  chosen after seeing which arm it favours.

  **The lexical ablation on the 20 development questions, reported because
  it ran and not because it decides anything:** gold-rule recall 6/26 —
  `definition_1hop` 4/4, `interaction_multihop` **1/18**,
  `negative_temporal` 1/3, `keyword_rule_2hop` 0/1, `legality_1hop` n/a by
  pin 9. One ablation of a hybrid whose dense half does not exist yet. No
  comparison may be drawn from it.

  **Two observations recorded now, inconvenient in different directions.**

  1. **Arm A may be stronger on `interaction_multihop` than the project
     assumed.** On ad-hoc probes BM25 surfaces the Scryfall rulings that
     discuss *Humility* / *Opalescence* directly — the stratum where
     `reachability.py` found the graph produces no seed for 15 of 30
     questions and where `rule_search` reaches a gold rule in 2 of 8. The
     rulings corpus contains prose about exactly the interactions the
     hypothesis calls out of reach for text. This is an anecdote from
     hand-written probes, not a measurement, and it is written down now
     because it points **against** the project's own hypothesis and
     arrived before the experiment. Note also that rule-number recall
     scores it as a miss: a ruling that answers the question carries no
     `gold_cr_rules` number, which is a limitation of pin 6's metric and
     not of the arm.
  **Two defects the first embedding pass found, both invisible at test
  scale.** Recorded because each is a class of failure rather than a
  one-off, and because the second is the same lesson E-002 already paid
  for, one layer further down.

  1. **The dense index was `list[list[float]]`.** Correct, tested, and
     unusable: 115,547 × 1,536 float32 is 710 MB as an array and **5.7 GB**
     as Python floats — a CPython float is 24 bytes plus an 8-byte pointer
     — and one query is 177M multiply-adds, tens of seconds in a loop
     against tens of milliseconds as a matrix product. Rewritten on numpy,
     which moves from an optional extra to a core dependency because
     `dense.py` cannot run without it. The defect existed from the first
     commit and no test could have caught it: the tests are right, and
     they run on three vectors.
  2. **The retry policy covered statuses and not transport.** The pass
     died at **16,640 of 115,547** on `httpx.ReadError` (WinError 10054,
     the remote host resetting the connection), which never becomes a
     status code and so went straight through a loop that only inspected
     `response.status_code`. `RETRY_EXCEPTIONS = (httpx.TransportError,)`
     now covers it in both `extraction/llm.py` and `evaluation/dense.py`.
     E-002's 429 taught that a long loop needs retry; this adds that a
     long loop meets every transient failure the network has, not only the
     ones the server was well enough to name.

     **The resume worked, which is the point of having built it.** All
     16,640 vectors were valid and the run continued from there — one
     batch lost rather than a whole pass, and no spend repeated.

  **Arm A complete 2026-09-04: 115,547 vectors, `text-embedding-3-small`,
  US$ 0.17, 20 min, no transport retry needed on the second pass.** All
  three modes run on the development split, and the numbers are recorded
  because they ran, not because they decide anything — arm B's answers are
  not judged, so no comparison exists.

  | mode | build | p50 query | gold-rule recall |
  |---|---|---|---|
  | lexical | 8.6 s | 0.12 s | 6/26 |
  | dense | 0.3 s | 0.48 s | 7/26 |
  | hybrid | 8.7 s | 0.68 s | 7/26 |

  Per stratum the three agree almost exactly: `definition_1hop` 4/4,
  `interaction_multihop` **1/18**, `keyword_rule_2hop` 0/1,
  `negative_temporal` 1–2/3, `legality_1hop` n/a by pin 9. The hybrid buys
  nothing over dense alone on this metric at this n, which is a fact about
  20 questions and not a reason to drop a registered ablation.

- **Amendment 2026-09-04 — pin 6 is close to uninformative on the stratum
  that carries the hypothesis, and the instrument that covers it already
  exists.** Prompted by seeing rule recall read 1/18, and the prompt is
  disclosed because that ordering matters.

  Measured on the 8 development `interaction_multihop` questions: **all 8**
  retrieve between 2 and 17 Scryfall rulings belonging to a card the answer
  key names, while **7 of 8** score zero on gold-rule recall. A ruling
  carries no CR number, so pin 6's rule-number granularity cannot see it.

  What may and may not be concluded from that, stated carefully: it shows
  rule recall **does not measure whether answer-bearing evidence was
  retrieved** when that evidence is a ruling. It does **not** show those
  rulings answer the questions — that is a judgement, and asserting it from
  card-name overlap would be exactly the shortcut this registry exists to
  refuse.

  **No new metric is invented here.** Inventing one after watching the
  registered one read zero is the pattern pin 7 forbids, and the roadmap
  already lists the right instrument: **Context Sufficiency**, judged, whose
  stated purpose is to separate a retrieval failure from a reasoning
  failure. Registered consequence: pin 6's rule recall is published
  unchanged, and on `interaction_multihop` the retrieval-layer claim is
  carried by Context Sufficiency rather than by rule recall, with the reason
  named in `docs/evaluation.md`. The blindness is symmetric — the graph arm
  holds the same rulings — so it cannot favour an arm, which is why it is
  a reporting decision and not a scoring change.

  3. **Token parity buys item-count disparity, larger than expected.** At
     the shared 6,000-token budget arm A keeps 55–100 documents per
     question against a median of 8 evidence items for the graph arms. The
     registered rule stands — token budget is what both arms face at
     generation — but pin 11's item-count ablation is no longer a
     formality: an order of magnitude in item count is exactly what
     E-010's precision metric reads, and the ablation is what stops the
     choice of parity from silently deciding which arm looks precise.

- **Actual result (2026-09-12, evaluation split, the single registered draw):**

  Gate cleared first and recorded in the decision journal: split intact (20/57,
  seed 20260809), dress rehearsal complete on all three arms, **pin 10
  re-verified 20/20** by `scripts/verify_legality_keys.py`, rubric frozen at
  `p6-c1` @ `dfcfb0851c8c` before anything on the evaluation side was judged.
  All three arms produced 57 retrieval, 57 answer and 57 verdict rows; no empty
  generations; `notice = 0` on every arm, so pin 11 held. Applied by
  `scripts/e001_analysis.py`.

  | stratum | n | A (vector) | B (graph) | C (hybrid) |
  |---|---:|---|---|---|
  | definition_1hop | 11 | 0.73 [0.43, 0.90] | 0.91 [0.62, 0.98] | 0.91 [0.62, 0.98] |
  | interaction_multihop | 22 | 0.41 [0.23, 0.61] | 0.27 [0.13, 0.48] | 0.36 [0.20, 0.57] |
  | legality_1hop | 15 | 0.80 [0.55, 0.93] | 0.93 [0.70, 0.99] | 0.93 [0.70, 0.99] |
  | negative_temporal | 7 | 0.43 [0.16, 0.75] | 0.57 [0.25, 0.84] | 0.57 [0.25, 0.84] |
  | keyword_rule_2hop | 2 | 1.00 | 0.50 | 0.50 |
  | **ALL** | **57** | **0.60 [0.47, 0.71]** | **0.61 [0.48, 0.73]** | **0.65 [0.52, 0.76]** |

  **Primary family — B vs A, exact McNemar, Holm at α = 0.05. Four strata,
  four verdicts, and every one of them is `inconclusive`.**

  | stratum | predicted | discordant | raw p | Holm p | verdict |
  |---|---|---|---|---|---|
  | definition_1hop | tie | +3/−1 | 0.6250 | 1.0000 | inconclusive |
  | interaction_multihop | fail | +2/−5 | 0.4531 | 1.0000 | inconclusive |
  | legality_1hop | lose | +3/−1 | 0.6250 | 1.0000 | inconclusive |
  | negative_temporal | fail | +1/−0 | 1.0000 | 1.0000 | inconclusive |

  **The central hypothesis is neither confirmed nor falsified.** Amendment
  2026-08-15c pinned three values and forbade reading a fourth into them; the
  answer on all four strata is the third one.

  **The data never approached the registered threshold, and the registry said
  in advance how far away it was.** Exact McNemar needs ≥ 6 discordant pairs one
  way for raw p < 0.05, and Holm's strictest step needs 8:0. The largest
  discordance observed in any stratum is **5**. This is not a near miss that
  more questions would have resolved at these effect sizes — it is the
  measurement the split could support, computed before the run and confirmed by
  it.

  **The falsifier could not have been confirmed, and it did not fire.**
  `definition_1hop` predicted `tie`; TOST gives 90% [−0.091, +0.455] against the
  registered ±0.15, so equivalence is **not shown** — exactly as the amendment
  registered in advance ("unpowered for equivalence at n = 11"). B leads there
  (+0.182, +3/−1), which is the falsifier's *own* direction: the stratum where
  the graph looks best is the stratum where a graph lead was the warning sign,
  not the win. Nowhere near significance, so the warning does not fire either.

  **On the stratum that carries the thesis the point estimate has the wrong
  sign.** `interaction_multihop` — the `fail` stratum, where the prediction was
  graph ≫ vector — reads **B − A = −0.136** [−0.364, +0.091], +2/−5. Inconclusive,
  and pointing away from the hypothesis. It is also the largest stratum (22 of
  57), so this is where the aggregate tie comes from: the graph's wins on the
  1-hop strata are paid back on the multi-hop one.

  **Six of arm B's seven refusals are on that stratum** (A refuses once, in
  `definition_1hop`; C twice). Pin 11 suppressed the incompleteness notice so
  that arms B and C would not be handed an invitation to hedge that A never
  receives, and `notice = 0` confirms the suppression — **B hedges anyway, and
  it hedges precisely where its context is thinnest.** Refusals score as
  incorrect. As an exploratory sensitivity, and labelled one because dropping
  refusals is a post-hoc exclusion that favours B: on the 16 `interaction_multihop`
  questions neither arm refused, A 0.438 against B 0.375, a gap of −0.063 against
  −0.136 overall. **Roughly half of the graph's deficit on the hypothesis-carrying
  stratum is the graph declining to answer, not answering wrongly.** That is the
  same failure E-009 reached from the other side, and it is a generation-side
  problem sitting on top of the retrieval-side floor E-013 measured.

  **The secondary head-to-head is withdrawn on both contrasts that matter**, by
  E-011's gate registered before a single pair existed.

  | pair | tally | order disagreement | |
  |---|---|---|---|
  | B vs A | A 11 / tie 42 / B 4 | **0.333** | WITHDRAWN |
  | C vs A | C 6 / tie 47 / A 4 | **0.368** | WITHDRAWN |
  | C vs B | C 6 / tie 50 / B 1 | 0.140 | reportable |

  The one pair that survives is the one the 2026-08-15 amendment already
  flagged as confounded (C vs B measures a handicapped text component). Note
  the pattern the gate exposes: the two pairs that put a *vector* answer beside
  a *graph* answer disagree with themselves a third of the time, while the pair
  whose answers are both graph-derived disagrees 14%. The judge's position bias
  is worst when the two answers differ **in kind** — the same property that made
  E-010's blinding unachievable.

  **Exploratory, and registered as unable to confirm or falsify anything:**
  C vs A +9/−6, uncorrected p = 0.6072, diff +0.053 [−0.070, +0.193]; C vs B
  +4/−2, p = 0.6875, diff +0.035 [−0.053, +0.123]. `keyword_rule_2hop` holds 2
  questions and carries no claim, as the 2026-08-09 amendment said it would not.

  **The retrieval comparison is budget-confounded, by a rule registered before
  this split opened.** E-010 amendment item 7 set a 3× gate on the median
  retrieved-item count at matched token budget; the evaluation run reads A 40.5
  against B 12.0, **3.38×**. So E-001's retrieval comparison is published as
  budget-confounded and **the headline retrieval statement is the
  token-normalised one** — A 0.030 against B 0.112. Token parity was the
  registered choice and it is the right one for what both arms face at
  generation; this is the price it charges, named in advance and paid here.
  The correctness comparison above is unaffected: it is scored per question
  against the answer key and does not depend on context shape.

  **What E-001 is now allowed to say.** Not "the graph beat the vector arm",
  and not "the vector arm beat the graph". At 57 questions, with a judge whose
  audit was published ungated, the three arms are indistinguishable in
  aggregate (0.60 / 0.61 / 0.65) and every registered per-stratum test is
  inconclusive. The directional pattern — graph ahead on 1-hop, behind on
  multi-hop — is the opposite of the registered stratification, and it is
  reported as a direction, not a result.

## E-002 — MetaQA calibration

- **Objective (as first declared, 2026-07-19, intent only):** run the same
  machinery on an academic multi-hop benchmark with an answer key, to
  separate "the pipeline works" from "the domain is hard" before any claim
  on MTG. The entry carried no configuration until the registration below.

- **Registered:** 2026-08-15, before the adapter exists and before a single
  MetaQA question has been run. The phase gives this a **4-day timebox**;
  registering after the timebox starts is registering after the fact.

- **Objective, stated narrowly because the roadmap's phrasing overclaims.**
  The roadmap says calibration proves "a maquinaria funciona". It cannot,
  and pretending otherwise would be the first thing a reader catches. What
  ships is heavily MTG-specific: `QueryLinker` resolves card names against a
  Scryfall lexicon, `router.plan` branches on whether an entity *seeds the
  rule graph*, and all **9 templates** in `retrieval/templates.py` are
  written in `Card` / `Keyword` / `Rule` / `Ruling` / `Format`. None of that
  transfers to a movie KG.

  What **does** transfer, and is therefore what this entry actually
  measures: the generic spine — typed traversal from a seeded entity, the
  `Subgraph` budget and `kind_cap` machinery, evidence serialization with
  citable handles, and grounded generation that answers only from what it
  was given. Registered claim: **"the traversal-and-grounding spine
  reproduces published behaviour on a benchmark with an answer key"** — not
  "the pipeline works". Any component not exercised is listed in the result
  block, so the reader knows what the number does not cover.

- **Configuration.** MetaQA vanilla KB (movie KG, ~43k triples) and its
  1-hop / 2-hop / 3-hop question sets. **A sampled subset of 500 questions
  per hop**, drawn at seed `20260815` from the test split and frozen to
  `data/golden/metaqa_subset.json` before the adapter runs; the seed and the
  file are recorded here and `split_golden.py`-style refusal to redraw
  applies. Metric: **Hits@1**, per hop, reported with cluster-free binomial
  intervals (each question is its own unit here — unlike the MTG audit,
  there is no question-level clustering to respect).

- **Isolation, and this is not optional — it is the E-008 incident's
  lesson.** E-008 loaded 9 fictional nodes with `MERGE` on keys that
  existed, adopted a real CR keyword, and teardown then deleted three real
  rules. MetaQA loads **~43k triples**, four orders of magnitude more, into
  a graph holding the production corpus. Therefore:

  - MetaQA goes into a **separate Neo4j database**, not a namespace inside
    the Magic one. If the deployment cannot supply one, the load is refused
    rather than tagged.
  - Labels and relationship types are prefixed (`MQ_Movie`, `MQ_DIRECTED`)
    so that even a misconfigured connection cannot match a Magic pattern.
  - The loader asserts **created == declared** and refuses on any
    pre-existing key, the check written after the incident.
  - Teardown is verified by a count returning to its pre-load value, and by
    a `verify-clean` pass, before any Magic experiment runs again.

- **Decision rule, and the phrase that needed a number.** The roadmap's DoD
  says "números dentro de faixas plausíveis da literatura OU divergência
  analisada por escrito". *"Plausible ranges"* is the same undecidable
  wording that broke the M2 ceiling and appeared three times more in the
  entries written yesterday. Fixed as a **procedure completed before the
  first run**, not as a judgement made after it:

  1. **The comparison band is extracted first.** Before the adapter runs,
     the reported Hits@1 per hop is taken from **named, cited KGQA papers
     that evaluate on MetaQA**, transcribed into this entry with citation
     and reported figure, and the band per hop is `[min, max]` across them.
     No number is written from memory, and the band is fixed before any of
     ours exists — per the house rule that concepts transfer and constants
     do not, these are *their* numbers recorded as theirs, never adopted as
     targets to hit.
  2. **A floor that does not depend on the literature.** MetaQA 1-hop is a
     single typed edge lookup — "what movies did X direct" — against a KB
     with no ambiguity and no rules text. A traversal spine that cannot
     reach **Hits@1 ≥ 0.90 on 1-hop** is broken, and that is a statement
     about our machinery, not about the benchmark. Below it, the divergence
     is chased as a defect before anything is written up, exactly as E-006's
     registered prediction told us to suspect the harness first — and that
     instruction is the only reason E-006's 0.067 was chased rather than
     believed.
  3. **The verdict is one of three**, per hop: *inside band*, *below band
     with a written analysis of where and why*, *above band* — which is
     itself suspicious at this scale and triggers a leakage check before it
     is reported as a success.

- **Timebox cut rule, registered before the clock starts.** If the adapter
  is not loading and querying by the end of day 4, calibration is cut to
  **1-hop and 2-hop** and the cut is documented as a scope decision in
  `docs/decision-journal.md` with the day it was taken. If day 4 ends with
  no working load at all, MetaQA is **dropped from Phase 6** and reported as
  an unmet deliverable — the roadmap's cut list already permits reducing
  calibration and forbids only cutting the domain evaluation. Deciding this
  now is what stops a 4-day timebox from becoming a 9-day one.

- **Predictions, recorded before the run.**
  - **1-hop lands inside the band; 3-hop lands below it.** The published
    systems on MetaQA are trained or tuned on it; ours is a zero-shot
    traversal spine with a generic template, and depth is where that gap
    shows.
  - **The dominant 3-hop failure is budget, not traversal.** A 3-hop ball in
    a 43k-triple KB is large, `enforce_budget` and `kind_cap` will trim it,
    and the answer will be dropped before the model sees it. Scoreable: the
    `dropped` / `capped` counters are recorded per question, and this
    prediction is confirmed only if failures correlate with non-empty
    counters.
  - **Grounded generation is not the bottleneck at any hop.** Where the
    answer entity is present in the subgraph, it is selected. If this is
    wrong, the finding is about generation and it transfers directly back to
    the MTG side, which is the main reason this calibration is worth its
    four days.

- **Threats to validity, recorded before the run.**
  - **The calibration exercises the spine, not the system.** Stated above,
    and it bounds every sentence the write-up may build on this number.
  - **MetaQA questions are templated.** Their surface forms come from a
    small set of patterns, so entity linking there is far easier than
    resolving *"Who // What // When // Where // Why"* against a Scryfall
    lexicon. A good MetaQA number is **not** evidence that this project's
    linking works — E-003 and E-005 measure that, and E-008 already found
    three linking defects the reach metrics could not see.
  - **A one-shot benchmark on a sampled subset.** 500 per hop at one seed;
    the subset is frozen and the run is not repeated with a better draw.
  - **Answer-set questions.** Some MetaQA questions have multiple correct
    answers; Hits@1 is defined against the full answer set, and the scoring
    rule is fixed in the adapter and tested before the run rather than
    settled while looking at failures.

### Amendment — the isolation is a separate instance, not a separate database (2026-09-02)

The registration above requires a separate Neo4j **database** and says the
load is refused if the deployment cannot supply one. It cannot supply one.
`docker-compose.yml` runs `neo4j:5-community`, and Community serves exactly
one user database — `CREATE DATABASE` is an Enterprise feature. This was
found on 2026-09-02, before the timebox clock started and before a single
MetaQA question had been run, by reading the registration against the
compose file rather than against the intention.

The requirement is met by a **separate instance**: a `neo4j-metaqa` service
under a `metaqa` compose profile, on its own port (7688), with its own
password, its own process, and **no volume**. This is a strengthening, not a
relaxation, and the three differences are the point:

1. **There is no teardown query.** E-008's incident was not the load — it
   was a teardown `DELETE` that matched three real CR rules. Teardown here
   is `docker rm -f graphrag-mtg-neo4j-metaqa`, and with no volume the 135k
   triples go with the container. **Corrected 2026-09-03:** this clause
   first read `docker compose --profile metaqa rm -sf`, which removes the
   corpus container as well — `--profile` adds a service to the default set
   rather than restricting to it. Run once, and the corpus container was
   destroyed; its named volume is the only reason the graph survived. The
   teardown names the container. No Cypher runs near the corpus at any
   point in E-002.
2. **`verify-clean` changes shape.** The registration verifies teardown by a
   count returning to its pre-load value. That check now reads: the
   container is absent and `bolt://localhost:7688` refuses connections. A
   count against a server that no longer exists is not a weaker check.
3. **The mismatch is caught in code, not in a runbook.**
   `graph/connection.py::metaqa_target()` refuses when the MetaQA URI
   resolves to the corpus URI, compared case-insensitively and without a
   trailing slash, and refuses before a driver is constructed.

Unchanged by this amendment, and restated so the change is bounded: the
`MQ_` label and relationship-type prefixes, the created == declared
assertion, the refusal to load into a target holding any node, the subset
size and seed `20260815`, the comparison-band procedure, the floor of
Hits@1 ≥ 0.90 on 1-hop, the timebox cut rule, and every prediction and
threat recorded above.

The alternative considered and rejected was Neo4j Enterprise under its
development licence, which would have satisfied the original wording
literally. It was rejected because it puts a licence acceptance in front of
`docker compose up` in a public portfolio repository, which costs more in
reproducibility than the wording is worth.

### Correction — the KB is 135k triples over 43k entities (2026-09-02)

The registration above says MetaQA loads "~43k triples". That is the
**entity** count. MetaQA's own description, as restated by Saxena et al.
(ACL 2020, §5.1), is a KG with **135k triples, 43k entities and nine
relations**. Corrected here rather than silently in place, because the
figure was used to argue the size of the isolation risk. The argument
survives and grows: against E-008's nine nodes, this is roughly four orders
of magnitude on nodes and more than four on edges.

### The comparison band, extracted before the adapter runs (2026-09-02)

Step 1 of the decision rule, executed before the loader has been pointed at
anything and before one MetaQA question has run. Every figure below was read
out of the table named in its row. **These are their numbers, recorded as
theirs. Nothing here is a target.**

The comparable setting is the **full KB** — the vanilla release, complete,
which is what this project loads. Papers that also report a 50%-KB or a
KB+text setting have those columns excluded; mixing them would compare our
full-KB run against somebody's ablation.

| system | 1-hop | 2-hop | 3-hop | read from | provenance |
|---|---:|---:|---:|---|---|
| KV-Mem (Miller et al. 2016) | 96.2 | 82.7 | 48.9 | PullNet Tab. 2, `KB`; same figures in EmbedKGQA Tab. 2 | secondary |
| VRN (Zhang et al. 2018) | 97.5 | 89.9 | 62.5 | EmbedKGQA Tab. 2, `MetaQA KG-Full` | secondary |
| GraftNet (Sun et al. 2018) | 97.0 | 94.8 | 77.7 | PullNet Tab. 2, `KB` | secondary |
| PullNet (Sun, Bedrax-Weiss & Cohen 2019) | 97.0 | 99.9 | 91.4 | arXiv:1904.09537 Tab. 2, `KB` | **primary** |
| EmbedKGQA (Saxena, Tripathi & Talukdar, ACL 2020) | 97.5 | 98.8 | 94.8 | 2020.acl-main.412 Tab. 2, `MetaQA KG-Full` | **primary** |
| NSM (He et al., WSDM 2021) | 97.1 | 99.9 | 98.9 | arXiv:2101.03737, "Performance comparison … (Hits@1 in percent)" | **primary** |
| TransferNet (Shi et al. 2021) | 97.5 | 100 | 100 | arXiv:2104.07302, "Hits@1 results of the label-formed datasets" | **primary** |
| UniKGQA (Jiang et al., ICLR 2023) | 97.5 | 99.0 | 99.1 | arXiv:2212.00959 Tab. 3 | **primary** |

Every table names the metric **Hits@1**, which is the metric this experiment
registered. Rows marked secondary are figures a later paper re-reports for
an earlier system; each was cross-checked against a second re-report, and
the primary was read wherever the project leans on the number.

**Chasing the primary caught one error, which is the argument for the
rule.** A first reading transcribed PullNet's 2-hop as 92.4. The primary
table shows 92.4 is its `50% KB + Text` column; the full-KB figure is 99.9.
Had that stood, the 2-hop band would have opened at 82.7 for the wrong
reason and a mis-sourced number would have sat under a decision rule.

**Band as the registration defines it** — `[min, max]` across the systems
above, full-KB setting:

| hop | band |
|---|---|
| 1-hop | [96.2, 97.5] |
| 2-hop | [82.7, 100] |
| 3-hop | [48.9, 100] |

**And the band, so defined, cannot carry the decision rule.** Three-hop runs
`[48.9, 100]`: the floor is a 2016 memory network and the ceiling is
saturation, so any result this project produces lands "inside the band", and
the registered prediction that 3-hop falls *below* it cannot fail. A rule
that cannot fail is not a rule. The three-way verdict — inside / below with
analysis / above and suspicious — degenerates with it.

Two facts about the benchmark explain the saturation, and both were read
today rather than assumed:

- Every system in the table is **trained on MetaQA**. This project's spine
  is zero-shot with a generic template. They are not the same kind of
  system, and the comparison cannot pretend otherwise.
- Saxena et al. describe the complete-KG setting as "the easiest setting for
  QA", because the data is built so that the answer always exists in the KG
  with no missing link along the path — and UniKGQA attributes the same
  saturation to the benchmark's handful of question templates and nine
  relation types.

**The decision rule is therefore open, and is fixed before the run, not
after.** Recorded today so the choice is visible: the band is real and
extracted, and what it is allowed to decide is the pending question.

### Amendment — the floor decides, the band is context (2026-09-02)

Written after the band was extracted and before the adapter has been pointed
at anything. It replaces clauses 1 and 3 of the decision rule; clause 2, the
floor, is carried over unchanged from the original registration and is now
the whole of the pass/fail reading.

**The band is computed over primary-sourced figures only.** A system enters
the band when its figure was read from the paper that proposes it. Systems
whose figures exist here only as a later paper's re-report stay in the table
as context and do not enter the band. The criterion is **provenance, not
performance** — it is the same rule the project already applies to every
number it leans on, and it is stated before our own figure exists.

| hop | band (primary-sourced, full KB) | systems |
|---|---|---|
| 1-hop | [97.0, 97.5] | PullNet, EmbedKGQA, NSM, TransferNet, UniKGQA |
| 2-hop | [98.8, 100] | idem |
| 3-hop | [91.4, 100] | idem |

**Clause 1 (replaced) — what the band is for.** The band is *reported*, not
decisive. For each hop, this project's Hits@1 is printed beside the band
with the gap stated in the same line. No pass/fail hangs on it, because a
zero-shot traversal spine and five systems trained on the benchmark are not
the same kind of system, and no interval across the second can adjudicate
the first.

**Clause 2 (unchanged) — the floor, and it is the only pass/fail.**
`Hits@1 ≥ 0.90 on 1-hop`. MetaQA 1-hop is a single typed edge lookup against
a KB with no ambiguity and no rules text. A spine that cannot reach it is
broken, and that is a statement about our machinery, not about the
benchmark. Below the floor, the divergence is chased as a defect before
anything is written up — the E-006 discipline, which is the only reason its
0.067 was chased rather than believed.

**Clause 3 (replaced) — the two readings that remain rules.**

1. *Above the band at any hop* triggers a **leakage check** before the
   number is reported as anything. Beating a saturated band of trained
   systems, zero-shot, is far more likely to be a leak than a result. This
   survives from the original registration and keeps its force.
2. *Below the band on 2-hop or 3-hop* requires the written analysis the
   original rule demanded — where the loss happens and why — and the
   registered prediction stands: the dominant 3-hop failure is budget, not
   traversal, confirmed only if failures correlate with non-empty
   `dropped` / `capped` counters.

**What may be claimed, bounded before the number exists.** If the floor is
met: *the traversal-and-grounding spine reproduces published behaviour on a
benchmark with an answer key at 1-hop, and degrades with depth by this much
against a literature that is trained on the benchmark and saturated on it.*
Nothing about the pipeline, nothing about linking, nothing about MTG. The
components not exercised are listed in the result block.

**Threat introduced by this amendment, recorded rather than left for a
reader to find.** Restricting the band to primary-sourced figures narrows
3-hop from `[48.9, 100]` to `[91.4, 100]`, which makes the registered
prediction that 3-hop lands *below* the band easier to confirm. The
criterion was chosen for provenance and applied before our figure existed,
but the effect is real and is stated here so the confirmation is read with
it in view. The prediction was never load-bearing: the floor decides, and
the floor is at 1-hop.

### Configuration pinned by the harness, before the first run (2026-09-02)

`scripts/run_e002.py` forced four choices the registration did not name.
Recorded here rather than left in code, because each one can move the number.

1. **Traversal is undirected, level by level, to the question's own depth.**
   MetaQA's relations are directed and its questions are not — *"what movies
   did X direct"* walks `directed_by` backwards — so a directed expansion
   answers none of them. Expansion runs from Python one hop at a time
   instead of as a single variable-length Cypher pattern, so the frontier
   can be bounded and the bounding counted.
2. **A frontier cap of 400 entities per level, counted as `truncated`.** An
   unbounded 3-hop ball in a 135k-triple KB is a query that does not return.
   This is a **third** way to lose evidence beside `dropped` and `capped`,
   and it is recorded per question and reported, because the registered
   3-hop prediction is about exactly this and would be untestable if one of
   the three losses were invisible.
3. **The prediction-extraction rule, fixed and tested before any answer was
   read.** The first non-empty line, citation markers and surrounding
   punctuation stripped; a refusal is not a prediction. `metaqa.SYSTEM`
   (prompt `e002-a1`) asks for the entity on its own line for this reason —
   scoring Hits@1 out of prose would measure a parser.
4. **`metaqa.SYSTEM` is the grounding contract with the Magic removed.**
   Evidence-only, cite the handle, refuse when it is not there. The shipped
   `answerer.SYSTEM` names cards, rules and rulings and would be scored on a
   movie KG; keeping its *shape* and dropping its domain is what makes this
   a calibration of the spine.

**IP posture, matching the golden set's.** MetaQA is somebody else's dataset
under somebody else's licence, so `data/golden/metaqa_subset.json` holds
**question ids only**; text and answers are materialised from the local
release at run time and `load_frozen` refuses a release that does not hold
every frozen id. The same rule the project already applies to RulesGuru.

**A reach ceiling is measured before any token is spent.** `verify`
traverses every question and records whether the answer entity is in the
subgraph at all. Hits@1 cannot exceed it, and a gap between the two is
retrieval rather than reasoning — the split E-006 and E-007 each had to be
re-run to obtain.

### Amendment — `kind_cap` re-derived, and an analysis rule that could not decide (2026-09-02)

Written after the free retrieval passes and **before any paid generation**.
Nothing registered as the experiment's metric has been measured: Hits@1 does
not exist yet.

**Two defects, found by decomposing a reach number instead of reporting it.**

1. *The ceiling was measured over the wrong set.* `verify` recorded whether
   the **traversal** touched the answer entity. The model never receives the
   traversal; it receives `subgraph.evidence`, after the per-kind cap and the
   token budget. The first pass therefore reported a ceiling more generous
   than the system — 1.000 at 2-hop, where what the model would actually see
   held the answer 0.752 of the time. `verify` now reports both, and only
   the second bounds Hits@1.
2. *A Magic-tuned constant had been inherited unchanged.*
   `DEFAULT_KIND_CAP = 25` is per `(template, kind)` and exists to stop a hub
   like `flying` returning thousands of cards in a graph whose evidence has
   five kinds. MetaQA evidence has **one** kind, so the cap was a hard
   ceiling of 75 items and the 6000-token budget never bound at all:
   `capped` fired on 100% of 3-hop questions and `dropped` on none. This is
   the house rule violated in the plainest possible way — concepts transfer,
   constants do not.

**The re-derivation, and the criterion that does not look at the outcome.**
`E002_KIND_CAP = 1000`: an order of magnitude above what the 6000-token
budget can hold, so the cap returns to being hub protection and
`enforce_budget` is what decides. The criterion is *which mechanism binds*,
settled by the machinery's own design. The alternative — sweeping cap values
and keeping the one with the best reach — was available and is refused:
that is choosing a constant by the number it produces.

**The re-derivation is not an improvement, and saying so is the point.**

| shown-reach | old cap (25) | re-derived cap (1000) |
|---|---|---|
| 1-hop | 0.996 | 1.000 |
| 2-hop | 0.752 | **0.842** |
| 3-hop | 0.564 | **0.448** |

It helps 2-hop and **hurts 3-hop**. The mechanism is now understood: at 25
items per level the subgraph never exceeded 75 items, the 6000-token budget
never trimmed, and the distance-3 layer survived *by accident*. Lifting the
cap lets the near layers fill the budget, and `enforce_budget` trims
farthest-first — so the frontier layer, which is where a 3-hop answer lives,
is deleted almost in full.

Measured rather than argued: **226 of the 500 3-hop questions (0.452) have
their answer already reachable within 2 hops**, and of the 224 whose answer
survived into the evidence, **213 (0.951) were among them**. Shown-reach at
3-hop is 0.448 against a shallow-reachable fraction of 0.452. The system is
answering the 3-hop questions that are not really 3-hop, and eleven others.

The cap is **not** reverted, and the reason is the same rule that motivated
changing it: 25 was never chosen for this behaviour, it produced it by
accident, and picking the value that scores better is choosing a constant by
its number. The configuration stays where the criterion put it, and the
consequence is published.

**What is deliberately NOT changed, and it is the headline.**
`enforce_budget` trims farthest-first, and on a multi-hop question the
answer is at the frontier. The two hops fail differently and both failures
are this project's own:

- *2-hop — size decides.* 79 questions walk to the answer and never show
  it. `dropped` fires on 79/79 of them against 42/421 of those that kept
  it, and the losers carry a median 4,434 triples in their neighbourhood
  against 17 for the rest. A big neighbourhood overruns the budget and the
  far layer goes first.
- *3-hop — the layer is gone regardless.* The counters stop discriminating
  entirely (`dropped` 258/258 against 222/224; identical median evidence of
  206 items and identical median dropped counts), and neighbourhood size
  *inverts* — the losers see fewer triples, not more. The budget removes the
  distance-3 layer on essentially every question, and what survives is the
  45% of 3-hop questions whose answer is also reachable within 2 hops.

Changing the trimming order would raise both numbers and empty the
experiment: E-002 calibrates the machinery that ships, not a variant tuned
on the benchmark. The behaviour is a result, not a bug to fix mid-run. What
to do about it is a Phase 6 decision taken on this evidence, after the run,
and recorded as its own entry.

**The analysis rule for the 3-hop prediction is corrected, because the
registered one could not decide.** It read: confirmed only if failures
correlate with non-empty `dropped` / `capped` counters. Under the inherited
cap the counters were non-empty on ~100% of questions, hits and misses
alike — a discriminator with no variance. It now reads:

> The prediction is confirmed when the counters **discriminate**: the share
> of losses carrying a given counter is materially higher than the share
> among non-losses, and the median neighbourhood size of losses exceeds that
> of non-losses. Presence alone decides nothing and is not reported as
> though it did.

**This transfers to E-001, and that is the finding.** `enforce_budget` trims
by distance, and `interaction_multihop` — **30 of the 57 evaluation
questions** — has its answer at depth by construction. A large Magic
neighbourhood would lose the answer layer the same way, and the result would
read as the central hypothesis failing when the cause is a budget. Found on
a KG where extraction and linking cannot be blamed, before the evaluation
set was touched, which is what the calibration was for.

### Amendment — the floor failed, the defect was the prompt, and the prompt was mine (2026-09-02)

The registered decision rule says that below the 1-hop floor the divergence
is **chased as a defect before anything is written up**, and that the
harness is the first suspect. It was chased. This entry records what the
first run measured, what was wrong with it, and the bounded repair.

**What the run under `e002-a1` measured** (frozen subset, 500 per hop,
`gpt-4o-mini` at temperature 0; 3-hop never ran, the pass died on a 429):

| hop | Hits@1 | shown-reach ceiling | refusals |
|---|---|---|---|
| 1-hop | 0.786 [0.748, 0.820] | 1.000 | 90/500 |
| 2-hop | 0.074 [0.054, 0.100] | 0.842 | 452/500 |

The floor **fails** at 0.786 < 0.90. Fabricated citations: **0 of 1000**.

**The failure is refusal, not error.** 90 of 107 1-hop misses and 452 of 463
2-hop misses are the model writing `CANNOT ANSWER` — on questions whose
answer was in the context, at 1-hop, every time. Its own words name the
cause: *"I do not have information on other films written by Randall
Wallace"* — the first hop resolved, the second never looked for.

**The defect is a section this experiment's prompt was supposed to have and
did not.** `answerer.SYSTEM` carries four sections; `e002-a1` carried three.
The missing one licenses multi-step reasoning over the evidence, and A1
compounded its absence by demanding the entity "and nothing else", which
leaves no room to compose. The registry described `metaqa.SYSTEM` as *"the
grounding contract with the Magic removed"*. It was the contract with a
section removed, and the description was wrong before the run was.

**`e002-a2` restores it** — walk the facts one step per line, cite each
step, then a final `ANSWER:` line that keeps the output machine-scoreable.
This is a repair of fidelity to the instrument being calibrated, not a
search for a better number.

**Iteration is bounded and happens off the frozen subset.** Prompt rounds
run on a development draw taken from the *complement* of the registered
subset (`--dev N`, seed `20260902`; the splits hold 9,947 / 14,872 / 14,274
questions against 500 drawn each). A prompt tuned until the registered set
improves is a number reporting its own tuning. **Budget: two rounds total**,
fixed here; A2 is round one. If A2 does not clear the floor, the number
stands as measured and the divergence is written up.

**Paired evidence for A2, on development questions only** (40 2-hop, same
questions both arms): A1 3/40 correct with 36 refusals; A2 23/40 correct
with 12. Exact McNemar: 21 improved, 1 regressed, **p = 0.00001**.

**What is republished and what is retired.** The A1 figures above are
reported as the diagnosis of a defective instrument — they are not the
calibration result and no claim is built on them. The registered result is
the A2 run over the same frozen subset, and the fact that the prompt was
repaired once, on a dev sample, before that run, is disclosed beside it.

### Round two, and the pre-commitment written before it ran (2026-09-02)

**A2 over the frozen subset** (500 per hop, `gpt-4o-mini`, temperature 0):

| hop | Hits@1 | shown-reach | published band | reading |
|---|---|---|---|---|
| 1-hop | 0.874 [0.842, 0.900] | 1.000 | [0.970, 0.975] | below |
| 2-hop | 0.566 [0.522, 0.609] | 0.842 | [0.988, 1.000] | below |
| 3-hop | 0.186 [0.154, 0.222] | 0.448 | [0.914, 1.000] | below |

Floor: **0.874 < 0.90 — FAIL.** Fabricated citations 38/1500 (A1 had 0; A2
asks for per-step handles and the model sometimes invents one).

**The 63 one-hop misses, decomposed** — the chase the rule demands:

| cause | n | whose |
|---|---|---|
| refusal on a question the context answered | 36 | prompt |
| no `ANSWER:` line — output unscoreable | 11 | prompt |
| correct by the edge, outside the gold set | 8 | **benchmark** |
| genuinely wrong | 8 | model |

The third row is a property of MetaQA, verified in its KB rather than
asserted: same-titled films collapse onto one node. `Lolita` carries
`directed_by` to **both** Kubrick and Lyne; `Blue Steel` carries
`starred_actors` to both John Wayne and Clancy Brown. The gold lists one
film's answers, so a model answering correctly from the evidence it was
shown is scored wrong. That is a hard ceiling of roughly 1.6% at 1-hop —
real, measured, and nowhere near enough to excuse 0.874.

**Disclosure.** This decomposition read failures on the frozen subset. The
registered rule requires chasing a sub-floor result as a defect, so the
procedure was correct, but it means the diagnosis saw test data. The repair
was designed and validated only on development questions.

**A3, and why it is being run.** Development comparison, paired, 150
questions per hop, outside the frozen subset:

| | A2 | A3 | exact McNemar |
|---|---|---|---|
| 1-hop Hits@1 | 0.853 | 0.887 | +6 / −1, p = 0.125 |
| 1-hop refusals | 11 | **3** | |
| 2-hop Hits@1 | 0.613 | 0.627 | +9 / −7, p = 0.80 |

**A3 is not established as more accurate** — no comparison reaches
significance and 2-hop shows nothing. It is run on a criterion that does not
look at the score: under A2, 11 of the 500 one-hop outputs carried no
`ANSWER:` line and were unscoreable, and A3 cuts refusals 11 → 3 on dev,
which is the mechanism it was written to fix. An instrument that obeys its
own output format is a better instrument at any accuracy.

**Pre-commitment, recorded before A3 touched the frozen subset.**

1. A3 is round two of the two-round budget, and **its numbers are the
   registered result** — whether they are better than A2's or worse.
2. A2's table above stays published as part of the diagnostic record, so
   the pair can be read against each other.
3. There is no round three. Whatever A3 reports is what E-002 reports, and
   a floor still unmet is written up as a divergence.

- **Actual result (2026-09-03, frozen subset, 500 per hop at seed `20260815`,
  `gpt-4o-mini` at temperature 0, prompt `e002-a3`, one run): the floor is
  not met and the calibration is reported as a divergence.**

| hop | Hits@1 | shown-reach ceiling | published band | reading |
|---|---|---|---|---|
| 1-hop | **0.884** [0.853, 0.909] | 1.000 | [0.970, 0.975] | below the band |
| 2-hop | **0.570** [0.526, 0.613] | 0.842 | [0.988, 1.000] | below the band |
| 3-hop | **0.156** [0.127, 0.190] | 0.448 | [0.914, 1.000] | below the band |

**Verdict on the registered rule: FAIL.** 1-hop 0.884 < 0.90. Below the
floor the divergence is chased and written up, and it was: the chase is what
produced the five defects listed in this entry's amendments. The round
budget is spent and there is no third round.

**A3 against A2, paired on the same questions** — reported because both runs
exist, not because either was selected after the fact:

| hop | A2 | A3 | exact McNemar |
|---|---|---|---|
| 1-hop | 0.874 | 0.884 | +14 / −9, p = 0.405 |
| 2-hop | 0.566 | 0.570 | +25 / −23, p = 0.885 |
| 3-hop | 0.186 | 0.156 | +17 / −32, p = 0.044 |

Three comparisons on one family: Bonferroni α = 0.0167, so **nothing here is
significant**, including the 3-hop regression. A3 and A2 are the same
instrument by every measure this experiment can make. A3 was run for
compliance — the unscoreable outputs — and it delivered that (refusals
428 → 377, fabricated citations 38 → 20) without moving accuracy.

**The 58 one-hop misses, decomposed:** 15 refusals, 11 outputs with no
`ANSWER:` line, 10 correct by the edge but outside the gold set, 22
genuinely wrong.

**A ceiling correction is computed and explicitly does not decide anything.**
The 10 correct-by-edge cases put MetaQA's own ceiling at 0.980 for this
sample, and crediting them would read 0.904 — above the floor. That number
is **not** the result. It is a post-hoc adjustment computed after seeing the
verdict, on a criterion invented after the fact, and allowing it to overturn
a pre-registered threshold is precisely the move this registry exists to
prevent. The floor is measured on Hits@1 as registered: 0.884, FAIL. The
ceiling is reported as context and as a caveat on the benchmark.

### Predictions, scored

1. **"1-hop lands inside the band; 3-hop lands below it."** *Half wrong.*
   3-hop is far below, as predicted. **1-hop is also below** — 0.884 against
   [0.970, 0.975]. The spine does not reach published 1-hop behaviour even
   on a single typed edge lookup.
2. **"The dominant 3-hop failure is budget, not traversal."** *Not
   confirmed, under the amended rule.* At 2-hop the counters discriminate
   cleanly (117/215 of misses against 4/285 of hits). At 3-hop they fire on
   421/422 misses **and** 77/78 hits — universal, therefore silent. The
   budget is not what separates a 3-hop success from a 3-hop failure.
3. **"Grounded generation is not the bottleneck at any hop."** *Wrong, and
   this is the finding.* Conditional on the answer being present in the
   evidence the model received:

   | hop | correct given the answer was shown |
   |---|---|
   | 1-hop | 0.884 [0.853, 0.909] |
   | 2-hop | 0.677 [0.631, 0.720] |
   | 3-hop | **0.339** [0.280, 0.404] |

   At three hops the model uses **one third** of what retrieval hands it.
   The registration said that if this prediction failed, the finding would
   be about generation and would transfer directly to the MTG side, and that
   this was the main reason the calibration was worth its four days. It
   failed, and it does.

### What this number covers, and what it does not

Exercised: typed traversal from a seeded entity, the `Subgraph` budget,
`kind_cap`, evidence serialization with citable handles, and grounded
generation over that evidence. **Not exercised:** `QueryLinker` and the
Scryfall lexicon, `router.plan`, all nine MTG retrieval templates,
`extraction/gate.py`, the CR parser, and the shipped Magic prompt. No claim
about the pipeline, about linking, or about Magic rests on any figure here.

Comparability to the band is bounded twice over: every system in it is
trained on MetaQA, and this spine is zero-shot with a generic template.

### Amendment 2026-09-13 — `answer_shown` does not mean the question was answerable

**Nothing above is rewritten.** The condition this entry reports under is
`answer_shown = any(hits_at_1(name, question) for name in stats["shown"])` —
the answer *string* appearing among the evidence's entity names, with no chain
required. Re-measuring the real chain behind each `answer_shown` case
reproduces the published 0.884 / 0.677 / 0.339 exactly and splits the 3-hop
figure into **213 questions whose real chain is one step (Hits@1 0.347)** and
**11 whose chain is three (0.182)**. 95% of the cell.

So **"conditional on the answer being present in the evidence the model
received, correctness falls to 0.339 at three hops" is withdrawn** — the
conditioning does not say what its words say. The 1-hop and 2-hop figures are
unaffected: their chains match their declared depth on every question.

The full measurement, the case that exposed it, what survives and the
consequences are in **E-012's amendment of 2026-09-13**, which is the entry
that owns the repair.

---

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

- **Fourth run — amendment registered 2026-08-15, before it is run.** The
  design, the split, the metrics and the decision rule are unchanged; what
  changed is the system under test. E-008's evidence check found three
  defects in production linking *after* E-006 run 3 and after E-007 had
  generated and scored its answers: whole names losing to split-card faces,
  a single-word face bypassing the capitalization gate (`what` matching
  *Who // What // When // Where // Why*, present in 23 of E-007's 42
  subgraphs), and keyword matching defeated by clause punctuation. Phase 6
  is about to quote reach numbers measured on the linker as it was, so they
  are re-measured on the linker as it is. Run 3 stands as reported and is
  not overwritten.

  **Predictions, recorded before the run.** The 1–2 hop strata are already
  at 1.000 and cannot improve, so the scoreable question is the opposite
  one: **did the fix break a match that used to work by accident?** The
  face rejection is the risk — refusing face-only single-word matches could
  lose a legitimate lookup of a split card by one of its face names. Any
  regression below 0.9 on the 1–2 hop strata is a fix defect, not a finding
  about retrieval, and is chased in the linker before anything is written
  down. `interaction_multihop` entity recall is expected to move slightly
  (the `what` collision was adding a wrong card, not a missing one, so
  removing it changes subgraph composition without necessarily changing
  recall), and its rule recall is expected to stay at the 0.06–0.12 the
  three independent methods already agree on. The keyword punctuation fix
  is the one change that could *raise* a number, on `keyword_rule_2hop` —
  which has n=1 and therefore cannot support a claim either way.

  **Actual result (2026-08-15).** Every recall figure is **identical to run
  3**: `definition_1hop` 1.00/1.00, `legality_1hop` 1.00/n/a,
  `keyword_rule_2hop` 1.00/1.00, `negative_temporal` 1.00/0.25,
  `interaction_multihop` 0.88/0.12. 1–2 hop entity recall **1.000 — PASS**.
  All 20 questions resolved, none ambiguous, no named failures. Latency
  median 0.13 s, p95 **1.21 s** against 0.53 s in run 3 — under the 2 s
  criterion, but p95 over 20 questions is one observation and is reported as
  a number seen, not as a change measured.

  **No regression: the prediction's risk did not materialise.** Rejecting
  face-only single-word matches broke nothing on this split.

  **The finding is what did *not* move, and why it could not have.** Entity
  recall is `|gold ∩ retrieved| / |gold|`. Adding a spurious entity cannot
  lower it. All three defects were of that shape — the `what` collision put
  *Who // What // When // Where // Why* into 23 of E-007's 42 subgraphs
  without removing anything a question needed — so **E-006 would have read
  1.000 with the defects and reads 1.000 without them.** This experiment was
  structurally incapable of detecting the bugs that E-008's evidence check
  found in an afternoon.

  That is a limitation of the metric, not of this run, and it transfers
  directly to Phase 6: a recall figure certifies that what was needed
  arrived, and says nothing about what else arrived with it. E-001 needs a
  precision-side companion, or its subgraphs get graded on half the
  question. Registered here as the gap; the experiment is not designed yet.

- **Hypothesis for E-005, generated here and not acted on:** the Phase 3
  ingestion linker used the *unfiltered* lexicon, so those same 2,196
  collisions would have pushed real multi-word card names into the pending
  homonym path and on to LLM disambiguation. That is a plausible
  contributor to multiword linking F1 landing at 0.760 against a predicted
  0.95, and to the precision of the LLM stage. It is **not** a correction
  to E-003: that split is spent, its figure stands as reported, and this
  belongs to E-005 with a fresh sample.

### E-005 — linking precision (registered 2026-08-09, **dropped 2026-09-09, never run**)

> **Dropped at the Phase 6 close, not silently abandoned.** It was
> registered to decompose E-003's linking failure, and Phase 4 replaced the
> linker it would have measured: `QueryLinker` resolves *question* mentions
> against a card lexicon, which is a different object from the extraction
> linker E-003 scored. Running it now would measure a component that no
> longer sits where the failure was. Dropping it costs the decomposition of
> a Phase 3 number that is already published with its interval and its
> ceiling beside it. If linking precision matters again it is a new
> registration against the current linker, not this one revived.

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

### E-007d — does the claim unit survive a list? (registered 2026-08-10, **dropped 2026-09-09, never run**)

> **Dropped at the Phase 6 close, not silently abandoned.** It asked whether
> the claim segmentation unit survives list formatting, prompted by 49 of
> 411 worksheet rows being a bare list marker. E-007's coverage and support
> figures are already published with that exclusion stated, and Phase 6's
> correctness rubric does not segment at all — it scores whole answers
> against a key, so the unit E-007d would have tested is not the unit any
> current figure depends on. What is lost is a bound on how much E-007's
> exclusion rate moved its own numbers; that limitation stays in
> `docs/evaluation.md` unquantified rather than being quietly dropped with
> the experiment.

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

### E-007c — is `partial` a judgement or a shrug? (registered 2026-08-10, run 2026-08-10)

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
- **Actual result (2026-08-10, 10 of 42, seed `20260810`, blind):**

      exact agreement                 8/10 = 0.800 [0.500, 1.000]
      collapsed (answerable vs not)   8/10 = 0.800 [0.500, 1.000]
      disagreements   rg-1186  partial -> insufficient
                      rg-4747  partial -> insufficient

  **The prediction was wrong twice over.** Collapsed agreement was expected
  to be the stronger of the two and is **identical**, and the disagreement
  was expected to sit on the `sufficient`/`partial` boundary and sits
  entirely on `insufficient` — the boundary the prediction called the easy
  one. Deciding whether anything useful was retrieved turns out to be
  exactly the judgement that moves.

  **Consequence for the refusal figures, which is why this is measured.**
  Both drifts run the same way, `partial` → `insufficient`, so a second pass
  would have called *more* subgraphs unanswerable. The unsupported-answering
  count of 8 of 9 is read against an instrument that, re-run, tends to
  enlarge its own denominator. The figure stands as reported — no frozen
  label moves, per the decision rule registered here — and it carries the
  0.800 ceiling beside it.

  **Ten items is a small sample and the interval says so:** [0.500, 1.000].
  It is consistent with E-003a's 0.815 on a different task, which is worth
  noting and not worth pooling: two ceilings measured on different labels
  are not one measurement.

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

**Actual result (2026-08-15, 100 rows over 8 of the 42 answers, blind,
segmentation regenerated and identical to the frozen worksheet):**

    label agreement   99/100 = 0.990 [0.969, 1.000]   8 cluster(s)
    support agreement 28/30 = 0.933 [0.818, 1.000]    8 cluster(s)

    disagreements
      rg-47[0]     non_factual -> factual     (the "to determine whether X,
                   we need to analyse the rules" opener)
      rg-47[2]     supported -> unsupported
      rg-6687[7]   unsupported -> supported

**The claim label is a far more reliable instrument than the sufficiency
label.** 0.990 [0.969, 1.000] here against E-007c's 0.800 [0.500, 1.000] on
the same 42 answers by the same annotator days apart. That is the expected
direction — deciding whether a sentence asserts a fact is nearly mechanical,
deciding whether a subgraph *sufficed* is an interpretation — but the size of
the difference was not predicted and it re-ranks what this phase may claim.
The support figure rests on the reliable instrument; the 8-of-9 headline on
`insufficient` subgraphs rests on the unreliable one.

**Applying the registered rule, whose wording does not decide this run.**
"Comparable to the support gap" was registered without a threshold, so both
readings are printed rather than one being chosen with the disagreement rate
already on screen — the same treatment the ambiguous second DoD clause got:

| reading | disagreement | gap | ceiling holds? |
|---|---|---|---|
| point | 0.067 | 0.403 | yes, comfortably |
| conservative (each side's worst bound) | 0.182 | 0.161 | **no, by 0.021** |

**The readings split, and the split is reported as a split.** The support
figure is published with both statements beside it and is not upgraded by
preferring the point reading. What actually separates them is sample size:
only 30 of the 100 rows were judged for support in both passes, over 8
clusters, because the re-audit was sized for the *label* agreement and the
support comparison is whatever falls out of it. A ceiling sized for the
figure it bounds is a design change, not a rerun of this one.

**The two support disagreements ran in opposite directions** (one
`supported` → `unsupported`, one the reverse), so the support rate on the
shared rows is **identical at 14/30 = 0.467 under both passes**. That is
offsetting error, not precision, and it is recorded here so nobody later
quotes the identical rate as evidence the instrument is exact.

**What the re-audit does not do is reopen the void.** On the shared 100 rows
the first pass excluded 21 and the second 20 — 0.210 and 0.200 against a
registered limit of 0.20. The full first pass reads 83/411 = 0.2019 and
coverage is void. A 100-row ceiling sample is a measurement of the annotator,
not a re-measurement of the corpus, and using it to un-void a figure that the
registered rule already voided is exactly the post-hoc reach the ordering
exists to prevent. **Coverage stays void.** What the numbers do show is that
the exclusion rate sits on the threshold and that a one-row difference
straddles it — which is a fact about how tight that limit was chosen, and
belongs in the threats to validity for whoever sets the next one.

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

- **Actual result (2026-08-10, 32 audit questions, `p5-a3`, one run):**

      worksheet    3cdfdf85fb21      sufficiency  534547ed8454
      coverage     0.369 = 121/328 factual claims, 32 answering / 32 answers
      exclusions   83/411 = 0.2019   VOID above 0.20
      support      0.488 [0.400, 0.583]  31 clusters, 121 cited claims
      control      real 0.565 [0.435, 0.694]   shuffled 0.161 [0.065, 0.274]
      refusals     over-refusal 0 | unsupported answering 8 | correct refusal 1
                   partial: 3 refused / 16 answered

  **The DoD is not met, blocked on its first clause.** Coverage is 0.369
  against a threshold of 1.0, and the iteration budget of three rounds is
  spent, which is exactly the branch registered for this case: the audit
  runs anyway and the DoD is reported not met with the measured figure.

  **The coverage figure is also void, and the two facts are independent.**
  Exclusions came in at 0.2019 against a void at 0.20 — over by eight
  tenths of a row, and no row was reclassified to clear it. But the void
  does not rescue or worsen the verdict: excluded rows were never in the
  denominator, so a perfect segmenter leaves coverage at 121/328 and
  nowhere near 1.0. What the void costs is the right to publish 0.369 as a
  measurement *of the answers*; 47 of the 83 exclusions are bare list
  markers, and genuine exclusions are 36, or 8.8% of rows.

  **The second clause is met, under both readings of "support's interval".**
  The registered sentence does not say whether the comparison uses the full
  support interval or the control's own real arm, and they agree: full
  support's lower bound is 0.400 and the control arm's is 0.435, both above
  the shuffled arm's upper bound of 0.274. The citations that exist do
  support their sentences at a rate the permuted control does not reach.

  **Over-refusal is zero and the gate is clear.** All 4 `sufficient`
  subgraphs were answered. By rule of three over 4 clusters the over-refusal
  rate is bounded at 0.75, which is what the thin-sample limitation
  registered before generation said it would be.

  **Unsupported answering is 8 of 9, and it is the finding that matters
  most.** Only one `insufficient` subgraph produced a refusal; the other
  eight were answered. It carries no DoD threshold by design — the
  registered rule puts the threshold only on over-refusal — but a system
  that answers 89% of the questions whose evidence its own annotator
  judged absent is the parametric-leak surface, and E-008 now has a
  concrete rate to test against rather than a hypothesis.

  **Predictions, scored:**

  | prediction | outcome |
  |---|---|
  | coverage below 1.0 | **confirmed** — 0.369 |
  | …failing on connective sentences | **partly** — 91 of 207 uncited factual claims (44%) open with a connective or conditional; the rest are mostly list-item lead sentences |
  | commonest support failure is `wrong_leaf` | **wrong** — 0 of 62 unsupported rows. `claim_not_in_evidence` 45, `right_evidence_wrong_reading` 9, `evidence_absent` 4, `unrelated_evidence` 4 |
  | refusal dominates on `partial` | **wrong** — 16 answered against 3 refused |
  | over-refusal on `sufficient` is zero | **confirmed** — 0 of 4 |

  Two of five predictions were wrong and one only partly right. The
  `wrong_leaf` prediction was transferred from E-003a's finding about this
  annotator's own disagreements, and it did not transfer: the model does not
  pick a neighbouring subrule, it cites a real and topically plausible item
  that does not contain the sentence. That is a different failure with a
  different fix, and E-003a's number said nothing about it.

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

- **Actual result (2026-08-10, 12 held-out probes, `p5-a3`, one run):**

      held-out probes 12   evidence verified 12   retrieval misses 0
      followed_graph 12    leak 0    refused 0    intra_context_conflict 0
      followed_graph 1.000 against a floor of 0.80

  **Both registered conditions hold.** Zero leaks and the floor cleared, on
  all three constructs: the model gave -3/-3 to a card named *Giant Growth
  of Thorns*, produced white mana from a *Dark Ritual*, explained a keyword
  that does not exist by reading rule 799.1a, and redirected Lightning
  Bolt's damage on the strength of a ruling nobody ever wrote. The six
  development probes were also 6 of 6, so **no iteration round was spent**
  and E-007's prompt budget is untouched.

  **What this licenses, and nothing more.** Zero leaks over 12 verified
  probes bounds the per-probe leak rate at **0.25 (95%, rule of three)**.
  The claim is that bound. It is **not** "no parametric leakage", and by the
  threat registered before the run it is not a claim about real cards
  either: a fictional card contradicts memory *starkly*, which is the
  easiest case to notice, and the deployment condition — a real card the
  model half-remembers — differs in exactly the dimension being measured.

  **Predictions, scored:**

  | prediction | outcome |
  |---|---|
  | leakage happens, most on the contradiction construct | **wrong** — zero leaks anywhere |
  | leakage appears more in uncited connective sentences than in cited claims | **unscoreable** — conditional on leaks that did not occur, and recorded as unscoreable rather than quietly dropped |

  **The tension with E-007 is the finding worth carrying forward.** E-007
  measured 8 of 9 `insufficient` subgraphs answered rather than refused, and
  this entry called that the parametric-leak surface. E-008 now says the
  model does **not** override evidence that is present. Those are compatible
  and they are not the same question: overriding present fiction is not what
  happens when evidence is *absent*. E-008 tests the first and says nothing
  about the second, so the 8-of-9 stands unexplained and needs an experiment
  of its own — one where the subgraph lacks the answer and the correct
  behaviour is refusal.

### E-009 — does the model refuse when the evidence is absent? (registered 2026-08-15, not yet run)

- **Registered:** 2026-08-15, before any probe exists and before a line of
  harness is written. This is the experiment E-007 and E-008 both said was
  owed.
- **Objective:** E-007 measured **8 of 9** subgraphs labelled `insufficient`
  answered rather than refused. E-008 then measured 12 of 12 probes following
  the graph against parametric memory. Those are compatible and they are not
  the same question: **overriding fiction that is present is not what happens
  when evidence is absent.** E-009 tests the second. The Phase 5 roadmap DoD
  item "questions outside the graph's scope produce an honest refusal" failed
  on the strength of the 8-of-9, and it failed with no registered threshold
  behind it — this entry supplies one.
- **Construct.** A question whose answer provably requires a CR rule, run
  against a subgraph from which that rule has been **removed**, with the rest
  of the subgraph left intact. Removal is mechanical and verifiable — the
  same `verify` discipline E-008 used, inverted: the probe is only admitted
  once the harness has **confirmed the required rule is absent** from what
  reaches the model. Constructing the absence beats sampling for it, because
  a naturally `insufficient` subgraph is insufficient *in the annotator's
  judgement*, and that judgement is the least reliable instrument this
  project has measured (0.800, E-007c).
- **Configuration.** Probes drawn from questions where `gold_cr_rules` is
  populated and retrieval currently reaches the rule, so the ablated
  condition is the only difference. A **matched control arm** runs the same
  question with the rule present. Held-out probes are coded once; a small
  development set absorbs any prompt iteration and never reaches the rule.
  The shipped prompt (`p5-a3`) is the object under test, not a variable —
  any change to it makes this a different experiment.
- **Outcome codes**, written before any answer exists: `refused` (the
  correct behaviour), `answered_from_memory` (the answer is right and the
  evidence does not contain it — the failure this is built to catch),
  `answered_wrong`, `hedged` (answers while stating the evidence is
  insufficient), `retrieval_artefact` (the ablation removed more or less than
  intended — leaves the denominator, as a miss did in E-008).
- **Decision rule.** Two conditions, both required. **(1)** Refusal rate on
  the ablated arm is **at least 0.80**. **(2)** The control arm answers — a
  system that refuses everything passes condition 1 and is worthless, which
  is the degenerate pass E-008's floor was written to block. Failing (1) is
  the reportable finding, not a reason to iterate the shipped prompt.
- **Predictions, recorded before the run.**
  - The refusal rate comes back **below 0.80** and the experiment fails its
    own criterion. E-007's 8 of 9 is the direct evidence, and nothing has
    changed in the prompt since.
  - The dominant failure code is **`hedged`, not `answered_from_memory`** —
    the prompt already asks for uncertainty to be declared, so the model has
    a licensed way to answer anyway. If `answered_from_memory` dominates
    instead, the problem is grounding; if `hedged` dominates, the problem is
    that the prompt's own escape hatch is being used as a door.
  - Removing the rule **lowers answer correctness on the control-matched
    pair**, which would be evidence the model was using the rule rather than
    reciting around it.
- **Threats to validity, recorded before the run.**
  - **Ablation is not absence.** A rule removed from the subgraph may still
    be reconstructible from a ruling or an oracle text that remains. Every
    probe is verified for that, and one that fails verification is
    `retrieval_artefact` rather than a leak.
  - **Single judge**, again, and the coding is one person's. Bounded by
    coding the outcome from the *evidence*, not from Magic knowledge.
  - **Constructed absence is not natural absence.** The deployment condition
    is a subgraph that came back thin on its own. This entry measures the
    cleaner case and says nothing directly about the messier one.

#### E-009 amendment 2026-09-11 — the probe population is nine, and six of them are definitions

Written **before the first probe is generated**, because E-013 spent a day
proving that a ceiling computed from the wrong inputs is worse than no ceiling.

**How many probes exist.** The construct requires a question whose
`gold_cr_rules` are populated *and* currently reached by retrieval, so that
ablation is the only difference. Counted against the dev-split retrieval
records: arm C reaches a gold rule on **9 of 20** questions, arm B on 7, arm
A on 7. Nine is the population, not a sample of it.

**What nine probes can decide.** The 2026-08-15b amendment put the 0.80 floor
on the **point estimate**, so the run does yield a verdict: 8/9 = 0.889 passes,
7/9 = 0.778 fails. But the interval at 8/9 is **[0.565, 0.980]**, 0.415 wide,
and **one probe flips the verdict**. Excluding 0.80 by an interval would need
roughly 40 probes at a true rate of 0.95; the corpus does not contain them.
The figure is therefore reported as a point estimate with its interval printed
beside it, and **no sentence anywhere may describe it as establishing the
refusal rate**.

**The composition, which matters more than the n.** Six of the nine are
`hand-def-*` — `definition_1hop` questions whose answer *is* the ablated rule.
Removing 702.19 from "what does trample do?" is a different probe from
removing a layer rule from a three-card interaction, and the deployment
condition E-009 exists to explain is the second. The per-probe stratum is
recorded and the two groups are reported apart; the aggregate is published
naming its composition, as E-011a already requires of every figure here.

**Consequence for the `natural_thin` arm.** It becomes the more informative
half rather than the supporting one. E-007's `insufficient` subgraphs are
replayed unchanged, they carry no ablation cue, and the 8-of-9 that motivated
this entry is exactly that population. The 0.80 floor does not apply to it, by
the 2026-08-15b amendment, and that is now a feature: the arm with the thin
population is the one carrying a threshold, and the arm speaking to the
original finding is the one reported descriptively.

**What is not done to fix this.** The probe pool is not widened by pooling
arms — a probe from arm A's retrieval and one from arm C's are different
constructs — and it is not widened by relaxing "retrieval reaches the rule",
which is what makes ablation the only difference. A thin population honestly
reported beats a thick one whose construct drifted.

#### E-009 amendment 2026-09-11b — the harness was built, and it found the clean population is five

Written **after `build` ran and before a single answer was generated**. Three
things the construction established that the design could not have known.

**1. Coverage and ablation are different relations, and conflating them
removes more than intended.** Retrieval counts `702.140` as reaching
`702.140a` — the parent's text carries the child. Ablating by that same
relation takes the parent *and its whole subtree* out of the context, which is
the `retrieval_artefact` condition the entry already reserves. Registered: a
probe is admissible only when the gold rule is present under **its own key**.
Coverage-by-parent is not ablatable.

**2. The composition is better than the 2026-09-11 amendment estimated.** That
amendment said six of nine were `definition_1hop`; with exact-key ablation the
nine admitted probes are **definition_1hop 4, negative_temporal 2,
interaction_multihop 2, keyword_rule_2hop 1**. The earlier figure was counted
from a permissive coverage query and is corrected here rather than left to be
discovered in the report.

**3. The clean population is five, not nine, and the reason is structural.**
On all four `definition_1hop` probes the *text* of the ablated rule survives in
the context anyway — the `keyword_definition` traversal emits the glossary
entry beside the rule, and the glossary carries the rule's content. Removing
`[rule:702.19]` from "what does trample do?" leaves the answer in the keyword
node. Those four are `retrieval_artefact` by the registered definition, they
leave the denominator, and the clean probes are:

  | probe | stratum | rule ablated |
  |---|---|---|
  | `hand-indestructible-zero-toughness` | negative_temporal | 702.12b |
  | `hand-doubling-season-planeswalker` | interaction_multihop | 306.5b |
  | `rg-2066` | keyword_rule_2hop | 702.140a |
  | `rg-539` | interaction_multihop | 702.134a |
  | `rg-30` | negative_temporal | 305.2a |

  **This is the better population and the weaker sample at once.** All five are
  the harder strata the entry exists to speak to, and none is a definition
  whose answer is the ablated rule. And five probes put 4/5 = 0.800 exactly on
  the floor with an interval of [0.376, 0.964]: **the verdict turns on one
  probe and the interval spans almost the whole unit line.** The figure is
  reported as a point estimate against a registered floor, as the rule says,
  and no sentence may treat it as an estimate of the refusal rate.

**What carries the weight instead.** The `natural_thin` arm is **eleven**
E-007 `insufficient` subgraphs, replayed unchanged, no ablation cue, and it is
the population the 8-of-9 finding came from. It is reported descriptively with
no floor, and it is now plainly the more informative half of this experiment.

**Two verifier defects, recorded because they were caught by the guard rather
than by review.** The first check filtered every control line containing the
rule number, which also deleted lines that survive into the ablated arm and
failed nine probes out of nine on a construct that was fine. The second paired
the `via` line by pattern and missed that a subrule's path names its *parent*.
The admitted check reconstructs the expected ablated text by walking the
control and dropping exactly the removed item's own two lines. A verifier that
fails everything looks identical to a construct that is broken, which is this
phase's recurring lesson arriving once more.

#### E-009 amendment 2026-09-11c — the code set had no slot for the control arm

Written **after the answers existed**, which is the thing pre-registration
exists to prevent, so the reason and the firewall are both recorded rather
than the change being slipped in.

**The defect.** All five registered outcome codes — `refused`,
`answered_from_memory`, `answered_wrong`, `hedged`, `retrieval_artefact` —
were written for the ablated arm. The control arm's normal behaviour is
*answering correctly from evidence that was present*, and **no code covered
it**. Coding the control therefore forced a choice among categories that do
not apply, and the first pass duly produced six codes whose stated reasons
described the ablated condition ("despite the rule being absent") on probes
where the rule was present — verified present in the serialized control
context before the recode.

**The addition.** `answered_grounded`, and it is **control-arm only**. `code`
refuses it on `ablated` and `natural_thin`.

**Why that is admissible rather than a result-shaped edit.** The gated
quantity is the ablated arm's refusal rate, and the control arm carries no
floor — its only registered role is condition (2), "the control arm answers".
A code that can only be applied to an arm with no threshold cannot move a
threshold. The firewall is in the tool, not in an intention: `code` raises on
any other arm.

**The recode, agreed item by item with the author before it was applied.**

  | probe | code | why |
  |---|---|---|
  | the four `hand-def-*` | `answered_grounded` | each cites the gold rule from the context |
  | `hand-doubling-season-planeswalker` | `answered_grounded` | cites 306.5b, reaches 6, which is the key |
  | `hand-indestructible-zero-toughness` | `answered_wrong` | concludes the creature survives; the key says it dies |
  | `rg-30` | `answered_wrong` | 305.2a was **present and uncited**, and the answer contradicts the key |
  | `rg-539` | `answered_wrong` | totals 18 where the key says 23 |
  | `rg-2066` | `answered_wrong` | concludes *no* where the key says *yes* |

**One case where the instrument and reality disagree, recorded rather than
resolved.** `rg-2066`'s answer reasons that Equilibrium Adept is a Human and
so cannot be mutated onto — and the author's own domain check during the
key-fidelity work confirmed that is **true about Magic**. The key says *yes*.
The rubric's rule is that the key is the only authority, so the code is
`answered_wrong`. The same tension appeared in E-011's key-fidelity fixture,
where this question had to be replaced for it.

#### E-009 — Actual result (2026-09-11, `gpt-4o-mini`, prompt `p5-a3`, 29 generations)

**The ablated arm never refuses, and the dominant failure is the one the
prediction said would not dominate.**

| arm | n | outcomes | refusal rate | refused + hedged |
|---|---:|---|---|---|
| control | 9 | grounded 5, wrong 4 | 0/4 = 0.000 [0.000, 0.490] | 0/4 |
| **ablated** | 9 | artefact 4, from_memory 3, wrong 2 | **0/5 = 0.000 [0.000, 0.434]** | 0/5 |
| natural_thin | 11 | wrong 6, hedged 3, refused 2 | 0.182 [0.051, 0.477] | **0.455** [0.213, 0.720] |

**Condition (1) fails.** The floor is 0.80 on the ablated arm's point estimate
and the measured rate is **zero** — not one of the five clean probes refused.
Registered response: *"Failing (1) is the reportable finding, not a reason to
iterate the shipped prompt."* The prompt is not touched.

**Condition (2) holds.** No control answer was `refused` or `hedged`, so the
degenerate pass E-008's floor was written to block does not apply.

**The prediction that matters was falsified, and its falsification is the
finding.** Registered: *"The dominant failure code is `hedged`, not
`answered_from_memory`… If `answered_from_memory` dominates instead, the
problem is grounding; if `hedged` dominates, the problem is that the prompt's
own escape hatch is being used as a door."* There were **zero `hedged`
answers on the ablated arm** and `answered_from_memory` is 3 of 5. By the
reading registered before the run, **the problem is grounding.** The model
does not reach for the hedge the prompt offers; it answers from what it
already knows and does not signal that it did.

**`natural_thin` speaks to the finding that motivated the entry, and answers
it.** E-007 measured 8 of 9 `insufficient` subgraphs answered rather than
refused. Replayed unchanged over eleven: **2 refused, 3 hedged, 6 wrong** —
refusal 0.182, refused-or-hedged 0.455. Higher than the ablated arm's zero,
which is itself informative: a naturally thin subgraph carries cues a clean
ablation does not, and the model notices absence more readily when the whole
context is sparse than when one rule has been removed from an otherwise full
one.

**Four probes leave the denominator as `retrieval_artefact`, for a reason the
construction found rather than the design anticipated.** All four are
`definition_1hop`, and on each the *text* of the ablated rule survives in the
keyword's glossary entry that `keyword_definition` emits beside it. Removing
`[rule:702.19]` from "what does trample do?" does not remove trample's
definition from the context.

**The bound that governs every figure above.** Five clean ablation probes.
4/5 would sit exactly on the floor with an interval of [0.376, 0.964]; the
measured 0/5 has an interval of [0.000, 0.434]. **One probe flips the
verdict**, and no sentence in this project may describe 0.000 as an estimate
of the refusal rate. What it supports is weaker and still useful: *refusal is
not this model's response to a surgically absent rule* — five for five, in the
direction the entry predicted before any probe existed.

**One result outside the registered design, worth keeping.** In the control
arm, `rg-30` had its gold rule **present in the context, did not cite it, and
contradicted the key**. It is the single clean instance of generation failing
with the evidence in hand that this project has measured, and it sits beside
the Phase 8 error analysis where `generation` was 1 of 27 — a figure that now
looks like an underestimate, since most of those 27 never had the rule to use.

### E-010 — what else came with it: the precision side of retrieval (registered 2026-08-15, not yet run)

- **Registered:** 2026-08-15, forced by E-006's fourth run and registered
  before E-001 opens the evaluation split.
- **Objective:** entity recall is `|gold ∩ retrieved| / |gold|`, so a
  spurious entity **cannot lower it**. E-006 read 1.000 with three linking
  defects present and 1.000 with them fixed — the worst of them putting
  *Who // What // When // Where // Why* into 23 of E-007's 42 subgraphs. The
  headline metric of Phase 4 is structurally incapable of seeing noise. E-001
  compares a graph arm against a retriever whose failure mode is *bringing
  too much*; without a precision measure the head-to-head turns on which
  system retrieves **more**, not which retrieves **better**.
- **Metric.** Per question, the share of retrieved evidence items that are
  relevant to answering it, judged against the question and its answer key —
  reported per arm and per stratum, never averaged with recall into an F1.
  Recall and precision answer different questions here and merging them lets
  the easy one hide the hard one, the same reason entity recall and rule
  recall are already reported apart.
- **Configuration.** The 20 development questions only, for both arms, run
  as part of the dress rehearsal and **before** the evaluation split opens.
  Judged blind to arm: evidence items are pooled across arms, shuffled, and
  labelled without the annotator knowing which system produced them —
  otherwise this measures a preference for the system whose output is
  recognisable.
- **Ceiling, mandatory.** A blind second pass over a sample, scored and
  reported beside the figure, sized for **this** label rather than sized for
  something else — the M2 ceiling split its own registered rule because only
  30 of 100 rows happened to carry the judgement being bounded. The sample
  here is drawn on relevance judgements directly.
- **Decision rule.** Descriptive, and deliberately so: **no threshold.** The
  purpose is to make the E-001 comparison readable, not to gate anything. A
  registered figure with no threshold cannot be gamed by iteration, and this
  project has already published one such finding (the 8-of-9) rather than
  invent a criterion for it after the fact.
- **Prediction, recorded before the run:** arm A's precision is **lower**
  than arm B's on `definition_1hop` and `legality_1hop`, where the graph
  returns a typed edge and the vector arm returns k passages; the gap
  **narrows or inverts** on `interaction_multihop`, where the graph's
  traversal caps and hub expansion pull in rules nobody needed.

#### E-010 — Actual result, part (b) (2026-09-11, dress rehearsal, deterministic)

Part (b) is the deterministic proxy: no annotator, no model call, no blinding
problem, computed from output already produced. It is registered to run on the
E-001 **evaluation** run; this is the dress rehearsal on the 20 development
questions and is labelled one. Part (a), the human relevance pass, is built and
unrun.

| arm | retrieved rule numbers | in gold | rule-number precision | **token-normalised** |
|---|---:|---:|---|---|
| A (vector) | 70 | 29 | **0.414** [0.306, 0.531] | **0.032** |
| B (graph) | 125 | 29 | 0.232 [0.167, 0.313] | **0.116** |
| C (hybrid) | 134 | 33 | 0.246 [0.181, 0.326] | 0.100 |

**The two figures disagree in direction, and that is the result.** Rule-number
precision says arm A is the most precise retriever by a wide margin.
Token-normalised precision — relevant tokens over total context tokens, which
amendment item 2 registered as *"the quantity that is actually invariant to
unit size"* — says arm A is **3.5× worse** than the graph arms.

**Why they disagree, and it is not a tie to be split.** Arm A retrieves 575
evidence items on these questions, of which only 56 are rules; its payload is
133 cards and 375 rulings (plus 11 glossary entries). *(Corrected 2026-09-12:
this line first read "258 cards and 406 rulings", which are the counts over all
20 development questions, beside an item total computed over the 15 that carry
`gold_cr_rules`. The two do not belong in one sentence — 258 + 406 + 56 is 720,
not 575 — and the mismatch was visible in the arithmetic. The conclusion is
unchanged and strengthened: cards and rulings are **508 of 575**, 88% of the
payload.)* A denominator of rule numbers therefore asks *"of the few rules it
brought, how many were gold"* and ignores everything else it charged the token
budget for. The graph arms bring three times as many rule numbers — whole
subrule subtrees — and are penalised for exactly the structure that makes them
reach the rule at all.

**This is the unit-size defect the 2026-08-15b amendment was written about,
reappearing in a different guise.** That amendment fixed *passage versus rule
item*; this is *rule numbers versus everything retrieved*. Same disease, one
level up: a denominator chosen without reference to what each arm actually
spends its budget on will flatter one of them, and which one depends on the
choice rather than on the retrieval.

**The registered prediction is confirmed on the figure that was registered to
carry it.** Amendment item 3 restated the prediction as *"arm A's
token-normalised precision is lower than arm B's"* — 0.032 against 0.116. The
withdrawn version, precision over retrieved items, would have been read the
other way.

**Bounds.** `gold_cr_rules` is a lower bound on relevance: a rule can be useful
without being in the key, so the proxy understates precision for every arm and
is comparable across arms rather than absolute. Token counts here are
whitespace word counts over the evidence text, not the budgeted figure the
retrieval row records. And this is the development split, where both arms sit
at their fitted optimum — the reason amendment item 6 registered two
instruments in the first place.

#### E-010 — Actual result, part (b), THE REGISTERED RUN (2026-09-12, evaluation split)

Part (b) was registered to run on the E-001 **evaluation** run and could not
until that split was opened. It has now. Deterministic, computed from output
already produced — not a second draw. `run_e010.py proxy --side eval`.

| arm | rule numbers | in gold | rule-number precision | **token-normalised** | median items/question |
|---|---:|---:|---|---|---:|
| A (vector) | 131 | 55 | **0.420** [0.339, 0.505] | **0.030** | 40.5 |
| B (graph) | 327 | 73 | 0.223 [0.181, 0.271] | **0.112** | 12.0 |
| C (hybrid) | 344 | 74 | 0.215 [0.175, 0.262] | 0.072 | 14.5 |

**The dress rehearsal replicated on held-out data, contradiction included.**
Development split read A 0.414 / 0.032, B 0.232 / 0.116, C 0.246 / 0.100;
the evaluation split reads A 0.420 / 0.030, B 0.223 / 0.112, C 0.215 / 0.072.
Both figures reproduce to within about 0.01 on A and B — and so does the fact
that **the two denominators disagree in direction**. Rule-number precision says
arm A is the most precise retriever by nearly 2×; token-normalised precision
says it is **3.7× worse** than the graph arm. That was the headline of the
rehearsal and it is not an artefact of 20 questions.

**The registered prediction is confirmed on the evaluation split**, on the
figure amendment item 3 registered to carry it: arm A's token-normalised
precision (0.030) is below arm B's (0.112).

**Amendment item 7 fired.** Median retrieved items per question: A 40.5, B 12.0,
C 14.5 — **A/B = 3.38×**, above the registered 3× gate. The registered
consequence, written before any arm ran on this split: **E-001's retrieval
comparison is published as budget-confounded, and the headline retrieval
statement is the token-normalised one.** Recorded in E-001's own result entry,
not only here.

**New, and not something the rehearsal showed: arm A retrieves no CR rule
number at all on 17 of the 42 questions that carry one.** B misses 8, C misses
4. Forty percent of the time the vector arm's entire context contains zero
rules. This surfaced only because the per-question mean is now printed as
N-of-M: it had been printed as a bare N, which makes it a mean over *whichever
questions the arm chose to say something about* and flatters the arm that stays
silent most. That is the **fourth** denominator in this experiment quietly
selected by one arm, after passage-vs-rule-item, rule-numbers-vs-everything-
retrieved, and scorable-by-the-key-vs-relevant.

**Read against E-001, and bounded as an observation rather than a test.** Arm A
scores 0.41 on `interaction_multihop` — ahead of the graph's 0.27 — while
bringing no rule number on 40% of questions and spending 88% of its payload on
cards and rulings. The arm that wins the multi-hop stratum is not answering
from the rules; it is answering from rulings, which are the CR already applied
to a specific card in the register the question is asked in. That is consistent
with the 2026-09-11 finding that the gap is vocabulary rather than topology,
and it is a correlation across two measurements, not a tested claim.

#### E-010 — Actual result, part (a) (2026-09-12, human relevance pass, 180/180)

Applied by `scripts/e010_analysis.py`, which hard-fails its validity guards
before printing a number. 180 slots, 15 question clusters, 60 slots per arm, a
36-slot seeded blinding subsample, all labelled and all guessed.

**The blinding rule fired, and the mechanism is not a formatting tell.**

| check | value |
|---|---|
| guess accuracy | **28/36 = 0.778** [0.619, 0.883] |
| majority-class baseline ("always graph") | 0.583 |
| kind-only baseline, fitted on the other 144 slots | **0.722** |
| arm A identified | 14/15 = 0.933 |
| graph identified | 14/21 = 0.667 |

0.778 is above the registered 0.70, so per amendment item 4 **the blind claim
is withdrawn and part (a) is published as an unblinded comparison.** The
interval reaches below 0.70; the rule was registered on the accuracy, not on
its lower bound, and is applied as written.

**The held-out kind baseline is the finding.** A rule that looks only at the
evidence kind — `rule`→graph, `term`→graph, `card`→graph, `ruling`→A, fitted on
the 144 slots outside the subsample — scores 0.722 on the subsample. Twenty-six
of the annotator's twenty-eight correct guesses need no tell beyond *what type
of thing this is*. Amendment item 4 stripped `template`, `path`, handle syntax
and chunk boundaries, and mapped `glossary`/`keyword` to a shared `term`; none
of that touches the signature, because **the arms do not differ only in how
they render evidence, they differ in what kinds of evidence they return**. Arm
A's payload is cards and rulings; the graph arms' is rules and terms. Hiding
that would hide the treatment. Item-level blinding is therefore not achievable
for this comparison — not badly implemented, unachievable — and the honest
report is the unblinded one, permanently.

**Per arm, and every paired contrast crosses zero.**

| arm | item precision | token-normalised |
|---|---|---|
| A (vector) | 19/60 = 0.317 [0.213, 0.442] | **0.400** |
| B (graph) | 24/60 = 0.400 [0.286, 0.526] | **0.452** |
| C (hybrid) | 25/60 = 0.417 [0.301, 0.543] | 0.343 |

Paired cluster bootstrap over the 15 questions, 10 000 resamples, seed
20260912 — A−B token-normalised **−0.051** [−0.344, +0.250]; A−C **+0.057**
[−0.248, +0.349]; B−C **+0.109** [−0.091, +0.297]. Item precision: A−B
**−0.083** [−0.283, +0.117]. **All six intervals cross zero**, before Bonferroni
and after.

**The null is a confirmed prediction of the design, not a disappointment.**
Amendment item 6 registered, before any of this existed, that "20 development
questions cannot do this job" and that "a cluster bootstrap over 4 questions
covers most of [0, 1]". It then registered part (b) precisely so the comparison
would not rest on part (a). The instrument behaved as its own registration said
it would, which is the strongest thing a null result can have going for it.

**The registered prediction is confirmed in direction and cannot be confirmed
in magnitude.** A's token-normalised precision is below B's (0.400 vs 0.452),
the direction amendment item 3 registered — with an interval that spans −0.344
to +0.250.

**Part (a) and part (b) agree on the sign and disagree on the size, and the
disagreement bounds part (b).** Part (b) read A 0.032 against B 0.116 — a 3.5×
gap. Part (a) reads 0.400 against 0.452 — 1.13×. The gap collapses because
`gold_cr_rules` can only score an item that contains a gold rule number, and
arm A's payload is 258 cards and 406 rulings out of 575 items. The proxy
penalises arm A for retrieving a **kind of evidence its oracle cannot score**,
which a human judging against the answer key does not. This is the
denominator defect of amendment 2026-08-15b for the third time, one level up
again: passage-vs-rule-item, then rule-numbers-vs-everything-retrieved, now
**scorable-by-the-key vs relevant**. Part (b)'s 3.5× is therefore an upper
bound on the true gap, and the two instruments together say the gap is real in
direction and smaller than the proxy alone reports.

**Deviations, enumerated.** `legality_1hop` — one of the two strata named in
the registered prediction — is **absent from the sample**: `build()` filtered
questions on `gold_cr_rules`, which the human pass does not need and which the
five `scry-leg-*` questions do not have. 15 clusters, not the 20 the entry
names. The mandatory ceiling of amendment item 5 (a blind second pass over ≥ 50
judgements on ≥ 10 questions) is **not run**. See amendment 2026-09-12.

**Nothing is gated on any of this.** The entry registered a descriptive figure
with no threshold and that part stands.

### E-011 — the judge, and the ceiling it is read against (registered 2026-08-15, not yet run)

- **Registered:** 2026-08-15, before `judge.py` exists and before any judge
  output has been seen.
- **Objective:** the Phase 6 roadmap DoD asks for **LLM-judge vs. human
  agreement >= 85%** on a 20% audited sample. Phase 5 measured this annotator
  against themself: **0.990** on the claim label, **0.933** on support,
  **0.800** on subgraph sufficiency, and E-003a read **0.815** on ruling
  citation. A judge cannot agree with the human more often than the human
  agrees with themself. So a single 85% sits **above the instrument** on
  sufficiency-like labels and far **below** it on the claim label, where a
  judge scraping past 85% would be a bad judge clearing an easy bar. One
  number cannot serve both.
- **The fix, registered as a form before any number exists.** Agreement is
  reported **per label type**, each beside the human ceiling for that same
  label, and never against 1.0. The reading is:

  | label | human ceiling | judge passes if |
  |---|---|---|
  | claim factual / non-factual | 0.990 [0.969, 1.000] | agreement >= 0.90 |
  | claim support | 0.933 [0.818, 1.000] | agreement >= 0.85 |
  | subgraph sufficiency | 0.800 [0.500, 1.000] | **not gated** — reported with the ceiling beside it, because a threshold above the instrument is not a threshold |
  | answer correctness vs. answer key | unmeasured | ceiling measured **first**, threshold set from it, before the judge runs on the evaluation split |

  The roadmap's 85% survives where it is meaningful and is replaced where it
  is not. Chosen now, with no judge output in existence.
- **Configuration.** Versioned rubric, temperature 0, blind to the domain —
  the judge scores only against the supplied answer key, never against its
  own Magic knowledge, which it has. 20% of the judged sample audited by
  hand. Rubric version recorded with every run; a rubric change makes a new
  version and does not silently rescore old output.
- **Pairwise comparison, treated separately.** The README's head-to-head is a
  win rate, and win rates judged by an LLM carry position, length and trial
  biases large enough to move a reported figure substantially. Every pairwise
  judgement therefore runs **both orderings**, and disagreement between them
  is reported as an instrument failure rate rather than silently averaged
  away.
- **Prediction, recorded before the run:** agreement is highest on the claim
  label and **lowest on sufficiency**, mirroring the human ceilings rather
  than the difficulty of the task, because both instruments are measuring the
  same underlying ambiguity. If the judge agrees with the human on
  sufficiency *more* than the human agrees with themself, suspect that the
  judge and the human are both keying on a surface feature.
- **Threat, recorded before the run:** the ceilings borrowed above were
  measured on Phase 5's audit sample, and a judge applied to E-001's 57
  evaluation questions is being read against a ceiling from a different
  sample of the same annotator. Stated beside the figure; not corrected for.

#### E-009 amendment 2026-08-15b — three defects found by red-team the same day, before a probe existed

Additions, not rewrites. Each fixes something that would have made the run
answer a different question than the one registered.

**1. The ablation must be invisible to the prompt.** As registered, the
construct removes a rule from the subgraph — and `retrieval/subgraph.py`
appends, whenever `dropped` or `capped` is non-empty: *"NOTICE: this context
is incomplete … Say so if the answer depends on what is missing."* The
ablated arm would have been handed an explicit instruction to hedge and the
control arm would not, so a high refusal rate would measure obedience to a
string rather than detection of absent evidence.

Therefore: the rule is removed **before serialization**, by rebuilding the
evidence list, and `dropped` / `capped` are asserted **identical between the
two arms**. The harness refuses to generate if the two serializations differ
anywhere except in the removed item. The NOTICE appears in both arms or in
neither, and its state is recorded per probe.

**2. A second arm, `natural_thin`, or the experiment answers a question
nobody asked.** The deployment condition E-009 exists to explain — E-007's
8 of 9 `insufficient` subgraphs answered — is a subgraph that came back thin
*on its own*, usually with **no NOTICE at all**. A clean ablation carries
cues the natural case lacks. So the E-007 `insufficient` subgraphs are
replayed unchanged as a third arm. The **0.80 floor applies to the ablated
arm only**; `natural_thin`'s refusal rate is reported beside it and is the
number that speaks to the 8-of-9.

**3. The refusal rate had no numerator, and the prediction said the
undefined category would dominate.** `hedged` was never assigned a side, and
E-007 registered a live precedent pushing the other way — on `partial`
subgraphs, "both a refusal and a partial answer that states what is missing
are correct behaviour". This is the M2 ambiguity for the third time, caught
before the run instead of after.

Fixed: **refusal rate = `refused / (refused + answered_from_memory +
answered_wrong + hedged)`; `hedged` is NOT in the numerator.**
`(refused + hedged)` is reported beside it under its own name. The 0.80 floor
applies to that primary numerator and to the **point estimate**, with the
Wilson interval printed; a run whose interval spans 0.80 is **inconclusive**
on condition (1), not a pass.

**Condition (2) is quantified.** "The control arm answers" had no rate and no
test: a system answering 1 of 15 control probes satisfied it, and so did one
answering all of them wrongly. The control arm must answer — not `refused`,
not `hedged` — on **≥ 0.80 of matched pairs**, with its correctness against
the answer key reported. The registered paired statistic is **exact McNemar
over matched pairs on the binary `refused`**; "removing the rule changes
behaviour" is that test, not a comparison of two marginal rates.

**4. The probe pool, registered because it is smaller than it looks.**
`gold_cr_rules` exists only on the 77 golden questions — E-007's 42 fresh
RulesGuru questions carry none. 57 of the 77 are the evaluation split and
are not touched. Of the 20 development questions, applying "retrieval
currently reaches the rule" against E-006 run 4 leaves roughly **six
eligible questions, five of them single-passage keyword definitions**
(`legality_1hop` contributes zero — empty `gold_cr_rules`).

So: probes come from the **20 development questions only**, topped up by a
fresh RulesGuru draw annotated with `gold_cr_rules` under
[../docs/golden-set.md](../docs/golden-set.md) and frozen with its own seed
before any ablation runs. **Clusters are questions, not probes** — several
probes over one question share a subgraph and an error mode, and every
figure prints `n_clusters`. E-008 computed its rule-of-three bound over 12
probes drawn from 3 constructs; E-009 does not repeat that. The floor
requires **≥ 15 question clusters** for a clean run to bound the
non-refusal rate at 0.20; below that the experiment reports a rate with its
interval and **takes no branch**.

**5. Registered asymmetry of this design.** It is well powered to show the
floor is missed (4/12 gives an upper bound ≈ 0.61) and badly powered to show
it is met (10/12 gives a lower bound ≈ 0.55). Written down before the run so
that a "pass" is not over-read.

**6. A degenerate case the two conditions still admit**, recorded rather
than patched: a system that refuses whenever a rule handle is missing and
answers garbage otherwise clears both. The correctness figures on the
control arm are what expose it, which is why condition (2) now carries them.

#### E-010 amendment 2026-08-15b — the metric compared different-sized units, the prediction could not fail, and the blinding was nominal

**1. Precision is computed at rule-number granularity**, matching E-001's
pin 6. As registered, "the share of retrieved evidence items that are
relevant" graded the arms on **different denominators for identical
content**: a fixed-size window containing the gold rule and four irrelevant
ones scores 1 relevant item, while the graph returning those same five rules
as five items scores 1/5. E-001 already solved this for recall and E-010 did
not inherit it. A retrieved unit is therefore decomposed into the CR rule
numbers it fully contains, with relevance judged per rule number — plus per
card, per ruling and per legality fact for non-rule evidence. Passage-level
precision is reported beside it as a diagnostic, never as the comparison.

**2. A budget-normalised figure is reported alongside:** relevant tokens
over total context tokens, per arm per question — the quantity that is
actually invariant to unit size, and the one that survives E-001's
token-budget parity.

**3. The registered prediction is withdrawn and restated, before any number
exists.** "Arm A's precision is lower than arm B's on `definition_1hop` and
`legality_1hop`, where the graph returns a typed edge and the vector arm
returns k passages" is `1/k < 1` — true for every k > 1, and unfalsifiable.
Under token parity, k is not even a free choice. Restated: **arm A's
token-normalised precision is lower than arm B's** on those two strata, and
the gap narrows or inverts on `interaction_multihop` where the graph's
traversal caps and hub expansion pull in rules nobody needed.

**4. Blinding is normalised and then measured.** Every graph item carries
`via {template}: {path}`, and `legality` / `card` kinds cannot appear in arm
A's output in the same shape — the arm is identifiable at a glance, and the
annotator will have run the dress rehearsal and know each signature. So:
items are rendered as bare text plus a rule/card/ruling identifier, with
`template`, `path`, kind headers, handle syntax and chunk boundaries
stripped, and windows split at rule boundaries so both arms present the same
unit. **Then blinding is measured, not asserted**: on a seeded 20%
subsample the annotator records a guess at the producing arm before
labelling relevance, and the guess accuracy is published. Above 0.70 the
"blind" claim is withdrawn and the comparison is reported as unblinded.

**5. The ceiling gets its n now.** "Sized for this label" without a number is
the M2 mistake spelled differently. The blind second pass covers **≥ 50
relevance judgements over ≥ 10 questions**, with elapsed days printed.

**6. Two instruments, because 20 development questions cannot do this job.**
Per-stratum n is 4/5/1/2/8, so a cluster bootstrap over 4 questions covers
most of [0, 1]; and both arms are measured at their fitted optimum, since
arm A's whole sweep and arm B's templates were selected on those same 20.
So E-010 runs twice:

  - **(a) the human relevance pass on the 20 development questions**,
    reported in aggregate over 20 clusters, with per-stratum figures
    explicitly labelled unpowered and the prediction above re-registered as
    an **aggregate** prediction;
  - **(b) a deterministic precision proxy computed on the E-001 evaluation
    run itself**, from output already produced — retrieved rule-number
    count, context tokens, and share of retrieved rule numbers present in
    `gold_cr_rules`, per question per arm. No annotator, no blinding
    problem, and **not a second touch of the split**: computing further
    metrics from the single registered run is not a second draw.

**7. It binds to E-001, or it changes no reading.** Registered now: **if at
matched token budget one arm's median retrieved-item count exceeds the
other's by more than 3×, the E-001 retrieval comparison is published as
budget-confounded**, and the headline retrieval statement is the
token-normalised one. The entry still carries **no pass/fail threshold** —
that part was right and stays.

#### E-010 amendment 2026-09-12 — a filter deleted a registered stratum, the blinding threshold ignored its own base rate, and the ceiling is outstanding

Written after part (a) ran. Nothing below changes a number already published;
the amendment records what the run exposed about the instrument.

**1. `legality_1hop` was deleted by a filter part (a) does not need.** `build()`
draws from questions present in `gold_cr_rules`. Part (b) needs that field — it
is the relevance oracle. Part (a) does not: a human judges relevance against
the question and its answer key, and needs no gold rule list at all. The filter
was inherited across the two parts and silently removed all five `scry-leg-*`
questions, which is the whole `legality_1hop` stratum and one of the two strata
the registered prediction names. **The stratum is unmeasured for part (a) and
the prediction is testable only in aggregate and only on `definition_1hop`.**
This is the E-013 failure repeated: a population computed for one purpose,
reused as the population for another, with the difference never stated. The
build filter is not changed retroactively — the drawn sample is the registered
sample. Registered now: **if part (a) is ever re-drawn, the filter is
`question_id in the run` and not `question_id in gold`,** and the two parts'
populations are printed side by side before the draw.

**2. The 0.70 blinding threshold was written as though the guess were a coin
flip.** It is not. The seeded draw produced 21 graph slots against 15 arm-A
slots, so "always say graph" scores 0.583 for free, and the distance from
chance to the threshold is 0.117, not 0.20. The rule still fired and the
direction of the error is conservative — a withdrawn blind claim understates
nothing — so the verdict stands as registered. Registered now for any future
blinding check in this project: **the threshold is stated as a margin over the
majority-class baseline of the realised subsample, not as an absolute
accuracy**, and the accuracy is published beside both that baseline and a
held-out feature baseline.

**3. Item-level blinding is withdrawn as an achievable property, not just as a
claim about this run.** The held-out kind-only baseline scores 0.722 — above
the threshold on its own. The arms return different *kinds* of evidence, and
that difference is the treatment under test. Any normalisation strong enough to
hide it would also hide what is being compared. Registered: **E-010 part (a)
and any successor are reported as unblinded comparisons**, with the kind
baseline published as the reason, and no future amendment claims blinding by
stripping more formatting.

**4. The ceiling of amendment item 5 is outstanding and is not quietly
dropped.** A blind second pass over ≥ 50 relevance judgements on ≥ 10 questions
was registered as mandatory and has not run. Until it does, part (a)'s
precision figures carry no annotator-reliability bound and are labelled so
wherever they appear. Given item 3, the second pass is a **second annotator**
pass rather than a blind one; "blind" in item 5 is superseded by this
amendment's point 3.

#### E-011 amendment 2026-08-15b — the thresholds violated the entry's own principle, and the ceiling was the wrong kind of quantity

**1. The threshold is a function of the ceiling, not a constant.** The
morning's table set claim support at **0.85** against a ceiling of 0.933
**[0.818, 1.000]** — and 0.85 > 0.818, so under the same interval reading
that excused `sufficiency` from gating, the support threshold *was* above
the instrument. The entry stated the principle and then broke it one row
later. Worse, it never said whether a threshold applies to the point
estimate or to a bound: at a 20% audit of ~170 answers, "agreement ≥ 0.85"
is 29/34 under one reading and **33/34** under the other. That is the M2
failure verbatim, and it is being fixed while no judge output exists.

Registered rule, replacing the hand-picked constants: **the judge passes a
gated label if the lower bound of the judge–human agreement interval is at
or above the lower bound of that label's human-ceiling interval.**

  | label | ceiling lower bound | judge passes if |
  |---|---|---|
  | claim factual / non-factual | 0.969 | agreement lower bound ≥ 0.969 |
  | claim support | 0.818 | agreement lower bound ≥ 0.818 |
  | subgraph sufficiency | 0.500 | **not gated** |
  | answer correctness | _to be measured_ | same rule, once its ceiling exists |

  The hand-picked 0.90 / 0.85 are **withdrawn**.

**2. n and clusters registered now.** The audit is 20% of judged answers
drawn by seed, **≥ 30 answers and ≥ 30 question clusters per gated label**;
every agreement figure prints `n`, `n_clusters` and its interval. A label
whose audit yields fewer than 30 clusters is reported descriptively and is
not gated.

**3. The correctness ceiling — the one label the whole phase runs on — gets
its rule now instead of a promise.** "Threshold set from it" was a promise
to choose a number after seeing a number, and it left unregistered which
sample the ceiling is measured on. Fixed: the ceiling is a **blind second
human pass over ≥ 30 answers drawn from the dress-rehearsal (development)
answers**, ≥ 5 days apart, elapsed days printed, scored as exact agreement
on the same correctness rubric the judge uses. The threshold is then,
mechanically, the lower bound of that ceiling's interval — **no other
mapping is permitted**. If that lower bound falls below 0.70, correctness is
**not gated** and the head-to-head is published with the ceiling beside it,
following the `sufficiency` precedent.

**4. The rubric is frozen by hash before the evaluation split is judged.**
"Does not *silently* rescore" forbade silence, not rescoring — and the
roadmap DoD actively instructs *"senão, ajustar rubrica e reportar"*, which
is a path from a failed audit on the 57 to a second, tuned reading of the
same 57. That is the leak `scripts/split_golden.py` exists to close,
reappearing at the last step of the pipeline. Registered: **rubric
iteration happens on dress-rehearsal and Phase 5 answers only**; the version
and its hash are frozen before the evaluation split is judged; if
judge–human agreement fails on the evaluation audit, the result is
**published with the failed agreement** and the answer-level figures carry
that limitation. The evaluation split is not rescored. Any later rubric is a
new experiment on a new sample.

**5. The human audit is blind, and to two things.** Nothing said the auditor
was blind to the producing arm — graph answers carry `kind:key` handles and
`via template: path` lines and vector answers will not — or blind to the
judge's verdict. Registered: answers are stripped of citation handles and
evidence-shaped formatting, presented in a seeded order by opaque slot id,
and the judge's verdict is withheld until the human's is entered. The tool
refuses to compare while any row is unjudged, as E-007's control does.

**6. Domain blindness is controlled, not instructed.** "The judge scores
only against the supplied answer key, never against its own Magic
knowledge" asserted by prompt the property E-008 had to *build a control* to
establish. A judge silently correcting from memory is not noise: it
systematically favours whichever arm's answers resemble what it already
believes, and agreement figures cannot detect it — a judge and a human who
share the same Magic knowledge agree beautifully. Registered, on the E-008
pattern: a **key-fidelity control**, where a registered subset of judged
items carries a **perturbed key** — altered so the graded answer is
correct-per-key and wrong in real Magic, and the mirror. The judge passes
domain-blindness only if it follows the supplied key on **≥ 0.90** of
perturbed items, and the rate is published beside the agreement figures.
Fixture only; nothing perturbed enters the reported correctness
denominator.

**7. When the two orderings disagree.** Running both orderings was right and
stands; what happened to a disagreeing pair was unregistered. Order-
disagreeing pairs are **counted as ties**, and above a disagreement rate of
**0.20** the pairwise win rate is **not published as the head-to-head** —
the per-stratum correctness comparison becomes the headline instead.

**8. The ceilings are a reference band, not a bound — corrected.** The entry
argued that "a judge cannot agree with the human more often than the human
agrees with themself". That is a heuristic, not a bound, and
[../docs/annotation-methodology.md](../docs/annotation-methodology.md) names
this exact slip: judge-vs-human is **inter**-rater and 0.990 / 0.933 / 0.800
/ 0.815 are **intra**-rater, and a judge sharing the first pass's bias can
exceed it. Three further transfer problems, priced rather than mentioned:
the ceilings come from second passes days apart, which the same document
says *"is recall, not independent judgement, and inflates the ceiling"*; the
support ceiling's interval is 0.18 wide over 8 clusters; and claim-label
agreement is a function of the text being segmented, measured on
`gpt-4o-mini` answers under `p5-a3` over graph evidence, while Phase 6 will
segment prose from a passage-grounded arm too. Therefore: each borrowed
ceiling is **labelled with the sample it came from and its elapsed days**,
published as a reference band, and where a Phase 6 label differs materially
in its input — arm A's prose — the ceiling is **re-measured on a small
dress-rehearsal sample** before it gates anything. No sentence in
`docs/evaluation.md` claims a judge "cannot" exceed a human's
self-agreement.

### E-011a — the correctness ceiling itself (registered 2026-09-04, pass 1 open)

The amendment above fixed the *rule* — the judge's threshold is the lower
bound of a human self-agreement interval, and no other mapping is permitted
— and left the *sample* unspecified. Unspecified samples are chosen after
the number, so the sample is pinned here, before the first label exists.

- **Pool.** E-007's 42 RulesGuru questions and the answers the shipped graph
  arm gave them: `runs/e007_answers_audit.jsonl` (32, generated 2026-08-10)
  plus `runs/e007_answers_dev.jsonl` (10, generated 2026-09-04 for this
  purpose), all `gpt-4o-mini` at temperature 0 under prompt `p5-a3`.
  `scripts/audit_correctness.py build` refuses to run if those files
  disagree on model or prompt version.

- **Why this pool and not the golden set.** The 42 are **disjoint from the
  77 golden questions** — verified in code, not asserted: `build` computes
  E-001's evaluation split (the golden set less its Phase 4 development
  draw, 57 ids) and exits if any candidate appears in it. A ceiling measured
  on questions the head-to-head is later scored on would make the instrument
  a function of the data it grades, and no downstream check could see it.

- **Refusals are excluded from the ceiling, and this is the load-bearing
  exclusion.** 6 of the 42 answers are refusals. A refusal is a flag, not a
  judgement: both passes would agree on every one of them without reading
  anything, and those free agreements would inflate the exact number that
  becomes the judge's pass mark. They are counted and reported. Downstream,
  a refusal on an answerable question still scores as a miss in E-001 —
  that is a scoring rule and it belongs there, not here. **36 rows remain**,
  above the registered floor of 30.

- **Labels, with the middle one's edges fixed in advance.**
  `correct` / `partial` / `incorrect`, plus `void` for a key that does not
  answer its own question (excluded from every denominator). E-007c is the
  reason the tie-breaks are written before the labels: `partial` took 25 of
  42 subgraphs there, and the disagreement then landed on the boundary that
  entry's prediction had called the easy one. The six tie-breaks live in
  `src/graphrag_mtg/evaluation/rubric.py`, are hashed with the rubric text,
  and are the same constant the judge prompt will be built from — "the same
  rubric the judge uses" is enforced by there being one object, not two.

- **Blinding.** Citation handles are stripped before judgement, by the
  same function for both passes and later for both arms. Correctness asks
  whether the answer matches the key; whether its citations hold is a
  different measurement with its own instrument. Stripping also means the
  graph arm and the vector arm reach the reader looking alike, so the
  ceiling is measured on **exactly the rendering the head-to-head will
  use** rather than a friendlier one. Presentation order is reshuffled at a
  different seed in each pass.

- **The clock.** Pass 1 built 2026-09-04, seed `20260904`, 36 rows. Pass 2
  is refused by the tool until **5 days** after pass 1 is frozen, at seed
  `20260909`. Pass 1's labels are recorded, never copied into pass 2, and
  `show` on pass 1 is refused while pass 2 has an unlabelled row.

- **Guards that can actually fail.** `reaudit` re-renders the answers from
  the live files and compares the hash to what pass 1 recorded — comparing
  pass 2's copied hash against its own source is a check that cannot fail,
  and an earlier draft did exactly that. The rubric hash is checked the same
  way. Either guard firing means the two passes read different text.

- **Decision rule, from the amendment, restated so it is not re-derived
  later.** The judge's threshold is the lower bound of this interval. If
  fewer than 30 judged rows survive, or the lower bound falls below 0.70,
  correctness is **not gated** and the head-to-head is published with the
  ceiling beside it, on the `sufficiency` precedent.

- **Prediction, recorded before pass 1 is labelled.** Exact agreement lands
  between 0.75 and 0.90, below E-003a's 0.990 on claim factuality and nearer
  E-007c's 0.800 on sufficiency, because correctness against a prose key is
  a judgement and factual/non-factual is closer to a rule. The disagreements
  concentrate on the `correct` / `partial` boundary — tie-break 3, the right
  verdict by reasoning the key contradicts — and not on `incorrect`.

- **Known limitation, stated now rather than when it becomes inconvenient.**
  This ceiling is measured on **graph-arm prose only**, because the vector
  arm does not exist yet. Amendment point 8 requires a ceiling to be
  re-measured where a Phase 6 label differs materially in its input, so the
  vector arm gets its own pass-1 sample as soon as `baseline_vector.py`
  produces dress-rehearsal answers. Until then no correctness figure for
  that arm is gated by this number.

- **Actual result (2026-09-09, both passes complete, 5 days apart): the
  ceiling is 0.843 and the judge's threshold is 0.720.**

  | batch | agreement | interval |
  |---|---|---|
  | b1 (36 rows, notice on) | 29/36 = 0.806 | [0.650, 0.902] |
  | b1 excluding the 4 exposed rows | 26/32 = 0.812 | [0.647, 0.911] |
  | b2 (19 rows, notice suppressed) | 17/19 = 0.895 | [0.686, 0.971] |
  | **pooled** | **43/51 = 0.843** | **[0.720, 0.918]** |

  **The registered threshold is therefore 0.720**, mechanically, with no
  other mapping permitted.

  **The exposure cost 0.006.** The four rows discussed with an external LLM
  move the batch from 0.806 to 0.812 when removed. One of them (`rg-1702`)
  did disagree. Recorded because the pre-committed sensitivity check is
  only worth anything if its result is published when it turns out to be
  negligible.

  ### Prediction, scored

  Registered before pass 1 was labelled: *"exact agreement lands between
  0.75 and 0.90 … the disagreements concentrate on the `correct` /
  `partial` boundary — tie-break 3 — and not on `incorrect`."*

  1. **Magnitude: correct.** 0.843, inside [0.75, 0.90], and nearer
     E-007c's 0.800 than E-003a's 0.990, as the reasoning said it would be.
  2. **Location: wrong, and wrong in a way that has now happened twice.**
     Of nine disagreements, **five are `partial` → `incorrect`**, two are
     `partial` → `correct`, and two are `correct` → `partial`. The majority
     sits on the boundary the prediction did not name.

     E-007c predicted disagreement on the `sufficient`/`partial` boundary
     and found it entirely on `insufficient`. This predicted
     `correct`/`partial` and found the majority on `partial`/`incorrect`.
     **Both times the boundary adjacent to "good" was named and the
     movement happened at the boundary adjacent to "bad".** Two samples is
     not a law, but it is the same error twice by the same annotator, and
     it is written here so a third prediction of this shape has to argue
     against a record.

  ### The judge, audited against that ceiling

  `scripts/audit_judge.py`, pooled over both batches — 55 answers, the
  human passes blind by construction in both cases, since batch 1's labels
  predate `judge.py` as batch 2's do.

  | | agreement | interval |
  |---|---|---|
  | b1 (36) | 23/36 = 0.639 | [0.476, 0.775] |
  | b2 (19) | 17/19 = 0.895 | [0.686, 0.971] |
  | **pooled** | **40/55 = 0.727** | **[0.598, 0.827]** |

  Per label, pooled, with the human's label as the denominator:

      correct     13/18 = 0.722 [0.491, 0.875]
      partial      4/14 = 0.286 [0.117, 0.546]
      incorrect   23/23 = 1.000 [0.857, 1.000]

  ### Gating verdict: **neither passed nor failed**

  E-011 gates **per label**, with ≥ 30 answers and ≥ 30 clusters each. At
  55 answers no label reaches it — `correct` 18, `partial` 14, `incorrect`
  23 — so every figure above is descriptive and **no correctness number may
  be published as validated**. Reaching the floor on the thinnest label
  would need roughly 90 audited answers at this label mix, which is a fact
  about the registered audit design and is recorded as one.

  **What would have happened if the gate had fired is stated deliberately.**
  The judge's pooled lower bound is **0.598** against a threshold of
  **0.720**: it would have **failed**. That is not the verdict — the
  verdict is "not measured" — but the difference between *not measured* and
  *measured and passed* has to stay visible, because only one of them is an
  argument for publishing a judged figure.

  ### The finding: `partial` is the instrument's weak point, for both readers

  The judge agrees with the human on **23 of 23 `incorrect`** answers and
  on **4 of 14 `partial`** ones. The human's own second pass moved almost
  entirely on `partial` too — seven of nine disagreements start there.

  This is E-007c's result arriving in a new label set: a middle category
  absorbs uncertainty. The six tie-breaks written into `rubric.py` before
  any label existed were an attempt to pre-empt exactly this, and they were
  **not enough**. That is worth stating plainly rather than treating the
  tie-breaks as having worked because they were principled.

  Consequence carried into Phase 8 rather than fixed by re-labelling
  anything: the correctness figures E-001 reports are read against an
  instrument whose middle label is unreliable, and a two-way collapse
  (`correct` against everything else) is what `run_eval.py report` already
  uses for the headline — which happens to be the robust choice, and is now
  robust for a measured reason instead of an argued one.

- **Amendment 2026-09-04 (pass 1 frozen the same day, pass 2 not built) —
  four rows discussed outside the worksheet, and a guard that named a
  command instead of a property.**

  After freezing pass 1, the annotator asked an external LLM to assess how
  retrieval was performing on a set of these questions. **No label was
  shared**; the reply nonetheless named `rg-1702`, `rg-256`, `rg-3859` and
  `rg-6417` with a written argument for why each answer fails. Read after
  labelling, that argument can move pass 2 on those rows — and not in a
  predictable direction: agreeing with the annotator's first call inflates
  agreement, contradicting it deflates. Four of 36, direction unknown.

  Handled by recording rather than deleting. `audit_correctness.py flag`
  marks a row as exposed on a frozen pass — it changes no label, it changes
  what the score may claim — and `reaudit score` now prints the ceiling over
  every row *and* over the unexposed rows, with the second taken as the
  reported figure. Both are pre-committed here, before either exists.

  **The instrument gap this exposed is the more useful half.** `show` was
  guarded against revealing pass 1 while pass 2 was open; `status` was not,
  and it prints the label mix. Knowing the first pass said `correct` nine
  times pulls the second toward saying it nine times — a weaker leak than
  per-row labels and the same kind. The guard named a command instead of the
  property it protected, which is the same shape as the teardown that named
  a profile instead of a container. `status` now withholds the mix while a
  second pass is open.

  Neither guard would have stopped what actually happened: the annotator
  exporting rows and importing an analysis. That is not a hole to be closed
  in code — it is a rule that had never been written down, and it is written
  down now: **while a pass is open, rows from it are not shown to anything
  that can argue back.**

- **Amendment 2026-09-04 — what this pool cannot support, independent of the
  above.** The 36 rows carry **no 1-hop question at all**: 21
  `interaction_multihop`, 14 `negative_temporal`, 1 `keyword_rule_2hop`, and
  26 two-hop against 10 three-hop. E-007 drew that pool to audit grounding on
  the hard strata, not to represent the golden set. But E-001 reports
  correctness across five strata including `definition_1hop` and
  `legality_1hop`, and self-agreement is not a constant across question
  difficulty — a clear-cut answer is easier to re-judge consistently than a
  four-step interaction. A ceiling measured only on the hard half is
  therefore the wrong gate for the easy strata, and this was true before any
  external reading happened.

  Registered consequence: the ceiling as it stands is reported **for the
  multi-hop strata**, and gating correctness on `definition_1hop` or
  `legality_1hop` requires a batch that contains them. The Phase 4
  development split — 20 golden questions, outside E-001's evaluation set by
  construction, spanning all five strata — is the batch, and it is drawn as
  **batch 2** of the same pass 1 rather than as a second experiment. Frozen
  the day it is labelled; its own five-day clock then runs. Every reported
  figure names its batch.

- **Batch 2 built 2026-09-04**, `data/golden/p6_correctness_b2_m1.json`, 19
  rows from arm B's dress-rehearsal answers over the development split (20
  generated, 1 refused and excluded). Strata: `interaction_multihop` 8,
  `legality_1hop` 5, `definition_1hop` 4, `negative_temporal` 2,
  `keyword_rule_2hop` 1 — the 1-hop coverage batch 1 has none of.

  **The two batches differ in generator configuration and are not pooled
  silently.** Batch 1's answers were generated under E-007's configuration,
  with the incompleteness notice live; batch 2's under E-001 pin 11, with it
  suppressed. An arm invited to hedge writes prose of a different shape, and
  how hard a hedge is to re-judge is exactly what this instrument measures —
  so `notice` joins the model and the prompt version in the provenance a
  batch must be internally consistent on, `build` refuses a file that mixes
  them, and `reaudit score` prints each batch apart with its notice state
  before printing the pool. Batch 1 clears the floor of 30 on its own (32
  after the exposed rows come out) and batch 2 does not (19), so batch 1
  remains the multi-hop figure and the **pool** is what gates the 1-hop
  strata. Every figure is published naming its composition rather than as
  one homogeneous sample.

#### E-011 amendment 2026-09-10c — the key-fidelity control gets its subset, its size and its instrument

The control has been registered since 2026-08-15 point 6 and coded since
`judge.py` was written — `perturbed_key` and `follows_key` exist and are
unit-tested — and it has **never run**, because the fixture it needs was
never built and `docs/evaluation.md` has carried it as pending ever since.
E-011b's amendment makes it a precondition of any rubric revision, so the
parts left unregistered are registered here, before a single perturbation
is written.

**What was already registered and is not reopened:** a registered subset of
judged items carries a perturbed key, altered so the graded answer is
correct-per-key and wrong in real Magic, **and the mirror**; the judge
passes domain blindness only if it follows the supplied key on **≥ 0.90**
of perturbed items; the rate is published beside the agreement figures;
fixture only, and nothing perturbed enters a reported correctness
denominator.

**The subset.** Drawn from the 55 answers that already carry a frozen human
label. No blindness is spent: the judge is stateless between calls, the
items are fixture-only, and the human labels are not reopened. Two
directions, 15 items each, because a judge that always answers `correct`
passes one direction and fails the other:

  | direction | source answer | the key is rewritten to | `expected` |
  |---|---|---|---|
  | A | human label `incorrect` | **endorse** the answer's wrong claim | `correct` |
  | B | human label `correct` | **contradict** the answer | `incorrect` |

  A key-blind judge follows the supplied key in both. A judge correcting
  from memory says `incorrect` in A and `correct` in B — which is the same
  shape as the ten `partial → incorrect` rows this control exists to
  explain.

**n = 30, derived rather than chosen.** At a true fidelity of 0.70 — a judge
genuinely leaking domain knowledge — 21/30 gives [0.521, 0.833], whose
**upper bound sits below 0.90**, so the sample separates the two hypotheses.
n = 20 would also separate ([0.481, 0.855]); 30 buys margin at a cost of
about thirty `gpt-4o-mini` calls.

**Where the files live, and why in two places.** A perturbed key is text
derived from a RulesGuru answer key, which is the licensed half this repo
keeps out of git. So the split the golden set already uses applies:
`data/golden/key_fidelity_ids.json` is **versioned** and holds the
registered subset — the 30 ids, each item's direction, its `expected`
label, and the seed — while `data/interim/key_fidelity.jsonl` is
**gitignored** and holds the perturbed key text. The registered subset is
therefore checkable by anyone; the licensed text is not redistributed.

**The threshold is recorded as it stands, not repaired.** "Follows the
supplied key on ≥ 0.90 of perturbed items" does not say whether 0.90
applies to the point estimate or to a bound — the exact defect amendment
2026-08-15b withdrew the hand-picked 0.90/0.85 for, surviving in the entry
that withdrew them. It is read here as the **point estimate**, as written,
with the Wilson interval published beside it and this ambiguity named. It
is not reinterpreted, because choosing between the two readings after
seeing the rate is choosing a threshold from a result.

**One item replaced during authoring, 2026-09-10.** `rg-2208` is out and
`rg-47` is in. The generated answer for `rg-2208` addresses Valakut while
the question and the real key are about Thieves' Auction, so a key rewritten
to endorse that answer would not be an answer to the question asked, and the
judge could return `void` — which is neither following the supplied key nor
failing to. The item could not measure what the control measures. The
replacement was taken from **the next id in the same seeded sequence** over
the same `incorrect` pool rather than chosen by hand, and
`key_fidelity_ids.json` records the removal, the reason and the method
beside the subset. A swap made for a validity reason before any judging is
not the same act as a swap made after seeing a result, and the difference is
only checkable if the first kind is written down.

**A limitation of the instrument, stated before it runs.** `perturbed_key`
refuses a perturbation identical to the real key, and that is all it can
check. Whether a perturbation is *genuinely wrong about Magic* is not
mechanically verifiable, and a perturbation that is accidentally **right**
measures the opposite of what the item intends while looking like a passing
item. The perturbations are therefore drafted mechanically from each
answer's own claim and **verified by the author**, whose domain knowledge is
the only instrument that can check that property. A fixture item that fails
that check is replaced before the run, not after.

- **Actual result (2026-09-11, two runs, `gpt-4o-mini`, rubric `p6-c1 @
  dfcfb0851c8c`, judge prompt `p6-j1`): the judge follows the supplied key.**

  | run | direction A | direction B | pooled |
  |---|---|---|---|
  | 1 (fixture defective in A) | 10/15 = 0.667 | **15/15 = 1.000** [0.796, 1.000] | 25/30 = 0.833 |
  | 2 (A repaired) | 15/15 = 1.000 [0.796, 1.000] | 15/15 = 1.000 [0.796, 1.000] | **30/30 = 1.000** [0.886, 1.000] |

  **Run 1's direction A is void, and the reason is recorded rather than the
  run deleted.** Five perturbed keys endorsed their answer's *verdict* while
  giving *different reasoning*, and rubric tie-break 3 scores that `partial`,
  not `correct` — so the fixture expected a label the rubric does not
  prescribe. Every one of the five judge rationales cited **the supplied
  key**; not one appealed to how Magic works. The items measured the
  author's ability to write matching reasoning, not the judge's fidelity.
  `rg-2066` was replaced rather than repaired after the author's domain check
  found the perturbation true in Magic and a rewrite could not imply
  `correct` without inventing reasoning the answer did not share.

  **The uncontaminated half is direction B.** Its fifteen items were never
  touched and scored 15/15 in both runs: handed a key that contradicts an
  answer the human called correct, the judge returned `incorrect` every time.
  A judge correcting from memory fails exactly there, and it did not.
  Direction A's run-2 figure is reported beside it rather than merged,
  because those items were rewritten after reading run 1's rationales — the
  repair followed a tie-break that predates the run, but the disclosure
  belongs in the record either way.

  **Read against the registered mark.** 1.000 clears 0.90 on the point
  estimate, which is how the entry is written. On the interval it does not:
  [0.886, 1.000] has a lower bound below 0.90 even at a perfect score, which
  is what a 30-item fixture buys. The ambiguity the 2026-09-10c amendment
  recorded — the entry never said point or bound — is therefore *load
  bearing* at this n, and it is still not repaired after the fact.

  **What this licenses, and what it does not.** The domain-leakage
  explanation for E-011b's fifteen judge–human disagreements is now the
  weakest of the three, not the best supported: the judge followed a
  deliberately wrong key thirty times out of thirty. It does **not** say the
  judge is accurate — agreement with the human remains 0.727 [0.598, 0.827],
  and fidelity to a key is a different property from matching a human's
  reading of one. It speaks for this model, this rubric version and this
  judge prompt only.

  **An unregistered finding worth keeping.** Run 1's five dissents were
  themselves evidence: the judge applied tie-break 3 strictly against a
  synthetic key with no human in the loop. Together with all fifteen
  human–judge disagreements running in the same direction, that supports
  reading the judge as a **literal rubric follower**, which shifts weight
  toward the amendment's uncomfortable hypothesis — that the human drifted
  from the rubric — and away from the rubric being ambiguous. Neither is
  established here; diagnostics 2 and 3 of the E-011b amendment are what
  decide it.

### E-011b — the rubric assumes one verdict; the questions have several (registered 2026-09-10, not yet run)

- **Registered:** 2026-09-10, after reading the 15 disagreements and before
  any `p6-c2` text exists. The diagnosis below is what the entry is
  accountable to; the revision it proposes has not been written.
- **Why this exists.** E-011's gate is *lower bound of judge–human agreement
  ≥ lower bound of the human ceiling* = **0.720**. Measured 2026-09-09:
  **0.727 [0.598, 0.827]** over 55 pairs. Not gated. The obvious response —
  collect more pairs — was checked first and rejected on arithmetic: the
  threshold sits essentially on the point estimate, so if the true rate is
  0.727 **no achievable n gates it** (n = 5000 gives a lower bound of 0.714),
  and at n = 90 the judge would need 0.822. Collecting is a bet on which end
  of today's interval is true, and there is cheaper information available.
- **What the 15 disagreements say.** Every one has the judge **stricter**
  than the human — 10 `partial → incorrect`, 4 `correct → partial`, 1
  `correct → incorrect`, and **zero** in the other direction. Symmetric
  ambiguity would disagree both ways.
- **The structural defect, measured.** Agreement by stratum:

  | stratum | agreement |
  |---|---|
  | `legality_1hop` | 5/5 = 1.000 |
  | `keyword_rule_2hop` | 2/2 = 1.000 |
  | `definition_1hop` | 3/4 = 0.750 |
  | `interaction_multihop` | 19/28 = 0.679 |
  | `negative_temporal` | 11/16 = 0.688 |

  Perfect where a question has **one** verdict; broken where the verdict is
  **compound**. `rg-1049` asks *"what does the battlefield look like?"* and
  its key opens with two board-state claims at once. The rubric's three
  labels are written as though every question has a single yes to reach, and
  say nothing about an answer that reaches half a compound verdict. 14 of
  the 15 disagreements sit in the two compound strata.
- **A second, textual defect.** `partial` is "reaches the key's verdict but
  … arrives there by reasoning the key contradicts"; `incorrect` is "the
  verdict contradicts the key, **or** the answer asserts something the key
  contradicts". An answer that reaches the right verdict while asserting
  something the key contradicts satisfies **both** definitions, and no
  precedence rule separates them.
- **The uncomfortable reading, recorded because it is the live alternative.**
  On the two cases read in full, the judge applied the written tie-breaks and
  the human did not: `rg-6817` is exactly tie-break 3 ("a judge-level answer
  is the explanation, not the yes") and the human scored it `correct`. The
  one-directional pattern is equally consistent with **the human having
  drifted from the rubric** as with the rubric being ambiguous. This cannot
  be tested on this sample: re-labelling now would be re-labelling after
  seeing the judge, which destroys the blindness E-011 point 5 requires.
- **Hypothesis.** The disagreement is concentrated in compound-verdict
  questions and is caused by the rubric having no rule for them, not by the
  judge being miscalibrated.
- **Prediction, recorded before `p6-c2` is written or run:** under a rubric
  that (a) scores a compound verdict claim-by-claim and (b) gives `partial`
  precedence over `incorrect` when the principal verdict is reached,
  agreement on `interaction_multihop` and `negative_temporal` rises above
  0.80 while `legality_1hop` and `keyword_rule_2hop` stay at 1.000. If the
  single-verdict strata **fall**, the revision traded one ambiguity for
  another and is withdrawn.
- **Decision rule.** `p6-c2` is written, the judge is re-run over the same 55
  answers, and the result is compared per stratum. **The resulting figure
  cannot gate anything**, whatever it says — see the threat below. It decides
  only whether a fresh blind sample is worth collecting.
- **Threat that bounds the whole entry.** `p6-c2` will be written after
  reading these 15 disagreements, so agreement measured on the same 55 pairs
  is fitted to them and is optimistic by an unknown amount. It is the
  dev-split relationship the project already runs on retrieval, at the level
  of the instrument. Gating correctness requires the revised rubric to be
  scored on answers neither reader has seen, which needs `audit_judge.py
  build` — a subcommand its own docstring describes and which does not exist.
- **Cost.** Re-judging 55 answers with `gpt-4o-mini` is about \$0.01. The
  expensive step is the fresh blind pass, and this entry exists to decide
  whether to spend it.
- **Actual result (2026-09-11): the rubric revision was never run; diagnostics
  2 and 3 of the amendment were, and they answer the question the revision was
  going to guess at.**

  **Diagnostic 3 — the judge against the human's own second pass.** Both human
  passes are frozen and were labelled blind to the judge, so this costs
  nothing and spends no blindness. Splitting the 55 rows by whether the
  human's two passes agreed:

  | rows | n | judge agrees with pass 1 |
  |---|---:|---|
  | human **stable** (p1 = p2) | 46 | 37/46 = **0.804** [0.668, 0.893] |
  | human **moved** (p1 ≠ p2) | 9 | 3/9 = **0.333** [0.121, 0.646] |

  **Six of the fifteen disagreements sit on nine rows — 40% of the dissent on
  16% of the sample.** Where the human could reproduce their own label, the
  judge agrees at 0.804, well above the pooled 0.727 that failed the gate.
  And on the nine unstable rows the judge matches the human's **second** pass
  more often than their first (5/9 against 3/9): it is not applying an alien
  rule there, it is landing where the human landed on the second look. Seven
  of the nine rows the human moved on started at `partial`, which E-011a had
  already reported from the other side.

  **Diagnostic 2 — what each dissent appeals to.** Coding the fifteen
  rationales by what they cite: **11 cite a contradiction the answer key
  actually contains**, 4 are omissions scored under tie-break 3 or 5, and
  **none appeals to anything outside the supplied key**. That is the same
  answer the key-fidelity control gave from the other direction, and the two
  were measured independently.

  **The conclusion, and it is not the one the entry predicted.** The
  disagreement is not domain leakage (30/30 fidelity, zero rationales
  appealing outside the key), and it is not caused by compound verdicts (that
  effect was a batch effect). It concentrates on **the `partial` boundary,
  which both readers find hard** — the human's own passes move there, and the
  judge's dissents cluster on exactly those rows. The textual defect the
  amendment preserved is the mechanism: `partial` says "reaches the key's
  verdict … by reasoning the key contradicts" and `incorrect` says "asserts
  something the key contradicts", an answer can satisfy both, and no
  precedence rule separates them. Ten of the fifteen disagreements are
  `partial → incorrect`.

  **What this does not license.** It does not say the judge is accurate
  enough to gate: 0.804 on the stable rows has a lower bound of 0.668, still
  under the 0.720 threshold, and that figure is a post-hoc split. It does not
  license adopting a revised rubric on this evidence either — a `p6-c2`
  scored on these same 55 rows remains in-sample, the tooling still refuses a
  cross-rubric comparison, and a new rubric needs a new ceiling. What it does
  establish is that **a rubric revision aimed at `partial` would be aimed at
  something real**, which is more than the withdrawn hypothesis could say.

  **A limitation of diagnostic 2 itself.** The coding is mine, single-coder,
  with no blind second pass — the very instrument property this project
  measures everywhere else. It is reported as a reading of fifteen rationales,
  not as an annotation with a ceiling.

- **Superseded hypothesis:** _not run — superseded before running by the
  amendment below. The hypothesis, the prediction and the decision rule above are
  withdrawn; they are kept in place because a withdrawn prediction that is
  deleted cannot be counted against the person who made it._

#### E-011b amendment 2026-09-10b — the effect is a batch effect, the prediction was an identity, and the best-supported hypothesis was missing

Red-teamed the same day it was registered, before any rubric text existed.
Nine blocking findings; four were verified by re-deriving them from the
data. Additions and withdrawals, not a rewrite.

**1. The structural defect is not identifiable in this sample.** The
five-row stratum table is confounded with batch. Decomposed:

| batch | single verdict | compound verdict |
|---|---|---|
| b1 | 1/1 | 22/35 = 0.629 |
| b2 | 9/10 = **0.900** | 8/9 = **0.889** |

**Within b2 — the only batch holding both kinds — there is no stratum
effect.** The entire contrast the entry called structural is b1 (0.639)
against b2 (0.895). b1 and b2 also differ on the incompleteness notice
(live in b1, suppressed in b2, and tie-break 4 therefore fires only in
b1), on the question pool, on answer-key provenance, and on the exposure
flags. Any of those explains a one-directional stricter judge concentrated
in b1 without reference to verdict arity. **Withdrawn:** the hypothesis
that compound verdicts cause the disagreement. If it is ever revived,
verdict arity must be annotated per question as its own variable, blind to
the disagreement outcome, rather than read off a stratum label assigned by
hop count.

**2. The count that looked like a finding is the null.** 44 of 55 rows sit
in the two compound strata, so a flat disagreement rate predicts 15 × 44/55
= **12** disagreements there; 14 were observed. Wilson intervals on the
five cells — legality [0.566, 1.000], keyword [0.342, 1.000], definition
[0.301, 0.954], interaction [0.493, 0.821], negative_temporal [0.444,
0.858] — **all overlap**, and four contain the pooled estimate. The entry
printed five bare proportions with no interval and no correction, in a
project whose own primary analysis Holm-corrects a family of four.

**3. The prediction was entailed by the revision, not tested by it.** Rule
(b), `partial` taking precedence over `incorrect`, is defined over exactly
the residual it would be scored on: 10 of the 15 disagreements are
`partial → incorrect`, and converting them is the rule's definition. To
clear "above 0.80", `interaction_multihop` needed 4 flips and
`negative_temporal` 2, out of ~10 available of precisely the targeted type.
The prediction could not fail unless the revision failed to implement its
own sentence. The withdrawal condition was no better: `legality` and
`keyword` are 5/5 and 2/2, contain no boundary case rule (b) can touch, and
staying at 1.000 has ~50% power against a true 10-point degradation.

**4. The hypothesis with the most support was absent, and the proposed fix
would have hidden it.** Tie-break 2 reads: *"an assertion the key neither
states nor contradicts is `partial`, never `incorrect`. Calling it
incorrect requires knowing it is false, which is knowledge the key did not
supply."* **Ten `partial → incorrect` rows and zero in the other direction
is the signature of a judge correcting from its own Magic knowledge** —
the failure `judge.py`'s docstring says agreement figures cannot detect,
the failure `perturbed_key` was written to control, and a control that has
never been run. Giving `partial` precedence over `incorrect` suppresses
that failure's only visible symptom. Agreement would rise, the rubric would
be recorded as the culprit, and a judge that favours whichever arm
resembles what it already believes would enter E-001's head-to-head
validated. **Registered as a precondition:** the key-fidelity control runs
*before* any rubric revision is written.

**5. The registered run is refused by the project's own tooling, and if
forced it measures the wrong pair.** `audit_judge.py` raises on a
rubric-hash mismatch — *"the judge and the human read different rubrics.
Their agreement would not describe one instrument"* — and there is no
override. The guard is right: a p6-c2 judge scored against p6-c1 human
labels measures whether the revised judge moved toward the *old human's*
reading, which is the drift hypothesis restated rather than evidence
against it.

**6. "Collecting is hopeless" was computed on a quantity E-011 does not
gate.** The pooled 0.727 against 0.720 is not the gate; the gate is per
label. Per label, `incorrect` is **23/23**, seven clusters below the floor
— about 17 more answers at the observed mix — and at 28/30 its interval is
[0.787, 0.982], which **passes**. So collecting is not a bet on which end
of an interval is true: it is a cheap measurement that would gate one label
and demonstrate two failing. `correct` (13/18) and `partial` (4/14) remain
unreachable at this threshold, and that is a result worth publishing rather
than an obstacle.

**7. Four exposed rows are silently inside every figure.**
`audit_correctness.py` honours the `exposed` flag and reports the ceiling
with and without the four b1 rows discussed with an external LLM, as the
2026-09-04 amendment pre-committed. `audit_judge.py` never reads the field.
The 0.727, the per-label table and the stratum table all include them, with
no with/without figure, and all four sit in the batch carrying the effect.
Registered: the exclusion is carried into `audit_judge.py` and every figure
above is re-reported both ways before any of it is treated as a diagnosis.

**8. What replaces the withdrawn design.** Three diagnostics, none of which
spends blindness, ordered; no rubric text is written until they report.

  1. **The key-fidelity control** (`perturbed_key`, registered, coded,
     never run). Discriminates domain leakage from rubric ambiguity
     directly. Costs cents.
  2. **Code the 15 judge rationales against the keys.** Each cites either
     something the key states (a compoundness or tie-break 5 difference),
     a contradiction *the key does not contain* (domain leakage), or
     tie-break 3 (human drift). This reads the judge's own text, reopens
     no human label, and makes the entry's claim that the alternative
     "cannot be tested on this sample" false — it was testable all along.
  3. **Cross-tabulate against human pass 2**, which is frozen and was
     labelled blind to the judge. E-011a reports that seven of nine human
     self-disagreements start at `partial`; the overlap with the judge's
     ten `partial → incorrect` rows is computable today and separates
     "both readers find this boundary hard" from "the judge applies a rule
     the human does not".

**9. Constraints carried forward for whatever design follows.** Any
threshold must be a function of a measured ceiling and must say whether it
applies to a point estimate or a bound — E-011's amendment withdrew
hand-picked constants for exactly the reason "above 0.80" repeated one
entry later, and no per-stratum ceiling exists. Any paired comparison over
the same 55 rows uses exact McNemar, as `run_eval.py` already does, with a
noise floor from re-running the judge under **unchanged** p6-c1 first,
because a model at temperature 0 is not deterministic. At most one rubric
version may be scored on these 55 answers, or the in-sample leak the entry
disclosed in prose becomes an iteration loop. And adopting any p6-c2
invalidates the 0.720 threshold, which was measured under p6-c1: a new
rubric needs a new ceiling, which is two more blind human passes five days
apart.

**What survives.** Two observations, neither of which depended on the
withdrawn hypothesis: every one of the 15 disagreements has the judge
stricter than the human, with none in the other direction; and the
`partial` and `incorrect` definitions overlap textually, with no precedence
rule separating an answer that reaches the key's verdict while asserting
something the key contradicts. The second is a real defect in the rubric
text. It is not established to be the cause of anything.

## E-012 — is long-context generation the bottleneck, and is it size or depth?

- **Registered:** 2026-09-03, before any 12b question has been drawn and
  before `enforce_budget` has been touched. E-002's data already exists and
  the exploratory half below reads it; the confirmatory half is registered
  first and is what any decision rests on.

- **The decision this informs, stated before the design.** Two things are
  pending on the Phase 6 critical path and both wait on this answer:
  (1) whether `retrieval/subgraph.py::enforce_budget` keeps trimming
  farthest-first before E-001 runs, and (2) whether the graph arm needs a
  context-reduction step — reranking, precision filtering, fewer and better
  triples — as part of its shipped configuration rather than as a later
  improvement. Both are answered differently depending on whether long
  multi-hop contexts fail because they are **large** or because they are
  **deep**, and E-002 cannot tell those apart because its 3-hop questions
  are both at once.

- **What E-002 established, and what it left confounded.** Conditional on
  the answer entity being present in the evidence the model received, Hits@1
  was 0.884 at 1-hop, 0.677 at 2-hop and **0.339 at 3-hop**. The registered
  prediction that generation would not be the bottleneck is falsified.
  But 3-hop subgraphs are simultaneously deeper *and* far larger — a median
  206 evidence items against 17 at 2-hop — so the drop has two candidate
  causes and the design cannot separate them.

### E-012a — exploratory, on data that already exists

Correctness against context size and hop depth, among the 1,148 questions
whose answer was shown, from the completed A3 run. **No decision hangs on
it.** Its job is to generate the hypothesis and to choose the size buckets
12b will use, and it is labelled exploratory wherever it is quoted. It is
free, it is re-analysable, and it is not evidence for a claim.

**Actual result (2026-09-03, `scripts/run_e012.py explore`, exploratory).** Hits@1
by context size and depth, restricted to questions whose answer was in the
evidence shown:

| items in context | 1-hop | 2-hop | 3-hop |
|---|---|---|---|
| 1–8 | 0.953 [0.925, 0.972] n=322 | 0.979 [0.926, 0.994] n=95 | — |
| 9–32 | 0.760 [0.692, 0.817] n=175 | 0.832 [0.773, 0.878] n=196 | — |
| 33–128 | (n=3) | 0.301 [0.208, 0.414] n=73 | (n=1) |
| 129–512 | — | 0.123 [0.061, 0.232] n=57 | 0.341 [0.282, 0.405] n=223 |

Two readings, both exploratory and neither decisive:

- **Down a column, size collapses accuracy.** At 1-hop — where there is no
  chaining at all — going from ≤8 items to 9–32 costs 19 points. At 2-hop
  the fall is monotone and total: 0.979 → 0.832 → 0.301 → 0.123.
- **Across a row, depth costs nothing visible.** At 1–8 items the 2-hop
  questions score *above* the 1-hop ones; at 9–32 likewise; at 129–512 the
  3-hop questions score *above* the 2-hop ones. Every comparison that holds
  size roughly fixed runs against the depth hypothesis.

**Why this cannot be the answer.** The buckets were observed, not assigned,
and the selection runs the wrong way inside them. A 2-hop question landing
in 129–512 is an unusual one — a hub seed with an enormous neighbourhood —
while every 3-hop question lands there by default, so that cell compares a
biased minority against a typical majority. This is precisely the confound
12b removes by setting *k* itself.

**And the fact that forces 12b to exist:** at 3-hop the smallest context
observed anywhere in 500 questions is **43 items**, with a median of 206.
Small 3-hop contexts do not occur naturally in this KB. No amount of
re-analysis will produce them; only assignment will.

**Bucket choice for 12b, which was 12a's registered job.** The collapse
straddles 8–64, so *k* is amended from {16, 64, 256} to **{8, 16, 64, 256}**
plus untrimmed. `k=8` anchors the arm where accuracy is still high and is
where a depth effect, if one exists, has the clearest room to show.

### E-012b — confirmatory, and the only part that decides

- **Design.** Questions are run at **matched context sizes** across hops,
  with the answer-bearing evidence guaranteed present. For each question,
  the subgraph is reduced to *k* items by a rule fixed here — keep every
  triple on a shortest path from the seed to the answer, then fill to *k*
  with the nearest remaining evidence, deterministic at a recorded seed.
  Sizes: *k* ∈ {8, 16, 64, 256} plus the untrimmed subgraph — amended from
  {16, 64, 256} by 12a, which is what 12a was registered to decide.

  Crossing *k* with hops is the whole point: **at matched *k*, size is held
  constant and only depth varies.** A drop that survives matching is
  compositional reasoning; a drop that disappears is context size.

- **Splits, from the first paid call this time.** A **development** draw
  (100 per hop, seed `20260903`) for every pilot, every prompt question and
  every sanity check, and a **frozen confirmatory** draw (300 per hop, seed
  `20260904`, ids only, written once) touched exactly once at the end.
  Both are drawn from the complement of E-002's subset, so no question that
  produced an E-002 number appears here. This is the structure E-002 should
  have had, and its absence there is the process error that entry records.

- **Configuration held fixed.** Same instance, same KB, `gpt-4o-mini` at
  temperature 0, prompt `e002-a3` unchanged — E-012 is not a prompt
  experiment and any prompt edit voids the comparison. `frontier_cap` 400,
  `kind_cap` 1000. The only thing that varies is *k* and the hop.

- **Metric.** Hits@1 by (hops × *k*), cluster-free binomial intervals, and
  the primary contrast is a **paired** comparison within question across
  *k*. Nine cells against a control: multiple comparisons get Holm
  correction, declared here rather than chosen after the p-values.

- **Decision rule, fixed before the run.**
  1. **If accuracy at matched *k* is flat across hops** (2-hop and 3-hop
     within each other's intervals at the same *k*), the bottleneck is
     **size**. Consequence: `enforce_budget`'s distance-first trim is a real
     hazard for `interaction_multihop`, a context-reduction step is added to
     the graph arm's shipped configuration before E-001, and the change is
     re-run against Phase 4 and Phase 5's numbers to price any regression.
  2. **If accuracy still falls with hops at matched *k***, the bottleneck is
     **depth**. Consequence: context reduction is not adopted, the budget
     policy stays, and E-001's multi-hop stratum is reported with the
     compositional limit named as a known bound on the graph arm.
  3. **If both** — a size effect *and* a residual depth effect — the size
     part is acted on and the depth part is published as a limitation. This
     branch exists so that a mixed result is not read as whichever half is
     more convenient.

- **Predictions, recorded before the run.**
  - **Size dominates.** At *k* = 16 with the answer guaranteed present, I
    expect 3-hop within roughly 10 points of 2-hop. The 0.339 is mostly a
    needle-in-a-haystack failure over 206 items, not an inability to chain
    three facts.
  - **A residual depth effect survives**, on the order of 5–15 points, so
    branch 3 is the likely outcome. Chaining three triples is genuinely
    harder than chaining two even on a short context.
  - **The untrimmed arm is worst at every hop**, including 1-hop, where
    E-002 already shows 58 misses on contexts whose answer was always
    present.

- **Threats to validity, recorded before the run.**
  - **Conditioning on "the answer was shown" is post-selection.** The
    reduction rule in 12b guarantees presence by construction, which fixes
    it for the confirmatory arm but not for 12a's exploratory reading.
  - **The reduction rule uses the gold answer.** It is an oracle filter, so
    12b measures *the generator's ceiling given good retrieval*, not
    end-to-end performance, and no number from it may be quoted as a system
    score. It bounds what a perfect reranker could buy.
  - **MetaQA questions are templated**, so the reasoning being measured is
    easier than a judge-level Magic question, and a depth effect here is a
    lower bound on the depth effect there.
  - **The budget does not currently fire on the Magic corpus.** `dropped`
    is 0 across all 42 E-007 questions and all 18 E-008 probes; MTG
    subgraphs are small (median 8 evidence items). So branch 1's consequence
    is a **design constraint for E-001**, not a repair of an observed Magic
    defect, and any change to `enforce_budget` is a change made on
    calibration evidence — which is stated wherever it is reported.
  - **Changing shipped trimming risks Phase 4 and Phase 5 regressions.**
    Branch 1 therefore carries the re-run as part of its cost, not as
    follow-up work.

- **Cost.** 12a is free. 12b is 4 sizes × 3 hops × (100 dev + 300
  confirmatory) ≈ 4,800 calls at `gpt-4o-mini`, estimated under US$ 5, with
  `--limit` and a dry-run estimate printed before any spend as the project
  rule requires.

- **Actual result (2026-09-03, confirmatory split, 300 questions per hop at
  seed `20260904`, `gpt-4o-mini` at temperature 0, prompt `e002-a3`, one
  run): branch 2 — the bottleneck is depth, and context size does nothing
  measurable.**

| *k* | 1-hop | 2-hop | 3-hop |
|---|---|---|---|
| 8 | 0.883 [0.842, 0.915] | 0.660 [0.599, 0.716] | 0.489 [0.407, 0.572] |
| 16 | 0.890 [0.850, 0.921] | 0.672 [0.612, 0.727] | 0.511 [0.428, 0.593] |
| 64 | 0.890 [0.850, 0.921] | 0.656 [0.595, 0.712] | 0.591 [0.508, 0.670] |
| 256 | 0.897 [0.857, 0.926] | 0.628 [0.567, 0.686] | 0.518 [0.435, 0.600] |
| untrimmed | 0.893 [0.853, 0.923] | 0.628 [0.567, 0.686] | 0.533 [0.450, 0.614] |

n = 300 / 250 / 137 per cell. 213 of 900 questions were excluded because the
answer was not reachable through the retrieved evidence — 0 at 1-hop, 50 at
2-hop, **163 at 3-hop**.

**Depth at matched size.** Every row is separated, with a spread of 0.30 to
0.39. Holding the context at 8 items, accuracy still falls 0.883 -> 0.660 ->
0.489. The fall is not the context being large.

**Size at fixed depth.** Nothing. 1-hop moves between 0.883 and 0.897 across
a 32x change in context. Paired within question, untrimmed against *k*=8:
2-hop +36/-28 p=0.382, 3-hop +19/-25 p=0.451, 1-hop +8/-11 p=0.648 — none
approaching its Holm threshold. Directionally, 3-hop is *worse* at *k*=8
than at *k*=64, which is the opposite of a size effect.

**Verdict: branch 2.** Per the rule fixed before the run: context reduction
is **not** adopted into the graph arm, `enforce_budget`'s distance-first
trim **stays**, and E-001's multi-hop stratum is reported with the
compositional limit named as a known bound on the graph arm.

### Predictions, scored

1. **"Size dominates; 3-hop within ~10 points of 2-hop at *k*=16."**
   *Wrong.* At *k*=16 the gap is 16 points, and at every size the depth
   ordering is intact and the size ordering is noise.
2. **"A residual depth effect of 5-15 points survives."** *Wrong in the
   direction of understatement.* The depth effect is the whole effect, at
   roughly 24 points per hop.
3. **"The untrimmed arm is worst at every hop."** *Wrong.* Untrimmed is
   statistically indistinguishable from every reduced arm at every hop.

Three predictions, three wrong. Recorded rather than quietly dropped: the
hypothesis this experiment was built to confirm is the one it refuted.

### What this changes, and what it costs to have learned it

**The obvious repair was the wrong repair.** After E-002 the actionable
finding looked like `enforce_budget` — it trims farthest-first, a multi-hop
answer lives at the frontier, and 3-hop shown-reach was 0.448. Changing that
policy was a day of work on shipped code with regression risk to Phases 4
and 5. E-012 says it would have bought nothing: when the answer is present,
how much surrounds it does not matter.

**What a perfect reranker would buy, bounded.** E-002 measured 0.339 at
3-hop conditional on the answer being in the raw retrieved evidence; E-012
measures 0.533 conditional on a clean chain being present. Different samples,
so the comparison is indicative and not paired — but it puts the value of
perfect evidence selection at roughly 19 points, against 47 points that
remain compositional. Retrieval quality is the smaller half of the 3-hop
problem.

**And the exploratory arm pointed the other way.** E-012a, on the same
1,500 answers, read as a size effect: accuracy collapsing 0.979 -> 0.123 as
observed context grew. The entry said in advance why that could not be
trusted — buckets observed rather than assigned, with a 2-hop question
reaching 129-512 items only when its seed is a hub. Assigning the size
inverts the conclusion. Two cuts of the same data, opposite answers, and
only the one that controls the confound is admissible.

**Bound on transfer.** MetaQA questions are templated and their chains are
uniform; a judge-level Magic question composes effects that are not the same
shape. The depth effect measured here is a floor on the depth effect there,
not an estimate of it. And this measures the generator given good retrieval:
no figure in this entry is an end-to-end system score.

---

### Amendment 2026-09-13 — the 3-hop column measures neither depth nor the generator, and the same defect is in E-002

**Nothing above is rewritten.** This is appended, the published figures stand
as the record of what was computed, and what changes is the scope of what they
may be read to mean.

**What prompted it.** `scripts/e014_inspect.py` was written to render one
scored cell — the prompt as sent, the answer key, the chain `answer_path`
found, the recorded outcome — because the claim holding up this entire entry,
*the model was handed a clean chain and still failed*, had never been looked at
for a single question. The first case it printed was `mq-3-10308`, a 3-hop
question reading **"the movies written by the screenwriter of The Best
Intentions were directed by who"**, whose 16-item context held hop one
(`The Best Intentions | written_by | Ingmar Bergman`), four other facts about
that film, and **eleven unrelated films released in 1992**. Nothing in it said
what Bergman wrote. Nothing in it said who directed those films. The model
refused, and by the system prompt's own rule it was right to.

It scored as a failure because `answer_path` looks for **any accepted answer
string reachable through the evidence**, found *Ingmar Bergman* — who is in the
answer set because he directed some of his own screenplays — and returned a
one-step chain. That chain proves `written_by`. The question asks `directed_by`.

**Measured, over the whole confirmatory split.** Chain length returned by
`answer_path`, against the declared hop count:

| declared | real chain | n | correct | refused | format | wrong |
|---|---|---:|---:|---:|---:|---:|
| 1-hop | 1 | 300 | 267 | 8 | 4 | 21 |
| 2-hop | 2 | 250 | 168 | 39 | 19 | 24 |
| **3-hop** | **1** | **126** | 67 | 43 | 6 | 10 |
| 3-hop | 2 | 2 | 0 | 0 | 0 | 2 |
| 3-hop | 3 | **9** | 3 | 3 | 2 | 1 |

**126 of the 137 questions in the 3-hop cell (92%) carry a one-step chain.**
Nine carry three. `reduce_to_k` preserves whatever chain `answer_path` found,
so at *k*=16 those 126 questions handed the model a one-hop context with a
three-hop question stapled to it.

**E-002 carries the same defect, and its condition is weaker still.** E-002
conditions on `answer_shown = any(hits_at_1(name, question) for name in
stats["shown"])` — the answer *string* appearing among the evidence's entity
names, with no chain required at all. Re-collecting the same subset and
measuring the real chain behind each `answer_shown` case reproduces E-002's
published figures exactly (0.884 at 1-hop, 0.677 at 2-hop, 76 of 224 = 0.339
pooled at 3-hop), which is what makes the decomposition trustworthy:

| E-002, 3-hop, `answer_shown` | n | Hits@1 |
|---|---:|---:|
| real chain of **1 step** | **213** | 0.347 |
| real chain of 3 steps | 11 | 0.182 |

**213 of 224 = 95%.**

**What this withdraws.**

- **The 3-hop column of 12b's table does not measure depth**, and the sentence
  this project has quoted most often — *conditional on the answer being present
  in the evidence the model received, correctness falls to 0.339 / 0.511 at
  three hops* — is withdrawn. The conditioning is not what its words say. It
  reads "an accepted answer string was reachable", not "the question was
  answerable from what the model was shown".
- **The 43 refusals in the 126 are re-read.** The grounding prompt instructs a
  refusal when the evidence is insufficient. On those questions it was
  insufficient. A refusal there is the model obeying, and scoring it as a
  generation failure attributes to the generator a decision the harness made.
- **"Generation is the bottleneck, not retrieval" is not supported at three
  hops by any figure in this registry**, and it is the claim that motivated
  E-014 and that has been repeated in `docs/evaluation.md`, the README, two
  TILs and the P3 handoff.

**What survives, and it is not nothing.**

- **The 1-hop and 2-hop rows are clean**: chain length equals declared hops on
  300 of 300 and 250 of 250. The fall from **0.890 to 0.672** is a real,
  correctly-conditioned depth effect and stands.
- **The size null stands where it was measured cleanly.** It is computed within
  a fixed depth, and 1-hop and 2-hop are unaffected.
- **Branch 2's consequences stand on the clean half.** `enforce_budget`'s
  distance-first trim keeps its verdict and context reduction stays unadopted,
  because the size null that decided both is intact at 1 and 2 hops. What is
  withdrawn is the 3-hop evidence that was cited alongside it.
- **E-001 is untouched.** Different corpus, different scorer; `answer_path` has
  no part in it. Its numbers stand exactly as published.

**The finding that replaces it, stated as a question and not as a result.**
Of 300 3-hop questions on the confirmatory split, 163 were already excluded as
unreachable and 126 more reach an answer only by shortcut. Retrieval reaches
the genuine three-step chain on **9 of 300 (3.0%)**, and on **11 of 500 (2.2%)**
in E-002. Within this project's own evidence that points at retrieval, not
generation, as the three-hop bottleneck — but it is a post-hoc re-cut of
finished runs, it is labelled exploratory wherever it is quoted, and it decides
nothing until an entry registers it with a rule written before the run.

**The defect, named.** *A denominator is a claim about what counts.* "The
answer is present in the evidence" was operationalised as "an accepted string
is reachable" and read as "the question is answerable". The two return an
identical non-empty chain and are distinguishable only by looking — which is
the other recurring shape here, a check whose negative case is invisible. Both
were registered as lessons in this project months before they decided this
entry's headline.

**Consequences, applied.**

1. **E-014 is suspended before its first call.** It is registered to ask
   whether the depth effect is a property of the generator, at a depth whose
   measurement has just been withdrawn. The entry stands; nothing about it is
   deleted; it does not run until the instrument is repaired and a depth cell
   exists that measures depth.
2. **`answer_path` needs a chain of the declared length**, and the repair ships
   with a test that fails against the current function. Registered here so the
   fix is on the record before it is written.
3. **A re-draw is required for any future 3-hop arm.** Requiring a real
   three-step chain leaves 9 usable questions on this split, so the split is
   exhausted for that purpose and a new frozen draw is the only honest route.

**Recorded against the process, not the result.** Pre-registration did its job
on everything it was pointed at — the decision rule, the buckets, the three
wrong predictions, all on the record. It could not protect a quantity nobody
had rendered. The cheap check that would have caught this on day one is the one
the repair now makes routine: **print one case and read it** before a number
built on it is quoted anywhere.

---

## E-013 — the rules the graph cannot reach, and whether an edge it already has gets to them (registered 2026-09-11, not yet run)

- **Registered:** 2026-09-11, after the Phase 8 error analysis and **before any
  change to the router or any re-run**. The ceiling below is arithmetic over
  the existing graph and is stated now precisely so the run cannot be read as
  having discovered it.
- **Where this comes from.** A human labelled 37 of 55 answers `partial` or
  `incorrect`. Attributing the 27 with a contemporaneous retrieval record gave
  **74% evidence, 19% routing, 4% generation**: retrieval resolved every time,
  returned 7–57 items every time, and dropped nothing to the token budget.
  Across the 26 questions carrying gold rules the answers needed **64** CR
  rules and retrieval supplied **7 (10.9%)**, six of them in chapter 700.
- **The structural cause, already measured.** `Keyword-[:DEFINED_BY]->Rule`
  reaches only chapter 700 (257 rules); adding `HAS_SUBRULE` to depth two
  still reaches only 700 (1,067). The first edge that leaves the chapter is
  `REFERENCES`, and the only template that walks it — `rule_neighbourhood` —
  ran in **none** of the 27, because the routed plan starts from cards and
  keywords and that template takes a rule number.
- **Objective.** Decide whether adding a `REFERENCES` expansion to the routed
  plan — after the keyword→rule hop, over the graph exactly as it stands —
  raises the fraction of gold CR rules that reach the context, and at what
  cost in precision and budget.
- **The ceiling, computed before the run.** Of the **52 distinct** gold rules
  needed and missed, **18 are reachable** by one `REFERENCES` hop from a
  keyword-defined rule and **34 are not**. So gold-rule recall can rise from
  **7/64 = 10.9%** to at most **25/64 = 39.1%** and no further. Anything above
  that is a bug in the measurement, not a result.
- **Primary metric, and it costs nothing.** *Gold-rule recall* — the fraction
  of each question's `gold_cr_rules` present in the retrieved evidence,
  pooled over the 26 questions, reported with a Wilson interval. No model call
  is involved: `retrieve` writes the evidence and the golden set already
  records the gold rules. **No answer is regenerated in this experiment.**
- **Secondary metrics, registered because the repair can pay for itself
  badly.** Context precision proxy: evidence items retrieved per gold rule
  reached, before and after. Budget pressure: the share of questions whose
  `dropped` or `capped` becomes non-empty. The current population drops
  nothing at a 6,000-token budget and a kind cap of 25, and E-012 measured
  that a longer context hurts the generator — so a change that fills the
  budget is not free even when recall rises.
- **Prediction, recorded before the run.** Gold-rule recall rises to between
  **0.25 and 0.39**, the upper end being the ceiling; the gains are spread
  across chapters rather than concentrated — the 18 reachable rules sit in
  600 (7), 700 (5), 500 (3), 300 (2) and 400 (1), so **11 of the 18 are
  outside chapter 700**, which is the point of the repair; and
  **`dropped` becomes non-empty on at least one question**, because the
  expansion adds rules to contexts that already run to 3,500 tokens. If recall
  rises *and* nothing is ever dropped, suspect the expansion did not fire.
- **Falsifiable outcome that would end this line.** If gold-rule recall stays
  below **0.15** — that is, the expansion fires and brings back fewer than a
  quarter of the 18 reachable rules — then the reachable set is reachable only
  in principle, and the routing repair is abandoned in favour of the bridge
  problem. Registered now so it cannot be renegotiated afterwards.
- **Decision rule.** Recall at or above 0.25 with no new drops: adopt the
  expansion and *then* spend on regenerating answers to measure whether
  correctness follows. Recall at or above 0.25 with new drops: the change is
  not adopted as-is, and the follow-up is the budget, not the router. Below
  0.15: abandoned as above. Between 0.15 and 0.25: reported and not adopted,
  because a change this cheap should not need a close reading to justify.
- **Threat that bounds the whole entry.** The repair was chosen **after**
  looking at these 26 questions, so recall measured on them is optimistic by
  an unknown amount — the same in-sample relationship this project already
  runs on retrieval, one level up. The 57-question evaluation split is the
  only clean confirmation, it opens once, and this experiment does not touch
  it. Any figure from E-013 is a development figure and is labelled one.
- **Second threat: reaching a rule is not citing it.** Gold-rule recall is a
  retrieval metric. It cannot say the answer improves, and the 74/19/4 split
  says nothing about whether an answer given the right rule uses it. The
  decision rule spends on generation only after retrieval moves, in that
  order, because the reverse cannot separate the two.
- **What it does not test.** The 34 unreachable rules. Those need a bridge
  from card or question to chapters outside 700, which is the problem G3
  withdrew inferred `CITES_RULE` from at F1 0.125 rather than solved. That is
  its own experiment with its own gate, and 0.125 is the prior it starts from.
- **Cost.** Zero model calls for the primary and secondary metrics. The
  generation follow-up, if the decision rule reaches it, is 26 answers plus
  judging.
- **Actual result (2026-09-11): the repair gains 1 gold rule of a registered
  ceiling of 18, and the ceiling was the wrong quantity.**

  | | gold-rule recall | evidence/question | tokens/question | dropped |
  |---|---|---:|---:|---:|
  | as shipped | 6/64 = 0.094 [0.044, 0.190] | 20.0 | 1,253 | 0/26 |
  | with the `REFERENCES` hop | 7/64 = 0.109 [0.054, 0.209] | 25.0 | 1,483 | 0/26 |

  **The registered decision rule fires: below 0.15, the routing repair is
  abandoned in favour of the bridge problem.** It is applied as written.

  **But the ceiling that made 0.15 look like a low bar was mis-specified, and
  the error is mine.** The reachability query asked *"is this rule one
  `REFERENCES` hop from **any** keyword-defined rule in the graph"* and the
  answer, 18, was registered as if it meant *"from the rules **this question**
  retrieved"*. Those are different quantities and only the second is one this
  experiment could reach. Recomputed against each question's own retrieved
  rules: **0 of the 58 missing gold rules are one hop away.** The single rule
  gained — `rg-241`'s `303.4f` — came from a seed beyond the eight the
  implementation expands or an inbound edge the recomputation did not count.
  The honest ceiling was one, not eighteen, and the experiment was never
  capable of the 0.25 its decision rule asked for.

  **The negative result is stronger than the positive one would have been.**
  The hop is not weak here, it is empty: the rules these answers need are not
  adjacent to anything the graph retrieves for these questions. Combined with
  the 20 of 26 whose rules are unreachable in principle, the bridge from card
  or question to chapters outside 700 is not one repair among several — it is
  the whole problem. Nothing cheap sits between the current graph and the
  rules its answers need.

  **Two secondary readings, as registered.** The expansion is cheap and
  harmless: +5 evidence items and +230 tokens per question, and **nothing was
  dropped on any of the 26** at a 6,000-token budget, so the prediction that
  `dropped` would become non-empty was wrong too — the contexts had room. And
  `rule_neighbourhood` entered the plan on only **16 of 26** questions; the
  other ten had no rule in their evidence to take a hop from, which is the
  seedless-routing case arriving one layer further down.

  **What stays in the code.** `retrieve(reference_hop=...)` remains, off by
  default, with the measurement recorded in its docstring. The implementation
  is not what failed, and a flag whose result is written down is cheaper to
  reason about than a deletion that leaves the next person to rediscover this.

  **Lesson recorded against the pre-registration, not the result.** A ceiling
  is a claim about the experiment, and this one was computed over the graph
  rather than over the experiment. Registering it early did exactly what
  pre-registration is for — it is on the record, in the wrong, and legible —
  but it did not protect against the quantity being mis-specified in the first
  place. The check that would have caught it is cheap: compute the ceiling
  from the same inputs the run will see.

---

### Exploratory, 2026-09-13 — where the budget actually goes, and a linking hypothesis refuted

A re-cut of E-001's finished arm-B evaluation run. It conditions on nothing,
tests nothing, and fires no branch. It exists because E-018's first rendered
case suggested a front this entry had not named, and the cheapest way to find
out was to measure rather than argue.

#### The hypothesis, and it does not survive

`rg-271` asks about an additional combat **phase**; the linker resolved the
keyword `Phase`, whose glossary entry carries two numbered senses — *"1. A
subsection of a turn… 2. A permanent 'phases in'…"* — and the traversal pulled
the whole of `702.26` into a question about turn structure. **1,123 of that
question's 2,373 context tokens are about phasing.** The rule it needed,
`500.8`, is one sentence.

Proposed reading: wrong-sense linking is systemic, and Phase 9's first front
should be routing rather than the bridge — reversing E-013's own decision.

Measured instead. The CR glossary has **739 entries, 28 of them carrying two or
more numbered senses** (`Phase`, `Counter`, `Copy`, `Draw`, `Exile`, `Play`,
`Power`, `Toughness`, `Type`, `Color`…). Across the 57 evaluation questions:

| arm | questions linking a polysemous keyword | tokens from those keywords' rules |
|---|---:|---:|
| A vector | **0** of 57 | 0% |
| B graph | **4** of 57 | 1,477 of 42,417 — **3.5%** |
| C hybrid | 4 of 57 | 2.3% |

Three of arm B's four are `Counter` at 9–16% of their context, and on
`hand-replacement-order-counters` the sense retrieved is the right one.
**`rg-271` is the only severe case.** The hypothesis is **refuted**: one vivid
case, not a pattern, and no front opens on it.

#### What the same pass found instead, and it is larger

Arm B's 42,417 evaluation context tokens, by the traversal that produced them:

| template | items | tokens | share |
|---|---:|---:|---:|
| `card_rulings` | 230 | 17,007 | **40.1%** |
| `card_keyword_rules` | 205 | 11,894 | 28.0% |
| `keyword_definition` | 172 | 9,353 | 22.1% |
| `card_core` | 84 | 3,696 | 8.7% |
| `card_legality` | 14 | 332 | 0.8% |
| `card_interaction` | 5 | 135 | 0.3% |

**Half the graph arm's budget — 50.1% — expands keywords into chapter 700.**
That is the only chapter E-013 measured as reachable from a card, so this is
E-013's finding from the other side: not *which rules the graph cannot reach*
but *what it reaches instead*.

Split by stratum, which is the cut that decides a front:

| stratum | n | keyword share | gold rule retrieved | correct |
|---|---:|---:|---:|---:|
| `definition_1hop` | 11 | **100%** | 11/11 | 10/11 |
| `keyword_rule_2hop` | 2 | 98% | 2/2 | 1/2 |
| `negative_temporal` | 7 | 57% | 2/7 | 4/7 |
| `legality_1hop` | 15 | 46% | — | 14/15 |
| `interaction_multihop` | 22 | **36%** | **2/22** | 6/22 |

The graph arm is a **keyword-definition machine**. Where the question is about
a keyword definition it spends the entire budget on exactly the right thing and
answers 10 of 11. On `interaction_multihop` — 22 questions, the hardest stratum
and the one the project was built for — it still spends over a third of the
budget on keyword definitions and the governing rule arrives on **2 of 22**.

#### What this licenses, and what it does not

- **Front C, the bridge, is confirmed as the right front** and by a measurement
  rather than by inheritance. The entities resolve; the gold rule does not
  arrive because from a card or a keyword the reachable rules *are* keyword
  definitions.
- **The routing/linking front does not open.** 3.5% of context and one case.
- **It does not establish that reaching the rule would help.** E-018's gate
  returned unresolved. This measures where the budget goes, not what a
  different budget would buy, and the two must not be conflated.
- **Rulings are doing work that rules are not.** They are 40.1% of the budget,
  and on `interaction_multihop` four of the six correct answers arrived with
  the gold rule absent. E-018 injected **rules only** and said so as a limit on
  its scope; nothing here or there has tested injecting gold *rulings*, and on
  this evidence that is the cheaper question.
- **Exploratory, and on the evaluation split**, whose readings are declared. No
  figure here is a system score or a registered contrast.

Reproducible as `python scripts/e001_inspect.py --arm B --context`, so the same
cut can be taken again after any front lands and the before/after is the same
measurement rather than two.

## E-014 — is the depth effect a property of the task, or of the generator? (registered 2026-09-13, **suspended 2026-09-13**, never run)

- **Registered:** 2026-09-13, before any call is made and before
  `run_e012.py` grows the flag this entry needs. **Registered *after* E-001
  and E-012 have returned results**, which is stated plainly rather than
  buried: this is a follow-up motivated by two known outcomes, not a blind
  prediction. The mitigation is structural and is the reason the entry is
  shaped the way it is — **E-014 cannot revise E-001 or E-012.** Their
  published numbers stand whatever this returns. The most it can do is earn
  a *new* registered experiment.

- **The decision this informs, stated before the design.** E-001 returned
  `inconclusive` on all four strata and the direction ran against the thesis
  on `interaction_multihop` (0.27 graph against 0.41 vector, n = 22). One
  explanation for that is live and unmeasured: **the comparison was run at a
  generator ceiling low enough to mask any retrieval difference.** E-012
  measured that ceiling on `gpt-4o-mini` — at a matched 16-item context with
  a clean chain guaranteed present, Hits@1 falls 0.890 -> 0.672 -> 0.511
  across one, two and three hops — but it varied size and depth, never the
  model. So the project does not currently know whether "the generator cannot
  chain three facts" is a statement about the task or a statement about
  `gpt-4o-mini`.

  Two decisions wait on the answer. (1) Whether the MTG evaluation split is
  opened a **second** time with a stronger generator, or whether that
  explanation is closed. (2) Whether P3's decomposition hypothesis — break a
  multi-hop question into single-hop retrievals, each in the regime where the
  generator was measured competent — is the right thesis to carry forward, or
  is solving a problem a model upgrade dissolves.

- **Why this runs on MetaQA and not on the MTG split.** The question is about
  the generator, and MetaQA has an answer key, a frozen split, a reduction
  rule that guarantees the answer is present, and a completed measurement to
  pair against. Answering it on the 57 MTG questions would spend the
  evaluation split's second look to learn something the calibration benchmark
  can say for under twenty dollars. **This experiment does not touch the MTG
  evaluation split.** Earning the right to open it is the outcome, not the
  method.

### Design

- **One variable changes.** Generator `gpt-4o-mini` -> **`gpt-4o`**,
  temperature 0, prompt `e002-a3` **unchanged**, same frozen confirmatory
  split (300 per hop, seed `20260904`), same reduction rule, same
  `frontier_cap` 400, `kind_cap` 1000, same answer normalisation and
  `hits_at_1`. Any prompt edit voids the comparison, exactly as in E-012.

- **Within the same model family, deliberately.** A cross-vendor swap changes
  prompt idiom, refusal behaviour and answer formatting at the same time as
  reasoning, and the entry could not attribute a movement to any of them. One
  step up inside the family is the only swap that leaves a single variable.
  A cross-vendor arm is a different question and would need its own entry.

- **The size sweep is dropped, and E-012 is why.** E-012 measured that
  context size does nothing at fixed depth — 1-hop moves between 0.883 and
  0.897 across a 32x change in context, and paired tests reach nothing near
  their thresholds. Re-running four sizes here would spend money to replicate
  a null. **Primary design: *k* = 16 at all three hops.** A single
  size-null replication at *k* = 256 runs at 3-hop only, as a check that the
  null survives the model change rather than as a contrast.

- **Primary contrast: paired across models, within question.** The same 3-hop
  questions scored by both models at *k* = 16, exact McNemar, n = 137.
  Pairing across hops is impossible — different questions — so the comparison
  that decides is the one that holds the question fixed and moves the model.

- **Secondary family.** The same paired contrast at 1-hop and 2-hop. Three
  tests, **Holm correction declared here rather than chosen after the
  p-values**, alpha = 0.05.

- **Detectable effect, computed before the run.** With reversals rare, exact
  McNemar needs **6 discordant pairs one way** for raw *p* < 0.05 and **8:0**
  for the strictest Holm step at family size 3. At n = 137 that is a shift of
  6 questions, or 0.044. This design is far better powered than E-001's was,
  and the reason is not sample size — it is that the pairing holds the
  question fixed and moves one variable, where E-001 had to compare different
  retrievers over a stratum of 22.

### Decision rule, fixed before the run

Let **D** = Hits@1(1-hop, *k*=16) minus Hits@1(3-hop, *k*=16) under `gpt-4o`.
Under `gpt-4o-mini`, D = 0.890 - 0.511 = **0.379**.

1. **D <= 0.15 *and* the 3-hop paired contrast reaches its Holm-adjusted
   threshold.** The depth effect is largely a property of that generator.
   Consequences: E-012's verdict is annotated as **model-conditional** — its
   numbers stand, its scope narrows; E-001's inconclusive result acquires a
   live, registered explanation, and this earns **one** second opening of the
   MTG evaluation split, as its own entry with its own decision rule, with
   both openings and their dates published; and P3's decomposition hypothesis
   is **weakened**, because a generator that chains three facts does not need
   the chain broken up for it.
2. **D >= 0.25.** The depth effect survives a generator change within the
   family. Consequences: **no second opening on a model swap alone**; E-001's
   multi-hop reading stands as published; P3 inherits this as its registered
   prior and the decomposition hypothesis is strengthened.
3. **0.15 < D < 0.25, or D <= 0.15 without a significant paired contrast.**
   Reported and not acted on. No second opening; the decision passes to P3.
   This branch exists so a middling result is not read as whichever half is
   more convenient, and so a spread that narrows on noise is not read as
   branch 1.

### Predictions, recorded before the run

1. **D lands between 0.05 and 0.15 — branch 1.** MetaQA's 3-hop chains are
   templated and short, and at *k* = 16 with a clean chain guaranteed present
   the task is template-following over a tiny KB. If this is right it is the
   most consequential thing the project has measured, because it narrows
   E-012's central finding to a statement about one small model.
2. **1-hop moves less than 5 points**, from 0.890, because it is near the
   task ceiling.
3. **The size-null replicates**: 3-hop at *k* = 256 falls inside 3-hop at
   *k* = 16's interval.
4. **The exclusion count is identical** — 163 at 3-hop, 213 overall.
   Exclusion is decided by retrieval, before any model call. **If it differs,
   the harness changed and not the model**, and no cell is readable until
   that is explained.

### Threats to validity, recorded before the run

- **The frozen split is read a second time.** Declared here, not discovered
  later. E-012's published numbers stand unchanged, E-014's may not be
  substituted into E-012's tables, and the number of reads and their dates
  are published wherever either is quoted. Two declared reads is not a garden
  of forking paths; undeclared reads are.
- **MetaQA is templated, and the asymmetry is the whole point.** A gap that
  **survives** here is a *floor* on the gap on judge-level Magic questions,
  whose chains are not templated. A gap that **closes** here proves nothing
  about Magic. This asymmetry is why branch 1 earns a new registered
  experiment and never a conclusion about E-001.
- **The reduction rule is an oracle filter.** It uses the gold answer, so
  E-014 measures the generator's ceiling given good retrieval, not
  end-to-end performance. **No figure in this entry may be quoted as a system
  score.** Inherited from E-012 verbatim.
- **A model swap changes more than reasoning** — answer formatting, refusal
  behaviour, prompt sensitivity, tokenisation. Guards: identical prompt and
  identical normalisation; the 1-hop instrument check below; the
  exclusion-count check in prediction 4; and `refused` reported per cell
  rather than folded into `correct`.
- **Registered with the motivating results already known.** Stated in the
  header. The structural mitigation is that no branch of the decision rule
  permits editing E-001 or E-012.
- **Cost asymmetry could tempt a mid-run stop.** Every cell is paid and
  written before any is read. A run read before it completes is exploratory
  and is labelled exploratory wherever it is quoted.

### Instrument check, and it can fail

**If 1-hop improves by more than 5 points** — from 0.890 to above 0.94 — the
comparison is contaminated before the 3-hop cells are read. At *k* = 16 with
a clean chain present there is no chaining at all at one hop, so a large
movement there is answer-matching, formatting or prompt sensitivity, not
reasoning. The 3-hop cells are not interpreted until that is explained. This
is registered as a check that **can** return negative, against the project's
recurring failure shape: a probe that cannot fail is not a probe.

### Cost

Up to 900 questions minus the 213 whose answer is unreachable, about **687
calls at *k* = 16**, plus **137 at *k* = 256** for the size-null replication,
about 824 calls. Contexts at *k* = 16 are small; most of the token cost sits
in the *k* = 256 arm. `--limit` and a printed estimate before any spend, per
the project rule. Expected under US$ 25; the printed estimate governs, and if
it exceeds US$ 40 the *k* = 256 arm is dropped and its absence recorded here.

### Suspended 2026-09-13, before the first call

The dry run was clean — 687 calls at *k*=16 for ~US$2.83, 137 at *k*=256 for
~US$2.97, and every registered count matched exactly (824 calls, 213 exclusions
overall, 163 at 3-hop), so registered prediction 4 held before a token was
spent. Nothing was spent anyway.

**E-012's amendment of 2026-09-13 withdrew the measurement E-014 exists to
interrogate.** The 3-hop cell this entry pairs across models is 92% shortcut:
`answer_path` accepted a one-step chain to an answer *string* on 126 of its 137
questions, so the cell measures neither depth nor the generator. Running a
stronger model against it would produce a number carrying the same defect, at
the same confidence, and would look exactly like an answer.

This entry stands unedited. It does not run until `answer_path` requires a
chain of the declared length, a depth cell exists that measures depth, and a
new frozen draw replaces the 3-hop arm — requiring a real three-step chain
leaves 9 usable questions on the current split. Whether the question E-014 asks
is still the right question after that repair is itself open: the same
amendment reports that retrieval reaches the genuine three-step chain on 3.0%
of 3-hop questions, which points at retrieval rather than the generator.

### Actual result

_Not run. Suspended as above._

---

## E-015 — does the three-hop chain survive retrieval, and what destroys it? (registered 2026-09-13, dev grid run 2026-09-13)

- **Registered:** 2026-09-13, before any cell is collected and before
  `scripts/run_e015.py` exists. It follows E-012's amendment of the same day
  and exists because that amendment left the three-hop question open rather
  than answered.

- **The decision this informs.** E-012's registered job was to decide whether
  `enforce_budget`'s distance-first trim is a hazard for multi-hop questions.
  It chose branch 2 — *context reduction is not adopted, the trim stays* — on
  a size null measured at fixed depth. **That null cannot see this hazard.**
  Every E-012 cell had the answer chain guaranteed present by construction,
  because `reduce_to_k` reinstated it before the model was called. A design
  that repairs the damage before measuring is structurally blind to the damage,
  which is this project's recurring shape arriving in the experiment built to
  catch it.

  So the consequence E-012 published about `enforce_budget` was not supported
  by evidence about `enforce_budget`. This entry supplies that evidence, or
  fails to and says which.

- **What is already measured, from fields E-002 recorded at the time.**

  | | questions with evidence dropped by the budget | with the frontier truncated | median evidence |
  |---|---:|---:|---:|
  | 1-hop | 0 / 500 | 0 / 500 | 7 |
  | 2-hop | 121 / 500 | 106 / 500 | 22 |
  | **3-hop** | **498 / 500** | **497 / 500** | 206 |

  And with the repaired `answer_path` — which requires a chain of the declared
  depth — the shipped configuration reaches a genuine three-step chain on
  **10 of 300** questions of E-012's confirmatory split (3.3%).

  `enforce_budget` sorts by `(-distance, -index)` and evicts from the front, so
  **distance-3 evidence is always the first thing thrown away** — on a 3-hop
  question, the hop the answer lives on. `frontier_cap` truncates upstream of
  that, removing entities before the third expansion runs at all.

- **Objective.** Measure, with **zero model calls**, the fraction of 3-hop
  questions on which retrieval delivers a chain of the declared depth, as a
  function of the two limits that are cutting it, and price each setting in
  evidence items and tokens.

### Design

- **Population.** The 3-hop questions of E-012's frozen draws: the **dev** draw
  (100, seed `20260903`) carries the sweep, and the **confirmatory** draw (300,
  seed `20260904`) is read once, at the single setting the sweep names. Both
  were drawn for a generation experiment; this entry runs retrieval only and
  draws no conclusion about any model, so it spends neither split's meaning.

- **Grid.** `frontier_cap` ∈ {400 *(shipped)*, 1600} × `token_budget` ∈
  {6000 *(shipped)*, 24000, 96000}. Six cells. `kind_cap` stays at
  E-002's 1000 and the expansion depth stays at the question's hop count —
  this entry varies the two limits that discard evidence, not the walk.
  **Extension rule, fixed here:** if reach is still rising at
  `frontier_cap` 1600, one further cell at 6400 is added and reported as an
  extension of this grid rather than as a new experiment.

- **Primary metric.** *Chain reach* — the fraction of questions on which
  `answer_path(..., hops=3)` returns a chain — with a Wilson interval. It is a
  retrieval metric and no model is involved.

- **Secondary metrics, registered because the repair can pay for itself
  badly.** Median evidence items and median tokens per question at each cell.
  E-012 measured the generator's tolerance for context up to 256 items; a cell
  that buys reach at 2,000 items is buying it outside anything this project
  has tested.

### Decision rule, fixed before the run

1. **Chain reach rises above 0.50 at some cell.** The three-hop failure is
   substantially an artefact of the two limits. Consequences: E-012's branch-2
   consequence about `enforce_budget` is **amended** — recorded as inferred
   from a null that could not see this — the cheapest cell clearing 0.50 is
   named as the setting any future 3-hop work uses, and E-014 becomes
   answerable again at that setting with its own amendment.
2. **Chain reach stays below 0.20 at every cell.** Breadth-first expansion
   from a seed does not reach three-hop answers at any setting worth paying
   for, and the finding is about the retrieval **strategy**, not its limits.
   Consequences: E-014 stays suspended in its current form permanently; P3's
   decomposition hypothesis inherits this as its registered prior, with the
   mechanism being that decomposition replaces one three-hop retrieval with
   three one-hop retrievals, and one-hop reach is 100%.
3. **Between 0.20 and 0.50.** Reported, and the cheapest cell above 0.20 is
   named. No consequence is drawn for `enforce_budget`, because a change to
   shipped trimming should not need a close reading to justify — the same bar
   E-013 was held to.

### Predictions, recorded before the run

1. **Reach at the shipped cell is below 0.10 on dev**, consistent with the
   3.3% already measured on conf.
2. **Reach is monotone non-decreasing in both limits.** Raising a cap or a
   budget can only add evidence. **A cell where reach falls as a limit rises
   is a harness bug and not a finding**, and no number is read until it is
   explained. Registered as the check in this entry that can return negative.
3. **`frontier_cap` dominates `token_budget`.** Truncation happens upstream:
   no budget can retain evidence that was never collected, because the entity
   it hangs off never entered the frontier. So the 400 → 1600 step moves reach
   more than the 6000 → 96000 step.
4. **Reach above 0.50 costs a context far outside what E-012 tested.** Median
   evidence at the shipped 3-hop cell is already 206; I expect the cheapest
   cell clearing 0.50, if one exists, to sit above 1,000 items.

### Threats to validity, recorded before the run

- **A chain present is necessary, not sufficient.** Reach says the evidence
  could support an answer, never that an answer would be right. **No figure in
  this entry may be quoted as a correctness or a system score**, and the
  distance between the two is exactly the mistake E-012's amendment corrects.
- **The repaired `answer_path` errs toward exclusion.** Its walk marks nodes
  seen at the depth it first reaches them, so an entity reachable both above
  and at the declared depth is consumed by the shallower path. Every reach
  figure here is therefore a **lower bound**.
- **Context the generator has never been tested on.** E-012's size null runs
  to 256 items. A cell that buys reach at thousands is outside it, and quoting
  the null there would be extrapolation.
- **MetaQA's KB is dense and uniform.** Its relation set is small and its
  degree distribution nothing like the CR's. Concepts transfer, constants do
  not: no cap or budget found here is carried to the Magic side.
- **Both splits were drawn for a generation experiment.** This entry reads
  them for retrieval only. If any later entry wants a *generation* claim at
  three hops, it needs a fresh draw, because the repaired filter leaves ten
  usable questions on the confirmatory split.

### Cost

**Zero model calls.** Six cells × 100 dev questions of graph traversal, plus
one confirmatory reading of 300. The expense is wall-clock on the MetaQA
instance at the larger frontier, not money, and the script prints the cell it
is on so a long cell is visible rather than silent.

### Actual result

**Actual result (2026-09-13, dev split, 100 3-hop questions, zero model calls):
branch 1 — the three-hop failure is substantially an artefact of the budget.**

| frontier | budget | chain reach | median items | median tokens |
|---:|---:|---|---:|---:|
| 400 | 6,000 *(shipped)* | 0.030 [0.010, 0.085] 3/100 | 207 | 5,985 |
| 400 | 24,000 | 0.180 [0.117, 0.267] 18/100 | 837 | 23,987 |
| 400 | 96,000 | **0.650** [0.553, 0.736] 65/100 | 2,007 | 59,512 |
| 1,600 | 6,000 | 0.030 [0.010, 0.085] 3/100 | 207 | 5,985 |
| 1,600 | 24,000 | 0.180 [0.117, 0.267] 18/100 | 837 | 23,987 |
| 1,600 | 96,000 | **0.650** [0.553, 0.736] 65/100 | 2,007 | 59,512 |

Monotonicity held: reach never fell as a limit rose.

**The registered rule fires: branch 1.** At the shipped configuration the chain
the question needs survives retrieval on **3 of 100** questions. Sixteen times
the token budget carries that to **65 of 100**, with nothing else changed. The
three-hop evidence was there and was being thrown away.

### Predictions, scored

1. **"Reach at the shipped cell is below 0.10 on dev."** *Right* — 0.030,
   matching the 3.3% measured on conf.
2. **"Reach is monotone non-decreasing in both limits."** *Held.* The check
   that could have returned negative did not.
3. **"`frontier_cap` dominates `token_budget`."** *Wrong, and wrong in the way
   that matters.* `frontier_cap` does not dominate; it does **nothing at all**.
   Every cell at 1,600 is identical to its twin at 400 to the last digit —
   same reach, same median items, same median tokens.
4. **"Reach above 0.50 costs a context far outside what E-012 tested."**
   *Right.* The cheapest cell clearing 0.50 has a median of **2,007 evidence
   items**, against the 256 that is the largest size E-012's generator null
   covers. Buying the chain and being able to use it are different purchases.

### Why `frontier_cap` is inert, measured rather than reasoned

On 40 dev questions at a 96,000-token budget:

| | questions truncated | questions capped | **items discarded by `kind_cap`** | evidence at distance 1 / 2 / 3 |
|---|---:|---:|---:|---|
| `frontier_cap` 400 | 39/40 | 39/40 | **174,228** | 388 / 31,708 / 39,021 |
| `frontier_cap` 1,600 | 33/40 | 39/40 | **430,137** | 388 / 31,708 / 39,021 |

Raising the frontier admits **2.5× more candidate triples and every extra one
is discarded**, because `add_evidence` caps per `(template, kind)` and the
template is `metaqa_expand_{distance}` — **1,000 triples per distance level**,
a ceiling of 3,000, which is the 2,007 median. The surviving evidence is
identical, level by level.

**So this entry named the wrong second limit.** Its design says it varies "the
two limits that discard evidence"; there are three, the one it varied second is
inert, and the one it never named is the binder. The grid caught it — two
columns identical to the digit is not a result, it is a limit that never fired
— but the registration should have listed `kind_cap` and did not.

And the remaining 35% is not the budget's doing: at 96,000 the median question
uses **59,512 tokens**, comfortably under. Whatever is keeping the chain from a
third of these questions at that cell, it is no longer the budget.

### What this changes, applied as registered

- **E-012's branch-2 consequence about `enforce_budget` is amended.** It held
  that the distance-first trim is not a hazard, inferred from a size null
  measured on cells where `reduce_to_k` had already reinstated the chain. At
  three hops the trim discards the answer's own hop on 97 of 100 questions.
  The null was never evidence about the trim.
- **The setting any future 3-hop work uses is a 96,000-token budget**, and it
  should be written that way rather than as a pair: `frontier_cap` is inert
  here and naming it would imply it was chosen.
- **E-014 becomes answerable again — into a regime nobody has tested.** A
  generator experiment at that setting runs on ~2,000-item contexts. E-012's
  size null covers 256. Its amendment must say that the context is
  extrapolated, or measure the null there first.
- **Reach is not correctness.** 0.650 says the evidence could support an answer
  on 65 of 100 questions. It says nothing about whether one would be right, and
  the distance between those two sentences is the mistake the 2026-09-13
  amendment to E-012 exists to correct.

### Amendment 2026-09-13b — registering the limit the entry should have varied

Registered **after** the grid above and **before** any `kind_cap` cell is
collected, and marked as such. The extension rule fixed in the original design
covers a further `frontier_cap` at 6,400 *if reach is still rising*; reach is
flat in that axis, so that rule correctly does not fire and is not used as
cover for a different arm.

- **New arm.** `kind_cap` ∈ {1,000 *(shipped for MetaQA)*, 4,000, 16,000} at
  the budget the grid named (96,000) and `frontier_cap` 1,600 — the larger
  frontier, because at a higher `kind_cap` the extra candidates it admits can
  finally survive, which is exactly what made it inert before.
- **Prediction.** Reach rises above 0.650 and the rise is smaller than the
  0.030 → 0.650 the budget bought, because at 96,000 the median question is
  already under budget and the cap therefore binds on fewer of them than it
  appears to. I do not expect reach above 0.90.
- **The same monotonicity check applies** and is the reason a cell may not be
  read on its own.
- **Decision rule.** This arm changes no consequence already applied above. It
  names the cheapest setting at which the chain reaches, and nothing else; if
  `kind_cap` turns out to dominate, the correction is recorded against this
  entry's design rather than used to re-open E-012's verdict a second time.
- **Cost.** Zero model calls. The 16,000 cell collects hundreds of thousands of
  triples per question and may be slow; if a cell exceeds ten minutes per
  question it is abandoned and its absence recorded here.

**Actual result (2026-09-13, dev split, 100 3-hop questions, zero model calls):
the monotonicity check fired, the script exited non-zero, and the explanation
is not a harness bug.**

| frontier | budget | `kind_cap` | chain reach | median items | median tokens |
|---:|---:|---:|---|---:|---:|
| 1,600 | 96,000 | 1,000 | **0.650** [0.553, 0.736] 65/100 | 2,007 | 59,512 |
| 1,600 | 96,000 | 4,000 | 0.460 [0.366, 0.557] 46/100 | 3,281 | 95,985 |
| 1,600 | 96,000 | 16,000 | 0.460 [0.366, 0.557] 46/100 | 3,281 | 95,985 |

**Reach falls as the cap rises**, twice, and per the rule fixed in the original
design no number here was read until it was explained. What follows is the
explanation, measured on 40 of the same questions rather than argued:

| `kind_cap` | surviving evidence at distance 1 / 2 / 3 | share at distance 3 | questions hitting the budget | items dropped |
|---:|---|---:|---:|---:|
| 1,000 | 388 / 31,708 / **39,021** | **54.9%** | **0 / 40** | 0 |
| 4,000 | 388 / 76,876 / **40,696** | **34.5%** | **34 / 40** | 110,780 |

Raising the cap admits roughly **45,000 more distance-2 triples** and barely
1,600 more at distance 3. That pushes the subgraph over the token budget — from
zero questions trimmed to 34 of 40 — and `enforce_budget` evicts farthest
first, which at three hops is the hop the answer lives on. Nearer, irrelevant
evidence displaces the chain.

**Prediction, scored: wrong, and the registered monotonicity claim with it.**
The amendment predicted reach would rise above 0.650 and not past 0.90. It
**fell**, to 0.460. And the original entry's prediction 2 — *"raising a cap or a
budget can only add evidence, so reach cannot fall"* — is false as stated. It
holds only while the added evidence cannot displace what was already kept. A
downstream selector that evicts by a criterion **correlated with what the
question needs** makes displacement not just possible but systematic.

**The guard is what makes this readable.** It could not tell a bug from an
interaction — nothing can — but it stopped 0.460 from being written down as
"a bigger cap is worse", which is true of the number and false about the cause.
Being forced to look is the whole return on registering it.

### The finding, and it is the opposite of what E-012 concluded

E-012's branch 2 kept `enforce_budget`'s distance-first trim, on a size null
measured where `reduce_to_k` had already reinstated the chain. This measures the
trim directly, and at three hops **it converts extra retrieval into worse
coverage of exactly the questions multi-hop retrieval exists for.** Retrieval
that brings back more is punished for it.

That is a mechanism, not a mandate. **No change to shipped trimming follows
from it here**, for the reason E-013 was held to: a repair this consequential
gets its own entry, with its own decision rule written before the run, rather
than being adopted off the back of a guard firing. What this entry supplies is
the target such an entry would aim at, and the measurement it has to beat.

### What stands from the original grid

Unchanged. The cheapest setting at which the chain reaches is still
**`kind_cap` 1,000 at a 96,000-token budget** — the amendment said in advance
that this arm names a setting and changes no consequence already applied, and
it does not. Branch 1 was read off the registered grid and stays read.

The three-hop reach figures now have a second bound on them: **0.650 is what
this retriever achieves when the budget does not bind at all**, and every
attempt so far to buy more by retrieving more has cost reach rather than
bought it.

---

## E-016 — can a trim that knows nothing about the answer keep the answer? (registered 2026-09-13, run 2026-09-13)

- **Registered:** 2026-09-13, after E-015's grid and its amendment, and
  **before any trim policy is written**. E-015 ended by naming the target this
  entry has to hit and explicitly refused to change shipped trimming off the
  back of a guard firing; this is the entry that was promised there.

- **The decision this informs.** Whether `enforce_budget` gains an alternative
  eviction policy. E-012 held that its distance-first trim is not a hazard,
  inferred from a size null measured on cells where `reduce_to_k` had already
  reinstated the chain. E-015 measured the trim directly and amended that: at
  three hops it discards the hop the answer lives on, and giving retrieval a
  larger pool makes it discard more. A replacement policy is now the obvious
  move, which is exactly when it needs a rule written before the code.

### The ceiling, computed before the run and from the collections the run will trim

Measured 2026-09-13 on the same 100 three-hop dev questions, `frontier_cap`
1,600, budget effectively unbounded, so nothing is evicted:

| `kind_cap` | chain present in the untrimmed pool | median pool | **the chain's own cost** |
|---:|---|---:|---:|
| 1,000 | 0.650 [0.553, 0.736] | 59,512 tokens | median **90** tokens, max 111 |
| 4,000 | **0.920** [0.850, 0.959] | 199,146 tokens | median 94 tokens, max 135 |

**That is the whole entry in two numbers.** The evidence that answers a
three-hop question costs about **90 tokens**; the budget is **6,000**; the
chain is in the retrieved pool on **92 of 100** questions; and the shipped
configuration delivers it on **3**. The trim discards one and a half percent of
its own budget to make room for distance-2 material the question did not ask
about.

This is the E-013 lesson applied: the ceiling is computed from the same inputs
the run will see, not from the graph. **0.920 is the number every arm below is
measured against, and no arm can exceed it** — anything above it is a bug in
the measurement, not a result.

### Design

- **All four arms trim the same pool.** For each question, retrieval runs
  **once** per `kind_cap` and the four policies are applied to that identical
  pre-trim evidence. The comparison is therefore **paired by construction**:
  no arm can win by having been handed a different retrieval.

- **The arms, and every one is oracle-free.** This is the constraint the entry
  exists under and the reason it is not trivial. `reduce_to_k` keeps the chain
  because it is *given* the answer; nothing here may be.

  | arm | policy |
  |---|---|
  | **A** | shipped: evict by descending distance, ties by later arrival |
  | **B** | proportional: each distance level is guaranteed an equal share of the budget; eviction takes from whichever level is over its share |
  | **D** | connectivity-first: prefer evidence whose head or tail already appears in kept evidence, so the kept set grows as connected paths rather than as a breadth-first shell |
  | **R** | random eviction at a recorded seed — **the control, and the falsifier** |

- **Why R is the falsifier and not a filler arm.** If random eviction matches B
  and D within their intervals, then nothing the designed policies do matters
  and the only thing that helped was *ceasing to evict by descending distance*.
  That is a different and much smaller claim, and it is the one that gets
  reported. Registered now so it cannot be quietly dropped if it is awkward.

- **Grid.** Four arms × `kind_cap` ∈ {1,000, 4,000} at the **shipped 6,000-token
  budget**, `frontier_cap` 1,600. The budget stays at 6,000 on purpose: E-015
  already showed that 96,000 tokens buys 0.650 with the naive trim, and the
  question here is how much of the 0.920 ceiling a better policy can deliver
  **without** paying sixteen times the budget.

- **Primary metric and contrast.** Chain reach at the declared depth. Primary
  family: **B vs A** and **D vs A**, exact McNemar paired within question, Holm
  over the two, alpha = 0.05. R vs the best designed arm is the falsifier check
  and is reported whatever it says.

- **Detectable effect, computed before the run.** Exact McNemar needs 6
  discordant pairs one way for raw *p* < 0.05 and 7:0 for the stricter Holm
  step at family size 2. With A at 0.030 and any working arm well above it,
  discordance will be in the tens. **This design is not underpowered and that
  is not a virtue of the sample size** — it is that the arms are paired on the
  same pool and the control is near the floor.

### Decision rule, fixed before the run

1. **The better of B and D beats A by at least 0.20 in chain reach, clears its
   Holm-adjusted threshold, and beats R.** The policy is added to
   `enforce_budget` as an option, **off by default**, with this measurement
   recorded in its docstring — the pattern E-013 set for `reference_hop`. It
   ships off because the Magic corpus does not currently hit the budget at all
   (E-013: `dropped` empty on all 26 questions), so adopting it as the default
   on MetaQA evidence would be changing shipped behaviour on calibration data.
2. **No arm beats A by 0.20.** The trim is not the lever. Reported, nothing is
   added to `enforce_budget`, and the three-hop retrieval problem is recorded
   as needing a different walk rather than a different eviction order.
3. **B or D beats A, but R matches the winner within its interval.** Reported
   as *abandoning descending-distance eviction is what mattered*; the specific
   policy is **not credited**, and if anything is added it is documented as
   "not distance-descending" rather than by the name of the arm that happened
   to win.

### Predictions, recorded before the run

1. **A at `kind_cap` 4,000 is no better than its 0.030 at 1,000**, and probably
   worse: a larger pool is more distance-2 material to displace the chain with,
   which is the mechanism E-015's amendment measured.
2. **B lands between 0.15 and 0.35.** Reserving a share for distance 3 is
   necessary and nowhere near sufficient — there are on the order of a thousand
   distance-3 candidates and the policy has no idea which one matters.
3. **D beats B.** A chain is a connected path, so preferring evidence that
   extends what is already kept is chain-shaped without an oracle. This is the
   entry's actual hypothesis and the reason it exists.
4. **R beats A.** This is the uncomfortable one and it is registered because it
   is uncomfortable: if it holds, the shipped policy is worse than chance at the
   job it exists to do, and that sentence is the finding rather than a footnote
   to it.

### Threats to validity, recorded before the run

- **Chain reach is not correctness.** It says the evidence could support an
  answer, never that one would be right. Carried forward verbatim from E-015,
  because the distance between those two sentences is what E-012's amendment
  had to correct.
- **A cheap ceiling makes a hard problem look easy.** The chain costs 90 tokens
  of a 6,000-token budget, so an oracle keeps it every time. **No arm here has
  an oracle**, and the gap between 0.920 and whatever the best arm returns is
  the price of not knowing which 90 tokens matter. Quoting the ceiling without
  that sentence would misread the entry.
- **Pairing removes collection variance and shares collection defects.** All
  four arms see the same pool, so any defect in `collect` is invisible to this
  comparison. It is the right trade for a policy contrast and it is not free.
- **MetaQA's KB is uniform and shallow in relation types.** Concepts transfer,
  constants do not: no share, seed or threshold found here is carried to the
  Magic side without being re-measured there.
- **The Magic corpus does not hit the budget.** Every consequence above is
  therefore about a *policy that is available*, not about a change to what
  Magic answers do today. Branch 1 ships the flag off for exactly this reason,
  and an entry that wants it on has to measure it there first.
- **`kind_cap` 4,000 was shown by E-015 to hurt under a binding budget.** It is
  included here anyway and deliberately: the point is whether a better policy
  turns a bigger pool from a liability back into an asset, which is the claim
  a depth-preserving trim implicitly makes.

### Cost

**Zero model calls.** Two collections per question over 100 questions, each
trimmed four ways in memory. The `kind_cap` 4,000 collections are the slow part
and are reused across all four arms rather than repeated per arm.

### Actual result

**Actual result (2026-09-13, dev split, 100 3-hop questions, four policies over
the identical pool, zero model calls): branch 2 at both caps — the trim is not
the lever.**

| arm | `kind_cap` 1,000 *(ceiling 0.650)* | `kind_cap` 4,000 *(ceiling 0.920)* |
|---|---|---|
| **A** shipped | 0.030 [0.010, 0.085] 3/100 | 0.030 [0.010, 0.085] 3/100 |
| **B** proportional | 0.100 [0.055, 0.174] 10/100 | 0.100 [0.055, 0.174] 10/100 |
| **D** connectivity | **0.120** [0.070, 0.198] 12/100 | 0.100 [0.055, 0.174] 10/100 |
| **R** random | 0.010 [0.002, 0.054] 1/100 | 0.020 [0.006, 0.070] 2/100 |

Paired within question against A, exact McNemar, Holm over the two primary
arms. At `kind_cap` 1,000: **B +8/−1, adjusted *p* = 0.0391; D +10/−1, adjusted
*p* = 0.0234 — both significant.** At 4,000 the same +8/−1 no longer clears its
Holm step (adjusted *p* = 0.0781). Falsifier: **D beats R +11/−0,
*p* = 0.00098**, so random is not what did it.

### The registered bar refused a significant result, and it was right to

**The designed policies work and are nowhere near enough.** They beat the
shipped policy reliably and they beat chance decisively; they move chain reach
from 0.030 to 0.120 against a ceiling of 0.650. The rule fixed before the run
asked for **0.20** and the best arm returned **0.090**.

Without that number written down first, "significant improvement over the
shipped trim, *p* = 0.023, and it beats random at *p* = 0.001" is an extremely
easy thing to adopt. It would have changed shipped behaviour to close a seventh
of the gap it was pointed at. **The p-value said yes and the registered effect
size said no, and the effect size was right.**

So, as registered: **nothing is added to `enforce_budget`**, and three-hop
retrieval is recorded as needing a different **walk** rather than a different
eviction order.

### Why no ordering could have saved it, in one line of arithmetic

A 6,000-token budget holds roughly 200 triples. An equal share gives distance 3
about **66 slots against 1,000 candidates** at `kind_cap` 1,000, and against
4,000 at the larger cap. Ordering decides which 66; it cannot make 66 cover
1,000. The chain costs 90 tokens and the problem was never the price — it is
finding those 90 tokens among 200,000.

What an eviction order *can* fix is the systematic part: not throwing away the
half of the haystack the needle lives in, first. That is worth **9 points**,
and it is worth exactly 9 points. The other 53 are the walk's.

This is also why the larger pool does not help. At `kind_cap` 4,000 the ceiling
rises to 0.920 and every arm stays flat or falls: four times the candidates for
the same 66 slots is a worse lottery, not a better one.

### Predictions, scored

1. **"A at `kind_cap` 4,000 is no better than at 1,000, probably worse."**
   *Half right.* No better — identical at 0.030 — and not worse either.
2. **"B lands between 0.15 and 0.35."** *Wrong.* 0.100 at both caps, below the
   range, and the arithmetic above is why the range was optimistic.
3. **"D beats B."** *Not supported.* 12 questions against 10 at one cap and a
   tie at the other. This entry's actual hypothesis returned a difference of
   two questions, which is nothing, and it is recorded as nothing rather than
   as a direction.
4. **"R beats A."** *Wrong*, and wrong in the comfortable direction: random is
   worse than shipped, 0.010 against 0.030. The uncomfortable sentence was
   registered so it could not be avoided if true; it was not true.

Four predictions: one half right, two wrong, one unsupported.

### What this leaves

**The three-hop problem is the walk.** Breadth-first expansion from a seed
builds a shell, and a chain is a path; at depth three the shell is four orders
of magnitude larger than the path, and neither a bigger budget (E-015: 0.650 at
sixteen times the tokens) nor a smarter eviction order (0.120 here) closes
that. Whatever fixes it has to search differently, not keep differently.

**And that is the strongest registered support the P3 decomposition thesis has
had.** One-hop chain reach is 1.000. If a three-hop question is answered as
three one-hop retrievals, none of this arithmetic applies — not because the
generator improves, but because the haystack is never built. That claim now
rests on two measured entries rather than on the withdrawn sentence it was
originally motivated by, and it still has to be registered and run on its own
terms before it is worth anything.

---

## E-017 — is the three-hop haystack the depth, or the untyped walk? (registered 2026-09-13, run 2026-09-13)

- **Registered:** 2026-09-13, after E-016 returned branch 2 and recorded that
  three-hop retrieval needs a different *walk* rather than a different eviction
  order. This entry tests that sentence before anything is built on it.

- **The decision this informs, and it is a build decision.** P3 is scoped as an
  agentic router whose thesis is decomposition: answer a multi-hop question as a
  sequence of single-hop retrievals. That thesis was originally motivated by a
  sentence this project has since withdrawn, and E-016 gave it new support
  indirectly. **Before P3 builds an agent, this entry asks whether the saving
  decomposition claims is real, and whether an agent is even the cheapest way
  to get it.**

  The cheapest version of the same idea needs no agent at all: **expand along
  the relation the question is about, instead of expanding along everything.**
  If typed expansion alone closes the gap, the agentic machinery is solving a
  problem that a `WHERE type(r) = $relation` already solved, and P3 should know
  that before writing a planner rather than after.

### What is already measured, and the bar it sets

| | |
|---|---|
| untyped three-hop pool, median | **199,146 tokens** (`kind_cap` 4,000) |
| the answer chain inside it | **90 tokens**, 3 triples |
| shipped budget | **6,000 tokens** |
| chain reach at that budget, best of four eviction policies | **0.120** (E-016) |
| chain reach at sixteen times the budget, shipped policy | 0.650 (E-015) |

So a typed expansion has to be at least **33× smaller** than the untyped shell
to fit the shipped budget at all. That factor is stated here, before the run,
as the thing the measurement has to clear.

### Design — retrieval only, zero model calls

- **The quantity.** For each three-hop dev question, read the relation sequence
  off the answer chain — three relation names — then expand from the seed
  following **only those relations, one per hop**, and measure the size of what
  comes back in triples and tokens.

- **What this is, said plainly.** The relation sequence comes from the gold
  chain, so this is a **ceiling**: it measures what a typed walk would cost *if
  something chose the relations correctly*. Nothing here chooses them.
  **No number in this entry is a system score**, and the entry may not be
  quoted as evidence that a system reaches anything. It is the same shape as
  `reduce_to_k` keeping the chain because it was handed the answer, and it is
  labelled that way on purpose — the mistake that cost this project its
  headline was letting an oracle-conditioned figure read as a system figure.

- **The comparison that carries the result** is therefore not reach — a typed
  walk along the gold relations reaches the answer by construction — but
  **size**: how many tokens the typed context costs against the 199,146 of the
  untyped one, and what fraction of questions fit inside 6,000.

- **Metrics.**
  1. *Fit rate*: the fraction of questions whose typed three-hop expansion fits
     the shipped 6,000-token budget, with a Wilson interval.
  2. *Reduction factor*: untyped tokens ÷ typed tokens, per question, reported
     as a median with quartiles.
  3. *Fan-out per hop*: entities reached at each hop, median. A three-hop
     MetaQA answer is a set, so the typed walk is a bounded tree rather than a
     path, and its size is the product of three branching factors. That
     product is what decides whether typing is enough.

- **Population.** The same 100 three-hop dev questions E-015 and E-016 used, so
  every figure here sits beside theirs without a population caveat. The
  confirmatory split is not touched: this entry decides a build direction, not
  a published result.

### Decision rule, fixed before the run

1. **Fit rate ≥ 0.80.** Typed expansion alone puts the three-hop chain inside
   the shipped budget. Consequence: **P3's first registered experiment is
   typed expansion, not an agent.** An agent is justified only by whatever
   typed expansion leaves on the table, and the next entry measures the price
   of choosing the relations without the gold chain — the analogue of E-016's
   "the price of not knowing which 90 tokens".
2. **Fit rate ≤ 0.30.** Typing is not the saving. The fan-out is inherent to
   this KB at depth three, and **E-016's reading that "the walk is the problem"
   is wrong or incomplete** — it would mean no walk of this family fits, typed
   or not. Consequence: the decomposition thesis does not inherit E-016 as
   support, and P3 has to justify itself on something else. This branch is the
   one that costs the most to accept and it is written down first for that
   reason.
3. **Between.** Reported, no build direction is decided here, and the reduction
   factor is carried into P3's own registration as a prior rather than as a
   verdict.

### Predictions, recorded before the run

1. **Fit rate above 0.80 — branch 1.** Nine relations, and only one is followed
   per hop, so the shell collapses by roughly the branching factor cubed.
2. **Median reduction factor between 100× and 1,000×.** If it comes back under
   33× the entry lands in branch 2 and my reading of E-016 was wrong.
3. **The fan-out is uneven and the middle hop dominates.** The first hop leaves
   a named entity and is small; the second lands on a person or a genre and
   fans wide; the third is bounded by that width. If any hop is the problem it
   is the second, and that is where a later selector would have to be good.
4. **A minority of questions will not fit at any typing.** Hub seeds — a
   prolific director, a common genre — fan out enough that even one relation
   per hop is thousands of triples. I expect 10–20% of questions in that
   condition, and if the figure is near zero I should suspect the measurement
   rather than celebrate.

### Threats to validity, recorded before the run

- **The relation sequence is an oracle.** Stated above and repeated here
  because it is the entry's whole limitation: this bounds what typing could
  buy, and says nothing about whether anything can pick the relations.
- **Reach is not measured and must not be inferred.** Following the gold
  relations reaches the answer by construction, so a reach figure from this
  design would be a tautology dressed as a result. Only size is reported.
- **A ceiling that looks generous makes the remaining problem look small.**
  E-016 is the precedent: its ceiling was 0.920 and the best oracle-free arm
  returned 0.120. Any reduction factor found here should be read as the
  numerator of a fraction whose denominator has not been measured yet.
- **MetaQA has nine relations and a uniform degree distribution.** The CR has
  neither. Concepts transfer, constants do not, and no branching factor from
  this entry is carried to the Magic side.
- **Multi-answer questions inflate the typed tree.** MetaQA three-hop answer
  sets run to a dozen entities; the typed walk must reach one of them, not all,
  but the walk does not know which and so pays for the whole level. The
  measurement reflects that and is not corrected for it.

### Cost

**Zero model calls.** Three targeted Cypher expansions per question over 100
questions, against the already-loaded MetaQA instance.

### Actual result

**Actual result (2026-09-13, dev split, 92 of 100 three-hop questions, zero
model calls): branch 3 — typing buys a great deal and is not enough, and the
residual has a name.**

Harness check first, because nothing below is readable without it: **the typed
walk reproduced the chain it followed on 92 of 92**. Following the gold chain's
own relations must return the gold chain; if it did not, the query, the
direction handling or the visited rule would be wrong and every size figure
would be fiction.

| | |
|---|---|
| questions measured | 92 (8 excluded — no chain in the pool, the same 8% as E-016's 0.920 ceiling) |
| **fit rate at the shipped 6,000 tokens** | **0.522** [0.421, 0.621] — 48/92 |
| typed tokens | median **5,676** (q1 1,412, q3 35,962) |
| untyped tokens | median 193,797 |
| **reduction factor** | median **30.6×** (q1 5.5×, q3 76.1×) — the bar was 33× |

Fan-out, entities newly reached per hop: **2 / 89 / 42** at the median, with a
hop-2 maximum of **7,363**.

**The median typed expansion costs 5,676 tokens against a 6,000-token budget.**
It fits by three hundred tokens. That is the whole result in one line: typing
takes a 193,797-token shell down to something that *just* fits, for half the
questions.

### The residual has a name, and it is not depth

An exploratory cut of the same run — descriptive of a distribution already
measured, no selection involved, and labelled exploratory wherever quoted:

| | questions that fit 6,000 | questions that do not |
|---|---:|---:|
| median hop-2 fan-out | **22** | **493** |

And the middle relation on the 44 that do not fit:

| relation | count |
|---|---:|
| `has_genre` | 20 |
| `release_year` | 19 |
| `starred_actors` | 3 |
| `in_language` | 1 |
| `has_tags` | 1 |

**Thirty-nine of forty-four are `has_genre` or `release_year`.** Those are hub
relations by nature: "movies in the same genre as X" or "released the same year
as X" passes through a node with thousands of neighbours. `written_by`,
`directed_by` and `starred_actors` pass through a person and fan out by tens.

So the three-hop problem, as far as this project has measured it, is **not
depth and not untyped walking**. It is **traversing a hub**. A chain of three
person-shaped relations is cheap at any depth; one genre or one year in the
middle is what builds the haystack.

Raising the budget does not fix it either: fit rate goes 0.522 at 6,000 →
0.609 at 12,000 → 0.685 at 24,000 → **0.793 at 48,000, and 0.793 at 96,000**.
Nineteen questions fit at no budget tested. They are the hub cases.

### Predictions, scored

1. **"Fit rate above 0.80 — branch 1."** *Wrong.* 0.522.
2. **"Median reduction between 100× and 1,000×."** *Wrong*, and by an order of
   magnitude: 30.6×. **The reasoning attached to it was also wrong**, separately
   and worth recording: it said that a reduction under 33× would put the entry
   in branch 2. It did not — the branch reads the *fit rate*, and a median
   reduction just under the bar sits happily beside a fit rate of 0.522 because
   the distribution is enormously skewed (q1 5.5×, q3 76.1×). Two quantities
   were conflated in a prediction written by the person who had defined both.
3. **"The fan-out is uneven and the middle hop dominates."** *Right*, and it is
   the only one. 2 / 89 / 42, with the hop-2 maximum at 7,363.
4. **"10–20% will not fit at any typing."** *Wrong, and optimistic.* 47.8% do
   not fit the shipped budget and 20.7% fit at no budget tested.

One of four right. The one that was right is the one that turned out to matter.

### What this decides, and what it refuses to decide

**Branch 3 applies as registered: no build direction is decided here.** The
reduction factor goes into P3's registration as a prior, not as a verdict. That
is the rule refusing to hand P3 a mandate on a 0.522, and it is the right
refusal — the same bar that stopped E-016 adopting a significant result.

What P3 inherits is sharper than a mandate anyway:

- **Typed expansion is necessary.** A 30× reduction is not a detail, and no
  agent should be built that expands untyped.
- **Typed expansion is not sufficient**, and the gap is concentrated: 39 of the
  44 failures pass through two relations out of nine.
- **The target is hub traversal, not multi-hop.** Any P3 design should be
  registered against that, and a design that helps with depth in general but
  not with hubs in particular would be solving the wrong half.
- **An agent is still not obviously the answer.** Seeing that an intermediate
  set has 493 members and deciding to filter is something a rule can do. That
  the cheapest mechanism has not been ruled out is, again, the finding.

### The limitation that bounds every figure above

The relation sequence was read off the gold chain. This measures what typing
would cost **if something chose the relations correctly**, and nothing here
chose. The price of choosing is unmeasured, and E-016 is the precedent for how
large that price can be: its ceiling was 0.920 and the best oracle-free arm
returned 0.120. Every number in this entry is a numerator whose denominator has
not been measured.

---

## E-018 — does the governing rule *cause* the answer, or do easy questions get it? (registered 2026-09-13, run 2026-09-13, **unresolved**)

- **Registered:** 2026-09-13, after the Magic-side audit and **before any
  injected context is built**.

- **Where this comes from.** An exploratory cut of E-001's evaluation run: on
  the 42 questions carrying `gold_cr_rules`, every arm sits near **0.80** when
  retrieval brought a gold rule and near **0.35** when it did not, and every
  arm brings one on about a third of the questions.

  | arm | gold rule retrieved | correct when present | when absent |
  |---|---:|---:|---:|
  | A vector | 14/42 | 0.786 | 0.393 |
  | B graph | 16/42 | 0.812 | 0.308 |
  | C hybrid | 17/42 | 0.824 | 0.360 |

  The between-arm difference E-001 measured is **0.01**. This is **0.39 to
  0.51**. If it is causal it is the largest effect this project has measured on
  its own corpus and it explains the null: the arms are indistinguishable
  because they fail at the same thing.

- **Why it cannot be published as it stands.** Conditioning on whether
  retrieval succeeded is post-selection. The questions where the gold rule
  arrives may simply be the easy ones — a card with a short ruling, a keyword
  with a definition one hop away. That is the confound that invalidated E-012a,
  where observed context-size buckets read as a size effect and assignment
  inverted the conclusion. **Assignment is the only thing that separates them**
  and this entry assigns.

- **The decision this informs.** Whether Phase 9's target is "make retrieval
  reach the governing rule" — a specific, expensive engineering programme — or
  whether that target rests on a correlation the data cannot support. If the
  effect survives assignment, the programme has a measured justification. If it
  does not, the arms' equality means something else and Phase 9 needs a
  different objective.

### Design

- **Population.** The 42 evaluation questions carrying `gold_cr_rules`. This is
  the evaluation split's **second reading**, declared here and published
  wherever any figure from it is quoted. It draws **no arm comparison**: E-001's
  verdict is untouched and cannot be revised by this entry, which is a
  within-arm intervention on one arm.
- **Arm.** `B` (graph) only. The question is whether the generator's
  correctness depends on the rule being present, which is not an arm property,
  and one arm keeps the cost to a few dollars.
- **Three conditions, paired within question.**

  | condition | context |
  |---|---|
  | **control** | exactly what retrieval produced |
  | **placebo** | control plus *k* CR rules drawn at random from outside the gold set, seeded |
  | **treatment** | control plus the question's `gold_cr_rules` |

  *k* is matched per question to the number of gold rules injected, so placebo
  and treatment add the **same number of items and comparable tokens**. The
  token budget is raised for all three conditions alike so that nothing is
  evicted and the comparison is not silently measuring `enforce_budget`.

- **Why the placebo is not optional.** Without it, a lift under treatment is
  equally explained by "more context" or "rule-shaped text in the prompt". The
  placebo is the registered falsifier: **if placebo lifts accuracy as much as
  treatment, the effect is not the governing rule** and this entry reports that
  instead.
- **Questions where the gold rule was already retrieved are kept and analysed
  separately.** For those, treatment is a near no-op and should show no lift. A
  lift there is evidence the intervention is doing something other than what it
  claims, and it is the second check that can return negative.
- **Metric and contrast.** Judge-scored `correct` under the frozen rubric
  `p6-c1`, the same two-way collapse E-001 used. Primary family: **treatment vs
  control** and **placebo vs control**, exact McNemar paired within question,
  Holm over the two, alpha = 0.05.
- **Detectable effect, computed before the run.** Exact McNemar needs 6
  discordant pairs one way for raw *p* < 0.05 and 7:0 for the stricter Holm
  step at family size 2. On the 26 questions where the gold rule was absent, an
  observational lift of 0.45 would produce roughly 12 discordant pairs. The
  design is adequately powered **for the effect the observational cut suggests**
  and underpowered for anything much smaller, which is stated rather than
  discovered.

### Decision rule, fixed before the run

1. **Treatment beats control at its Holm step and placebo does not.** The
   governing rule causes the answer. Consequence: **Phase 9's registered
   objective is retrieval reaching the gold rule**, and E-013's abandoned
   bridge problem — from card or question to chapters outside 700 — becomes its
   first entry rather than a parked one.
2. **Placebo beats control by a comparable margin.** The effect is context
   volume or prompt shape, not the rule. Consequence: Phase 9 does not target
   gold-rule recall, and the observational cut is retracted in the journal
   where it was recorded.
3. **Neither beats control.** The observational lift was selection, exactly as
   E-012a's was. Consequence: the null in E-001 is not explained by retrieval
   reaching the rule, and Phase 9 needs an objective this project has not yet
   identified. **This branch is the one that costs the most and it is written
   first for that reason.**

### Predictions, recorded before the run

1. **Treatment lifts correctness on the rule-absent subset by 0.25 to 0.45** —
   less than the observational 0.45, because some of that gap is selection and
   I expect the selection share to be real but minority.
2. **Placebo lifts by less than 0.10.** If it lifts more, the entry lands in
   branch 2 and the Magic-side reading from 2026-09-13 is retracted.
3. **No lift on the already-present subset**, within noise.
4. **Some treatment answers will be wrong *with* the gold rule in front of
   them**, and that residual is the interesting number rather than a failure of
   the design — it is this corpus's version of what E-016 measured, the price
   of having the evidence and not using it.

### Threats to validity, recorded before the run

- **The judge is not blinded to the condition.** Treatment answers can cite a
  rule number that control answers cannot, and the judge sees the answer.
  E-010's blinding check failed at 0.778 on a weaker version of this problem
  and the project concluded item-level blinding was unachievable there. The
  same is likely true here. **The entry publishes unblinded and says so**,
  under the `sufficiency` precedent; it does not assert a blind it has not
  measured.
- **Injecting the gold rule is an oracle intervention.** No figure here is a
  system score — it measures the generator's use of evidence, not any
  retriever's ability to find it. The project has three precedents for that
  distinction being missed and one withdrawal that cost a headline.
- **Second reading of the evaluation split**, declared. E-001's numbers stand;
  this entry may not be substituted into them.
- **`gold_cr_rules` is a human key.** A loose key injects rules the question
  did not need and dilutes the treatment toward the placebo; a tight key does
  the opposite. The keys were written before any retriever existed, which
  protects against one direction of bias and not the other.
- **n = 42, of which 26 carry the effect.** Adequately powered for a large
  effect and nothing else.

### Cost

Three conditions × 42 questions = 126 generations plus 126 judge calls on arm
B, at the pinned `gpt-4o-mini`. Expected under US$ 3, with `--limit` and a
printed estimate before any spend.

### Amendment 2026-09-13 — five of the questions carrying the effect never called the model, and the branch that cancels a phase fires on failure to reject

Written after a red-team pass over the entry and **before the first API call**.
Nothing below was learned from a run. Every figure in it is recomputed from
E-001's recorded arm-B evaluation artifacts, which have not changed.

#### What was verified first

The entry's motivating table reproduces exactly from
`runs/e001_B_{retrieval,verdicts}_eval.jsonl`: 42 questions carry
`gold_cr_rules`, 16 have a gold rule among their retrieved `rule` evidence and
13 of those score `correct` (0.812), 26 do not and 8 score `correct` (0.308).
Two facts the entry did not have came out of the same pass.

**Five of the 26 never reached the generator.** All five —
`hand-humility-opalescence`, `hand-clone-copies-printed-pt`, `rg-1182`,
`rg-3915`, `rg-1469` — retrieved with `outcome = no_seed`, and
`answerer.py` refuses on `outcome is not RESOLVED or is_empty` before any
model call. This is deliberate and documented: `NO_SEED` means *entities
exist, none reaches the rule graph*, and `Outcome`'s docstring says no value
other than `RESOLVED` may be answered from. It is not a defect. But it means
the manipulated variable on those five is not the presence of the governing
rule, and it is worth recording that the refusal these five received is **not**
retrieval returning nothing: they carried 12, 9, 7, 5 and **28** evidence items
respectively. The refusal text — *"retrieval returned no usable evidence"* — is
false as written on all five, and is the shape of sentence that makes an
aggregate read wrong later.

Applying standing rule 9 to the entry's own table: *of the questions whose gold
rule retrieval did not bring, how many did the arm answer correctly* — what
**else** makes that return 0.308? **Retrieval resolving no seed, so the arm
never answered at all.** Among the 21 questions the generator actually saw, the
absent-condition rate is **8/21 = 0.381**, and the observational gap the entry
is built on is **0.812 − 0.381 = 0.431**, not 0.504. It remains the largest
effect this project has measured on its own corpus, and it is smaller than the
entry claimed.

**The gold key is thinner than assumed, and this confirms rather than weakens
the entry.** The median question carries **one** gold rule, and **13 of the 16
present questions have their full gold set retrieved**. The entry's claim that
treatment is a near no-op on the present subset holds for 13 of 16; three
questions receive a genuine remainder. (An earlier draft of this amendment
carried 2.5 gold rules per question — that constant is E-013's, measured on the
26-question failure population, and it does not transfer. It was checked
against this population before being used, which is the only reason it is a
sentence here and not an error in the design.)

#### Change 1 — the five `no_seed` ids leave the primary, and are run anyway

Frozen to `data/golden/e018_no_seed_ids.json` **before any injected context is
built**, from E-001's recorded retrieval rather than recomputed at run time.
They are **excluded from the primary contrast**: on them the intervention would
manipulate entity linking as well as rule presence, and a design that moves two
things answers neither.

They are still run in all three conditions and reported as a **named
exploratory stratum** — *what the governing rule buys on questions where
linking resolved nothing* is a real question, it is the question Phase 9's
Front C is partly about, and five cases at ≤ US$ 0.30 is not a saving worth
making. The stratum fires no branch and enters no test family. The alternative
considered and rejected was a fourth condition that lifts the `outcome` guard;
it measures something valuable and it makes the primary uninterpretable on its
own.

#### Change 2 — the primary denominator is frozen, and it is 21

The entry stated its population as 42, computed its power on 26, and attached
neither to its decision rule. Two defensible denominators with opposite
verdicts on a marginal result, chosen after the labels exist, is the 2026-09-13
defect class reappearing inside the entry written to avoid it.

**The primary contrast is computed on the rule-absent subset**: the arm-B
evaluation questions carrying `gold_cr_rules` whose retrieved evidence contains
no gold rule, minus the five above. Ids frozen to
`data/golden/e018_absent_ids.json` before the run, from E-001's record.
**n = 21**, printed here before the first call. The 16-question present subset
and the 42-question pooled figure are secondaries and fire no branch.

#### Change 3 — branch 3 splits, because failure to reject is not evidence of absence

This is the amendment the entry most needed. Branch 3 cancelled a phase on a
null, and the entry's own prediction 1 registers a lift of **0.25 to 0.45**
while its power arithmetic detects far less than that.

Recomputed at n = 21, exact McNemar, Holm over a family of two (strict step
α/2 = 0.025):

| discordant split | *p* | net lift | clears strict step |
|---|---:|---:|---|
| 6:0 | 0.031 | 0.286 | no |
| 7:0 | 0.016 | 0.333 | yes |
| 8:1 | 0.039 | 0.333 | no |
| 9:1 | 0.021 | 0.381 | yes |
| 10:2 | 0.039 | 0.381 | no |
| 11:2 | 0.022 | 0.429 | yes |

**The smallest net lift that can clear the strict step is 0.333.** The bottom
half of the entry's own predicted interval is undetectable by its own design.
So:

- **3a — inconclusive, and it is the default.** Neither contrast clears its
  Holm step and the treatment−control paired difference's 95% interval
  **includes +0.20**. Consequence: **nothing is cancelled.** The observational
  cut stays unpublished, Phase 9's objective is recorded as *unresolved*, and
  the entry states that 21 paired questions cannot separate a 0.25 effect from
  zero.
- **3b — evidence of absence.** Neither contrast clears its Holm step **and**
  the interval **excludes +0.20** — at n = 21 that is roughly net discordance
  of at most one in the treatment's favour. Only 3b carries the registered
  consequence of cancelling Phase 9's objective.

Registered now, before the run: **this entry is far better able to confirm the
effect than to rule it out**, and that asymmetry is published wherever any
figure from it is quoted.

#### Change 4 — the construct gets a bar, and the bar is placed where it can bind

Branch 1 fired on significance alone. On 2026-09-13 a registered effect-size
bar refused two significant results in this project and was right both times,
so the omission is not defensible.

But an honest bar has to be able to bind. On the treatment−control contrast at
n = 21 it cannot: the smallest clearing split already carries a net lift of
0.333, so any bar at or below 0.25 is decorative. **Recorded as such rather
than written as a rule**: the discordance threshold already enforces a lift of
at least 0.333 on that contrast, and no separate bar is added to it.

The bar that can bind is on the construct. **Branch 1 additionally requires
treatment − placebo ≥ 0.15** on the frozen subset. That contrast is what names
the thing the entry claims — goldness net of volume and rule-shaped text — and
it is where a null can hide behind a significant treatment-vs-control result.
It is registered as a **bar, not a third test**: at n = 21 a Holm family of
three would need 7:0 on every contrast and would make branch 1 nearly
unreachable at the entry's own predicted effect. Below 0.15, the result is
reported as *"the rule helps, and this design cannot separate that help from
putting more rule-shaped text in the prompt"*, and Phase 9's objective is
**reported, not adopted**.

#### Change 5 — the branches are made exhaustive, and branch 2 stops using an adjective

> *"2. Placebo beats control by a comparable margin."*

That is the sentence E-001's amendment 2026-08-15c was written to outlaw: it
has at least two defensible readings with opposite verdicts. Four real outcomes
fall outside the three branches as registered — most importantly the likeliest
one, *both clear their steps and treatment clears by more*. Restated
mechanically, and now covering every outcome:

1. **The rule causes the answer.** Treatment clears its Holm step **and**
   treatment − placebo ≥ 0.15. Consequence unchanged.
2. **The effect is volume or prompt shape.** Placebo clears its step **and**
   treatment − placebo < 0.15. Consequence unchanged: Phase 9 does not target
   gold-rule recall and the observational cut is retracted in the journal where
   it was recorded.
3. **3a inconclusive / 3b evidence of absence**, as above.
4. **The injection hurts.** Either contrast clears its step in the **negative**
   direction. Consequence: the entry reports a distraction effect, Phase 9's
   objective is not adopted on this evidence, and the finding is registered as
   the Magic-side counterpart of what E-015 measured, where more retrieval
   bought worse coverage.

#### Change 6 — a manipulation check, and branch 3 does not fire without it

Nothing in the entry verified that the injected rule reached the prompt as
sent. A null under an injection that silently failed is indistinguishable from
a null under an injection that worked, and this project has already shipped one
cell that had been handing the model the wrong evidence for months without a
trace showing it.

Per treatment generation the run records the injected rule numbers, whether
each appears in the text `prompt_sha256` was computed over, and whether the
answer's handles include any of them.

- **Registered floor: the injected rule appears in the prompt as sent on
  21/21**, checked mechanically, hard-failing the run if not.
- ***Gold-rule citation uptake*** — the share of treatment answers citing at
  least one injected rule — is reported as a named secondary. **If uptake is
  below 0.50, branch 3 does not fire**: the entry reports that the intervention
  did not reach the answer, and a null under a treatment the generator never
  used is a null about the harness.

#### Change 7 — the ceiling, computed before the run and from the keys the run will score

E-013 paid for this lesson and E-016 answered it: *a ceiling is a claim about
the experiment, and it has to be computed over the experiment's own inputs.*
E-018 computed a detectable effect and no ceiling, and the ceiling matters more
here than in either of them, because the 2026-09-13 audit recorded that
**roughly 60% of this arm's correct answers cite no CR rule at all — they are
grounded in rulings and card text.**

Before any call, the author reads each of the 21 keys and records whether the
key's verdict is derivable **from that question's `gold_cr_rules` alone**. That
count is the maximum number of flips this design can produce; it is printed in
this entry before the run, and any result above it is a defect in the
measurement rather than a finding. **If the ceiling is below 0.333 × 21 ≈ 7
questions, the entry is redesigned rather than run**, because branch 1 would be
unreachable by construction.

This is also the only honest test of the entry's own fourth threat —
*`gold_cr_rules` is a human key* — which was stated and never measured.

#### Change 8 — the rendering deliverable, which standing rule 8 already required

The entry registered no rendering step, on the same day the rule requiring one
was adopted, for a comparison whose gate consequence is a whole phase.

`scripts/e018_inspect.py` renders per case: the question, the key, the
control / placebo / treatment **prompts as sent** with `prompt_sha256` verified
against the rebuilt prompt, the three raw answers, the three judge labels and
rationales, and the injected rule numbers. Categories read **in full** because
each holds five cases or fewer: treatment flips to correct, treatment flips to
incorrect, placebo flips, the `no_seed` stratum, `void`, and unparseable judge
output. Written to `docs/error-samples/e018.md`, versioned, and read **before
any figure leaves this entry**.

#### Change 9 — no pair is dropped for a condition-dependent reason

The rubric carries `void` and the judge short-circuits refusals to a label
without a model call, and the entry said nothing about either. A refusal scores
*not correct* in every condition, inheriting E-001's scoring rule. A `void`
label voids the **question in all three conditions**, is counted, and its ids
are listed. No other exclusion is permitted after the run; any exclusion
proposed post hoc is reported both ways.

#### Threats added to the list, recorded before the run

- **The outcome instrument is not validated, and the treatment stresses its
  weakest boundary.** E-011's gate did not fire at 55 audited answers; the
  judge agreed with a human on `correct` 13/18 and on `partial` **4/14**, and
  all 15 disagreements ran one way with the judge stricter. The two-way
  collapse puts this entire result on the `correct`/`partial` boundary, which
  tie-break 3 decides on *reasoning matching the key* — a property the
  treatment moves directly, since the key cites CR rules and treatment puts
  those rules in front of the model. Consequences registered now: the
  **three-label distribution is reported per condition** beside the collapsed
  figure; an ordinal shift with no change in the collapse is named as its own
  outcome — *"the rule improves the answer below the resolution of the
  registered measure"* — and **blocks branch 3**; and no figure here is
  described as validated correctness.
- **The placebo controls volume and rule-shaped text; it does not control
  topicality.** A random draw from the CR is off-topic by construction, so
  branch 1 cannot distinguish *this governing rule* from *any rule about this
  subject area*. Those imply different Phase 9 programmes — exact gold-rule
  recall, which E-013 measured at a ceiling near zero, versus topical rule
  coverage, which the `REFERENCES` work already scoped. Branch 1's consequence
  is therefore narrowed to **"retrieval reaching rules of the right subject
  area"**, of which exact gold-rule recall is the strictest reading. A
  near-miss condition — *k* rules from the gold rules' own chapter, excluding
  the gold rules — would separate them for about US$ 1 and is **registered as
  optional, to be decided before the run, not after seeing the result.**
- **No noise floor, which E-011's amendment item 9 made binding** for paired
  comparisons over these rows: a model at temperature 0 is not deterministic.
  A second control replicate (21 generations, 21 judge calls, ≈ US$ 0.50) runs
  **first**; control-vs-control discordance is published beside the treatment
  contrast, and if it reaches 4 one way the thresholds above are recomputed
  against that floor before any branch fires.
- **The motivating comparison is between two non-equivalent question sets.**
  0.431 is a difference between the questions whose gold rule arrived and those
  whose did not; E-001's 0.01 is paired within question between two arms. They
  are not commensurable and the entry will not call one larger than the other.
  The stratum composition of the 16 and the 21 is printed before the run, and
  no per-stratum claim is made from either side.
- **What the treatment changes besides goldness, now pinned.** Injected rules
  enter the `Subgraph` through the same path as retrieved ones, so
  serialization, handle contract and `expand()`'s fabricated-citation detector
  treat them identically. The merged evidence is shuffled at a recorded seed in
  all three conditions, so injected items are never a contiguous block at one
  end. The placebo draw is redrawn until its token count is within ±20% of the
  treatment's for that question, and the realized per-question deltas are
  published. `notice=False` is set explicitly and `dropped`/`capped` are
  recorded per condition. The 63 generations are interleaved by question rather
  than batched by condition. And a check that can fail is registered: **0 of 21
  control contexts differ from E-001's under the raised budget**, verified
  mechanically — E-013 measured `dropped` empty at this budget, so this should
  hold, and if it does not then the control is not "exactly what retrieval
  produced".
- **The second reading of the evaluation split is spent here.** After this
  entry no third reading is available for Phase 9's confirmation. Whether the
  development split must grow before Front C opens is **open**, recorded in the
  journal for 2026-09-13, and not answered by this entry.

#### Cost, restated

Three conditions × 21 primary questions = 63 generations and 63 judge calls,
plus 15 questions × 3 in the present subset, 5 × 3 in the `no_seed` stratum,
and 21 in the noise-floor replicate. Still under US$ 3 at the pinned
`gpt-4o-mini`, with `--limit` and a printed estimate before any spend.

#### What this amendment does not change

The design's core is untouched: assignment rather than observation, a placebo
as the registered falsifier, arm B only, pairing within question, and the
expensive branch written first. The red-team pass did not find a reason to
abandon the entry. It found that the entry could return a number that reads as
a verdict and is not one, in six specific ways, and every one of them is closed
above **before the first call rather than after the result.**

### Amendment 2026-09-13b — what "inject the gold rule" injects, and what the ceiling is computed over

Written while building the ceiling instrument the previous amendment
registered, and **before the first API call**. Both changes come from rendering
the 21 questions rather than from reasoning about them.

#### The treatment injects the subtree, not the bare rule

The entry said *"control plus the question's `gold_cr_rules`"* and never said
what a rule is. The CR answers that differently than the entry assumed: a rule
number can name a heading whose substance lives entirely beneath it.

Measured over the frozen primary population, from the CR the run will use
(effective August 7, 2026):

| | |
|---|---:|
| gold rules across the 21 questions | 30 |
| of those, rules that have subrules | **10** |
| largest: `613.7` | 13 subrules |
| `400.7` | 12 subrules |
| `707.10` | 7 subrules |
| own text only, all 30 rules | 11,197 chars |
| with subtrees | **24,082 chars** |

Injecting `613.7` alone injects a paragraph of preamble and leaves out the
thirteen subrules where the cases live. On `701.15` it injects the single word
*Goad*. A treatment that does this and returns a null would be reported as *the
governing rule does not cause the answer*, when what was injected was a
heading — and standing rule 9 asks what **else** makes a null come back, which
is exactly this.

**Registered:** treatment injects each gold rule **with its subtree**, in
document order, through the same `Subgraph` path as retrieved evidence so
handles and the fabricated-citation detector treat them identically. The
subtree is taken from `cr_parser.subtree`, which walks parent links rather than
number prefixes — `613.4b` does not start with `613.4.`, and a prefix match
would pull `613.41` into `613.4`.

**The placebo follows the treatment, not the rule count.** The previous
amendment matched the placebo to within ±20% of the treatment's token count.
That stands and now binds against the subtree: the placebo draws whole rule
subtrees at random from outside the gold set and redraws until it matches. A
placebo matched against bare parents while the treatment carries subtrees would
stop controlling volume, which is the only thing it exists to control, and the
entry would land in branch 1 on a context-size effect.

**The token budget is raised for all three conditions alike**, as already
registered. At roughly 24,000 characters of rule text spread over 21 questions
this is about 280 added tokens per question on average, well inside the budget
E-013 measured as never firing on this corpus. `dropped` and `capped` are
recorded per condition anyway, and a non-empty one invalidates the comparison
rather than being noted afterwards.

#### The ceiling is computed over control plus the rules, not over the rules alone

The instrument first asked the reader whether the key's verdict was derivable
*from the gold rules alone*. That is a stricter and different question, and it
would have produced a lower ceiling for the wrong reason: these 21 questions
already receive cards and rulings — what they lack is a rule — so judging the
rules in isolation marks `false` exactly where the card text was present all
along and the rule was the only missing piece. Those are the cases the entry
exists to find.

**Registered question, and it is the treatment's own definition:** *with what
retrieval already brought, plus the gold CR rules, is this key's verdict
derivable?* The worksheet lists the evidence each question already carries, by
kind and handle, so the reader is judging the context the treatment actually
produces. The wording was corrected before any verdict was recorded; no reading
was taken under the earlier phrasing.

#### A stale gold annotation, and what it would have done

`hand-regeneration-zero-toughness` carries `gold_cr_rules: [701.15, 704.5f]`
and its key reads *"Regeneration replaces a destruction event (701.15)"*. In
this CR, **701.15 is Goad**; regeneration is 701.19. The number resolves, so
nothing raises — the injection would have carried four subrules about goading
into a question about regeneration, and the null would have been invisible.

This is one case in 21 and it was found by rendering, not by a check. The
verdict sheet therefore carries `stale` as a field of its own, separate from
the derivability answer, because the two have different consequences: `false`
is a fact about the corpus and belongs in the ceiling, while `stale` is a
defect in the key file and belongs in Phase 9's backlog. **`score` reports any
stale question and the run does not proceed over one**: either the key is
corrected before the run, or the question is excluded and the exclusion is
declared here. It may not be left as it is.

Whether the other 41 gold annotations are stale in the same way is **not known
and is not claimed**. A number that resolves to the wrong rule cannot be
detected mechanically, only read. The 21 in the primary are read as part of the
ceiling; the remaining 21 are not, and any figure drawn from them carries this
sentence.

#### What this amendment does not change

The population, the branches, the effect-size bar, the manipulation check and
the rendering deliverable all stand as amended earlier today. This changes what
a condition contains and what the ceiling's question means — both before any
verdict was recorded and before any spend.

### Amendment 2026-09-13c — how the placebo is drawn, and a clause amendment 2026-09-13b broke and did not say so

Written while implementing `scripts/run_e018.py`, **before any API call**. The
run's checks are what produced each of these; none was reasoned out in advance.

#### The placebo draws at the gold rule's own depth in the CR tree

The first implementation drew **level-1 chapters**. The treatment never injects
one — the 30 gold rules in this population are 19 level-2 numbered rules and 15
level-3 lettered subrules, and none is a chapter — so the placebo was a
different shape of object from the thing it controls, out of a pool of 147
instead of 3,161. It could not match: no draw for a two-rule question landed
inside the registered ±20% in 400 attempts, and the run **refused rather than
widening the tolerance**, which is what the check exists for.

**Registered:** the placebo draws one subtree per gold rule, **at that rule's
level**, excluding every number in the treatment's subtrees. Level carries both
things the placebo controls. *Volume*, because a level-2 subtree runs to a
median 342 characters against a level-3 subtree's 200, so drawing across levels
makes the token match a lottery. *Shape*, because a numbered rule trailing
lettered subrules reads differently from a lone subrule, and a treatment that
is always the first paired with a placebo that is sometimes the second differs
by more than goldness.

#### A clause amendment 2026-09-13b broke, named here rather than left standing

The original entry reads: *"k is matched per question to the number of gold
rules injected, so placebo and treatment add the **same number of items and
comparable tokens**."* Amendment 2026-09-13b changed the treatment to inject
subtrees and **did not update that clause**, which quietly stopped being true:
matching the number of injected *roots* no longer matches the number of items,
because subtree sizes differ. The first level-matched implementation produced
`rg-2249` with **9 items against 23** at equal tokens — same volume, visibly
different context.

**Registered, replacing the clause:** tokens are the criterion and item count
is a **tiebreak, not a second gate**. Every candidate draw inside the ±20%
token tolerance is collected and the one whose item count is closest to the
treatment's is taken. Realized counts are published per question either way.
After the tiebreak the run matches item count exactly on 13 of 20 questions and
within two on 18 of 20; `rg-2249` is 9 against 11.

This is recorded as a **broken promise found by printing the number**, not as a
refinement. The clause was published on 2026-09-13 and was false from the
moment amendment b landed.

#### The realized match, published before the run rather than after

Worst token delta across the 20: **19.6%**, on `rg-396`, whose treatment adds
56 tokens — the largest percentages sit on the smallest injections, where a few
tokens are a large share, and that is where the tolerance binds rather than
where the design is weak. Median delta 9.2%. The full per-question table is
printed by `run --dry-run` and by the run itself.

#### Constants fixed here and not elsewhere

- **`TOKEN_BUDGET = 24,000`**, four times the shipped budget, for all three
  conditions alike. E-013 measured `dropped` empty at 6,000 on this corpus and
  the treatment adds a median 199 tokens, so the raise is generous — and the
  run **hard-fails if anything is dropped or capped in any condition anyway**,
  because a budget that is merely probably slack is a guard that passes for two
  reasons.
- **`RANDOM_SEED = 20260913`** for the draw and for the shuffle.
- **Injected evidence carries `template="e018_injection"` and
  `path="(:Rule {N})"`.** It is not a traversal and a path claiming one would
  be a fabricated provenance inside the file that measures honesty about
  provenance. It enters through the same `Evidence` dataclass and the same
  `add_evidence` path as retrieved evidence, so `serialize`, `cited_handles`
  and `expand`'s fabricated-citation detector cannot tell it apart — which is
  what makes a citation of an injected rule count as a citation rather than as
  a fabrication.
- **`distance = 0`** on injected items: the oracle named this node, the way a
  question naming a card gives that card distance 0. It also puts injected
  items last in `enforce_budget`'s eviction order, which is moot because the
  run refuses if anything is evicted at all.

#### The noise floor runs first and the run refuses without it

`floor` generates control twice on all 20 and publishes control-vs-control
discordance; `run` refuses when `runs/e018_floor.jsonl` is absent and **reuses
the first replicate as the comparison's control**, so the pairing is exact
rather than approximate and the floor costs no extra control generations. At
four or more discordant pairs the decision rule's thresholds are recomputed
against the floor before any branch fires, as already registered.

#### Cost, measured rather than estimated from a table

`run --dry-run` prices the built prompts: **60 generations and 60 judge calls,
about US$ 0.06** at the pinned model, plus the floor's 40 and 40. The entry's
registered "under US$ 3" was an order of magnitude high and is superseded here.

### The ceiling, read 2026-09-13 and before any API call

**17 of 20 — 0.850 [0.640, 0.948] Wilson.** The gate registered before the
reading was 7. The design can run.

The question each of the 21 frozen questions was read against: *with what
retrieval already brought, plus the gold CR rules, is this key's verdict
derivable?* One question left the denominator as `stale` (below). Every verdict
carries a written justification and they are summarised here rather than
stored as a count, because a ceiling nobody can inspect is the thing this entry
exists to avoid.

#### What the ceiling changes about reading E-018's result

Before the reading, *"the model did not improve"* and *"the rules were not
enough"* were indistinguishable outcomes. They no longer are. With 17 of 20
derivable and a bar of 7, **a null in E-018 is a finding about the generator,
not about the corpus** — it would mean the model had the governing rule in
front of it and did not use it, which is this corpus's version of what E-016
measured. Prediction 4 is sharpened accordingly: the residual is the
interesting number and it now has a denominator.

It also sharpens the oracle threat already recorded. A treatment this
sufficient is a strong intervention; no figure from it is a system score, and
the distance between 0.850 and whatever E-018 returns is the generator's, not
any retriever's.

#### The three that are not derivable, and they have three different causes

The count is 3. The causes are not one thing, and the decomposition is worth
more than the count:

| id | why the verdict does not follow | what would fix it |
|---|---|---|
| `rg-102` | **card text is missing.** The context holds `Temur Battle Rage` and not `Death's Shadow`, whose power and toughness are the crux. The gold rules explain damage assignment and cannot supply a card that is not there. | retrieval reaching the second card, not more rules |
| `rg-271` | **a rule the annotation did not list.** `500.8` covers Aurelia adding a phase; nothing in the gold set establishes Time Stop skipping the remaining steps and phases. | a better gold key, or retrieval reaching beyond it |
| `rg-20` | **the key does not establish its own answer** — see below | nothing retrieval can do |

Only one of the three is *"retrieval must reach more CR rules"*. That is a
direct input to Phase 9's front ordering and it was not available from any
aggregate.

#### `rg-20` is a `void` candidate that three arms were scored against

Its key opens **"Probably 49,278."** and continues: *"There are
15,511,210,043,330,985,984,000,000 different ways to order the triggers on the
stack, so it's difficult to be certain of the maximum total power."* The key
does not assert the verdict it is used to score.

The rubric already has the label for this. `Correctness.VOID` is *"the answer
key does not answer the question asked"*, and it is excluded from every
denominator. Checked against E-001's evaluation run: all three arms were
scored **`incorrect`** on `rg-20`, each rationale of the form *"contradicts the
key's assertion of 49,278"* — the judge treating a hedged key as an assertion.
And `void` fired **zero times across the whole evaluation split**.

Naming that quantity in words, per standing rule 9: *of the 57 evaluation
questions, how many did the judge call `void`* returns 0 — and what **else**
makes it return 0? A rubric whose void criterion is narrower than *"the key
does not establish its answer"*, or a judge that never reaches for a label it
is not pushed toward. This is not evidence the label is broken; it is evidence
nobody has checked whether it can fire.

**What this does and does not change.** It does **not** change E-001's verdict.
`rg-20` is a concordant `incorrect` in all three arms, so removing it from
every denominator moves each arm by the same one question and the paired
contrasts are untouched. It does affect the absolute correctness figures, which
are computed over 57 rather than 56. **No figure is revised here**: the finding
is recorded, and re-auditing the split for further `void` candidates is a
Phase 9 task with its own entry, because one case found while reading is not a
survey.

#### The stale annotation, corrected, and what it moved

`hand-regeneration-zero-toughness` carried `gold_cr_rules: ["701.15",
"704.5f"]` while this CR numbers regeneration **701.19** — 701.15 is Goad.
Retrieval had brought `701.19`, `701.19a`, `701.19b` and `701.19c`: **the graph
found the governing rule and the annotation was looking for the wrong number.**

Corrected to `["701.19", "704.5f"]`, with `gold_path` corrected alongside.
Consequences, all checked:

- **`snapshot_sha256` is intact.** It hashes `question + "|" + answer`, not the
  annotations, so `pool_fingerprint` and every frozen hash in the project are
  unaffected. Verified rather than assumed.
- **The key's prose is NOT edited**, though it also says "(701.15)". The key is
  what E-001 was scored against; editing it retroactively would make published
  labels describe text that no longer exists. The inline citation stays stale
  and is recorded as such here.
- **The populations moved**, and the frozen files refused the change until it
  was made deliberately, which is what they are for. Gold rule retrieved:
  **16 → 17 of 42**. Primary population: **21 → 20**. The five `no_seed` ids
  are unchanged.
- **The ceiling is unchanged at 17 of 20**, because the stale question was
  already outside the denominator. The gate was registered at 7 of 21 and is
  not restated downward; the reading cleared it either way.

The motivating table at the head of this entry reads **16/42** for arm B. That
figure is superseded by **17/42** as of this amendment and is left in place,
per the project's practice of amending rather than rewriting.

#### How much staleness is there, and the honest bound

Of the 20 primary questions, **18 received rule evidence anyway** — the graph
brought rules, none of which matched the annotation. That is the population
where a stale number could hide, and it was read as part of this ceiling.

The pattern in 17 of the 18 is **not** staleness. It is E-013's bridge, now
visible question by question: retrieval brings the keyword definition
(`702.7` First Strike, `702.10` Haste, `702.12` Indestructible, `701.26` Tap)
and the key needs a structural rule (`613.x` layers, `614.x` replacement,
`400.x` zones, `603.x` triggers, `103.6` mulligans). `hand-regeneration-zero-
toughness` is the exception precisely because its gold and retrieved numbers
sit in the same neighbourhood, which is the signature of a renumbering.

**The bound, stated rather than implied:** that signature fires on 1 of 18 in
this population. It says nothing about the 22 evaluation questions outside it,
and staleness that lands far from what retrieval brought would not show this
signature at all. A number that resolves to the wrong rule cannot be detected
mechanically, only read.

### Actual result

Run 2026-09-13. Noise floor first, then the three conditions, 20 primary
questions, arm B, US$ 0.10 in total. **Branch 3 does not fire, and Phase 9's
objective is UNRESOLVED: nothing is cancelled and nothing is adopted.**

#### The contrasts

| | control | placebo | treatment |
|---|---:|---:|---:|
| `correct` | 6/20 | 5/20 | **8/20** |
| `partial` | 3 | 1 | 2 |
| `incorrect` | 11 | 14 | 10 |

- **treatment vs control** — discordant **2:0**, exact McNemar *p* = 0.500,
  Holm-adjusted 1.000. Difference **+0.100** [+0.000, +0.250].
- **placebo vs control** — discordant **0:1**, *p* = 1.000. Difference
  **−0.050** [−0.150, +0.000].
- **treatment − placebo** — **+0.150**, landing *exactly* on the registered
  0.15 bar. Reported as landing on it, not as clearing it; the bar is moot
  because branch 1 requires the Holm step first and the Holm step was not met.
- **Noise floor, collapsed: 1 discordant pair of 20.** The floor run announced
  2 over three labels; one of them (`rg-2711`, `partial` against `incorrect`)
  does not survive the two-way collapse the contrasts use, and comparing a
  two-label signal against a three-label floor would compare a number with
  somebody else's noise.

**The treatment contrast rests on two discordant pairs. Two identical control
runs produced one.**

#### Which branch, and why it is not branch 3

Neither contrast clears its Holm step, so branch 3 is reached — and one of the
two conditions registered in the 2026-09-13 amendment to stop it firing did
fire. The three-label distribution shifted toward the key by **+3 net steps**
(`rg-271` incorrect→correct, `rg-6370` partial→correct, `rg-650`
incorrect→partial, against `rg-2711` partial→incorrect) while the collapse did
not clear. That is the registered case for *"the rule improves the answer below
the resolution of the registered outcome"*, and it means the entry may not
report evidence of absence. Gold-rule citation uptake was **10 of 20, exactly
50.0%** — the other registered blocker asks for *below* 50%, so it did not
fire, and that is recorded as landing on the boundary.

#### Reading the cases, which is what standing rule 8 is for — and it changes the result

Two flips carry the whole contrast, so both were rendered with the prompt as
sent and the digests verified.

| question | control → treatment | injected | cited an injected rule? |
|---|---|---:|---|
| `rg-271` | incorrect → **correct** | 500.8 | **no** |
| `rg-6370` | partial → **correct** | 15 rules under 613.1f/613.7 | **yes, 613.1f** |

`rg-271`'s treatment answer reaches the right verdict — *"there is no
additional combat phase"* — and builds the whole argument on a **Time Stop
ruling that was in the control context too**. Rule 500.8 appears in the prompt
and nowhere in the answer. Under a prompt that requires a citation on every
claim, that flip is **not attributable to the injected rule by this run's own
instrument**. Uncited use cannot be ruled out; what can be said is that the
run provides no evidence for it.

So of the two gains, **one is attributable to the treatment and one is not.**
The effect this design was built to detect is, after reading, **one case**,
against a noise floor of one.

That reading was available only by rendering. The aggregate said +0.100.

#### Predictions, scored

1. **"Treatment lifts correctness on the rule-absent subset by 0.25 to 0.45."**
   **Failed.** Observed +0.100, not significant, and after the case reading the
   attributable part is one question.
2. **"Placebo lifts by less than 0.10."** **Held**, in the strongest direction:
   the placebo came in at **−0.050**, slightly below control. Adding
   token-matched, level-matched, non-gold rules did not help and marginally
   hurt. The 2026-09-13 Magic-side reading does not have to be retracted on
   volume grounds.
3. **"No lift on the already-present subset."** **Not tested.** The 17-question
   present subset was not run; only the primary was. It remains available.
4. **"Some treatment answers will be wrong *with* the gold rule in front of
   them, and that residual is the interesting number."** **Confirmed, and it is
   the largest thing in the run.** See below.

#### The residual, which is bigger than the effect

The ceiling read before the run said **17 of 20** questions are answerable from
what retrieval brought plus the gold rules. Treatment reached **8**.

**Residual: 9 questions where a reader judged the evidence sufficient, the
model had it, and the answer was still not right.**

And the citation record makes part of that concrete. **Five questions cite an
injected gold rule and are still scored `incorrect`** — `rg-102` (510.4,
702.19b), `rg-1591` (307.5), `rg-2249` (707.10), `rg-3155` (120.6), `rg-778`
(103.6, 103.6a). The rule arrived, the model quoted it, and the answer did not
follow. On another five the model cited nothing injected at all.

This is the Magic-side counterpart of what E-016 measured on MetaQA: the price
of having the evidence and not using it. It was registered as prediction 4 and
it is the finding this run actually produced.

#### What this does not license

- **It does not cancel Phase 9's objective.** Branch 3 did not fire. The run
  is underpowered by its own registered arithmetic — 2 discordant pairs where
  7:0 was needed — and an underpowered null is not evidence of absence.
- **It does not establish the generator as the bottleneck either.** The
  residual is striking and it rests on one reader's ceiling judgement, on n =
  20, and on citation as a proxy for use. It is a **lead that needs its own
  registered entry**, not a conclusion, and it must not be quoted as one.
- **No figure here is a system score.** Injecting the gold rule is an oracle
  intervention. It measures the generator's use of evidence, never any
  retriever's ability to find it.
- **E-001's verdict is untouched.** This was a within-arm intervention on arm
  B and the second declared reading of the evaluation split.

#### What the run exposed that was not on anyone's list

`rg-271`'s control context is **2,373 tokens, most of them about phasing**. The
question asks about an additional combat *phase*; the linker resolved the
keyword `Phase`, whose glossary entry covers both a subsection of a turn **and**
permanents phasing in and out, and the traversal then pulled the whole of
`702.26` — `702.26b`, `702.26d`, `702.26h`, `702.26m`, `702.26p` — into a
question about turn structure. The gold rule it needed, `500.8`, is one
sentence.

That is a **linking defect, not a reachability defect**, and Phase 9's fronts
are all aimed at reachability. It is recorded here because it was visible in
the first case anyone opened, and one case is not a survey.

#### Design lessons for E-019, recorded now

- **A bar placed on a multiple of 1/n is a bar that lands on itself.** At
  n = 20 every difference is a multiple of 0.05, so the 0.15 construct bar can
  only be hit exactly or missed by 0.05, and uptake can only be 0.45, 0.50 or
  0.55. Two of this entry's thresholds landed exactly on their boundary. Bars
  belong *between* attainable values.
- **Citation uptake is the instrument that made the case reading possible**,
  and it should be recorded by default on any injection experiment. Without it
  `rg-271` would have been counted as an effect.
- **The noise floor earned its cost.** It is the only reason the sentence "two
  discordant pairs against a floor of one" can be written at all, and at
  US$ 0.04 it was the cheapest part of the entry.

### The secondary subset, run 2026-09-13 — the negative control passes, and it exposes a defect in this entry's own floor

17 questions where retrieval had already brought a gold rule, three conditions,
US$ 0.05. Registered as *"kept and analysed separately… treatment is a near
no-op and should show no lift. A lift there is evidence the intervention is
doing something other than what it claims."* It fires no branch.

After de-duplication — required by the 2026-09-13 amendment and implemented
here — **13 of the 17 already carry every gold rule, so the treatment injects
nothing on them.** Four receive a genuine remainder.

#### The registered check passes

On the 13 where the treatment injects nothing:

| contrast | gained | lost |
|---|---:|---|
| treatment vs control | **0** | 1 (`hand-def-mill`) |
| placebo vs control | **0** | 4 |

**No lift, in either condition.** The intervention does not manufacture
correctness where it adds nothing, which is what prediction 3 asked and what
the primary needed in order to remain interpretable. Prediction 3 **holds**.

#### The four with a real injection, and the falsifier earning its place

| question | control | placebo | treatment | treatment cited |
|---|---|---|---|---|
| `hand-regeneration-zero-toughness` | incorrect | **correct** | **correct** | 704.5f |
| `hand-deathtouch-trample` | incorrect | **correct** | partial | none |
| `hand-first-strike-deathtouch` | correct | correct | correct | 510.4 |
| `hand-lifelink-prevented-damage` | correct | correct | correct | 615.1, 615.1a |

Both questions that moved were moved **by the placebo as well** — and on
`hand-deathtouch-trample` the placebo, which injects rules drawn at random,
beat the treatment. On these four the gold rule is not distinguishable from a
random rule of the same size and depth. That is the second independent reading
pointing the same way as `rg-271` in the primary.

`hand-regeneration-zero-toughness` is the question whose stale annotation was
corrected earlier the same day; its missing rule was `704.5f`, the
state-based-action rule that decides the answer. Treatment cited it and got
the answer right. **So did the placebo, which never saw it.**

#### The defect this run found, and it is in this entry's own design

On the 13 no-op questions the three conditions carry **identical content**. They
do not carry identical prompts: `conditions_for` shuffles the merged evidence
once per condition from a single generator, so each condition receives a
**different ordering of the same items**. Verified directly on
`hand-def-flying` — same five handles, three different orders.

The effect is not small:

| same content, different order | collapsed discordance, 13 questions |
|---|---:|
| control vs placebo | **4** |
| placebo vs treatment | 3 |
| control vs treatment | 1 |

**mean pairwise rate 0.205**, against the noise floor this entry published for
the primary of **0.050**.

And it is the generator, not the judge. On `hand-def-flying` the control answer
contains *"a creature with flying can block a creature with or without flying
[rule:702.9b]"* and is scored `correct`; the placebo answer, on the same five
items in a different order, **omits that sentence** and is scored `incorrect`.
The judge was right both times. Reordering identical evidence made the model
drop a clause the key requires.

#### What that does to the primary, stated plainly

`floor` generated control **twice from the same prompt object**, so it measured
decoding stochasticity at temperature 0 — and nothing else. But `run` gives
control, placebo and treatment **three different orderings**, so the primary
contrast carries a variance source the floor never sampled, and that source is
demonstrably larger than the one it did sample.

**The sentence "two discordant pairs against a floor of one" is withdrawn.** It
compared a contrast against a floor that excluded the contrast's dominant
variance. The floor passed for a reason other than the one claimed, which is
the defect class standing rule 9 was adopted for, one day after adopting it,
in a design written by the same hand.

**The verdict does not change.** Branch 3 was blocked and Phase 9's objective
was recorded as unresolved; more noise cannot turn a null into a rejection.
What changes is that the primary's null is **weaker evidence than it was
written up as**, and the case-level reading of `rg-271` — which never depended
on the floor — is now the load-bearing part of that result.

#### The fix, registered here before it is run

1. **The floor is re-run with the two control replicates at different
   shuffles**, which is the variance the design actually carries. 20 questions
   × 2 generations, about US$ 0.04. Until it exists, no figure from the primary
   is quoted against a floor.
2. **E-019 does not shuffle per condition.** The shuffle was introduced in
   amendment 2026-09-13 to keep injected items out of a recency slot, and it
   succeeded at that while introducing a larger problem. The replacement:
   shuffle the control's evidence **once**, share that ordering across every
   condition, and insert injected items at positions drawn from one seed. Order
   is then held constant and only content varies, which is what a controlled
   comparison requires.
3. **Order sensitivity gets its own entry.** *Does reordering identical
   evidence change the answer, and how often?* It is measurable without any
   injection, on any existing run, for the price of one extra generation per
   question — and if it holds at the rate seen here it is a larger effect than
   anything E-001 measured between arms, which would be a finding about the
   generator that the whole trilogy has been walking past.

#### What is not claimed

The 13 questions are `hand-def-*` definition items, which E-001 scored 0.91 on
and which sit near the `correct`/`partial` boundary E-011a measured the judge
worst at. The 0.205 rate is **measured on those questions and does not transfer**
to the primary's `interaction_multihop` population. What transfers is the
structural point: the floor did not measure the variance the contrast carries.
How large that variance is on the primary is unknown and is what fix 1 buys.

---

## E-020 — does reordering identical evidence change the answer? (registered 2026-09-13, not yet run)

- **Registered:** 2026-09-13, after E-018's secondary subset and **before any
  code exists**. `E-019` is reserved for Phase 10's three-arm comparison on a
  fresh split and is deliberately skipped here.

- **Where this comes from.** E-018's secondary subset ran 13 questions on which
  the treatment injected nothing, so all three conditions carried **identical
  content**. They did not carry identical prompts: the runner shuffled the
  merged evidence once per condition, so each received a different **ordering**.
  Collapsed discordance across those orderings was **4 of 13** (control against
  placebo), **3** and **1** for the other pairs — mean pairwise **0.205** —
  against the **0.050** that entry published as its noise floor, which had been
  measured by generating twice **from the same prompt**.

  It is the generator, not the judge. On `hand-def-flying` the control answer
  contains *"a creature with flying can block a creature with or without
  flying"* and scores `correct`; the same five items reordered produced an
  answer that **omits that sentence** and scores `incorrect`. The judge was
  right both times.

- **The decision this informs, and it is larger than one entry.** E-001
  measured a between-arm difference of **0.01** and published `inconclusive`.
  If reordering identical evidence moves the judged outcome at anything near
  0.20, then **every paired figure this project has published sits below a
  variance source nobody controlled**, and E-019 cannot be run until it is
  controlled. That is the claim this entry exists to confirm or kill, and it
  must be settled before Phase 10 spends a fresh split.

### Design

- **Population.** The **20 development-split questions**, arm B, from the
  existing retrieval dump. No new retrieval, no new annotation, and **no
  reading of the evaluation split** — the dev split is where iteration is
  allowed, and this entry needs no gold key of any kind.
- **Orderable by construction, checked:** all 20 carry more than one evidence
  item, so every question can be reordered. A one-item context would be a
  question this design cannot move and it would silently dilute the rate.
- **Four generations per question**, from one recorded seed:

  | sample | ordering |
  |---|---|
  | `A1` | ordering **A** |
  | `A2` | ordering **A**, generated again |
  | `B` | ordering **B** |
  | `C` | ordering **C** |

  `A1` against `A2` is the **same-prompt floor**: byte-identical input, so any
  disagreement is decoding stochasticity at temperature 0. `A1` against `B` and
  `A1` against `C` carry decoding stochasticity **plus** order. The difference
  between them is the order effect, and it is measured **within question**.
- **Orderings are permutations of the identical item set** — nothing is added,
  removed or rewritten. Verified per question before any call: the three
  prompts must contain the same multiset of handles and differ in sequence.
- **Outcome.** Judge-scored `correct` against everything else under the frozen
  rubric `p6-c1`, the collapse E-001 used.
- **Primary contrast.** Per question, two indicators: *the same-order pair
  disagreed* and *at least one different-order pair disagreed*. Exact McNemar
  paired within question, alpha = 0.05, one contrast, **no correction needed
  and none applied**.
- **Effect-size bar, and it is placed off the grid on purpose.** Order
  discordance must exceed same-prompt discordance by **0.175**. At n = 20 every
  rate is a multiple of 0.05; E-018 put two bars *on* multiples of 0.05 and
  both landed exactly on their boundary, which decided nothing. A bar between
  attainable values cannot be landed on.

### Ceiling, computed before the run and from the run's own inputs

20 of 20 dev questions carry more than one evidence item, so the maximum
number of questions this design can move is **20**. The floor it is measured
against is whatever `A1` vs `A2` returns, which is not knowable in advance and
is therefore **not** treated as a constant from E-018 — that entry's 0.050 was
measured on a different split and does not transfer.

### Decision rule, fixed before the run

1. **Order discordance exceeds same-prompt discordance at its test and by
   ≥ 0.175.** Evidence order is a variance source this project has never
   controlled. Consequence: **E-019 holds one ordering fixed across conditions**;
   every published paired figure gains a recorded caveat naming this entry; and
   *retrieval order as a design parameter* becomes a Phase 9 front in its own
   right, because an ordering that is chosen rather than incidental is free.
2. **They are statistically indistinguishable, or the gap is under 0.175.**
   E-018's secondary reading was the `hand-def-*` stratum being fragile near
   the `correct`/`partial` boundary, not order. Consequence: the 2026-09-13
   reading is **retracted in the journal where it was recorded**, and E-019
   proceeds without an ordering control.
3. **Inconclusive** — neither the test nor the interval separates them.
   Consequence: nothing is cancelled, nothing is adopted, and the entry states
   that 20 paired questions cannot separate the two. **This is the default**,
   and it is written before the others because E-018 is the entry that taught
   this project to write it first.

### Predictions, recorded before the run

1. **Same-prompt discordance lands between 0.00 and 0.10** — E-018 measured
   0.05 on 20 eval questions and this is a different split.
2. **At least one different-order pair disagrees on 0.15 to 0.35 of
   questions.** Below the 0.205 seen on `hand-def-*`, because those are short
   recitations where dropping one clause is easy and the dev split is mixed.
3. **The questions that move are the ones with the most evidence items.** If
   the movers are instead the shortest contexts, the mechanism is not order and
   the entry says so.
4. **Where an answer changes, it will change by omission rather than by
   contradiction** — a clause dropped, as on `hand-def-flying` — and the
   omitted clause will usually be cited to an item that moved late in the
   context. That is the mechanism this entry can name and it is checked by
   reading, not by a statistic.

### Threats to validity, recorded before the run

- **Three orderings sample the permutation space of a 5-to-40 item list almost
  not at all.** The rate measured is a lower bound on order sensitivity, not an
  estimate of it, and the entry reports it as such.
- **The judge is not validated** and sits worst at the `correct`/`partial`
  boundary (E-011a: 4/14 agreement on `partial`). The three-label distribution
  is reported per sample beside the collapse, and a movement confined to that
  boundary is named rather than pooled.
- **The dev split is 20 questions and differently composed from the
  evaluation split.** No rate from here is transferred; what transfers is
  whether the effect exists.
- **`A1` vs `A2` is the floor for *this* run only.** E-018's 0.050 was measured
  elsewhere and is cited as motivation, never as a comparator.
- **Temperature 0 is not determinism** and never was; that is what the floor
  measures, and it is why the floor exists rather than being assumed zero.

### Cost

80 generations and 80 judge calls on the pinned `gpt-4o-mini`, about
**US$ 0.08**, with `--limit` and a printed estimate before any spend.

### Actual result

_Not yet run._

---

## E-021 — do gold *rulings* do what gold rules did not? (registered 2026-09-13, not yet run)

- **Registered:** 2026-09-13. **Blocked on an annotation that does not exist**,
  and that is the honest headline of this entry rather than a footnote.

- **Where this comes from.** Three measurements from the same day, none of
  which was looking for this:
  - Arm B's evaluation context is **40.1% `card_rulings`** — the largest single
    line item, larger than keyword definitions at 28.0% and keyword glossary at
    22.1%.
  - On `interaction_multihop`, the stratum this project exists for, the gold
    **rule** arrives on 2 of 22 — and **four of the six correct answers arrived
    with it absent**.
  - The 2026-09-13 Magic-side audit recorded that roughly 60% of this arm's
    correct answers **cite no CR rule at all**.
  - E-018 injected **rules only**, returned unresolved, and declared in branch
    3's narrowing that it *"does not establish that reaching the governing
    evidence is worthless — rulings are the citation behind roughly 60% of this
    arm's correct answers and are not manipulated here."* This is the entry
    that manipulates them.

- **The decision this informs.** Whether Phase 9's Front C should bridge toward
  **rules** at all. If correctness on the hard stratum is carried by rulings,
  then a bridge out of chapter 700 is an expensive way to deliver evidence the
  answers do not use, and the cheaper repair is ruling coverage.

### The blocker, stated first because it is the cost

The golden set carries `gold_cr_rules` and **no gold-ruling field**. Its
fields are `answer`, `gold_cr_rules`, `gold_entities`, `gold_path`, `hops`,
`stratum`, `vector_should` and provenance. There is nothing to inject.

**So this entry has two stages and the first is curation, not code:**

1. **`gold_rulings` annotated** on the `interaction_multihop` stratum — 22
   questions — by the author, from the key, **before any retriever output is
   consulted for those questions**, in the same posture that made
   `gold_cr_rules` usable: written against the key, not against what the system
   found. Ruling ids only; ruling text is never committed. Annotation guide
   entry first, then the annotation.
2. **The injection**, mirroring E-018 exactly: control / placebo / treatment,
   paired within question, arm B, de-duplicated against what retrieval already
   brought, placebo matched on **ruling count and tokens**, one ordering shared
   across conditions (pending E-020, which decides whether that matters).

**Stage 2 does not start until stage 1 is complete and versioned.** An entry
that injects an annotation written while looking at the run is an entry that
measures the annotator.

### Design, for stage 2

- **Population.** The `interaction_multihop` questions carrying `gold_rulings`,
  frozen by id before the run. Expected 22 minus whatever the annotation cannot
  key. **A third reading of the evaluation split**, declared here; if that is
  judged too expensive when stage 1 lands, the entry moves to a dev-split
  population and says so.
- **Conditions, metric, correction** — as E-018, amended: exact McNemar paired
  within question, Holm over treatment-vs-control and placebo-vs-control, the
  construct bar on treatment-vs-placebo, and branch 3 split into *inconclusive*
  and *evidence of absence*. The amendments E-018 paid for are inherited rather
  than rediscovered.
- **The ceiling is read before the run**, by the same instrument
  (`e018_ceiling.py`, extended): *with what retrieval already brought plus
  these rulings, is the key's verdict derivable?* E-018's ceiling of 17 of 20
  does **not** transfer — different population, different injected material.
- **Gold-rule citation uptake has a counterpart here** and is recorded by
  default: the share of treatment answers citing an injected ruling. E-018
  showed that without it a flip that used nothing injected reads as an effect.

### Decision rule, fixed before the run

1. **Treatment beats control at its Holm step and clears the construct bar.**
   Rulings carry the hard stratum. Consequence: **Front C's target changes from
   CR rules to ruling coverage**, and the bridge out of chapter 700 is
   deprioritised rather than abandoned.
2. **Placebo matches treatment.** Volume or shape, not rulings. Consequence:
   the 40.1% observation is retracted as an explanation.
3. **Neither, and the interval includes the bar** — inconclusive, the default,
   nothing cancelled.
4. **Neither, and the interval excludes it** — rulings do not carry it either.
   Consequence: the hard stratum's correctness is explained by neither gold
   rules nor gold rulings, and **Phase 9 has been looking in the wrong place
   twice**, which is the branch that costs the most and is written first.

### Threats to validity, recorded before the run

- **The annotation is new and is the instrument.** `gold_cr_rules` was written
  before any retriever existed; `gold_rulings` will be written after the author
  has read E-018's cases, which is a real contamination risk in one direction.
  Mitigation: annotate from the key alone, record the date, and keep the
  retrieved rulings out of view during annotation. It is a mitigation, not a
  blind, and the entry says so.
- **Rulings are Scryfall content.** Ids are versioned; text never is.
- **Third reading of the evaluation split**, declared, and the trigger to move
  to dev is written above rather than decided later.
- **This entry inherits E-018's oracle framing.** No figure in it is a system
  score.
- **It also inherits E-018's power problem**: 22 questions, and the same
  arithmetic that needed 7:0 discordant pairs applies. The entry is registered
  as **far better able to confirm than to rule out**, in advance.

### Cost

Stage 1: curation, no API spend. Stage 2: roughly 66 generations and 66 judge
calls, under **US$ 0.10**, plus the ceiling reading.

### Actual result

_Not yet run. Stage 1 not started._
