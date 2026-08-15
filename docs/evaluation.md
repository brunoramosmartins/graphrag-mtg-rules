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
