# Evaluation — pre-registration

Source of truth for how this project is measured. Written **before any
retrieval or generation exists**, which is the point: predictions recorded
after seeing results are not predictions.

Results land here as each phase closes. The pre-registration below is
**unedited**: where a result contradicts a prediction, the analysis is
written in the results section and the prediction stays as it was recorded.

**Status, 2026-09-04.** Phases 3, 4 and 5 are reported. Phase 6 Act 1
(calibration) is reported and **failed its registered floor**; the failure
analysis is the section that matters. Phase 6 Act 2 has completed its dress
rehearsal on the 20 development questions — **no number in it is a result
about the arms.** The 57 evaluation questions are opened once, in Phase 8,
and the judge that would score them is not yet audited above its registered
floor. What is pending, and what each pending item blocks, is tabulated at
the end of the Act 2 section.

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

## The one command, and what CI's version of it does not check

*Added 2026-09-10, Phase 7.*

One arm, from the raw sources to a markdown report and a forest plot:

```bash
python scripts/run_eval.py run --arm C --figures docs/figures
```

Retrieval, generation and judging happen in one process, which is also
what makes a whole question one OpenTelemetry trace — every other
subcommand is a single stage with a JSONL between it and the next, so
its trace covers a fragment. Add `--trace` to export.

The cost figure printed before the loop is an **upper bound**, not the
exact prompts. Interleaving retrieval and generation is what keeps one
question in one trace, and it means the real prompts do not exist until
money could already have been spent; every context is capped at the token
budget, so a bound exists and is the honest thing to print.

### `--smoke` tests the wiring, not the quality

CI runs the same command with `--smoke`: a fixture corpus of invented
cards, a generator that answers by citing the first handle it is handed,
and a judge that returns a fixed label. No API key, no Neo4j, no
`data/raw/`.

**A green CI badge is a claim about the wiring and never about the
answers.** What the smoke checks is that the corpus builds, retrieval
runs, the budget is enforced, the context serializes, the prompt
assembles, citations expand, unknown handles are detected, verdicts are
written and the report and figures render — and that every one of those
stages still agrees with the next about its format.

What it cannot check is whether the prompt still works, whether the judge
still agrees with a human, or whether any arm is better than any other.
Those need a real model on real questions, they are E-001's job, and the
judge doing the scoring is itself gated on the correctness ceiling. An
API key in CI is a secret exposed on every pull request, which is the
trade this makes and the reason it is stated here rather than assumed.

Because the fake judge labels everything `correct`, a smoke report shows
1.00 across every stratum. That number is an artefact of the fixture. It
is marked as such on the console, in the generated markdown, on the face
of the SVG, in the filenames (`runs/smoke_*`, never `runs/e001_*`) and in
every row (`"smoke": true`, `"model": "smoke-fake"`) — five places,
because a banner is the one that scrolls away.

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

## What the system actually ships (schema reduced, 2026-08-09)

G3's consequence, executed. `(:Ruling)-[:CITES_RULE]->(:Rule)` is now produced
by `extraction/explicit_citations.py` from rule numbers the ruling states, and
the gate rejects anything inferred (`citation_not_explicit`). The check lives in
`gate.py`, not in the prompt or the caller, so it holds for future callers —
E-003 is the measurement of what the same guarantee is worth in a prompt.

Scored on the same 125 rulings. **Descriptive, not a new test:** the reduction
was mandated by a rule fixed on 2026-07-20, and the numbers get worse.

| | inferred (E-003, headline) | shipped (reduced) |
|---|---|---|
| citations, overall F1 | 0.125 [0.073, 0.180] | **0.047** (tp=4 fp=2 fn=161) |
| citations, `explicit` stratum | — | **0.727 [0.222, 1.000]** (P 0.667, R 0.800) |
| gated citation edges / 125 rulings | 140 | **6** |

Trading 99.97% of the coverage is only defensible because the coverage was not
real: at F1 0.125 roughly seven of every eight inferred edges were wrong, and a
graph that cites wrongly is worse than one that stays silent — it looks
grounded. What the edge now means is narrower and true: *the ruling names this
rule*, not *this rule governs this ruling*.

**The reduction has its own version hazard.** Precision on the `explicit`
stratum is 0.667, not 1.0. One of the two misses is a ruling that writes
"(704.5w)" where the August 2026 CR moved that state-based action to `704.5x`
and reused `704.5w` for something else. `scripts/cr_migrate.py` migrated the
gold with the rule text; a ruling is a historical document and cannot be
migrated. The number still resolves, so no existence check catches it — the
same silent displacement that moved `initiative` off 725.1.

## Consequences for E-001, checked before Phase 4

No golden-set question loses a written path: **0 of 77** `gold_path` values name
`CITES_RULE` or a `Ruling` node (the edges they name are `DEFINED_BY` ×25 and
`HAS_KEYWORD` ×1). But only **23 of 77** are written as traversals at all, and
the rules the rest require split by stratum: `definition_1hop` and
`keyword_rule_2hop` sit entirely in the keyword chapters and stay reachable via
`Keyword-[:DEFINED_BY]->Rule`; `legality_1hop` needs no CR rule; but
`interaction_multihop` — the `vector_should: fail` stratum that carries the
central claim — needs 61 rules of which only 8 are keyword rules, the rest
sitting in the 600s, 500s, 700s and 300s with no deterministic edge from any
card. `CITES_RULE` was to be that bridge, and it was never good enough to be it.

Phase 4 therefore chooses deliberately between finding another deterministic
bridge, accepting that rules are reached by text retrieval while the graph
supplies entity structure (which reframes E-001 as a test of the combination),
or reopening an inferred path under its own pre-registration.

## Phase 4 — what retrieval reaches (E-006, development split)

Preliminary and deliberately quarantined: measured on the **20 development
questions** frozen in `data/golden/phase4_dev_ids.json`, never on the 57 that
E-001 will score in Phase 6. The split was drawn before the first traversal was
written, because Phase 4 was otherwise going to build templates against the
questions that measure them.

| stratum | entity recall | rule recall | n |
|---|---|---|---|
| `definition_1hop` | 1.00 | 1.00 | 4 |
| `legality_1hop` | 1.00 | n/a | 5 |
| `keyword_rule_2hop` | 1.00 | 1.00 | 1 |
| `negative_temporal` | 1.00 | 0.25 | 2 |
| `interaction_multihop` | 0.88 | **0.12** | 8 |

**1–2 hop entity recall 1.000** against the DoD's 0.9 floor. All 20 questions
returned a subgraph or a named failure — none silent. Latency p95 0.53 s
against the 2 s criterion. n=10 on the threshold: read it as a smoke test.

Entity recall and rule recall are reported apart and never averaged. Reaching
*Humility* and reaching `613.4b` are not interchangeable achievements, and a
combined figure would let the easy one hide the hard one — which is exactly
what the `interaction_multihop` row shows.

**Three measurements now agree about that row.** `scripts/reachability.py`
found 15 of its 30 questions have no graph seed at all;
`scripts/eval_rule_search.py` found lexical retrieval reaches a gold rule in 2
of 8 dev questions; E-006 end to end reads 0.12. Neither half of ADR-007's
hybrid covers the stratum that carries the central hypothesis, and that
convergence is the Phase 4 finding rather than a defect still to fix.

**Re-measured 2026-08-15 against the fixed linker, and every figure is
identical.** Three production linking defects were found by E-008 *after* this
table was produced, so it was re-run rather than left standing on a linker that
no longer exists. Nothing moved: 1–2 hop entity recall 1.000, all 20 resolved,
`interaction_multihop` still 0.88/0.12.

That is not reassurance, it is a limitation coming into view. Entity recall is
`|gold ∩ retrieved| / |gold|`, so a spurious entity cannot lower it — and all
three defects were additive, the worst of them putting *Who // What // When //
Where // Why* into 23 of E-007's 42 subgraphs while removing nothing. **This
measurement reads 1.000 with the bugs and 1.000 without them.** A recall figure
certifies that what was needed arrived and says nothing about what else arrived
with it; E-001 needs a precision-side companion in Phase 6 or it grades
subgraphs on half the question.

**Two harness defects preceded the passing number, and both are on record.**
The first run returned entity recall **0.067** — the router passed
`Keyword.display_name` where the graph keys on the normalized `name`, and
`card_legality` was never wired at all. E-006's registered prediction had said
to suspect the harness before the templates if that happened, which is the only
reason it was chased rather than believed. A third run reached 1.000 after the
query lexicon stopped admitting `art_series` prints and tokens, which had made
6% of card names resolve to more than one `oracle_id`.

---

# Results — Phase 5, grounded generation (E-007 / E-007c / E-008, 2026-08-10 → 15)

Measured on the **32 audit questions** answered from their retrieved subgraphs,
with the 10 development questions used for the prompt iterations and never
scored here. Every judgement below is one annotator's, and every figure carries
the ceiling measured for the instrument that produced it.

The ordering was fixed before any answer was read, because each step would
otherwise be free to move the one before it: subgraph sufficiency labelled and
**frozen** first; answers generated; the claim worksheet segmented and hashed;
then and only then, claims judged.

## The DoD, clause by clause

**Clause 1 — every factual claim carries a citation: NOT MET.**

    coverage 0.369 = 121/328 claims over 32 answers
    excluded 83/411 (20.2%) — VOID

Two separate statements, and the second is the stronger one. Coverage reads
0.369 against a registered target of 1.0, with the three-round iteration budget
spent. It is also **void**: the registered rule voids coverage when more than
20% of segmented rows are excluded as non-factual, and exclusions came in at
**0.2019** — over the line by 0.8 of a row. 47 of the 83 exclusions are
segmentation artefacts (list numbering, headers, fragments), which is precisely
the failure the void rule was written to catch: at that exclusion rate the
figure describes the segmenter, not the answers.

Voiding costs the *right to publish the number as a measurement of the answers*.
It does not rescue the verdict. A perfect segmenter that reclassified every
artefact would still leave 121 cited claims out of 328, and the clause would
still fail. Both facts are reported; neither is used to soften the other.

**Clause 2 — cited claims are actually supported by their citations: MET.**

| arm | support | 95% CI |
|---|---|---|
| real pairing | 0.565 | [0.435, 0.694] |
| shuffled citations | 0.161 | [0.065, 0.274] |

The real arm's lower bound clears the control's upper bound, which is the
reading registered before any answer existed. Over the full worksheet the
support rate is **0.488 [0.400, 0.583]** over 31 question clusters and 121
cited claims. Intervals are cluster bootstraps that resample *questions*, not
claims: claims within an answer are not independent, and resampling them would
report an interval narrower than the evidence supports.

The control is a **derangement** — no citation keeps its own sentence — because
a shuffle with a fixed point scores a real pairing as random and biases the
comparison toward passing.

Where support fails, it fails in one place:

    claim_not_in_evidence          45
    right_evidence_wrong_reading    9
    evidence_absent                 4
    unrelated_evidence              4

**Over-refusal on `sufficient` subgraphs: 0.** The registered blocker is clear.

## The finding that carries no threshold, and matters most

    unsupported answering 8 | correct refusal 1

**Eight of the nine subgraphs labelled `insufficient` were answered rather than
refused.** No registered criterion covers this — by design, since the label did
not exist when the DoD was written — so it is reported as a finding and not as
a pass or a fail. It is the largest open risk in the phase and it has its own
experiment owed: one where the subgraph provably lacks the answer and the
correct behaviour is refusal.

E-008 does **not** explain it. Overriding fiction that is present and answering
when evidence is absent are different behaviours, and E-008 measured the first.

## E-008 — does the model answer from the graph or from memory?

Nine fictional nodes loaded into the production graph across three constructs
(a card whose oracle text contradicts the real card, a fictional keyword with
its own CR subtree, a fictional ruling on a real card), 12 held-out probes
authored with their `graph_says` / `memory_says` discriminators written before
any answer existed.

    evidence verified   12/12   (0 retrieval misses)
    followed_graph 12 | leak 0 | refused 0 | intra_context_conflict 0

Both registered conditions hold. The claim this licenses is a bound, not an
absence: **a per-probe leak rate of at most 0.25** (95%, rule of three over 12
probes). It is not "no parametric leakage", and it says nothing about real
cards the model half-remembers — the deployment condition differs in exactly
the dimension being measured.

The probe names carry no marker of their fictionality, because a model that
spots a fake and refuses would be coded as a grounding failure and the detector
would end up measuring itself.

## The ceilings — what these numbers may be read against

Every figure above is one person's judgement, so each instrument was re-run
blind against itself, days later, with the originals hidden.

| instrument | agreement | 95% CI | n |
|---|---|---|---|
| claim label (factual / non-factual) | 0.990 | [0.969, 1.000] | 100 rows, 8 answers |
| claim support | 0.933 | [0.818, 1.000] | 30 rows, 8 answers |
| subgraph sufficiency | 0.800 | [0.500, 1.000] | 10 of 42 |
| ruling citation (E-003a, prior phase) | 0.815 | [0.679, 0.938] | 20 rulings |

**The two claim instruments are far more reliable than the sufficiency one**,
and that re-ranks what this phase may assert. Deciding whether a sentence
asserts a fact is nearly mechanical; deciding whether a subgraph *sufficed* is
an interpretation. So the support result rests on a 0.990/0.933 instrument,
while the 8-of-9 headline rests on a 0.800 one — and both of that instrument's
disagreements ran the same way, `partial` → `insufficient`, meaning a second
pass would have called *more* subgraphs unanswerable. The 8-of-9 is read
against an instrument that tends to enlarge its own denominator.

**The registered ceiling rule does not decide this run, and that is published
rather than resolved.** The rule voids the support figure's ceiling if the
second pass disagrees "at a rate comparable to the support gap". *Comparable*
was registered without a threshold, so both readings are stated: on point
estimates, disagreement 0.067 against a gap of 0.403 — the ceiling holds
comfortably; on each side's worst bound, disagreement 0.182 against a gap of
0.161 — it does not, by 0.021. Choosing between them with the disagreement rate
already on screen is the thing pre-registration exists to prevent, so neither
is chosen. The cause of the split is sample size: only 30 of the 100 re-audited
rows carried a support judgement in both passes, because the re-audit was sized
for label agreement. A ceiling sized for the figure it bounds is a change to
the next experiment, not a re-draw of this one.

One coincidence recorded so it is never misquoted: the two support
disagreements ran in opposite directions, so the support rate on the shared
rows is **identical, 14/30, under both passes**. That is offsetting error, not
precision.

## Predictions, scored

| prediction | outcome |
|---|---|
| coverage below 1.0, failing on connective sentences | **partly right** — coverage failed; 44% of uncited claims open with a connective |
| the commonest support failure is `wrong_leaf` | **wrong** — 0 of 62 |
| refusal is the dominant failure on `partial` subgraphs | **wrong** — 16 answered against 3 refused |
| E-008: leakage happens, most on the contradiction construct | **wrong** — zero leaks anywhere |
| E-008: leakage appears more in uncited connectives than in cited claims | **unscoreable** — conditional on leaks that did not occur |
| E-007c: collapsed agreement exceeds exact agreement | **wrong** — identical, 0.800 |
| E-007c: disagreement sits on the `sufficient`/`partial` boundary | **wrong** — entirely on `insufficient` |

`wrong_leaf` transferred from E-003a, where it was 3 of 6 disagreements, and
came in at zero here. Concepts transfer between experiments; error *shapes* do
not.

## Threats to validity specific to Phase 5

- **Three production linking defects were found after E-007 ran**, by E-008's
  evidence check: whole names losing to split-card faces, a single-word face
  bypassing the capitalization gate (`what` matching *Who // What // When //
  Where // Why*, in **23 of E-007's 42 subgraphs**), and keyword matching
  defeated by clause punctuation. E-007 was **not** re-run — the answers were
  generated, judged and reported against the subgraphs as they were. Every
  figure in this section therefore describes a retrieval layer that has since
  improved, which biases the reported grounding **downward**. E-006 was re-run
  against the fix on 2026-08-15 and every recall figure came back identical —
  which bounds nothing about Phase 5, because entity recall cannot see a
  spurious entity and all three defects were additive.
- **Single judge throughout.** The author wrote the prompt, labelled
  sufficiency, segmented the answers and judged support. Not fixable by a
  larger sample. What bounds it is the ordering, the shuffled-citation control
  and the ceilings above — not the earlier claim that coverage is "nearly
  mechanical", which is false: coverage is mechanical only *given* a
  segmentation, and the segmentation is the judgement-laden step.
- **The exclusion threshold is tight enough that one row in a hundred straddles
  it.** On the 100 re-audited rows the two passes read 0.210 and 0.200 against
  a 0.20 limit. This does not reopen the void — a ceiling sample measures the
  annotator, not the corpus — but whoever sets the next threshold should know
  how little separates its two sides.
- **The audit sample carries no hop annotations**, so strata were assigned by
  the author from the question text rather than inherited from a verified
  golden set.

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

---

# Results — Phase 6, Act 1: calibration on MetaQA (E-002, 2026-09-02 → 03)

Act 1 asks a single question: does the retrieval-plus-generation machinery
work at all, measured on a benchmark with a published answer key, before it
is pointed at Magic. The registered pass/fail was one clause — **Hits@1 ≥
0.90 on 1-hop** — because MetaQA 1-hop is a single typed edge lookup against
a KB with no ambiguity and no rules text. A spine that cannot reach it is
broken, whatever the literature reports.

**Configuration.** 500 questions per hop from a frozen subset at seed
`20260815`, `gpt-4o-mini` at temperature 0, prompt `e002-a3`, one run. The
MetaQA KB was loaded into a **separate Neo4j instance** — Community serves
one user database, and a namespace inside the Magic graph is what E-008's
teardown deleted three real CR rules from.

| hop | Hits@1 | shown-reach ceiling | literature band | reading |
|---|---|---|---|---|
| 1-hop | **0.884** [0.853, 0.909] | 1.000 | [0.970, 0.975] | below the band |
| 2-hop | **0.570** [0.526, 0.613] | 0.842 | [0.988, 1.000] | below the band |
| 3-hop | **0.156** [0.127, 0.190] | 0.448 | [0.914, 1.000] | below the band |

## Verdict: FAIL, and the failure is the useful part

1-hop 0.884 < 0.90. Below the floor the registered rule requires the
divergence be chased before anything else is claimed, and the chase produced
five defects that a passing run would have hidden:

1. `subgraph.serialize()` looped over the five Magic evidence kinds, so
   MetaQA's 206 `triple` items per subgraph were **dropped silently** —
   retrieved, budgeted, never rendered. Caught by a cost estimate that came
   in too small, not by a test.
2. `kind_cap` was inherited from the Magic configuration and truncated the
   benchmark's evidence.
3. Reach was being measured over **walked** entities rather than **shown**
   ones. Only what the model receives can bound Hits@1.
4. The HTTP client had no retry, and a 429 killed a 500-question pass 163
   answers in.
5. Prompt `e002-a1` was missing one of the grounding contract's four
   sections, which produced 542 refusals out of 1,000.

**A ceiling correction was computed and explicitly refused.** Ten of the 58
one-hop misses are correct by the edge and outside MetaQA's gold set;
crediting them reads 0.904, above the floor. That number is not the result.
It is a post-hoc adjustment on a criterion invented after seeing the
verdict, and letting it overturn a pre-registered threshold is the move this
whole apparatus exists to prevent. The floor is measured as registered:
**0.884, FAIL.**

## The finding: generation, not retrieval — WITHDRAWN AT THREE HOPS, 2026-09-13

> **The 3-hop row below is withdrawn.** Not the number — the number is what
> was computed — but what it may be read to mean. `answer_shown` is
> `any(hits_at_1(name, question) for name in shown)`: the answer *string*
> appearing among the evidence's entity names, with no chain required. Behind
> the 224 three-hop cases it selects, **213 have a real chain of one step**
> and 11 have three. So "conditional on the answer being present in the
> evidence the model received" does not say what its words say, and the
> conclusion drawn from it at three hops does not follow. See E-002's and
> E-012's amendments of 2026-09-13 in
> [experiments/registry.md](../experiments/registry.md).
>
> **1-hop and 2-hop largely survive** — their chains match their declared depth
> on every question — so the fall from 0.884 to 0.677 stands as a real depth
> effect. *"Largely", corrected 2026-09-13: matching the declared **depth** is
> not the same as matching the relations the question asks for, and an audit
> found an unambiguous shortcut on **3.0% of 1-hop and 3.2% of 2-hop** chains
> — a chain of attribute relations answering a question about a person. The
> word "clean" was an overclaim from a proxy; at 3% the depth effect is
> unaffected, and the audit's own looser check over-fired, so 3% is a floor
> and 10%/27% an unreliable ceiling.*

The registered prediction "grounded generation is not the bottleneck at any
hop" is **falsified**, and that is the transferable result. Conditional on
the answer entity being present in the evidence the model actually received:

| hop | correct given the answer was shown | |
|---|---|---|
| 1-hop | 0.884 [0.853, 0.909] | stands |
| 2-hop | 0.677 [0.631, 0.720] | stands |
| 3-hop | **0.339** [0.280, 0.404] | **withdrawn — 213 of 224 are one-step chains** |

At three hops the model uses **one third** of what retrieval hands it.

## E-012 — is it size or depth? (confirmatory, 2026-09-03)

E-002 could not separate the two: its 3-hop subgraphs are simultaneously
deeper *and* far larger (median 206 evidence items against 17 at 2-hop). So
E-012 ran questions at **matched context sizes** across hops with the
answer-bearing chain guaranteed present, on a frozen confirmatory draw of
300 per hop taken from the complement of E-002's subset.

| *k* | 1-hop | 2-hop | 3-hop *(withdrawn)* |
|---|---|---|---|
| 8 | 0.883 [0.842, 0.915] | 0.660 [0.599, 0.716] | 0.489 [0.407, 0.572] |
| 16 | 0.890 | 0.672 | 0.511 |
| 64 | 0.890 | 0.656 | 0.591 |
| 256 | 0.897 | 0.628 | 0.518 |
| untrimmed | 0.893 | 0.628 | 0.533 |

> **The 3-hop column is withdrawn, 2026-09-13.** `answer_path` returned the
> shortest chain to any accepted answer *string*, and `reduce_to_k` preserved
> whatever it returned. **126 of the 137 questions in that cell (92%) were
> accepted on a one-step chain**, so the model received a one-hop context with
> a three-hop question stapled to it — and 43 of its refusals there were the
> grounding prompt being obeyed, scored as generation failures. The repair
> requires a chain of the declared depth; applied to this split it leaves
> **10 usable 3-hop questions of 300**, and leaves the 1-hop and 2-hop
> exclusion counts **byte-identical** (0 and 50), which is the mechanical
> check that the columns below survive.
>
> With that column gone, **no figure in this document supports "generation is
> the bottleneck, not retrieval" at three hops.** What replaced it is three
> registered entries run the same day — E-015, E-016 and E-017, below — and
> their answer is neither generation nor depth.

**Depth at matched size, on the columns that survive: 0.890 to 0.672 at
*k*=16, separated.** Holding the context at 8 items, 0.883 to 0.660.

**Size at fixed depth: nothing.** 1-hop moves between 0.883 and 0.897 across
a 32x change in context. Paired within question, untrimmed against *k*=8:
2-hop p=0.382, 3-hop p=0.451, 1-hop p=0.648 — none near its Holm threshold.

Three predictions were registered; **all three were wrong**, including the
one this experiment was built to confirm. The registered consequence stands:
context reduction is **not** adopted, `enforce_budget`'s distance-first trim
**stays**, and E-001's multi-hop stratum carries the compositional limit as
a named bound.

## What three hops actually costs (E-015, E-016, E-017 — all run 2026-09-13, all free)

When E-012's three-hop column was withdrawn, the question it had appeared to
answer reopened. Three entries were registered and run the same day, none of
them spending a token, and between them they move the answer off generation
and off depth.

### E-015 — the evidence was there and the budget was discarding it

Chain reach is the fraction of questions on which retrieval delivers a chain of
the **declared depth** — the repaired `answer_path`, which refuses a shortcut
to an accepted answer string.

| frontier | token budget | chain reach | median items |
|---:|---:|---|---:|
| 400 | 6,000 *(shipped)* | 0.030 [0.010, 0.085] | 207 |
| 400 | 24,000 | 0.180 [0.117, 0.267] | 837 |
| 400 | 96,000 | **0.650** [0.553, 0.736] | 2,007 |

Sixteen times the budget, nothing else changed, and three-hop coverage goes
from 3 questions in 100 to 65. `enforce_budget` evicts by descending distance,
so on a three-hop question the first thing it throws away is the hop the answer
lives on — and E-002's own recorded fields had said so all along: **498 of 500
three-hop questions had evidence dropped, against 0 of 500 at one hop.**

**This amends E-012.** Its holding that the distance-first trim is not a hazard
was inferred from a size null measured on cells where `reduce_to_k` had already
reinstated the chain. A design that repairs the damage before measuring cannot
see the damage.

Two things went wrong in E-015's own design and are recorded rather than
smoothed. `frontier_cap` turned out **inert** — every cell at 1,600 identical
to its twin at 400 to the last digit, because `add_evidence` caps per
`(template, kind)` and the template carries the distance, so a thousand triples
per level swallowed 2.5× more candidates without changing what survived. And
the amendment that added `kind_cap` **fired the monotonicity check**: raising
the cap admits ~45,000 more distance-2 triples, which pushes 34 of 40 questions
over a budget none had hit, and the farthest-first trim then evicts the answer's
hop. Reach falls 0.650 → 0.460. **More retrieval buys worse multi-hop
coverage**, and the registered claim that reach could only rise was wrong: it
holds only while added evidence cannot displace what was already kept.

### E-016 — the trim is not the lever, and a significant result was refused

Four eviction policies, all oracle-free, trimming the **identical** pool at the
shipped 6,000-token budget. Paired by construction.

| arm | reach at `kind_cap` 1,000 | ceiling 0.650 |
|---|---|---|
| **A** shipped | 0.030 [0.010, 0.085] | |
| **B** proportional | 0.100 [0.055, 0.174] | adjusted *p* = 0.0391 |
| **D** connectivity first | **0.120** [0.070, 0.198] | adjusted *p* = 0.0234 |
| **R** random, fixed seed | 0.010 [0.002, 0.054] | the control |

The designed policies beat the shipped trim and beat chance decisively
(D vs R: +11/−0, *p* = 0.00098). **The rule fixed before the run asked for a
gain of 0.20 and the best arm returned 0.090, so nothing was added to
`enforce_budget`.**

Why no ordering could have worked: a 6,000-token budget holds about 200
triples, and an equal share gives distance 3 roughly 66 slots against 1,000
candidates. Ordering decides which 66; it cannot make 66 cover 1,000. **The
chain costs 90 tokens** — the price was never the problem. What an eviction
order can fix is the systematic part, not discarding the needle's half of the
haystack first, and that is worth nine points exactly.

### E-017 — the residual has a name, and it is hub traversal

The cheapest version of the decomposition idea needs no agent: expand along the
relation the question is about instead of along everything. Measured as
**size**, never reach — the relation sequence is read off the gold chain, so a
reach figure would be a tautology.

| | |
|---|---|
| untyped three-hop context | median **193,797** tokens |
| typed along the chain's own relations | median **5,676** tokens |
| reduction | **30.6×** (q1 5.5×, q3 76.1×) |
| fits the shipped 6,000-token budget | **0.522** [0.421, 0.621] — 48 of 92 |

Typing takes the haystack down by thirty times and the median expansion then
fits **by three hundred tokens**, for half the questions. Fan-out per hop is
2 / 89 / 42, and the middle hop is where it goes wrong.

Of the 44 questions that do not fit, **39 pass through `has_genre` or
`release_year` at the middle hop.** Those are hub relations: one node with
thousands of neighbours. Median hop-2 fan-out is **22** on the questions that
fit and **493** on the ones that do not, and nineteen fit at no budget tested,
including 96,000.

### The position this leaves, stated as the source of truth

**What three hops costs is not depth and not generation. It is traversing a
hub.** A chain of three person-shaped relations is cheap at any depth; one
genre or one year in the middle builds the haystack that the budget then trims
from the wrong end.

Three things follow, and two of them are refusals:

- **Typed expansion is necessary.** A 30× reduction is not a detail, and
  nothing should expand untyped at depth.
- **It is not sufficient**, and the gap is concentrated in two relations of
  nine, so a repair aimed at depth in general would miss it.
- **Nothing was adopted.** E-016 declined to change shipped trimming on a
  significant result because the registered effect size was not met, and E-017
  declined to hand P3 a build direction on a fit rate of 0.522. Both bars were
  written before the runs.

**Every figure in this section is a retrieval figure.** Chain reach says the
evidence could support an answer; it says nothing about whether one would be
right. And E-017's relation sequence came from the gold chain, so it bounds
what typing would buy *if something chose correctly* — nothing there chose, and
E-016 is the precedent for how large that price can be: its ceiling was 0.920
and the best oracle-free arm returned 0.120.

## What Act 1 transfers, and what it does not

- **Transfers, narrowed 2026-09-13.** Between one and two hops, depth costs
  accuracy and context size does not — 0.890 to 0.672 at a matched *k*=16,
  with the size null flat across a 32x change. MetaQA questions are templated
  and their chains uniform, so that effect is a **floor** on the depth effect
  in judge-level Magic questions, not an estimate of it.
- **No longer claimed.** That the bottleneck at *three* hops is compositional
  reasoning. The cell that said so was 92% one-step chains; see the withdrawal
  above.
- **Transfers, and this is the replacement.** At three hops the cost is
  **hub traversal**, not depth: typed expansion cuts the context 30x, and what
  remains too large passes through a relation whose middle node has thousands
  of neighbours (E-017). The shape transfers — a regulatory corpus has its own
  hubs, and "see rule 704" is one. The numbers do not.
- **Does not transfer.** No number in Act 1 is a Magic number. The budget
  does not currently fire on the Magic corpus at all — `dropped` is 0 across
  all 42 E-007 questions, all 18 E-008 probes, and all 20 Phase 6
  development questions — so every conclusion about trimming is a design
  constraint carried forward, not a repair of an observed defect.

---

# Results — Phase 6, Act 2: the domain head-to-head (E-001)

**Status: the dress rehearsal is complete; the evaluation split is not
open.** Everything below ran on the 20 frozen **development** questions. The
57 evaluation questions are opened once, in Phase 8, and no number here is a
result about the arms.

## What is being compared

| arm | what it is | what it tests |
|---|---|---|
| **A** | vector baseline over the same corpus, no graph | control |
| **B** | graph-only traversal | the thesis in [`hypothesis.md`](hypothesis.md) |
| **C** | hybrid: graph plus the same text retriever arm A uses | the shipped system |

Registered ablations, each published on and off: retriever mode
(hybrid / dense / lexical), arm C's text half (vector / TF-IDF), arm C's
routing (shipped / always-on), and iterative retrieval.

## Corpus parity, and why it decided more than the retriever did

Every fact any arm may cite is in every arm's index: 115,547 documents —
3,308 CR rules and subrules, 739 glossary entries, 34,236 cards, 77,264
rulings.

The clause that mattered is the card document, and it exists because of an
asymmetry that would otherwise have decided the experiment. All 20
`legality_1hop` questions carry an **empty `gold_cr_rules`**: their answer
lives in Scryfall's structured legality field and in **no document** of
CR + rulings + MTR. Fifteen of them are in the evaluation split — **26% of
the 57**. A vector arm indexing only prose could not have answered one of
them, the graph arms would have swept the stratum, and the per-stratum table
would have read "graph wins" for a reason with nothing to do with graphs.

So each card document carries its oracle text **and its legality as prose**:
"Mindsparker is not legal in Pauper." A fact only counts as indexed if the
arm can retrieve it, and an enum is not retrievable by a sentence.

Parity runs the other way too. The Scryfall bulk holds 38,262 card records
and the graph loads 34,236 — `etl/cards.py` filters tokens, art series and
non-playable layouts. Indexed naively, arm A would have held 4,026 documents
no other arm can cite. The corpus builder reuses the same predicate; the
counts now match exactly.

## Registered deviation: the dense encoder

The roadmap names BGE-M3 as reuse from Project 1. Arm A uses OpenAI
`text-embedding-3-small`. The practical reason is 8.6M tokens — hours of CPU
and a 2.5 GB dependency against US$ 0.17 and twenty minutes.

The reason it is **admissible** is the direction it moves the result:
`text-embedding-3-small` is the stronger English retrieval model, so the
substitution makes **arm A stronger**, and arm A is the control this project
predicts losing to the graph. A change that strengthens the control cannot
manufacture the predicted outcome. Had it weakened arm A it would have been
refused at any price. What it costs is a sentence in the README: arm A is
not "the Project 1 pipeline", it is the same protocol with a current
embedding model.

## The dress rehearsal (development split, n = 20, nothing gated)

Generator parity was checked before any comparison, as registered — `p5-a3`
was iterated against *graph* serializations, so a materially different
malformed-citation rate, refusal rate or answer length per arm would have
required an arm-A serialization adapter built and published first.

| configuration | answered | refused | unknown handles | mean chars |
|---|---|---|---|---|
| A, hybrid | 18 | 2 | 1 | 838 |
| B | 17 | 3 | 1 | 819 |
| C, vector, routed | 17 | 3 | 0 | 964 |
| C, TF-IDF, routed | 19 | 1 | 1 | 947 |

**No material difference; the adapter is not built.** Recorded as a check
that passed, not a step nobody took.

Per-stratum judge-scored correctness (`correct` against everything else;
`partial` counts as not-correct, because E-007c found a middle category
absorbs uncertainty and letting it count as a win would let the headline
move with how generously it was applied):

| stratum | n | A | B | C-vector | C-TF-IDF |
|---|---|---|---|---|---|
| definition_1hop | 4 | 0.25 | 0.25 | 0.25 | 0.25 |
| interaction_multihop | 8 | 0.38 | 0.38 | 0.25 | 0.25 |
| keyword_rule_2hop | 1 | 0.00 | 0.00 | 0.00 | 0.00 |
| legality_1hop | 5 | 1.00 | 1.00 | 1.00 | 1.00 |
| negative_temporal | 2 | 0.50 | 0.00 | 0.50 | 0.00 |
| **ALL** | 20 | 0.50 | 0.45 | 0.45 | 0.40 |

No paired McNemar reaches p < 0.5. **Nothing separates** — which at n = 20
is the expected outcome whatever is true, since E-001's own power analysis
already registered that even the 57-question evaluation split cannot clear
the strictest Holm step on `negative_temporal`. This is a statement about
the rehearsal's power, not about the arms.

One thing it does establish: **`legality_1hop` reads 1.00 for every arm.**
That is corpus parity working. The stratum is now uninformative in the good
way instead of decisive in the bad way.

## The pairwise gate fired

The pairwise head-to-head judges every pair **twice**, with the two answers
swapped. Registered before any pair existed: an order-disagreeing pair is a
**tie**, and above a disagreement rate of **0.20** the pairwise win rate is
not published as the head-to-head at all.

| comparison | order disagreement | resolved |
|---|---|---|
| B vs A | **0.368** | 17 tie / 3 A |
| C-vector vs A | **0.368** | 16 tie / 2 A / 2 C |
| C-vector vs B | 0.158 | 15 tie / 2 B / 3 C |

Two of three are above the gate, so for those the pairwise win rate is
**withdrawn** and the per-stratum correctness comparison above is the
headline — which is what the 2026-07-19 decision rule always said.

A win-rate table is the figure a portfolio README wants: one number, one
direction, easy to read. Discovering that the judge answers differently when
the answers swap places on 37% of pairs and *then* choosing which figure to
publish is a choice that could be argued either way. Having chosen in
advance, there is nothing to argue.

Both comparisons above the gate involve arm A, whose contexts hold 55 to 100
documents against the graph arms' 8 to 40. Position bias plausibly rises
when the two answers differ in shape — that is a **hypothesis from three
numbers**, it is untested, and it is written here so it cannot later be read
as something the experiment established.

## The judge, and what its numbers are worth so far

The judge is built from the same hashed rubric constant the human annotator
reads, so "the judge uses the same rubric" is a property of there being one
object rather than a promise. Every verdict carries the rubric hash, the
prompt version and the model.

> This section records how the judge was built and measured through
> 2026-09-09. **[The judge, published ungated](#the-judge-published-ungated)**
> below carries the 2026-09-11 close: the key-fidelity result, where the
> disagreement actually sits, and why no further auditing is planned.

### The ceiling (E-011a, both passes complete 2026-09-09)

Two blind human passes, five days apart as registered.

| batch | agreement | interval |
|---|---|---|
| b1 (36 rows) | 29/36 = 0.806 | [0.650, 0.902] |
| b1 excluding 4 externally-discussed rows | 26/32 = 0.812 | [0.647, 0.911] |
| b2 (19 rows) | 17/19 = 0.895 | [0.686, 0.971] |
| **pooled** | **43/51 = 0.843** | **[0.720, 0.918]** |

**The judge's threshold is therefore 0.720**, mechanically, with no other
mapping permitted. The four exposed rows cost 0.006 — reported because a
pre-committed sensitivity check is worth something only if its result is
published when it turns out to be negligible.

The registered prediction — "0.75 to 0.90, disagreements concentrating on
the `correct`/`partial` boundary" — got the magnitude right and the location
wrong: five of nine disagreements are `partial` → `incorrect`. E-007c made
the same error in the same direction, naming the boundary adjacent to
"good" while the movement happened at the boundary adjacent to "bad".

### The judge, audited against it

Pooled over both batches, 55 answers, both human passes blind by
construction because both predate `judge.py`.

| | agreement | interval |
|---|---|---|
| b1 (36) | 23/36 = 0.639 | [0.476, 0.775] |
| b2 (19) | 17/19 = 0.895 | [0.686, 0.971] |
| **pooled** | **40/55 = 0.727** | **[0.598, 0.827]** |

Per label, human's label as the denominator:

    correct     13/18 = 0.722 [0.491, 0.875]
    partial      4/14 = 0.286 [0.117, 0.546]
    incorrect   23/23 = 1.000 [0.857, 1.000]

**Verdict: neither passed nor failed.** E-011 gates per label at n ≥ 30 and
no label reaches it — 18, 14, 23 — so every figure here is descriptive and
**no correctness number may be published as validated**. Reaching the floor
on the thinnest label needs roughly 90 audited answers at this label mix,
which is a fact about the registered audit design.

What would have happened is stated deliberately: the judge's pooled lower
bound is **0.598** against a threshold of **0.720**, so it would have
**failed**. The verdict is "not measured", and the difference between that
and "measured and passed" is the whole reason the floor exists.

### The finding: `partial` is where both readers break

The judge agrees with the human on **23 of 23** `incorrect` answers and
**4 of 14** `partial` ones. The human's own second pass moved almost
entirely on `partial` as well — seven of nine disagreements start there.

This is E-007c's result arriving in a new label set: a middle category
absorbs uncertainty. `rubric.py` carries six tie-breaks written before any
label existed, citing E-007c explicitly and designed to prevent this, and
**they were not enough**. Being principled in advance is not the same as
being right in advance.

Nothing is re-labelled. The consequence is carried into Phase 8: the
headline `run_eval.py report` computes is `correct` against everything else,
a two-way collapse that does not depend on the unreliable label. That was
chosen for a different reason — E-007c's warning that a middle category
counting as a win lets the headline move with how generously it is applied
— and it is now robust for a measured reason as well.

## Pending, and what each one blocks

| pending | blocks |
|---|---|
| ~~Correctness ceiling, second blind pass~~ — **done 2026-09-09: 0.843, threshold 0.720** | — |
| ~~Key-fidelity fixtures~~ — **done 2026-09-11: 30/30, see below** | — |
| Judge audit at n >= 30 **per label** — 18 / 14 / 23 of 55, and **not being pursued**; see below | correctness being called *validated*, which it is not |
| ~~Error analysis over the failed answers~~ — **done 2026-09-11: 74% evidence, 19% routing; see below** | — |
| ~~Evaluation split, 57 questions, opened once in Phase 8~~ — **opened 2026-09-12; the gate is recorded in the decision journal** | — |
| E-010's reliability ceiling: a second pass over >= 50 relevance judgements on >= 10 questions, **not before 2026-09-19** | E-010a's precision figures carrying any annotator-reliability bound |
| E-010a's `legality_1hop` stratum, removed from the sample by a filter the human pass did not need | the registered per-stratum precision prediction, which is now readable on `definition_1hop` only |
| **E-014**, registered 2026-09-13, **suspended 2026-09-13 before its first call** | nothing, for now — see below |
| A 3-hop cell that measures three hops: the repaired `answer_path` leaves **10 usable questions of 300**, so a new frozen draw is required | any future claim about depth beyond two hops, E-014 included |

E-014 was registered to ask whether the depth effect is a property of the task
or of `gpt-4o-mini`, pairing across models on MetaQA's frozen split so that
earning a **second** opening of the MTG evaluation split would be the outcome
rather than the method. Its dry run was clean and every registered count
matched — 824 calls, 213 exclusions, 163 at 3-hop, about US$5.80.

It was suspended the same day, unspent. The 3-hop cell it pairs across models
was withdrawn: 92% of it is one-step chains, so a stronger model run against it
would produce a number carrying the same defect and looking exactly like an
answer. The entry stands unedited in the registry; it does not run until a
depth cell exists that measures depth.

**The evaluation split has been opened once, on 2026-09-12**, and nothing since
has touched it. E-001's numbers are unaffected by any of this — different
corpus, different scorer, and `answer_path` has no part in it.

## The judge, published ungated

The judge is not gated, will not be gated in this phase, and this section is
what replaces the gate. The `sufficiency` precedent applies: E-011's amendment
registered that a label whose audit falls short is **reported descriptively
with its ceiling beside it**, and that is what follows.

**Agreement with a human.** 40/55 = **0.727 [0.598, 0.827]**, against a
threshold of **0.720** — the lower bound of the human's own correctness
ceiling, which is the only mapping E-011 permits. The interval's lower bound
is 0.598, so the judge does not pass. Per label: `correct` 13/18, `partial`
4/14, `incorrect` 23/23. Every label is below the registered floor of 30
answers and 30 clusters, so each is descriptive and gates nothing.

**Why more auditing is not the answer.** The threshold sits essentially on
the point estimate. If the true agreement is 0.727, no achievable sample
gates it — n = 5000 still yields a lower bound of 0.714. At n = 90 the judge
would need 0.822. Only `incorrect` is reachable: it is 23/23 today, about 17
answers short of the floor, and would pass at 28/30. That is a real and cheap
measurement, and it is recorded here as available rather than done.

**The judge reads the key, not its own knowledge of Magic.** E-011 point 6's
key-fidelity control ran on 2026-09-11 over 30 items carrying deliberately
wrong keys — 15 rewritten to endorse an answer the human called incorrect, 15
to contradict one they called correct. The judge followed the supplied key
**30/30 = 1.000 [0.886, 1.000]**, both directions perfect. A judge correcting
from memory fails the second direction, and it did not. Note the interval:
even a perfect score on 30 items has a lower bound below the registered 0.90,
so that mark is read as a point estimate, as the entry wrote it.

**Where the disagreement actually is.** Splitting the 55 pairs by whether the
human's own two blind passes agreed:

| rows | n | judge agrees |
|---|---:|---|
| human stable (pass 1 = pass 2) | 46 | **0.804** [0.668, 0.893] |
| human moved (pass 1 ≠ pass 2) | 9 | **0.333** [0.121, 0.646] |

Six of the fifteen disagreements sit on those nine rows — 40% of the dissent
on 16% of the sample — and on them the judge matches the human's **second**
pass more often than their first (5/9 against 3/9). Seven of the nine started
at `partial`. Coding what each dissent appeals to: 11 cite a contradiction the
key actually contains, 4 are omissions under tie-break 3 or 5, and **none**
appeals to anything outside the key.

**So the limitation has a name and a location.** `partial` and `incorrect`
overlap textually — `partial` is "reaches the key's verdict … by reasoning the
key contradicts" and `incorrect` is "asserts something the key contradicts",
an answer can satisfy both, and no precedence rule separates them. Ten of the
fifteen disagreements are `partial → incorrect`. The human's own passes are
unstable on the same boundary. Anyone repairing this instrument should start
there, and the repair is a new rubric version with a newly measured ceiling,
not an edit.

**What this does not excuse.** Two-way collapses — `correct` against
everything else — do not depend on the unreliable boundary, and the headline
`run_eval.py report` computes is exactly that. Three-way figures produced by
this judge carry the limitation above wherever they appear.

## What a human says the answers are worth

The section above is about a measuring instrument. This one is about the
system, and it needs no judge at all: a human read the answers.

| batch | correct | partial | incorrect | correct rate |
|---|---:|---:|---:|---|
| b1 — E-007 pool, 36 answers, incompleteness notice live | 9 | 11 | 16 | **0.250** [0.138, 0.411] |
| b2 — E-001 dev split, arm C-tfidf, 19 answers | 9 | 3 | 7 | **0.474** [0.273, 0.683] |

**Between a quarter and a half of the answers are right**, and the intervals
are wide enough that the gap between the batches is not itself a finding —
they differ in arm, in question pool, and in whether the generator was invited
to hedge.

This is the number that would stop a release to actual players, and it is
worth being explicit that no amount of work on the judge moves it. Calibrating
the instrument further would change how precisely this is known, not what it
is. The pending item that does move it is the error analysis over the 37
answers a human labelled `partial` or `incorrect`, classifying where the chain
broke — linking, routing, missing evidence, the token budget, or generation.
Those labels already exist, the analysis costs nothing, and it produces a
ranked list of repairs rather than another figure.

### Where the chain breaks (2026-09-11)

The analysis ran. `scripts/error_taxonomy.py` assembles each failed answer
beside the retrieval record that produced it, and the attribution below is a
**measurement rather than a reading**: the golden set records `gold_cr_rules`
per question, so "was the rule this answer needed actually retrieved?" is a
set comparison.

Of the 37 answers a human labelled `partial` or `incorrect`, **27 have a
contemporaneous retrieval record**. The other 10 are batch 2, whose answers
and verdicts were kept and whose retrieval rows were never written; they are
left unattributed rather than reconstructed, because re-running retrieval
today would query a graph loaded from a different Scryfall bulk and attribute
a stage using evidence that did not produce the answer.

| stage | n | share |
|---|---:|---|
| **evidence** — the rule is not reachable from any card or keyword | 20 | 74.1% |
| **routing** — reachable by an edge the router never plans | 5 | 18.5% |
| generation — everything needed was in context, answer still wrong | 1 | 3.7% |
| key — no gold rules recorded, not attributable | 1 | 3.7% |

**Retrieval did not fail; it succeeded and returned the wrong rules.** All 27
have `outcome: resolved`, every one returned evidence — 7 to 57 items — and
**not one lost anything to the token budget** (`dropped` empty throughout).
The budget and the generator are not where this system is losing.

**The measurement.** Across the 26 questions carrying gold rules, the answers
needed **64** CR rules and retrieval supplied **7 — 10.9%**. By chapter:

| chapter | needed | retrieved |
|---|---:|---:|
| 100 · game concepts | 10 | 0 |
| 200 · parts of a card | 1 | 0 |
| 300 · card types | 4 | 0 |
| 400 · zones | 3 | 0 |
| 500 · turn structure | 3 | 0 |
| 600 · spells & abilities | 30 | 1 |
| **700 · keyword abilities** | 13 | **6** |

**The graph reaches chapter 700 and essentially nothing else.** That is not a
tuning problem, it is the shape of the edges: `Keyword -[:DEFINED_BY]-> Rule`
lands only in 700 (257 rules), and adding `HAS_SUBRULE` to depth 2 still
lands only in 700 (1,067 rules). The first hop that leaves 700 is
`REFERENCES`, and the only template that walks it — `rule_neighbourhood` —
**ran in none of the 27**.

This is the consequence the decision journal predicted on 2026-08-09, when
G3 withdrew inferred `CITES_RULE` at F1 0.125: *"roughly 87% of the CR rules
`interaction_multihop` needs sit in chapters with no deterministic edge from
any card. `CITES_RULE` was going to be that bridge. It is gone."* Measured
here: **89.1%**.

### The repairs, in the order the measurement ranks them

Of the **52 distinct** gold rules that were needed and not retrieved:

1. **18 (34.6%) are reachable with edges that already exist**, one
   `REFERENCES` hop from a keyword-defined rule. The template exists and the
   router never plans it. This is a routing change over the current graph —
   no model call, no new data — and it is where the next experiment should
   go. It is a ceiling, not a promise: reaching a rule is not citing it
   correctly.
2. **34 (65.4%) are not reachable at all.** These need a bridge from card or
   question to rules outside chapter 700, which is the problem `CITES_RULE`
   was withdrawn from rather than solved. Any attempt is a new experiment
   with its own gate, and the F1 0.125 result is the prior.
3. **Generation and budget are not on this list**, and the record says why:
   nothing was dropped, and exactly one case had its full gold context and
   still answered wrongly.

Both repairs are measurable against this same population before any answer is
regenerated, because "is the gold rule in the retrieved set?" needs no LLM.

### The floor: nothing available here reaches these rules (2026-09-11)

Repair 1 was run and is recorded as E-013: the `REFERENCES` hop gains **one**
rule, and the ceiling registered for it was mis-specified — recomputed from
each question's own retrieved rules it is zero. Then two more measurements
closed off the cheap alternatives.

**The glossary bridge.** The CR's own glossary holds **482 (term, rule) pairs
outside chapters 701/702**, aimed at 100 (138), 300 (58), 600 (49), 200 (47),
500 (39), 400 (13) — and **52 of the 58 missing gold rules (89.7%) are the
target of one**. `graph/loader.py` excludes them deliberately, on the stated
grounds that no golden-set question needs a general glossary node. That
ground was wrong. But the linking side does not hold: matching those terms
against the question text recovers **12 of 58 (0.207)**, against the cards'
oracle text **13 of 58 (0.224) at 14.7 rules pulled per question**, and
restricting to multiword terms — dropping "X", "Pay", "Hand" — collapses it
to **1 of 58**. The rules are pointed at; the vocabulary that points at them
is not the vocabulary anyone writes.

**A plain lexical retriever over all 3,308 rules**, queried with the question
text, on the same population:

| retriever | gold-rule recall |
|---|---|
| the graph, as shipped | 7/64 = 0.109 [0.054, 0.209] |
| lexical, top-25 | 6/64 = 0.094 [0.044, 0.190] |
| lexical, top-50 | 11/64 = 0.172 [0.099, 0.282] |
| lexical, top-100 | 12/64 = 0.188 [0.111, 0.300] |

**At a realistic context size the full-corpus lexical search does worse than
the graph, and even pulling a hundred rules per question it reaches 12 of
64.** So the failure is not that the graph is the wrong instrument. On this
population, *no retriever this project has* finds the rules the answers need.

**The bound on that claim, stated because it is easy to overread.** These 26
questions are the ones where the pipeline already failed — a population
selected for retrieval being hard. The measurement says what nothing reaches
*here*; it does not estimate retrieval quality overall, and the comparison
that would is a run over the successes too.

**What it points at.** Three measurements now say the same thing from
different directions — the `REFERENCES` hop is empty, the glossary links at
0.22, and full-corpus lexical retrieval tops out at 0.188. The gap is
**vocabulary, not topology**: a question names cards and player verbs, a rule
is written in defined terms, and nothing in the current design bridges the
register. Approaches that make the *rule* carry the question's language are
the only family these measurements have not ruled out, and 0.188 is the floor
any of them has to beat.

The judge audit needs roughly **90 audited answers** at the observed label
mix to put 30 behind the thinnest label. That is a larger commitment than
the registered "20% of judged answers" implied, and it follows from gating
**per label** rather than in aggregate — a choice E-011 made for a good
reason (a judge perfect on `incorrect` and hopeless on `partial` passes an
aggregate and should not) whose sample-size cost was never computed when it
was registered.

## E-001 on the evaluation split — the single draw (2026-09-12)

The 57 evaluation questions were opened once, on 2026-09-12, after a gate that
was checked rather than assumed: the split intact (drawn 2026-08-09 at seed
20260809), the dress rehearsal complete on all three arms, **pin 10's legality
keys re-verified 20/20** against the bulk the run would read, and the rubric
frozen at `p6-c1` @ `dfcfb0851c8c` before anything on this side was judged.
All three arms returned 57 retrieval, 57 answer and 57 verdict rows, with no
empty generations and `notice = 0` — pin 11 held.

| stratum | n | A (vector) | B (graph) | C (hybrid) |
|---|---:|---|---|---|
| definition_1hop | 11 | 0.73 [0.43, 0.90] | 0.91 [0.62, 0.98] | 0.91 [0.62, 0.98] |
| interaction_multihop | 22 | 0.41 [0.23, 0.61] | 0.27 [0.13, 0.48] | 0.36 [0.20, 0.57] |
| legality_1hop | 15 | 0.80 [0.55, 0.93] | 0.93 [0.70, 0.99] | 0.93 [0.70, 0.99] |
| negative_temporal | 7 | 0.43 [0.16, 0.75] | 0.57 [0.25, 0.84] | 0.57 [0.25, 0.84] |
| keyword_rule_2hop | 2 | — | — | — |
| **ALL** | **57** | **0.60 [0.47, 0.71]** | **0.61 [0.48, 0.73]** | **0.65 [0.52, 0.76]** |

### The registered verdict is `inconclusive`, four times

The primary family is B vs A on the four strata with n ≥ 7, exact McNemar,
Holm-corrected at α = 0.05 — pinned in August, before any arm ran.

| stratum | predicted | discordant | raw p | Holm p | verdict |
|---|---|---|---|---|---|
| definition_1hop | tie | +3/−1 | 0.6250 | 1.0000 | inconclusive |
| interaction_multihop | fail | +2/−5 | 0.4531 | 1.0000 | inconclusive |
| legality_1hop | lose | +3/−1 | 0.6250 | 1.0000 | inconclusive |
| negative_temporal | fail | +1/−0 | 1.0000 | 1.0000 | inconclusive |

**The central hypothesis is neither confirmed nor falsified.** The amendment
pinned three values and forbade reading a fourth into them; the answer is the
third one, on every stratum.

**And the distance to the threshold was computed before the run.** Exact
McNemar needs 6 discordant pairs one way for raw p < 0.05; Holm's strictest
step needs 8:0. The largest discordance observed anywhere is **5**. This is
what the split could support, written down in advance and confirmed.

**The falsifier could not have been confirmed either.** `definition_1hop`
predicted a tie, and ties are scored by equivalence, never by a failed test —
TOST gives 90% [−0.091, +0.455] against the registered ±0.15, so equivalence is
not shown, exactly as "unpowered for equivalence at n = 11" predicted. B leads
there (+0.182), which is the falsifier's own direction: **the stratum where the
graph looks best is the one where a graph lead was the warning sign.** Not
close to significance, so the warning does not fire.

### The direction runs against the thesis, and half of it is refusal

`interaction_multihop` — the `fail` stratum, where the prediction was graph ≫
vector — reads **B − A = −0.136** [−0.364, +0.091]. Inconclusive, and pointing
the wrong way. It is also the largest stratum, 22 of 57, which is where the
aggregate tie comes from: the graph's 1-hop wins are paid back on the multi-hop
questions the thesis was written about.

**Six of arm B's seven refusals land on that stratum.** Arm A refuses once,
arm C twice. Pin 11 suppressed the incompleteness notice so B and C would not
receive an invitation to hedge that A never gets, and `notice = 0` confirms the
suppression — B hedges anyway, exactly where its context is thinnest. Refusals
score as incorrect.

As an **exploratory** sensitivity, labelled one because dropping refusals is a
post-hoc exclusion that favours B: on the 16 `interaction_multihop` questions
neither arm refused, A reads 0.438 against B's 0.375 — a gap of −0.063 against
−0.136 overall. **Roughly half the graph's deficit on the hypothesis-carrying
stratum is the graph declining to answer rather than answering wrongly.** That
is a generation-side failure sitting on top of the retrieval-side floor, and it
is the same thing E-009 found from the other direction.

### The pairwise gate fired again, and the dev-split hypothesis replicated

| comparison | order disagreement | |
|---|---|---|
| B vs A | **0.333** | withdrawn |
| C vs A | **0.368** | withdrawn |
| C vs B | 0.140 | reportable |

Two of three above the registered 0.20, so those win rates are not the
head-to-head — the per-stratum table above is, as the 2026-07-19 decision rule
always said.

The dress rehearsal produced 0.368 / 0.368 / 0.158 and this document recorded a
guess beside it: position bias plausibly rises when the two answers differ in
shape, *"a hypothesis from three numbers, untested"*. The evaluation split
returns 0.333 / 0.368 / 0.140 — the same ordering, the same two pairs above the
gate, and the same pair below it. **The untested hypothesis now has held-out
support**: the contrasts that put a vector answer beside a graph answer disagree
with themselves about a third of the time, while the contrast whose two answers
are both graph-derived disagrees 14%. It is the same property that made E-010's
blinding unachievable — the arms differ in kind, not only in quality — and it
is still a three-number observation, now made twice.

### The retrieval comparison is budget-confounded, by a gate set in advance

E-010's amendment registered, before this split opened, that if one arm's
median retrieved-item count exceeds the other's by more than **3×** at matched
token budget, E-001's retrieval comparison is published as budget-confounded
and the headline retrieval statement becomes the token-normalised one.

Median items per question on the evaluation run: **A 40.5, B 12.0, C 14.5** —
**A/B = 3.38×**. The gate fired. The headline retrieval figure is therefore
token-normalised precision: **A 0.030, B 0.112, C 0.072**.

Token parity was the registered choice and remains the right one — it is the
constraint both arms actually face at generation. This is the price it charges,
named before the run and paid here. The **correctness** comparison above is
unaffected: it is scored per question against the answer key and does not
depend on the shape of the context.

### Arm A wins the multi-hop stratum without retrieving rules

E-010 part (b) on this same run shows arm A retrieving **no CR rule number at
all on 17 of the 42 questions that carry one** — B misses 8, C misses 4 — while
spending 88% of its payload on cards and rulings. Yet A scores 0.41 on
`interaction_multihop` against the graph's 0.27.

The arm ahead on the multi-hop stratum is not answering from the rules. It is
answering from **rulings**: the Comprehensive Rules already applied to a
specific card, written in the register the question is asked in. That is
consistent with the 2026-09-11 finding that the gap is vocabulary rather than
topology. It is a correlation across two measurements on one run, not a tested
claim, and it is written here as an observation so it cannot later be read as
something this experiment established.

### What E-001 is allowed to say

Not "the graph beat the vector arm", and not the reverse. At 57 questions, with
a judge published ungated, the three arms are indistinguishable in aggregate
(0.60 / 0.61 / 0.65) and every registered per-stratum test is inconclusive. The
directional pattern — graph ahead on 1-hop, behind on multi-hop — is the
opposite of the registered stratification and is reported as a direction, not
as a result.

## The precision proxy on the registered run (E-010b, 2026-09-12)

Part (b) was registered to run on the E-001 evaluation split and could not
until that split opened. It is deterministic, computed from output already
produced, and is not a second draw.

| arm | rule numbers | in gold | rule-number precision | token-normalised | median items |
|---|---:|---:|---|---|---:|
| A (vector) | 131 | 55 | **0.420** [0.339, 0.505] | **0.030** | 40.5 |
| B (graph) | 327 | 73 | 0.223 [0.181, 0.271] | **0.112** | 12.0 |
| C (hybrid) | 344 | 74 | 0.215 [0.175, 0.262] | 0.072 | 14.5 |

**The rehearsal replicated, contradiction and all.** The development split read
A 0.414 / 0.032, B 0.232 / 0.116, C 0.246 / 0.100. The two figures reproduce to
within about 0.01 on A and B — and so does the disagreement between them.
Rule-number precision says arm A is the most precise retriever by nearly 2×;
token-normalised precision says it is 3.7× worse than the graph. A denominator
chosen without reference to what each arm spends its budget on decides the
answer, and which arm it flatters depends on the choice rather than on the
retrieval. That was the rehearsal's headline and it is not an artefact of 20
questions.

The registered prediction — arm A's token-normalised precision below arm B's —
is **confirmed on held-out data**.

**A fourth quietly-selected denominator, found by printing one honestly.** The
per-question mean had been printed as "over N questions". N differs per arm,
because it counts only the questions where that arm retrieved at least one rule
number — so the mean was taken over *whichever questions the arm chose to say
something about*, flattering whichever stays silent most. Printed as N-of-M it
reads: **arm A retrieves no CR rule number at all on 17 of 42 questions**, B on
8, C on 4.

## Precision, and why it is published unblinded (E-010a, 2026-09-12)

Entity recall cannot fall when a retriever brings something spurious, so the
headline metric of Phase 4 is structurally blind to noise. E-010 measures the
other side. Part (b) is deterministic and ran on 2026-09-11; part (a) is the
human pass — **180 relevance judgements, 15 question clusters, 60 slots per
arm**, each item judged against the question *and its answer key*, pooled
across arms and rendered without anything that names the producing system.

**The blinding check fired.** On a seeded 36-slot subsample the annotator
recorded a guess at the producing arm *before* labelling relevance:
**28/36 = 0.778** [0.619, 0.883], above the 0.70 registered in advance. Per the
registered rule the blind claim is withdrawn and everything below is an
**unblinded** comparison.

**The reason it fired is not a formatting leak, and this is the part worth
reading.** A classifier that sees *only the evidence kind* — fitted on the 144
slots outside the subsample, scored on the 36 inside — reaches **0.722**, above
the threshold by itself. Twenty-six of the twenty-eight correct guesses need no
information beyond *rule*, *term*, *card*, or *ruling*. The normalisation had
already stripped `template`, `path`, handle syntax and chunk boundaries and
mapped `glossary` and `keyword` onto a shared `term`; none of it mattered,
because the vector arm returns cards and rulings and the graph arms return
rules and terms. **That difference is the treatment under test.** A
normalisation strong enough to hide it would hide what is being compared, so
item-level blinding here is not badly implemented — it is unachievable, and is
withdrawn as a goal rather than retried.

| arm | item precision | token-normalised |
|---|---|---|
| A (vector) | 19/60 = 0.317 [0.213, 0.442] | **0.400** |
| B (graph) | 24/60 = 0.400 [0.286, 0.526] | **0.452** |
| C (hybrid) | 25/60 = 0.417 [0.301, 0.543] | 0.343 |

**Every paired contrast crosses zero.** Cluster bootstrap over the 15
questions, 10 000 resamples: A−B token-normalised **−0.051** [−0.344, +0.250],
A−C **+0.057** [−0.248, +0.349], B−C **+0.109** [−0.091, +0.297]. Item
precision A−B **−0.083** [−0.283, +0.117]. Before and after Bonferroni.

That null was registered in advance. The 2026-08-15b amendment stated that 20
development questions cannot carry this comparison and built the deterministic
proxy for that reason. The prediction it registered — arm A's token-normalised
precision below arm B's — is **confirmed in direction and unconfirmable in
magnitude** at this n.

**The two instruments agree on the sign and disagree on the size, and that
bounds the proxy.** Part (b) read 0.032 against 0.116, a 3.5× gap; the human
pass reads 0.400 against 0.452, 1.13×. The proxy scores relevance by
`gold_cr_rules`, which **cannot score a card or a ruling** — and **508 of arm
A's 575** retrieved items on these questions are cards (133) and rulings (375),
against 56 rules. It therefore penalises arm A for
retrieving a kind of evidence its own oracle is unable to credit. **Part (b)'s
3.5× is an upper bound on the gap**, and the honest statement is that the graph
arms retrieve a denser payload in direction, by an amount these 15 questions
cannot pin down.

Two registered items are outstanding and are not quietly dropped: the
`legality_1hop` stratum is **absent** from part (a)'s sample — `build()`
inherited a `gold_cr_rules` filter the human pass does not need, which removed
all five `scry-leg-*` questions — and the mandatory second-annotator ceiling
(≥ 50 judgements over ≥ 10 questions) **has not run**, so these precision
figures carry no annotator-reliability bound.

## Limitations, stated because they bound every number above

- **Part (a)'s precision figures are unblinded and unbounded by a second
  annotator.** The blind claim was withdrawn by the registered rule, and the
  reliability ceiling that would bound them is outstanding. They are one
  reader's judgements, published as such.
- **`legality_1hop` is unmeasured for precision.** A filter part (a) did not
  need removed the whole stratum, so the registered per-stratum prediction can
  be read on `definition_1hop` only, and the aggregate carries the rest.
- **The retrieval metric cannot see the evidence the arms retrieve on the
  stratum that carries the hypothesis.** Pin 6 grades at rule-number
  granularity against `gold_cr_rules`. All 8 development
  `interaction_multihop` questions retrieve between 2 and 17 Scryfall
  rulings belonging to a card the answer key names, while 7 of 8 score
  **zero**, because a ruling carries no CR number. This shows rule recall
  does not measure whether answer-bearing evidence was retrieved when that
  evidence is a ruling; it does **not** show those rulings answer the
  questions, which is a judgement. No new metric was invented — proposing
  one after watching the registered one read zero is exactly what the
  pre-registration forbids — and **Context Sufficiency**, already registered
  and judged, carries the retrieval-layer claim on that stratum. The
  blindness is symmetric across arms.
- **Token parity buys an item-count disparity of roughly an order of
  magnitude.** At the shared 6,000-token budget arm A keeps 55 to 100
  documents per question against a median of 8 evidence items for the graph
  arms. Matching on tokens was registered in advance as the constraint both
  arms face at generation, and the item-count ablation is therefore
  load-bearing rather than a formality: it is what stops the choice of
  parity from silently deciding which arm looks precise.
- **Arm C's text half fires on 2 of 20 development questions.** The router
  sends a question to text retrieval only when the graph cannot seed it, so
  arm C differs from arm B on a tenth of the split and "C vs B isolates the
  text contribution" is close to a null comparison by construction. The
  router was **not** changed — arm C is the shipped system, and quietly
  making the shipped system retrieve more so a comparison looks better is
  the move this apparatus exists to prevent. Arm C runs in two published
  states instead, and the README quotes the shipped one.
- **Arm B is single-shot by construction.** Iterative retrieval is offered
  to every arm that can accept it; arm B cannot today. The multi-hop claim
  is bounded in writing naming which arms had the affordance.
- **The incompleteness notice is suppressed on every arm**, so no arm is
  handed an invitation to hedge that another cannot receive. It changed
  nothing observable here — `context_incomplete` is 0 of 20 — so it is a
  parity guarantee against a case that has not occurred, not an intervention
  with a measured effect.
- **The correctness ceiling is measured on shipped-hybrid prose**, not on
  graph-only prose. Both ceiling batches were generated with text retrieval
  attached. That happens to be the arm the README figure quotes, so the
  ceiling is on the right prose **by accident rather than by design**.
- **Arm A was swept and nothing was adopted, which is a limitation of the
  objective rather than of the baseline.** Pin 7's good-faith tuning sweep
  ran across 588 cells plus three follow-up probes, with no LLM call —
  published in [`sweeps/README.md`](sweeps/README.md). Every apparent gain
  lives in a degenerate regime: gold-rule recall rises monotonically with
  candidate depth (11/26 at depth ≤ 200, 16/26 at ≤ 1600, 19/26 at ≤ 12800,
  by which point the arm reads 11% of the corpus per query), and the one
  parameter that looked like a real gain, `b = 0.4`, does **nothing** at
  defensible depths — 7/9/9/10 at depths 50/100/200/400 regardless of `b`.
  `k1`, `rrf_k` and `iterative` likewise tie everywhere the depth is
  defensible.

  The mechanism is the same metric defect as the bullet above, reached by a
  different route: rule recall counts gold numbers surviving the budget, so
  a bigger candidate pool always helps, and the metric measures recall into
  a pool rather than retrieval precision.

  So arm A stays at published defaults, and the standard objection to a
  baseline — "you never tuned it" — does not apply. What this does **not**
  license is "arm A is at its optimum": the correct reading is that the
  registered retrieval objective cannot tell arm A's configurations apart.
  A sweep on **answer correctness** would be the informative one and costs
  15 generations plus 15 judge calls per cell, against a judge not yet
  audited above its floor. Named as future work with its cost.


---

# Results — Phase 9: where this GraphRAG works, and where nothing here does (2026-09-13 → 14)

Phase 9 opened to repair retrieval so the governing CR rule would reach the
context. **It closed without shipping a repair, because the repair was measured
to be unavailable before any was built.** What it produced instead is the
statement below: a bounded description of the stratum this graph serves and the
stratum it cannot, with the ceiling of each alternative on the table.

This section changes **no figure in E-001**. Its verdict stands with the date it
has, over the system that produced it.

## The claim

**This GraphRAG outperforms the vector baseline exactly where its topology
reaches, and is outperformed outside it.** The reach is not a tuning parameter;
it is a property of the edges the corpus supports.

## What retrieval delivers, decomposed

Arm B, evaluation split, `interaction_multihop` — the stratum this project was
built for, 22 questions:

| what retrieval has to find | delivered |
|---|---:|
| the cards the question names | **39 / 40** |
| the rulings of those cards | **182 / 191** |
| **the governing CR rule** | **2 / 22** |

Everything reachable from a card arrives at 95% or better. The rule the answer
key says governs arrives on **9%**.

And the budget goes where the edges go. Half of arm B's 42,417 evaluation
context tokens — **50.1%** — expand keywords into chapter 700, the only chapter
E-013 measured as reachable from a card:

| traversal | items | tokens | share |
|---|---:|---:|---:|
| `card_rulings` | 230 | 17,007 | 40.1% |
| `card_keyword_rules` | 205 | 11,894 | 28.0% |
| `keyword_definition` | 172 | 9,353 | 22.1% |
| `card_core` | 84 | 3,696 | 8.7% |
| `card_legality` | 14 | 332 | 0.8% |
| `card_interaction` | 5 | 135 | 0.3% |

Reproduce with `python scripts/e001_inspect.py --arm B --context`.

## Where that lands, per stratum

| stratum | n | keyword share of budget | gold rule reached | correct, arm B | correct, arm A |
|---|---:|---:|---:|---:|---:|
| `definition_1hop` | 11 | **100%** | 11/11 | **10/11** | 8/11 |
| `keyword_rule_2hop` | 2 | 98% | 2/2 | 1/2 | 2/2 |
| `negative_temporal` | 7 | 57% | 2/7 | **4/7** | 3/7 |
| `legality_1hop` | 15 | 46% | — | 14/15 | 14/15 |
| `interaction_multihop` | 22 | 36% | **2/22** | **6/22** | **9/22** |

Where the question *is* a keyword definition, the graph spends its whole budget
on exactly the right thing and answers 10 of 11 — ahead of the vector arm.
Where the question is a multi-card interaction, it spends over a third of the
budget on keyword definitions, reaches the governing rule twice in twenty-two,
and is **behind** the arm with no graph at all.

**These per-stratum numbers are descriptive and are not a verdict.** E-001
declined to publish per-stratum comparisons on strata this small and this
section inherits that refusal: `keyword_rule_2hop` holds two questions and runs
*against* the claim. The pattern is what a Phase 10 hypothesis should be sized
to test, not something these 57 questions establish.

## Four repairs, each measured and each unavailable

Phase 9 did not choose the bridge by elimination-by-argument. Every alternative
was measured, and three of the four closed before any code was written.

| candidate repair | measured | outcome |
|---|---|---|
| **the bridge out of chapter 700** (E-022) | of 39 missing gold rules, expanding `REFERENCES` **and** parent/child in both directions from the rules retrieval already delivers | **1 reachable at one hop (3%)**, 2 at two hops (5%), and the two-hop closure adds a median of **138 rules per question**. The edges do not exist. |
| **gold ruling coverage** (E-021) | rulings Scryfall holds for the resolved cards, against what arrived | **182 of 191.** Nothing to inject on 21 of 22 questions. Withdrawn before its annotation was written. |
| **wrong-sense entity linking** | glossary entries with two or more numbered senses, and how often they are linked | **4 questions of 57, 3.5% of context**, one of them severe. Not systemic. |
| **budget policy** (E-013, E-007) | `dropped` and `capped` | empty on every question measured. The budget never fires on this corpus. |

And the intervention that would have justified the whole programme returned
nothing: **E-018 injected the governing rule directly and came back
`unresolved`** — 2 discordant pairs where 7:0 was needed, and one of the two
gains cited nothing that was injected.

## Is it the graph, or is the rule just hard to find?

It is not the graph. On the same 22 questions the **vector** arm reaches the
gold rule **2 of 22** and the hybrid **3 of 22**. The governing rule for a
multi-card interaction is not recoverable from the question's surface text or
from the card's neighbourhood **by any method built here**.

That is the load-bearing sentence of this section, and it is what makes the
finding a property of the problem rather than of one implementation.

**And the vector arm's two are the graph arm's two.** Not two of the same
count — the same two questions, `hand-deathtouch-trample` and
`hand-first-strike-deathtouch`. Split by where the target annotation came from,
of the 22: 6 are `hand-*` where the author wrote key and annotation, **13 are
transcribed from RulesGuru's curated `citedRules`**, and 3 are RulesGuru
questions whose `citedRules` was empty and which the author filled in. On the
13 curated:

| arm | gold rule reached, curated subset |
|---|---:|
| A — vector | **0 / 13** |
| B — graph | **0 / 13** |
| C — hybrid | 1 / 13 (`rg-1469`) |

Both of the questions the vector and graph arms reach are `hand-*`. **Where the
target was cited by a judge rather than by this project's author, neither
single-strategy arm reaches it at all.**

Reproduce with `retrieved_rules` over `e001_*_retrieval_eval.jsonl`. One
measurement caveat, stated because it is not ruled out: `retrieved_rules`
requires an **exact** key match, so a rule reached through its parent — `608.2`
where the annotation says `608.2n` — counts here as a miss.

## What this does not say

- **It does not say GraphRAG loses.** It says *this* graph, over *this* corpus,
  reaches keyword-defined rules and not structural ones, and that its
  correctness tracks that reach.
- **It does not revise E-001.** The head-to-head verdict is `inconclusive` and
  stays so, with its date and its system.
- **It is not a per-stratum verdict.** The strata are small, one runs against
  the claim, and E-001's refusal to publish comparisons at these sizes applies
  here unchanged.
- **It does not clear the generator.** E-018's manual sample
  ([error-samples/e018.md](error-samples/e018.md)) puts **four of 16** derivable
  questions in "reasoned wrong with the evidence in hand". Read case by case
  against the prompt as sent and countersigned by the author on 2026-09-14,
  with zero departures from the proposed split. The denominator is a ceiling
  computed with the gold rule injected — **oracle-conditioned, not a system
  score** — and at that size the figure is a lead for E-023, not a rate.
- **One retrieval defect remains open and is not part of the claim**: 7 card
  items over 6 questions reach the graph arm as a bare name, and power and
  toughness are never serialized for any card. Zero occurrences in the vector
  arm. Small, specific, cheap to close, and it does not move the 2/22.
- **The target these figures are scored against has external provenance, and
  nine questions are the exception.** `gold_cr_rules` reproduces RulesGuru's
  judge-curated `citedRules` on **24 of 24** golden-set questions carrying one
  at chapter level and **23 of 24** exactly, which is what the project's
  curate-don't-author decision was for. The exceptions are the six `hand-*`
  questions, where the author wrote key and annotation, and three RulesGuru
  questions whose `citedRules` was empty. **None of those nine has been read by
  a second annotator**, and nine is too few to measure determinacy on — see
  E-025, withdrawn 2026-09-14 before its first reading.

## Why the phase is reported this way

A phase that ends without a repair, having measured that the repair was not
available, is a cheaper outcome than the same phase ending after the repair was
attempted. Every closure above cost counting; the only API spend in Phase 9 was
**US$ 0.19** across E-018 and E-020.

The mechanism that produced that is worth naming, because it is the transferable
part: **ceilings computed from the run's own inputs before code, and a gate
experiment that had to return positive before the engineering opened.** The
ceilings closed three fronts; the gate declined to open the fourth.


# Results — Phase 10: the floor of this evaluation, and what sits above it (2026-09-14)

Phase 10 opened to take a second correctness verdict on a fresh split. **It
measured, before curating a single question, that no such verdict was available
to it** — and then found the claim that is.

Two results, both computed over runs that already existed, both at zero cost.

## 1. The floor: 0.20 at n = 57, and nothing this project measured ever cleared it

E-026 asked one question, in words before it was a number:

> *Of the paired correctness comparisons this project has run on the Magic
> side, how many produced an effect large enough that a comparison of that size
> could have distinguished it from zero at 80% power?*

**Zero of nine.**

| contrast | *d* | n | floor | n needed |
|---|---:|---:|---:|---:|
| E-001 overall, B vs A | +0.018 | 57 | 0.203 | — |
| E-001 `legality_1hop` | +0.133 | 15 | 0.395 | 132 |
| E-001 `definition_1hop` | +0.182 | 11 | 0.461 | 71 |
| E-001 `negative_temporal` | +0.143 | 7 | 0.578 | 115 |
| E-001 `interaction_multihop` | −0.136 | 22 | 0.326 | 126 |
| E-001 `keyword_rule_2hop` | −0.500 | 2 | 1.082 | 10 |
| E-018 treatment vs control | +0.100 | 20 | 0.342 | 235 |
| E-018 placebo vs control | −0.050 | 20 | 0.342 | 937 |
| E-020 order vs floor | +0.053 | 19 | 0.351 | 846 |

The smallest effect this evaluation can see, at E-001's pooled discordance of
17/57:

| n | simple contrast | interaction |
|---:|---:|---:|
| 20 | 0.342 | 0.484 |
| **57** | **0.203** | 0.287 |
| 120 | 0.140 | 0.198 |
| 400 | 0.077 | 0.108 |

**An interaction costs about four times the questions of the simple effect it
is built from.** That line was available on 2026-09-12 and would have prevented
three registered entries — E-025, and both designs of E-019 — from being
written. Nobody had measured it.

### What this does and does not say

**It does not say the effects are zero.** It says this evaluation could not have
told the difference, so **every `inconclusive` it returned was the only answer
available to it.** E-001 was not badly designed; it was measured with a ruler
whose smallest mark is larger than the thing measured.

**It does not condemn the entries.** An entry that registers its decision rule
and returns `inconclusive` has done its job. What is measured here is whether
the instrument was ever capable of returning anything else.

**It does say that curating more questions is not a plan.** The largest
correctness effect this project has measured is **+0.182**, itself estimated at
n = 11 with SE 0.17. Detecting it needs **71** questions for a simple contrast
and roughly **280** for an interaction. The annotated golden set holds 77 rows
and all 77 are spent.

### Computed twice, and the estimators disagree

| n | normal approximation | exact permutation |
|---:|---:|---:|
| 20 | 0.342 | **0.430** |
| 57 | 0.203 | **0.220** |

The approximation **understates** the floor below n ≈ 50, where *d* is discrete
and the permutation null pools the variance. The tables above use the
approximation and this correction is published beside them rather than folded
in. Reproduce with `python scripts/detectability.py --simulate`.

## 2. What sits above the floor: economy, not precision

The first proposal for Phase 10's claim was that **evidence precision**
separates the arms, citing this document's own Phase 8 figures: A **0.420**
[0.339, 0.505] against B **0.223** [0.181, 0.271], non-overlapping.

**Those intervals are computed over 131 and 327 pooled evidence items, and
evidence items are clustered inside questions.** Paired within question and
bootstrapped over questions, the same contrast returns **−0.001
[−0.044, +0.039]**. The entire gap was the clustering.

E-027 reports every endpoint paired within question, 10,000 resamples over
questions, seed 20260914:

| endpoint | A vector | B graph | B − A | 95% CI | |
|---|---:|---:|---:|---|---|
| evidence items | 38.86 | 12.46 | **−26.40** | [−29.46, −22.89] | **separates** |
| context tokens | 3892 | 744 | **−3148** | [−3428, −2843] | **separates** |
| CR rule items | 2.09 | 5.47 | **+3.39** | [+1.65, +5.37] | **separates** |
| rule precision | 0.07 | 0.08 | +0.00 | [−0.02, +0.02] | crosses zero |
| gold-rule reach | 0.43 | 0.48 | +0.05 | [−0.07, +0.19] | crosses zero |
| correctness | 0.60 | 0.61 | +0.02 | **[−0.12, +0.16]** | crosses zero |

### The claim, with the bound it travels with

> On these 57 questions the graph arm answers **within [−0.12, +0.16] of the
> vector baseline's correctness** while spending **19% of the context tokens**
> and **32% of the evidence items**, and surfacing **more** CR rules — 5.47
> against 2.09.

**"Within ±0.16" is not "the same".** The economy is a ten-standard-error
effect; the equivalence it rests on is the widest thing in this document. That
asymmetry is the honest shape of the result and it goes wherever the figure
goes.

### What is not claimed

- **Not that the arms are equally correct.** That would need an evaluation with
  a lower floor than 0.20.
- **Not that the graph retrieves better.** Rule precision and gold-rule reach
  are measured null with tight intervals.
- **Not a pre-registered finding.** E-027 is **registered retrospectively** and
  marked so in the registry: the numbers were computed while deciding whether
  the entry was worth writing. There was no decision rule fixed in advance and
  this is an exploratory measurement of existing runs. E-028 is named as the
  confirmatory successor.
- **Not a budget artefact.** Both arms ran under the same 6,000-token cap with
  `dropped` empty on every question, so neither was truncated. The graph spends
  less because its traversal returns less. Under a tighter budget the comparison
  would differ, and that is not predicted here.

## Three proposals died on checking, and the pattern is the result

Phase 10 proposed three claims in one day and measured each before publishing
it. All three failed:

| proposal | killed by |
|---|---|
| the stratum × arm **interaction** on correctness | power at its own declared bar is 0.26; 80% needs 440 questions, against the 296 that got its alternative rejected |
| **gold-rule reach** as the estimand | reach is 11/11 in all three arms on `definition_1hop` and 2/22 in both A and B on `interaction_multihop` — the large effect is between strata, not between arms |
| evidence **precision** | the published non-overlapping interval was pooled over clustered items; paired, it is −0.001 |

Each died to a measurement that could have been taken before the proposal was
made. **That is the transferable part of this phase**, and it is the same
lesson E-018 wrote in different words: the check that matters is the one run
before the claim, not after it.

Reproduce: `python scripts/detectability.py`, `python scripts/e027_economy.py`.
