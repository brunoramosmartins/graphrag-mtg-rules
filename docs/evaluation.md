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

## The finding: generation, not retrieval

The registered prediction "grounded generation is not the bottleneck at any
hop" is **falsified**, and that is the transferable result. Conditional on
the answer entity being present in the evidence the model actually received:

| hop | correct given the answer was shown |
|---|---|
| 1-hop | 0.884 [0.853, 0.909] |
| 2-hop | 0.677 [0.631, 0.720] |
| 3-hop | **0.339** [0.280, 0.404] |

At three hops the model uses **one third** of what retrieval hands it.

## E-012 — is it size or depth? (confirmatory, 2026-09-03)

E-002 could not separate the two: its 3-hop subgraphs are simultaneously
deeper *and* far larger (median 206 evidence items against 17 at 2-hop). So
E-012 ran questions at **matched context sizes** across hops with the
answer-bearing chain guaranteed present, on a frozen confirmatory draw of
300 per hop taken from the complement of E-002's subset.

| *k* | 1-hop | 2-hop | 3-hop |
|---|---|---|---|
| 8 | 0.883 [0.842, 0.915] | 0.660 [0.599, 0.716] | 0.489 [0.407, 0.572] |
| 16 | 0.890 | 0.672 | 0.511 |
| 64 | 0.890 | 0.656 | 0.591 |
| 256 | 0.897 | 0.628 | 0.518 |
| untrimmed | 0.893 | 0.628 | 0.533 |

**Depth at matched size: every row separated, spread 0.30 to 0.39.** Holding
the context at 8 items, accuracy still falls 0.883 to 0.660 to 0.489.

**Size at fixed depth: nothing.** 1-hop moves between 0.883 and 0.897 across
a 32x change in context. Paired within question, untrimmed against *k*=8:
2-hop p=0.382, 3-hop p=0.451, 1-hop p=0.648 — none near its Holm threshold.

Three predictions were registered; **all three were wrong**, including the
one this experiment was built to confirm. The registered consequence stands:
context reduction is **not** adopted, `enforce_budget`'s distance-first trim
**stays**, and E-001's multi-hop stratum carries the compositional limit as
a named bound.

## What Act 1 transfers, and what it does not

- **Transfers.** The bottleneck at depth is compositional reasoning, not
  context size and not retrieval volume. MetaQA questions are templated and
  their chains uniform, so the depth effect measured here is a **floor** on
  the depth effect in judge-level Magic questions, not an estimate of it.
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
| Evaluation split, 57 questions, opened once in Phase 8 | every claim about the arms |

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

## Limitations, stated because they bound every number above

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
