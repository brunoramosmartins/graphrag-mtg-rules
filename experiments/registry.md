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

- **Dress rehearsal, arm B only (2026-09-04, development split, nothing
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

- **Actual result:** _pending (Phase 8)._

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

**Result (2026-09-03, `scripts/run_e012.py explore`, exploratory).** Hits@1
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
