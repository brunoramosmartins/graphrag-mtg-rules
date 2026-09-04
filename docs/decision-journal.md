# Decision Journal

Dated entries, written the day the decision is made. Entries
reconstructed from git history after the fact are marked
*(retrospective, written 2026-07-19)*. Architectural decisions get a
full ADR in [docs/adr/](adr/); the journal records the smaller,
dated calls that an ADR would be too heavy for — and points at the
evidence that forced each one.

---

## 2026-07-17 — Domain choice gated by motivation and licensing *(retrospective, written 2026-07-19)*

MTG rules chosen as the domain (ADR-001) with an explicit licensing
gate before any data touched the repo: Fan Content Policy compliance,
no bulk data committed, Scryfall attribution. Contingency gates
defined up front so an abandoned phase fails loudly instead of
lingering. Embodied in `9cd111d`.

## 2026-07-17 — Neo4j property graph over RDF *(retrospective, written 2026-07-19)*

Property graph (ADR-002): the ontology is small and typed, queries are
path-shaped, and Cypher templates are auditable. A written comparison
with RDF/OWL was not produced at decision time — parked as a possible
TIL, not re-litigated.

## 2026-07-18 — Curate, don't author, the golden set *(retrospective, written 2026-07-19)*

Golden set sourced from judge-curated RulesGuru questions rather than
self-authored ones, with `vector_should` predictions (fail/lose/tie)
recorded per question **before** any system runs. The `tie` stratum is
deliberate: a hypothesis that cannot lose anywhere is not a
hypothesis. Embodied in `ddca2bf`; source of truth in
[evaluation.md](evaluation.md).

## 2026-07-19 — Deterministic backbone; LLM only for the residual *(retrospective, written 2026-07-19)*

Phase 2 build decisions, each forced by measurement rather than taste:

- `subtree()` walks parent links, not number prefixes — `613.4b` does
  not start with `613.4.` (caught by a failing test).
- `mana_value()` refuses combined multi-face costs — 209 adventure
  cards would silently get a wrong value (caught by cross-checking
  against Scryfall `cmc`).
- Keywords keyed on normalized names — Scryfall's `"First strike"` vs
  the CR glossary's `"First Strike"` silently split every keyword into
  two nodes, leaving `Card → Keyword → Rule` empty while node counts
  looked healthy.
- Load reports use Neo4j result counters, not row counts — `0 created`
  on a reload is direct idempotency evidence.
- `PRUNE_STALE_RULES` keyed on `source_sha256` — `MERGE` never
  deletes, so withdrawn rules survived a CR update until pruned.

## 2026-07-19 — `rulings_2hop` deferred to Phase 3 on evidence *(written same day; measurement corrected 2026-07-20, see below)*

Measured: 1 of 77,999 rulings contains a CR rule number (and it is
about a store locator). `CITES_RULE` therefore has no deterministic
component — the edge can only come from validated LLM extraction,
which is exactly Phase 3's job. The stratum moves there instead of
being faked here.

## 2026-07-20 — G3 assessed on the dev split: proceed, iterate to grounded mode

First extraction run (open mode, gpt-4o-mini, 30 dev rulings, ~$0.01):
31 candidates, 2 fabricated quotes killed by the parser, 7 of 31
(23%) citing **plausible but nonexistent** rule numbers — all caught by
the gate's existence check. Spans and concepts look right; the numbers
are invented (e.g. 702.74b for connive, which is 701.50). Neither
trivial nor infeasible under E-003's decision rule, so Phase 3 proceeds
as designed: round 2 grounds the prompt in candidate rules retrieved
from the graph. What the gate cannot catch — existing-but-wrong numbers
— is exactly what the manual annotations will measure.

## 2026-07-21 — Lexical CR search aids the citation pass without contaminating the gold

The liberal citation pass requires naming the CR rule each ruling invokes,
which by hand means grepping 3,000+ rules. Built `cite_search.py`: a
deterministic TF-IDF ranking of CR rules by term overlap with a ruling, so
the annotator reads ~8 candidates instead of the whole document (for the
Crib Swap example it ranks 608.2b first; for connive, 701.50b first).

Why this is allowed where an LLM suggester would not be: the distinction is
"accelerate the search" vs "generate the answer". The tool ranks candidates;
the human reads the actual rule text and decides which one *governs*. It is
lexical, so it shares no mechanism with the LLM extractor under evaluation,
nor with the semantic retrieval the vector baseline will use — gold
citations found with its help do not correlate with either system, so the
CITES_RULE F1 and the Phase 6 baseline comparison stay honest. An LLM
suggester was rejected precisely because it would grade the extractor
against a gold it helped write. Embedding retrieval was deferred to Phase 4
for the same correlation reason plus its infrastructure cost.

## 2026-09-04 — Phase 6 Act 2 is sequenced by a clock, not by the deliverable list

The roadmap lists Act 2's deliverables in a reasonable order and that
order is wrong, because one item on it cannot be compressed by working
harder. E-011's amendment fixes the judge's pass mark as the lower bound
of a human self-agreement interval, and that interval requires a **second
blind pass at least five days after the first**. Nothing else in the phase
has a calendar dependency; everything else is work. So the first task is
whatever starts that clock, and the rest of Act 2 runs beside it.

Starting it needed a pool of ≥ 30 dress-rehearsal answers, and none
existed: `runs/e008_answers_dev.jsonl` holds 6 fixture probes, and E-007's
audit is claim-level, not answer-level. Resolved by pooling E-007's two
sides — the 32 audit answers already on disk plus 10 newly generated for
the dev side, US$ 0.01, same model and prompt version, which the tool
verifies rather than assumes.

**The choice that took the most thought was which questions.** The
tempting pool is the golden set, because those are the questions Phase 6
cares about — and that is exactly why it is disqualified: a ceiling
measured on questions the head-to-head is later scored on makes the
instrument a function of the data it grades, and nothing downstream could
detect it. E-007's 42 turn out to be **disjoint from the golden 77**, which
was not a fact I trusted from memory: `audit_correctness.py build`
computes E-001's evaluation split and exits if any candidate appears in it.

**Refusals are excluded from the ceiling, and that exclusion is
load-bearing.** 6 of the 42 answers are refusals. Both passes would agree
on all six without reading anything — a refusal is a flag, not a judgement
— and those free agreements would inflate the precise number that becomes
the judge's pass mark. Excluding them costs 6 rows and leaves 36, still
above the registered floor of 30. A refusal still scores as a miss in
E-001; that is a scoring rule and it belongs there.

Registered as E-011a before the first label, with the sample, the seeds,
the label set, the six `partial` tie-breaks and a prediction. The rubric
lives in `evaluation/rubric.py` as one hashed constant so that "the same
rubric the judge uses" is enforced by there being a single object rather
than a promise.

Two guards were written the wrong way round first and are worth recording:
the second pass carried a *copy* of the first pass's answer hash and
compared it against its source, which is a check that cannot fail. It now
re-renders from the live files. And stripping citation handles left a space
before the punctuation they preceded — a typo the model did not make, and a
tell that a handle had stood there, which is the arm-identifying cue the
blinding exists to remove.

## 2026-09-03 — The teardown I wrote to prevent E-008 destroyed the corpus container

Running E-002's documented teardown removed **both** Neo4j containers, the
corpus one included. `docker compose --profile metaqa rm -sf` does not mean
"act on the metaqa profile"; `--profile` *adds* a profiled service to the
default set. Confirmed after the fact: `docker compose config --services`
lists one service, with the flag it lists two, and `rm -sf` took both.

The corpus data survived because it lives in a named volume — `docker
compose up -d --wait` recreated the container and reattached it, and the
counts are unchanged: 34,236 cards, 3,308 rules, 77,229 rulings, 895,082
relationships. Nothing was lost. That is luck wearing the costume of design.

What makes this worth an entry is where it happened. The whole amendment of
2026-09-02 argued that moving MetaQA to a disposable container **removes**
the failure mode behind E-008 — where a teardown `DELETE` matched three real
CR rules — because there would be no teardown query at all. That reasoning
was right about the query and wrong about the blast radius: I replaced a
dangerous Cypher statement with a dangerous shell command and did not read
the second one as carefully as I had read the first. The class of failure
was never "Cypher". It was **a teardown whose scope I assumed instead of
verified.**

The correction, in the compose file, `.env.example`, the registry clause and
the script's own output: teardown names the **container**,
`docker rm -f graphrag-mtg-neo4j-metaqa`. A container name cannot expand to
include something else; a profile can.

Two things I am taking from it beyond the command itself. The isolation that
actually held was the one I did not argue for in the amendment — the corpus
having a named volume and the throwaway having none. And a destructive
command deserves the same treatment as a destructive query: run it once
against something you can afford to lose, or check what it resolves to
before running it. `docker compose config --services` would have taken five
seconds.

## 2026-09-03 — E-012: the obvious repair was the wrong repair, and three predictions fell

Branch 2. Holding the context at 8 items, accuracy still falls 0.883 → 0.660
→ 0.489 across depth; holding depth fixed, a 32× change in context size
moves nothing that survives a paired test. The bottleneck at three hops is
composition, and context size is not a factor.

So the repair I was about to build is not worth building. After E-002 the
actionable finding looked obvious: `enforce_budget` trims farthest-first, a
multi-hop answer lives at the frontier, 3-hop shown-reach was 0.448 — change
the policy. That is a day inside shipped code with regression risk across
two closed phases, and E-012 says it buys nothing. When the answer is
present, how much surrounds it does not matter. **The experiment that stopped
me from doing the work cost about a dollar and three hours of machine time.**

Three predictions registered, three wrong — size dominates, a residual depth
effect of 5–15 points, untrimmed worst everywhere. The depth effect is not
residual, it is the entire effect, at roughly 24 points per hop. I am
writing that down rather than softening it: E-002's falsified prediction was
the finding that justified E-012, and now E-012's falsified predictions are
what stopped a pointless refactor. Two experiments, and in both the value
came from being wrong on the record.

**The methodological result is the one I want to keep.** E-012a, reading the
same 1,500 answers observationally, said *size* — accuracy collapsing 0.979
→ 0.123 as context grew. E-012b, assigning the size, says *depth*. Same
data, opposite conclusions, and the entry stated in advance why the first
could not be trusted: the buckets were observed, and a 2-hop question only
reaches 129–512 items when its seed is a hub, so that cell compared an
anomalous minority against a typical majority. If I had shipped 12a's
reading — and it was tempting, it was clean and it matched my prior — I
would have built the wrong thing with a confident chart behind it.

One number worth carrying to E-001: E-002 measured 0.339 at 3-hop given the
raw retrieved evidence, E-012 measures 0.533 given a clean chain. Different
samples so it is indicative, but it prices perfect evidence selection at
about 19 points against 47 that stay compositional. **Retrieval quality is
the smaller half of the multi-hop problem.** That is a sobering thing to
learn in a project whose central hypothesis is about retrieval — and it is
the kind of sentence the limitations section exists for.

## 2026-09-03 — E-012 registered: the 3-hop drop has two candidate causes and E-002 cannot separate them

E-002 says the generator uses a third of what retrieval hands it at three
hops. It does not say why, and the reason matters more than the number: its
3-hop subgraphs are simultaneously **deeper** and **far larger** — a median
206 evidence items against 17 at two hops — so "the model cannot chain three
facts" and "the model cannot find the fact in 206 of them" fit the data
equally well and imply opposite fixes.

E-012 separates them by holding size constant and letting depth vary: each
question run at *k* ∈ {16, 64, 256} and untrimmed, with the answer-bearing
evidence guaranteed present. If 3-hop catches up at small *k*, the problem
is size and the graph arm needs a reduction step before E-001. If it does
not, the problem is composition, context reduction buys nothing, and the
multi-hop stratum gets its limit published instead. A third branch exists
for both being true, written down specifically so a mixed result cannot be
read as whichever half suits the day.

Two things I did differently because of what E-002 cost.

**Both splits exist before the first paid call.** Development and
confirmatory, drawn now, from the complement of E-002's subset, so nothing
that produced an E-002 number can be reused. That is the whole of the
process lesson from yesterday, applied rather than promised.

**The reduction rule uses the gold answer, and I registered that as a
limit.** It guarantees the answer is present, which is what makes the
comparison clean — and it means E-012b measures the generator's ceiling
given perfect retrieval, not end-to-end performance. No figure from it may
be quoted as a system score. It bounds what a perfect reranker could buy,
and that is a genuinely useful thing to know before deciding to build one.

One honest constraint on all of it: the budget never fires on the Magic
corpus — `dropped` is 0 across every E-007 question and every E-008 probe,
where subgraphs run around 8 evidence items. So if E-012 says "size", the
consequence is a design constraint on E-001 taken on calibration evidence,
not the repair of an observed defect in Magic. That distinction goes
wherever the result goes, because a fix justified by a movie KG and applied
to a rules corpus is exactly the kind of transfer this project keeps saying
it does not do.

## 2026-09-03 — E-002 closes as a FAIL, and the falsified prediction is the valuable part

The floor is 0.90 at 1-hop. A3 came in at **0.884** [0.853, 0.909]. The
round budget is spent, there is no third round, and the calibration is
reported as a divergence. Writing that down plainly matters more than
anything else in this entry: the headline of Phase 6's first act is a
threshold this project set for itself and did not clear.

A3 is not a better prompt. Paired against A2 on the same 1500 questions:
p = 0.405, 0.885, 0.044 across the three hops, and with a Bonferroni
correction for the family none of them is significant — including the 3-hop
regression that would otherwise read as A3 being worse. A3 was run for
compliance, not for score, and that is exactly what it delivered: refusals
428 → 377, fabricated citations 38 → 20, accuracy unchanged. The dev
comparison predicted this, which is the first time this phase a prediction
made *before* a paid run came true.

**The number I refuse to use.** Ten of the 58 one-hop misses are the model
answering correctly about a MetaQA node that merges two same-titled films.
Credit them and the score reads 0.904 — over the floor. That adjustment was
invented after seeing the verdict, and letting it overturn a pre-registered
threshold would make every threshold in this repo decorative. It goes in the
entry as a caveat on the benchmark and changes nothing. If I had wanted a
ceiling correction to count, the place to define it was before the run.

**What actually pays for the four days is a prediction I got wrong.** I
registered that grounded generation would not be the bottleneck at any hop —
that where the answer entity is present in the subgraph, it gets selected.
Conditional on the answer being in the evidence the model received: 0.884 at
1-hop, 0.677 at 2-hop, **0.339 at 3-hop**. At three hops the model uses one
third of what retrieval hands it. The registration itself said that if this
prediction failed, the finding would be about generation, would transfer
straight to the MTG side, and would be the main reason the calibration
earned its budget. It failed. It transfers.

So Phase 6's first act ends with two things pointing at the same place: the
budget policy deletes the frontier layer on large neighbourhoods, and the
generator then uses a third of what survives. Both are about long multi-hop
contexts, and `interaction_multihop` is 30 of the 57 evaluation questions.
That is not a reason to stop — it is the pre-registration for the next
experiment, and E-012 is written before anything is changed.

I also want the process error on the record, because it is the one worth not
repeating: **I did not build a development split before the first paid run.**
The two-round budget I imposed afterwards is a patch over that, and a worse
instrument than the structure it replaced. With a dev split from the start,
iteration would have been unlimited where it is free and the frozen subset
would have been touched exactly once. Instead it was scored three times, and
the disclosure that the diagnosis read test-set failures is the price.

## 2026-09-02 — The floor failed at 0.786, and the defect was a section I deleted

The registered rule fired exactly as written: 1-hop Hits@1 came in at 0.786
against a floor of 0.90, and below the floor nothing gets written up — the
divergence is chased, harness first. Chased, and it was the harness. Mine.

The shape gave it away before the cause did. The misses are not wrong
answers, they are **refusals**: 90 of 107 at 1-hop, where the shown-reach
ceiling is 1.000 and the answer was in the context every single time. At
2-hop, 452 of 463. Zero fabricated citations in a thousand answers, which
says the grounding half of the contract was working perfectly while the
answering half never engaged.

The model's own refusals name the cause — *"I do not have information on
other films written by Randall Wallace"*. It resolves the first hop and then
declares the second missing without looking for it. `answerer.SYSTEM` has
four sections and the one I dropped when stripping the Magic vocabulary is
the one that says to walk the evidence step by step. I then asked for the
entity "and nothing else", which removes the room to compose at all. I had
registered that prompt as "the grounding contract with the Magic removed";
it was the contract with a section removed, and the registry sentence was
wrong before the run was.

Two things I want on the record about how this was repaired, because both
are places where a project like this quietly cheats.

**The iteration does not touch the registered questions.** Prompt rounds run
on a draw from the complement of the frozen subset — 500 of 9,947 are
spoken for at 1-hop, so the complement is enormous and free. Iterating on
the subset would make the final number a report of its own tuning. Phase 5
made the same split for the same reason, and I nearly skipped it here
because the fix felt too obviously correct to need a control.

**The budget is fixed now, at two rounds, not when I see the result.** A2 is
round one. If it does not clear the floor, the number stands as measured and
gets written up as a divergence. A repair budget decided after seeing
whether the repair worked is not a budget.

A2 restores the walk-the-steps section and keeps the output scoreable with a
final `ANSWER:` line. On 40 development questions, paired: A1 got 3 with 36
refusals, A2 got 23 with 12. Exact McNemar, 21 improved against 1 regressed,
p = 0.00001. The diagnosis holds.

What I take from the whole day: the calibration's value has not been a
single number, it has been four defects surfaced in machinery that the MTG
evaluation depends on — a silent evidence-dropping renderer, an inherited
constant, a missing retry, and now a grounding prompt missing a quarter of
its contract. Every one of them would have been invisible on the Magic side
until it produced a plausible wrong number.

## 2026-09-02 — The budget deletes the answer, and MetaQA found it before the golden set could

The calibration paid for itself before a single token was spent, and not in
the way the roadmap expected.

The MetaQA KB loaded — 43,234 entities, 133,582 relationships, the 1,159
duplicate lines in the release collapsing exactly as `read_kb`'s comment
said they would. Then the free retrieval pass, and a number I nearly
published: the traversal reaches the answer entity on 500 of 500 questions
at 1-hop and 2-hop, and 482 of 500 at 3-hop.

**That number was measured over the wrong set.** It asked whether the
*traversal* touched the answer. The model never sees the traversal; it sees
`subgraph.evidence`, after the per-kind cap and the token budget. Measured
where the model actually looks, 2-hop was **0.752**, not 1.000. I had built
a ceiling that flattered the system by a quarter of its questions.

Underneath that sat a plain violation of this project's own rule.
`DEFAULT_KIND_CAP = 25` was tuned on the Magic graph, where evidence has
five kinds and the cap stops a `flying` hub returning thousands of cards.
MetaQA evidence has one kind, so 25 per level meant 75 items total and the
6000-token budget never bound: `capped` fired on 100% of 3-hop questions and
`dropped` on none. Concepts transfer, constants do not — and I had carried a
constant across a corpus boundary without re-deriving it. Re-derived at 1000
by a criterion that never looks at the score: high enough that the budget is
what binds, which is what the cap was designed to allow. Sweeping cap values
against the reach number was available and refused.

**The re-derivation is not an improvement, and the correction matters more
than the number.** It lifts 2-hop shown-reach from 0.752 to 0.842 and
*drops* 3-hop from 0.564 to 0.448. I said "reach improved" before the 3-hop
pass finished; that was wrong, and the trade is the interesting part. At 25
items per level the subgraph never exceeded 75 items, so the token budget
never trimmed and the distance-3 layer survived **by accident**. Lifting the
cap lets the near layers fill the budget, and `enforce_budget` trims
farthest-first — deleting the frontier, which on a 3-hop question is where
the answer is.

I did not revert. Reverting because 3-hop scores better under the old value
is choosing a constant by its number, which is the thing I refused an hour
earlier when I refused to sweep caps. The accident is not a design.

**What is left is the actual finding, and I am not fixing it either.** At
2-hop the failure is size: `dropped` fires on 79 of 79 losses against 42 of
421 keeps, and losers carry a median 4,434 triples against 17. At 3-hop the
counters stop discriminating altogether and neighbourhood size inverts —
because the layer is gone on nearly every question. Measured: 226 of 500
3-hop questions have their answer reachable within 2 hops anyway, and 213 of
the 224 survivors are among them. Shown-reach 0.448 against a shallow
fraction of 0.452. **The system answers the 3-hop questions that are not
really 3-hop, plus eleven.**

Changing the trimming order would raise both numbers and empty the
experiment of meaning: E-002 calibrates the machinery that ships. So the
behaviour stays and gets published, and what to do about it is a decision
taken after the run, on this evidence.

**And it is not a movie-KG problem.** `interaction_multihop` is 30 of the 57
evaluation questions, and its answer is at depth by construction —
composition of two or more effects. A large Magic neighbourhood loses the
answer layer by the same mechanism, and the run would read as the central
hypothesis failing when the cause is a budget policy. That is the failure
E-002 existed to catch: found on a graph where extraction and linking cannot
be the explanation, before the 57 questions that are touched once.

One process error to write down, since the phase note is emphatic about the
harness being the first suspect: I left two 3-hop passes writing to the same
`.jsonl` concurrently, one under each cap. The console numbers were computed
in memory and are fine; the file was garbage. Killed and re-run to a clean
file rather than analysed as it stood.

## 2026-09-02 — The E-002 harness, and the frontier cap nobody would have counted

Writing the runner forced four choices the registration had not named, and
they are in the registry now rather than in the code alone. One of them is
worth the entry on its own.

**A 3-hop ball in a 135k-triple movie KG does not fit anywhere.** The
traversal has to bound its frontier, and I capped it at 400 entities per
level. That makes **three** ways this experiment can lose evidence —
`dropped` by the token budget, `capped` by the per-kind cap, and now
`truncated` by the frontier — and only the first two were instrumented. The
registered 3-hop prediction says the dominant failure is budget rather than
traversal, confirmable only against those counters. A truncation the counters
cannot see would have let that prediction be confirmed or refuted by
something nobody was measuring. So it is counted per question and reported
beside the other two.

Also decided, and only obvious in hindsight: the frozen subset holds
**question ids only**. MetaQA is somebody else's data under somebody else's
licence, and the project already refuses to redistribute RulesGuru's text
for the same reason. The text and answers are read from the local release at
run time, and loading refuses a release that does not hold every frozen id —
a subset drawn from a different release would score a different sample while
looking identical.

The last piece is a prompt. `metaqa.SYSTEM` is the shipped grounding
contract with every Magic sentence removed: evidence only, cite the handle,
refuse when it is not there. Keeping the shape and dropping the domain is
exactly what makes this a calibration of the spine rather than of the
pipeline — and it is the difference the registered claim already promised
to respect.

## 2026-09-02 — The band becomes context; the floor is the whole pass/fail

Decided the same day the defect was found, and still before the adapter has
been pointed at anything, which is the part that matters: this is a rule
written before a number exists, not a rule adjusted around one.

The band stops deciding. It is reported per hop, beside our figure, with the
gap stated — and nothing hangs on it, because five systems trained on MetaQA
cannot adjudicate a zero-shot traversal spine. What decides is the floor
that was already registered and never depended on the literature: Hits@1
≥ 0.90 on 1-hop, a single typed edge lookup against a KB with no ambiguity.
Below it, the divergence is a defect to chase before anything is written,
which is exactly what saved E-006's 0.067 from being believed.

Two readings keep their force as rules. Landing **above** the band at any
hop triggers a leakage check before the number is called a success —
beating a saturated band of trained systems, zero-shot, is far likelier to
be a leak than a result. Landing **below** it at 2 or 3 hops still owes the
written analysis, with the registered prediction intact that the dominant
3-hop failure is budget rather than traversal, confirmable only against the
`dropped` / `capped` counters.

The band itself is now computed over primary-sourced figures only: a system
enters it when its number was read from the paper that proposes it. The
criterion is provenance, which is the rule this project already applies to
every number it leans on, and it was fixed before our figure existed.

It has a consequence I would rather write down than have a reader find:
narrowing to primary sources takes 3-hop from [48.9, 100] to [91.4, 100],
which makes the registered prediction that 3-hop falls below the band easier
to confirm. The criterion was not chosen for that, but the effect is real,
so it is recorded in the amendment next to the prediction it flatters. The
prediction was never carrying weight — the floor is at 1-hop, and the floor
is the only thing that passes or fails.

## 2026-09-02 — The MetaQA band is extracted, and it turns out it cannot decide anything

E-002's decision rule opens with a step to be done before the adapter runs:
extract the published Hits@1 per hop from named KGQA papers, and let the
band be `[min, max]` across them. Done today, into the registry, with eight
systems, the table each figure was read from, and the full-KB setting
isolated so our complete-KB run is not compared against somebody's ablation.

Two things came out of it that were not the number.

**Chasing the primary source paid for itself on the first try.** A first
reading had PullNet's 2-hop at 92.4. The primary table shows 92.4 is the
`50% KB + Text` column — the full-KB figure is 99.9. That single wrong cell
would have opened the 2-hop band eight points too low, for a reason that has
nothing to do with the benchmark. The house rule that says chase the primary
for any number the project leans on has now caught something the first time
it was applied.

**The band, defined as registered, is not falsifiable.** Three-hop comes out
`[48.9, 100]` — a 2016 memory network at the floor, saturation at the
ceiling. Anything we measure is "inside the band", so the registered
prediction that 3-hop lands *below* it cannot fail, and the three-way
verdict degenerates with it. The cause is not sloppy sourcing: every system
in the table is trained on MetaQA, and Saxena et al. describe the complete-KG
setting as "the easiest setting for QA" because the data is built so the
answer always exists in the KG with no missing link on the path. A zero-shot
traversal spine and a trained system are not the same kind of thing, and a
band across the trained ones cannot referee the untrained one.

I am not choosing the replacement rule while looking at a band I already
know embarrasses the design — the same reason the 85% judge threshold was
left alone on 2026-08-15. What is recorded today is the band, its
provenance, and the defect. What the band is allowed to decide is fixed
next, before any adapter runs, and the leading candidate is to let the
literature be context and let the decision rest on the floor that does not
depend on it: Hits@1 ≥ 0.90 on 1-hop, already registered, and a statement
about our machinery rather than about the benchmark.

Also corrected today, in the open: the registration called MetaQA "~43k
triples". That is the entity count — the KG is 135k triples over 43k
entities and nine relations. The figure had been used to size the isolation
risk, so the correction is recorded rather than edited in place, and the
argument it supported gets stronger, not weaker.

## 2026-09-02 — E-002's isolation was unbuildable as registered; it becomes a second instance

The E-002 entry requires MetaQA to load into a separate Neo4j database and
instructs the loader to refuse if the deployment cannot supply one. The
deployment cannot: `docker-compose.yml` runs `neo4j:5-community`, and
Community serves exactly one user database. `CREATE DATABASE` is Enterprise.
The registration was written against what the incident report demanded, not
against what the compose file could do, and nobody checked the two against
each other until today.

Found before the timebox started, which is the only reason this is a
decision and not an incident. Day 1 of a four-day timebox spent discovering
that the isolation clause is unimplementable is how a four-day timebox
becomes a nine-day one.

**The fix is a second instance, and it is stronger than what was
registered.** A `metaqa` compose profile brings up a second Neo4j on port
7688 with its own password and no volume. What matters is not the extra
isolation on the write path — it is that **the teardown stops being a
query**. E-008 did not go wrong on the load; it went wrong when a cleanup
`DELETE` matched three real CR rules. Here, teardown is destroying a
volume-less container, so no Cypher runs near the corpus at any point in the
experiment. The failure mode that produced the incident stops existing
rather than acquiring another guard. `verify-clean` changes with it: instead
of a count returning to its pre-load value, it reads as the container being
absent and the port refusing connections.

One guard is still worth having in code, because the cheapest way back into
the corpus is now a typo in `.env`: `metaqa_target()` refuses when the two
URIs resolve to the same server, compared case-insensitively and without a
trailing slash. A guard that only caught byte-identical strings would look
responsible and stop nothing.

Enterprise under its development licence was the other option, and it would
have satisfied the original wording literally. Rejected: it puts a licence
acceptance in front of `docker compose up` in a public portfolio repo, and
the wording is not worth that. The registry carries the amendment, dated
today, stating what changed and — more importantly — the list of what did
not, so the reader can see the scope of the edit rather than trusting that
it was small.

## 2026-08-15 — The golden set audits clean, and E-002 is registered against a claim it can actually support

Two things closed today before any Phase 6 code was written.

**The golden set needed no work.** Annotation coverage across all 77
questions is complete on `gold_entities`, `gold_path`, `hops`,
`vector_should` and `verified`; the only zero is `gold_cr_rules` on
`legality_1hop`, and yesterday's corpus-parity amendment already handles it.
What the audit bought is the knowledge that it is the **only** gap — no
other stratum has an undefined retrieval metric waiting to be discovered
during the evaluation run.

A scare on the way: 30 of the 77 rows carry no `answer` field. They are
exactly the 30 RulesGuru rows, whose text lives in a gitignored cache
because the Fan Content policy forbids committing it — the design working,
not a hole. Verified with the project's own function: **30 of 30 cached
questions still hash to their curated snapshot**, no upstream drift since
curation. (My first check reported 30 mismatches because I hashed the raw
cache file; `snapshot_sha256` is over the *resolved* content — id, question,
answer, card names — which is the right thing to hash, since RulesGuru
substitutes cards procedurally.) It is still an operational dependency
nobody had registered: the answer key for 39% of the benchmark is not in the
repo, so "reproducible from one command" includes a fetch step, and the
cache must be verified present and hash-matched **before** the evaluation
run rather than during it.

**E-002 was registered, and its objective narrowed on the way in.** The
roadmap says calibration proves "a maquinaria funciona". It cannot. What
ships is MTG-specific down to the bone: the linker resolves card names
against a Scryfall lexicon, the router branches on whether an entity seeds
the *rule* graph, and all nine templates are written in Card / Keyword /
Rule / Ruling / Format. Almost none of it can run on a movie KG. What
transfers is the generic spine — typed traversal from a seeded entity, the
subgraph budget, citable evidence serialization, grounded generation — and
that is what the entry now claims to measure. Registering the broad version
would have produced a number that reads as validating components MetaQA
never touches.

Two decisions inside it worth their own line. The DoD's *"faixas plausíveis
da literatura"* is the same undecidable phrase that broke the M2 ceiling and
showed up three more times yesterday, so it became a **procedure completed
before the run**: transcribe reported Hits@1 per hop from named, cited KGQA
papers into the entry first, take `[min, max]` as the band, and never write
a number from memory. Beside it, a floor that does not depend on anyone's
paper — MetaQA 1-hop is a single typed edge lookup, so below **0.90** the
spine is broken and the divergence is chased as a defect. And the timebox
cut rule is fixed now, before the clock starts: day 4 without a working
adapter cuts calibration to 1- and 2-hop; day 4 without a working load at
all drops MetaQA and reports it as an unmet deliverable.

The isolation clause is the E-008 incident paying rent. That experiment
loaded **9** fictional nodes, adopted a real keyword through `MERGE`, and
its teardown deleted three real CR rules. MetaQA is ~43,000 triples. It goes
into a separate database with prefixed labels, a created-equals-declared
assertion, and a verified teardown — not into a namespace inside the Magic
graph.

## 2026-08-15 — Four registrations red-teamed the day they were written, and eleven objections landed

The four Phase 6 entries — the E-001 configuration, E-009, E-010, E-011 —
were red-teamed before any of the code they describe exists and with nothing
measured. Eleven findings were blocking. About half were defects I had put
in that morning. Amending on the same day, before a run, is the one moment
when an amendment is free, and every change below is an **addition**: no
registered sentence was rewritten.

**The worst one was a hole in the word "protocol".** I pinned chunking,
embeddings, generator, budget and judge as shared across the three arms, and
called that parity. It governs *affordances*. The asymmetry lives in the
*source data*: all 20 `legality_1hop` questions carry an empty
`gold_cr_rules`, because "Is X legal in Modern?" is answered by Scryfall's
structured legality field and by **no document in CR + rulings + MTR**.
Fifteen of them are in the evaluation split — **26% of the 57**. As pinned,
the vector arm could not answer a quarter of the benchmark, the graph would
sweep the stratum, and the per-stratum table would have read "graph wins"
for a reason with nothing to do with graphs. That is the roadmap's own
*critical* credibility risk, and I built the door it came through. Fixed by
requiring that every fact any arm may cite is in every arm's index, and by
giving that stratum its own retrieval metric, since rule-number recall is
undefined where there are no gold rules.

**The second was mine and it was subtler.** E-009 removes a rule from a
subgraph — and `serialize()` appends "NOTICE: this context is incomplete …
Say so if the answer depends on what is missing" whenever anything was
dropped. The ablated arm would have been *told to hedge* and the control arm
would not. I would have measured whether the model obeys a string. And the
deployment case the experiment exists to explain — E-007's eight of nine
thin subgraphs answered — usually carries no NOTICE at all, so a clean pass
would have been published as "the system refuses when evidence is absent"
while the eight of nine stayed exactly as unexplained. Fixed with an
ablation invisible to the prompt and a third arm that replays the real thin
subgraphs.

**The third is the one I flagged myself yesterday and was right to
distrust.** E-011's per-label thresholds were constants I picked while
looking at the ceilings. One of them, 0.85 for claim support, sits above
0.818 — the lower bound of the ceiling it was meant to respect — so the
entry stated a principle and broke it one row later. And it never said
whether a threshold applies to a point estimate or to a bound, which at the
audit's size is the difference between 29 of 34 and 33 of 34. The M2
ambiguity, third occurrence. The threshold is now a **function** of the
ceiling — the agreement interval's lower bound must clear the ceiling
interval's lower bound — and the constants are withdrawn.

**And a correction to something I wrote confidently.** I argued that a judge
cannot agree with a human more often than the human agrees with themself.
That is a heuristic, not a bound: judge-vs-human is *inter*-rater and every
ceiling I borrowed is *intra*-rater, and this project's own
[annotation-methodology.md](annotation-methodology.md) names that exact
confusion as a common slip. A judge that shares the first pass's bias
exceeds it comfortably. The ceilings are now published as a reference band,
each labelled with the sample and the elapsed days it came from.

The rest, briefly: `hedged` had no side in E-009's refusal rate and my own
prediction said it would dominate; E-010's prediction was `1/k < 1` and could
not fail; E-010's blinding was defeated by `via template: path` on every
graph item; arm C's TF-IDF text half endangers **C vs A**, the README figure,
not just C vs B, so C now uses arm A's retriever with TF-IDF kept as an
ablation; the multi-hop dichotomy was a false dilemma when the reranker two
items above it already showed the flag-and-ablate pattern — and the parity
clause ran one way, granting iteration to A alone in an experiment about
path-shaped questions while arm B stays single-shot by construction.

One thing I want kept, because it is the pattern and not the incident: **the
phrase that broke the M2 ceiling appeared three more times in entries I
wrote after learning that lesson.** "Matches the predicted stratification",
"agreement ≥ 0.85", "refusal rate". Each looked decidable until someone
asked what it would return. Writing a criterion is not the same as writing a
criterion that can only return one answer, and I do not seem to be able to
tell the difference from the inside.

## 2026-08-15 — Phase 6 opens carrying three items, and one registered threshold I do not believe

Gate check on Phase 5 passed on code and failed on outcome, which was the
point of closing it that way. Carried into Phase 6 as explicit tasks rather
than as hopes: the experiment for the 8-of-9 answering on `insufficient`
subgraphs, a precision-side companion for E-001, and E-007d. The `as_of`
half of citable negative answers is **dropped**, not carried, and the reason
is measured rather than argued: **0 of the 20 `legality_1hop` questions asks
for a date.** All twenty are "Is X legal in Y?", answerable from `status`
alone, which already ships. `negative_temporal` turns out not to be about
temporal legality at all — it is negative *rule* answers ("indestructible
with toughness 0?" — no). The feature has no measurement that would exercise
it. Its code side is half a day; its data side is a scraper over B&R
announcement articles with no stable contract, inside a project whose whole
ingestion discipline is hash-verified idempotency and whose IP rules forbid
committing the article text. So it is dropped and the reason is published as
a result: **the edge answers whether a card is legal, not since when,
because the canonical source carries no dates and the golden set does not
ask.** If it is ever wanted, the honest order is inverted — author the
questions first, watch them survive curation, and only then go looking for a
source. Building the ingestion and then hunting for what it measures is how
dead features are made.

The thing worth writing down on the day the phase opens is a problem with
its own DoD, found by reading it against what Phase 5 just measured.

**"LLM-judge vs. human agreement ≥ 85%" is a threshold with no ceiling
under it.** Phase 5 measured this annotator against themself: 0.990 on the
claim label, 0.933 on support, **0.800 on subgraph sufficiency**, 0.815 on
ruling citation in Phase 3. A judge asked to reproduce a sufficiency-like
judgement cannot agree with the human more often than the human agrees with
themself, so on that kind of label 85% is above the instrument. On the claim
label, by contrast, 85% is far *below* the ceiling and a judge scraping past
it would be a bad judge passing an easy bar. One number cannot serve both.

I am not editing the threshold today, because a threshold rewritten while
staring at the ceiling that embarrasses it is worth nothing. What I am doing
is registering the problem before the judge exists, and committing to the
form of the fix: **agreement is reported per label type, each beside the
human ceiling for that same label**, and the pass/fail reading is fixed in
the registry before the judge is run. Whether 85% survives as the number is
a decision for that entry, taken before any judge output is seen.

**The 57 evaluation questions are touched once.** E-006's first run read
0.067 because of two harness bugs, and it was allowed to be re-run because
it was the development split. There is no second draw here. So Phase 6 gets
a dress rehearsal: the whole pipeline, both arms, the judge and the report
run end to end on the 20 development questions first, and the evaluation set
is only opened when that produces a report with no defect left to chase.

## 2026-08-15 — Phase 5 closes with its DoD failed on two of three items

Closing the phase rather than extending it until the checkboxes tick. The
audit ran, the rule was applied, and the rule says no on coverage and no on
honest refusal. Extending the phase to fix the number would be iterating
against the measurement that judges it — the iteration budget was fixed at
three rounds precisely so that this moment could not be negotiated.

What closes: `answerer.py`, `citations.py`, the audit harness, E-007,
E-007c, its M2 ceiling, E-008, and the Phase 5 section of
[evaluation.md](evaluation.md). Support is met against its control; over-
refusal is clear at zero.

What does not, and is carried rather than quietly dropped:

- **Citable negative answers, half delivered.** The mechanism exists —
  `legality` is an evidence kind and the `HAS_LEGALITY` edge renders as a
  path — but the roadmap's `as_of` does not, because Scryfall's bulk
  `legalities` is a current-state snapshot with no ban dates. Delivering it
  needs a B&R announcement source this project does not ingest. Scope not
  delivered, not a bug. The path also has no end-to-end measurement: every
  audited question came from RulesGuru, which asks about rules and not
  formats.
- **8 of 9 `insufficient` subgraphs answered.** No registered threshold
  covers it, the sufficiency instrument that produced it is the least
  reliable one measured (0.800), and both of that instrument's disagreements
  ran toward *more* subgraphs being unanswerable. It goes to Phase 6 as its
  own experiment: a subgraph that provably lacks the answer, where refusal
  is the correct behaviour.
- **A precision-side companion for E-001**, forced by E-006's re-run.

Phase 6 therefore opens carrying three items, and the tag ships on a phase
whose headline result is a failure with its causes decomposed. That is the
version worth shipping: a phase that reports 0.369 with a void, a ceiling
that splits its own registered rule, and eight unexplained answers is more
useful to whoever reads this repo than one that reports a number it tuned
until it passed.

## 2026-08-15 — E-006 re-run came back identical, and the metric is why

The three linking defects E-008 found landed after E-006 run 3 and after
E-007's answers were generated and scored. Phase 6 is about to quote reach
numbers, so I re-ran E-006 against the fixed linker rather than let Phase 4's
table stand on a system that no longer exists. Amendment registered first:
same design, same split, same decision rule, different system under test.

Every recall figure came back identical. 1–2 hop entity recall 1.000, all 20
resolved, `interaction_multihop` still 0.88/0.12. The predicted risk — that
rejecting face-only single-word matches would break a lookup that used to work
by accident — did not materialise.

The decision this forced is what to *do* with an unchanged number. The
temptation is to read it as "the defects did not matter". That reading is
wrong, and the reason is in the metric's definition: entity recall is
`|gold ∩ retrieved| / |gold|`, so an entity that should not be there cannot
lower it. Every defect fixed was additive — the `what` collision put a wrong
card into 23 of E-007's 42 subgraphs and removed nothing — so **E-006 reads
1.000 either way.** It was structurally incapable of detecting the bugs, and
an afternoon of E-008's evidence check found all three.

So the re-run's finding is not about the linker. It is that Phase 4's headline
measures half the question, and I only know that because a *different*
experiment, built to check something else, tripped over the other half.
Recorded as a Phase 6 gap: E-001 needs a precision-side companion, or the
comparison against the vector baseline is decided on which system retrieves
more, not which retrieves better. The companion is not designed yet, and
designing it after seeing E-001's numbers would not count.

## 2026-08-15 — The ceiling split the registered rule, and the split is what gets published

The M2 re-audit came back at **0.990 [0.969, 1.000]** on the claim label and
**0.933 [0.818, 1.000]** on support, blind, over 100 rows from 8 answers,
with the segmentation regenerated and identical to the frozen worksheet.

The registered rule says the support figure has no ceiling if the second pass
disagrees "at a rate comparable to the support gap being reported". That
sentence has no threshold, and I was reading it with the disagreement rate
already on screen — the exact position in which a threshold gets chosen to
suit. So neither reading was picked. Point estimates: disagreement 0.067
against a gap of 0.403, the ceiling holds comfortably. Each side's worst
bound: disagreement 0.182 against a gap of 0.161, the ceiling does not hold,
by 0.021. **Both go into the report.** The precedent is this project's own
handling of the ambiguous second DoD clause, where both readings happened to
agree; here they do not, and a split that is resolved by preference is not a
pre-registered result at all.

Two things this forced me to fix in the instrument before believing it. The
agreement rates were being computed with every row as its own cluster while
the figure they exist to bound resamples by question — a ceiling with a
narrower interval than its own measurement. Clustered by question the support
interval widens from [0.833, 1.000] to [0.818, 1.000], which is what tipped
the conservative reading. And the script never printed the registered branch
at all; it printed two numbers and left the rule to be applied by memory.

**Why the readings split is sample size, and that is a design fault, not a
result.** Only 30 of the 100 rows carried a support judgement in both passes,
because the re-audit was sized for label agreement and the support comparison
is whatever falls out of it. A ceiling sized for the figure it bounds would
sample *cited factual claims* directly. That is a change to the next
experiment, not a rerun of this one — re-drawing a ceiling sample after
seeing which way it fell is the same error in a different coat.

**Coverage stays void.** On the shared 100 rows the two passes read 0.210 and
0.200 exclusions against a 0.20 limit, and the temptation to read that as
"the void was a coin flip" is real. It is also not what a ceiling sample
measures: it measures the annotator, not the corpus. The full first pass says
0.2019 and the registered rule voided coverage on it. What the numbers do
license is a note for whoever sets the next threshold — 0.20 was tight enough
that one row in a hundred straddles it.

One more thing written down before it can be misquoted: the two support
disagreements ran in opposite directions, so the support rate on the shared
rows is **identical, 14/30, under both passes**. That is offsetting error.
It is not evidence that the instrument is exact, and the agreement rate of
0.933 is the honest statement of what it is.

## 2026-08-10 — A second-pass judgement landed on the reported worksheet, one row from flipping the verdict

`claims show --worksheet <m2>` printed a `set` command with no path in it,
so the first M2 judgement went at the **first pass** — the file the
reported figures were computed from. It flipped `rg-1015[0]` from
`non_factual` to `factual`, and that single row moves the audit's exclusion
rate from **0.2019 to 0.1995**: from void to not void, the exact threshold
this phase spent an entry refusing to cross deliberately.

**Git caught it. Nothing in the tool did.** `git status` showed the
worksheet modified, `git diff` named the row, and `git checkout` restored
it. That is the whole reason this is a near miss rather than a silently
corrected verdict, and it is not a control — it is luck plus the habit of
committing the labelled artefacts.

Two fixes, because the hint alone was already tried and did not survive a
refactor:

- **The printed command carries its target file** whenever it is not the
  default, in the claim view as in the sufficiency view.
- **A judged row is not overwritten by surprise.** `claims set` refuses a
  row that already carries a label unless `--relabel` says the change is
  deliberate, and it names the wrong-worksheet case in the message because
  that is what the mistake usually is. A batch containing one judged row is
  refused whole rather than partly applied.

The lesson I want kept: every guard in this harness protects the *ordering*
of judgements, and none protected the *destination* of one. A tool that
makes the right order awkward to break should make the wrong file awkward
to write to as well.

## 2026-08-10 — E-008 came back clean, and the clean result is the smaller claim

12 of 12 held-out probes followed the graph. Zero leaks, zero refusals,
zero retrieval misses, on all three constructs. The six development probes
were 6 of 6, so no iteration round was spent.

**The claim is the bound, not the absence.** Zero over 12 puts the
per-probe leak rate at most 0.25 by rule of three. Writing "the system does
not leak" would be claiming something 12 probes cannot support, and the
threat registered before the run says more: a fictional card contradicts
memory *starkly*, which is the easiest case for a grounded reader to
notice. The deployment condition is a real card the model half-remembers,
and that differs in exactly the dimension being measured.

**Both predictions failed, and one could not be scored at all.** Leakage
was predicted to happen, most on the contradiction construct; it did not
happen anywhere. The second prediction — where leakage would appear — is
conditional on leaks that never occurred, and is recorded as unscoreable
rather than quietly dropped.

**The interesting part is the tension with E-007.** E-007 found 8 of 9
`insufficient` subgraphs answered rather than refused, and I called that
the parametric-leak surface E-008 would test. E-008 says the model does not
override evidence that is *present*. Both are true, and they are not the
same question. Answering when the evidence is absent is a different
behaviour from contradicting evidence that is there, and E-008 measured the
second. So the 8-of-9 is still unexplained, and it needs an experiment
built for it: subgraphs that lack the answer, where the correct behaviour
is refusal and the failure is fluent invention.

## 2026-08-10 — E-008's teardown deleted three real CR rules. Restored, and the cause fixed

**Incident.** `run_e008.py load` created its fictional rules with
`MERGE (r:Rule {number: ...}) SET r.text = ..., r.fixture = 'e008'`. Rule
**702.184 is the real keyword *Station***. `MERGE` on an existing key does
not create — it *adopts*, so the fiction overwrote the text of 702.184 and
702.184a/b and stamped them as fixture nodes. `teardown` then did exactly
what it was written to do and deleted every node carrying that tag.

The arithmetic was in the output the whole time and I read past it: the
graph held 117,435 nodes before the load and 117,432 after the teardown —
three fewer than it started with, and eight relationships fewer.

**Repair.** The CR loader is idempotent by design (ADR and CLAUDE.md both
say so, for the quarterly-release case), and re-running `load_rules`
restored 702.184 *Station* with its subrules. The graph's rule set now
matches the CR file exactly in both directions: **3308 nodes, 3308 rules
in the file, zero drift either way.**

The repair also created **45 `Keyword` nodes with glossary definitions
that did not exist before**, because `MERGE_KEYWORD_DEFINITIONS` creates
what it cannot match. So the graph had been out of step with the parsed CR
before any of this, and I cannot attribute that gap after the fact.
Recorded rather than explained away — and it means the graph E-007 ran
against is not the graph standing now.

**Cause fixed, not symptom.** `load` now checks every fixture key against
the production graph and refuses with the list of collisions, and it
verifies that the number of nodes created equals the number the fixture
declares — a tagged node the load did not create is a real node awaiting
deletion. The fictional rules moved to 799.1, outside the CR's numbering.
Tests pin both, including the integration case that a pre-existing key
stops the load.

**What this cost, honestly.** Nothing measured. E-007's retrieval ran
before the load, E-008 had generated only its six development probes, and
the held-out set has not run. Had the order been different this would have
been a corrupted corpus underneath a reported number, which is the failure
mode this entry exists to make expensive to repeat.

## 2026-08-10 — E-008's evidence check found three linking defects before a token was spent

`run_e008.py verify` came back 11 of 18 probes with their fiction absent —
the entire fictional-ruling construct. The graph was correct: Lightning
Bolt was there and the injected ruling hung off it. The linker was not.

- **A face of a multi-face name outranked nothing.** `Lexicon.build`
  indexes "Fire // Ice" under the combined name *and* each face, in the
  same tables with equal standing, so *Lightning Bolt* came back
  **AMBIGUOUS** against a face of "Emeritus of Conflict // Lightning Bolt".
  A whole-name match now outranks a face match.
- **"what" resolved *Who // What // When // Where // Why*.** Single-word
  surfaces skip the capitalization gate, so any question containing the
  word pulled that card in. A single word that is only ever a face no
  longer resolves; the cost is a bare "Fire" for *Fire // Ice*, a missed
  card rather than a wrong one.
- **Keyword surfaces kept clause punctuation.** `Tidebind,` matched
  nothing. The card path had this trim; the keyword path never got it.

Only the query-time linker changed. The `faces` table is additive and the
ingestion linker does not read it, because its behaviour was measured in
E-003 and changing a measured component from underneath its result is how
a number stops meaning what it says.

**The uncomfortable part: 23 of E-007's 42 subgraphs carried the
interrogative card.** E-007 is **not** re-run and its numbers are not
replaced. The labels were made against those subgraphs, and the result
describes the system as it was measured. What this becomes is a threat to
validity with a count attached: irrelevant evidence occupied budget in
more than half the questions, and it plausibly inflated the
`claim_not_in_evidence` failures that dominate the support taxonomy. A
re-measurement is a new registered experiment, not a retroactive repair.

E-006 must be re-run against the fix before Phase 6 quotes its reach
numbers — the same check the earlier linking fixes got, where it came back
unchanged.

## 2026-08-10 — E-007 read: the DoD fails on coverage, and the real problem is elsewhere

The decision rule was applied as written; nothing was invented at reading
time.

**Clause 1 not met.** Coverage 0.369 = 121/328 against a threshold of 1.0,
with the three-round iteration budget spent. The registered branch for
that case says the audit runs anyway and the DoD is reported not met with
the measured figure, so that is what Phase 5 reports.

**Clause 2 met.** Support 0.488 [0.400, 0.583] against a shuffled-citation
control at 0.161 [0.065, 0.274]. The registered sentence is ambiguous
about which interval it means — the full support figure or the control's
own real arm — and it does not matter: 0.400 and 0.435 both clear 0.274.
Recorded rather than quietly resolved, because the next experiment should
fix the wording.

**Over-refusal zero, gate clear**, on 4 `sufficient` subgraphs, bounded at
0.75 by rule of three exactly as the thin-sample limitation predicted
before generation.

**The finding that matters is not in the DoD.** 8 of 9 `insufficient`
subgraphs were answered rather than refused. The registered rule puts a
threshold only on over-refusal, deliberately, so nothing here fails — and
a system answering 89% of the questions whose evidence its own annotator
judged absent is the parametric-leak surface E-008 exists to test. E-008
now has a rate to test against instead of a hypothesis.

**Two of five predictions were wrong.** `wrong_leaf` was predicted to be
the commonest support failure and came in at **zero of 62**;
`claim_not_in_evidence` is 45. That prediction was transferred from
E-003a's measurement of this annotator disagreeing with themself, and the
transfer failed: the model does not pick a neighbouring subrule, it cites
a real and topically plausible item that does not contain the sentence.
Concepts transfer, constants do not — and apparently error *shapes* do not
either. Refusal was also predicted to dominate on `partial` and did not:
16 answered against 3 refused.

## 2026-08-10 — Coverage voided by one row, and the row was not reclassified

The audit's 411 claim rows came back **83 `non_factual`, 328 `factual`**.
`83/411 = 0.2019` against a void at `0.20`, and `0.20 × 411 = 82.2` — the
figure is void by **eight tenths of one row**.

One reclassification clears it. That is the entire reason none was made.
The threshold was written before any answer existed precisely for the case
where honouring it costs something, and a rule honoured only at
comfortable margins is not a rule. The entry written two days into this
labelling pass — while the outcome was still open — said the annotator was
told the running rate and told not to let it move a label. That held.

**The diagnosis, offered as a diagnosis:** 47 of the 83 exclusions are
bare list markers produced by the registered segmenter; genuine exclusions
are 36, or 8.8% of rows. Without the artefact the rate would be nowhere
near the void. This is what the rule says it detects — coverage measuring
the segmentation rather than the answers — so the rule identified its own
target. It is not converted into a corrected coverage figure, because a
denominator recomputed after seeing the verdict is the thing being guarded
against, whatever justification is attached.

**What Phase 5 can and cannot say.** Coverage is unreadable this run, so
the DoD's first clause has no reading; the second clause is still read
against the shuffled-citation control, and the over-refusal gate is
unaffected — it rests on the frozen sufficiency labels and no claim label
touches it. E-007d is the registered path to a readable coverage number,
and it was registered mid-labelling, before this outcome existed, with its
reading pre-committed and an explicit statement that its number does not
retroactively become E-007's.

## 2026-08-10 — The exclusion rate may void coverage, and the segmenter is not being touched

Recorded **mid-labelling, before the outcome is known**, which is the only
time this entry is worth anything.

Numbered-list answers produce worksheet rows that are a bare list marker —
`2.` and nothing else. The registered segmenter splits on punctuation +
whitespace + a sentence opener, and `2. Merieke activates…` matches that
as exactly as `Ends here. Next one` does. It is the instrument behaving as
registered, not a defect discovered late.

    bare list-marker rows          49 of 411 (11.9%), 12 answers, up to 6 in one
    labelled so far                210 rows: 150 factual, 60 non_factual
    of those exclusions            38 are bare markers, 22 are genuine (10.5%)
    exclusion rate so far          0.286, against a void at 0.20

Where it lands is open — 11 markers remain among 201 unlabelled rows, so
the floor is 0.173 and the realistic projection is near 0.22.

**No repair.** Re-segmenting now would rebuild the worksheet after seeing
that its exclusion rate is uncomfortable, which is the move the frozen
hash exists to make visible. The annotator was told the number and told
plainly not to let it move a label: a bare `2.` is `non_factual` under the
guide's closed list, and it stays that way whether or not the consequence
is a void figure.

If the rate clears 0.20, Phase 5 reports **coverage void** and reports why:
a decomposition into artefact exclusions and genuine ones, offered as a
diagnosis and never as a repaired coverage figure. The void rule says the
metric would be measuring the segmentation rather than the answers, and
that is precisely what 38 bare markers in 60 exclusions would mean. The
rule firing correctly is not the rule failing.

## 2026-08-10 — Development-side peek: coverage 0.361, and no decision is taken here

118 claim rows labelled on the 10 development answers under `p5-a3`.
Recorded because a peek that is not written down is a peek that can be
denied later.

    coverage   0.361 = 35/97 factual claims, 9 answering clusters
    exclusions 21/118 = 0.178 (void above 0.20)
    support    0.429 [0.265, 0.595], 9 clusters, 35 cited claims
    failures   claim_not_in_evidence 15, right_evidence_wrong_reading 4,
               unrelated_evidence 1, wrong_leaf 0, evidence_absent 0
    refusals   over-refusal 0, unsupported answering 0, correct refusal 2

**No decision is taken here.** This is the split the prompt was written
against; it carries no threshold, and the DoD is read on the audit side
only. Three things are worth writing down anyway:

- **The three registered prompt rounds are spent.** Coverage at 0.361
  against a threshold of 1.0 means the first DoD clause is very likely to
  fail on the audit. A fourth round chosen *now*, after seeing that number,
  would be the registry's whole purpose defeated — the budget was three,
  and the audit runs on `p5-a3`.
- **The prediction about where support fails looks wrong.** E-007 predicted
  `wrong_leaf` — right rule family, wrong subrule — would dominate. On dev
  it is **zero of 20**, and `claim_not_in_evidence` is 15: the model cites a
  real, relevant-looking item that simply does not contain the sentence.
  Not scored here; predictions are scored on the audit.
- **Exclusions came in at 0.178 against a void at 0.20.** Some of that is
  segmentation artefact — answers written as numbered lists produce rows
  like `3.` — and the guide forbids re-splitting them. If the audit clears
  0.20 the coverage figure is void by a rule written before any of this
  existed, and that outcome is reported, not repaired.

One limitation is now visible and is going into the write-up rather than
into a fix: the claim unit is a **sentence**, and this model cites at the
end of a numbered bullet covering three or four sentences. Sentence-level
coverage counts those as uncited, which is what the unit was registered to
do. Whether a bullet-level unit measures the same thing is a question for a
successor experiment, not a redefinition of this one.

## 2026-08-10 — A card with no rulings was never in the subgraph; 32 labels reopened

*Guardian of the Guildpact* is linked correctly, exists in the graph, and
reached no subgraph at all. Every card traversal arrived at the node
through a relationship — rulings, keywords, legality — so a card with
none of those contributed nothing to a question that named it, **not even
its oracle text**, which is the evidence a rules question about that card
most needs. `card_core` now runs unconditionally for every resolved card
and is the only template emitting the card node; the duplicate emits on
`card_rulings`, `card_legality` and `card_interaction` were removed rather
than left to print the card twice. Cards reaching a subgraph across
E-007's pool: **164 → 195**. The residual gap is one card mentioned
several times in one question (264 traversals planned, 195 distinct
cards).

Evidence changed on **42 of 42** questions, so the sufficiency labels no
longer described the subgraphs they were frozen against. The decision:
reopen the **audit** side only — 32 labels — and keep the 10 development
labels as they are, marked `stale_labels`. Re-judging a question whose
generated answer the annotator has already read is precisely the
contamination E-007's ordering exists to prevent; for the development side
re-labelling would not merely be expensive, it would be invalid. So the
development labels stay, flagged, and the stronger evidence they now sit
on is a limitation carried into the write-up rather than a correction
applied after the fact. `sufficiency reopen` demands a written reason and
records it with the previous hash, because a frozen label that moves
without a reason in the file was never frozen.

**The re-label did not go the way I predicted.** I expected oracle text to
turn `partial` into `sufficient` on many questions. Over the 32:

| | `sufficient` | `partial` | `insufficient` |
|---|---|---|---|
| before the fix | 5 | 20 | 7 |
| after the fix | 4 | 19 | 9 |

21 of 32 unchanged; of the 11 that moved, 7 moved *away* from sufficiency.
So the evidence these questions are missing is rules and rulings, not card
text — the fix repaired a real hole without making the sample easier. Two
things are confounded here and I cannot separate them: the evidence
genuinely changed, and the annotator judged the same 32 questions twice.
An 11-of-32 disagreement is **not** an agreement measurement and is not
reported as one; E-007c still has to measure the ceiling on unchanged
evidence.

## 2026-08-10 — The contingency held, and I did not move it

Sufficiency labelled on all 42 before any answer existed. Audit side: **5
`sufficient`, 20 `partial`, 7 `insufficient`.**

The registered contingency does not fire — `sufficient` + `partial` is 25
against a floor of 12 — so generation proceeds. But the composition is worse
than the headline suggests, and the honest thing is to say so rather than
quietly re-cut the criterion:

**The only DoD-blocking gate now rests on 5 questions.** Over-refusal is
defined on `sufficient` alone, and zero over-refusals over 5 bounds the rate
at 3/5 = 0.60 by rule of three. Passing that gate will prove very little,
and the write-up has to say so instead of reporting "the system does not
over-refuse".

I wanted to change the criterion — to require some number of `sufficient`
specifically, now that I can see there are five. That is precisely the move
pre-registration exists to prevent: the floor was chosen before the labels
existed, it was met, and disliking the composition afterwards is not a
reason to re-cut it. The limitation goes in the record; the gate stays.

What *is* legitimate is measuring the instrument, and the project's own
default says to: `partial` absorbed 25 of 42 subgraphs, and a category that
takes the majority of a sample is the one most likely to be absorbing
uncertainty rather than describing it. **E-007c** is registered — a blind
re-label of 10 subgraphs, scored both exactly and collapsed to
answerable / not, since the collapsed version is what the refusal gates use.
It carries no decision rule and changes no frozen label. E-003a already
measured this annotator at 0.815 against themself; a label with no ceiling
is a label reported against a 1.0 that does not exist.

## 2026-08-10 — Three linking defects, found by prose the golden set never had

Reading the first sufficiency case turned up something wrong before a single
label was written. `rg-4825` came back `resolved` with 11 evidence items and
**one** card — yet the router had planned four card traversals. Across the 42
questions: **245 card entities planned, 51 reaching the subgraph**, and every
one of the 42 missing at least one card.

Three separate defects, each found by pulling the previous one apart:

1. **The router derived the query parameter from the surface text.** The
   tokenizer deliberately keeps commas and periods, because card names
   contain them (*Omnath, Locus of Creation*), so a mention written
   mid-sentence arrives as `New Way Forward,` and normalizes to
   `new way forward,` — a string matching no node. The linker had already
   resolved it correctly through the loose table; the router threw that
   resolution away and re-derived the name. `EntityRef` now carries the
   resolved card's own `normalized_name`, and the router uses it.
2. **A single-word name with clause punctuation did not resolve at all.**
   `humility,` is in no lookup table: not `exact`, not `loose` (multi-word
   only), not `single_word`. Multi-word names survived through `loose`;
   single-word names — Humility, Opalescence, Opt — simply failed, which
   from outside looks exactly like a card the corpus does not hold. The
   surface as written is now tried first, then once more with edge
   punctuation trimmed.
3. **"What" resolves to a card** — *Who // What // When // Where // Why*
   exists, and the capitalization gate cannot help because the capital is
   sentence-initial. Costs an empty traversal rather than wrong evidence,
   and goes to E-005 rather than being patched here.

Effect on E-007's pool, re-run before anything was frozen: outcomes went from
32 resolved / **10 no_match** to **42 resolved / 0 no_match**; cards in the
subgraph 51 -> 164; rulings 196 -> 657; median evidence 11.5 -> 30 items.
Every one of the ten "the graph has nothing for this" verdicts was the
punctuation bug.

**E-006 was re-run and does not move.** The corrected table is identical to
the published one — `interaction_multihop` 0.88 entity / 0.12 rule, 1–2 hop
entity recall 1.000, p95 0.40 s — so the Phase 4 figures stand as reported
and the tagged release needs no amendment. The reachability and
`eval_rule_search` measurements never touched the linker, so the phase's
"`interaction_multihop` is out of reach" conclusion is untouched too.

The lesson is about the sample, not the bug. **The defect could not be seen
from the golden set**, whose development questions are generated or authored
and name cards cleanly. It took RulesGuru prose — real sentences, with real
commas — to expose it. A measurement can be correct and still be blind, and
what made this visible was reading one case by hand before labelling it,
which is the only reason the E-007 dump is not now frozen around ten false
`no_match` verdicts.

## 2026-08-10 — The audit pool's hardest stratum was already spent

The first dry run of E-007's draw returned 23 new questions and **zero
`interaction_multihop`**. The registered filter — `complexity: Complicated`,
judge levels 0–2 — matched three questions, and the golden set already holds
all three. Counting properly: of the 30 RulesGuru questions in the golden
set, **22 are `interaction_multihop`**. The bucket is exhausted, not unlucky.

This is not a logistics problem, and the fix is not to sample around it.
`interaction_multihop` is where Phase 4 measured rule recall 0.12 — the only
stratum that will produce `insufficient` subgraphs, correct refusals, and any
chance of over-refusal. An audit without it measures citation behaviour on
the easy half and reports nothing about the half where grounding is actually
at risk. It is exactly the "an unstratified draw silently determines the
result" hole the red-team flagged, arriving as fact rather than risk.

The golden set left the answer in its own documentation: `golden-set.md`
records that the complexity-seeded stratum was **wrong** and left two strata
empty, so its 22 interaction questions came from human reclassification, not
from the `Complicated` filter. `STRATUM_PLAN` says the same in a comment —
complexity is a hint, the human confirms.

Decision: widen the filter on judge level and complexity, and assign the
stratum by hand from the question text — which E-007 already required.
`build_golden_pool.py` takes `--stratum`, `--complexity` and `--level`
rather than carrying them as constants, and prints the filter used with the
draw, because widening changes what the sample represents and that belongs
in the record instead of in an edited constant. Registered as an amendment
to E-007 before the draw is frozen and before a single answer exists.

Which axis to widen was measured, not assumed. Judge level is not it:
`Complicated` at levels 0–3 returned the same three questions and zero new.
Complexity is: `Intermediate` + `Complicated` at levels 0–2 returned 14 new
of 20.

The probes also corrected something I had wrong. The three `STRATUM_PLAN`
entries are **source filters, not strata** — `ids_v0.jsonl` holds no
`rulings_2hop` question at all, because the complexity-seeded stratum was
reclassified by hand during annotation. So the pool's stratum mix cannot be
known until the manual pass, and gets reported as achieved rather than
planned.

And a limitation worth writing down before it can be discovered
conveniently: `definition_1hop` and `legality_1hop` were generated from
Scryfall, not drawn from RulesGuru, so no filter here can produce them.
That is 35 of the golden set's 77 questions on which E-007 will say
nothing. It runs in the conservative direction — those are the easiest
questions, where coverage would be highest — so the figure is a floor, and
the write-up names the strata it covers instead of implying all of them.

If the widened draw cannot reach 40, the registered n changes and the
rule-of-three bound is recomputed from it. 3/30 = 0.10 is a property of the
sample size; reporting it after drawing 23 would be arithmetic theatre.

**Drawn the same day: 42.** Two passes — the default filters, then the
widened interaction source — giving 10 development and **32** audit
questions, so the bound is **3/32 = 0.094** and not the 0.10 the entry first
named. Nine of the 42 touch a card name the golden set also uses; recorded
with the sample, not dropped, because a second question about Blood Moon is
not the same question.

One ordering consequence I had wrong when I wrote the command list: the
hand reclassification has to happen **before** the 10/32 split, not after.
The split draws proportionally by stratum, so splitting on seeded labels
would be stratified in name only — and if the true `interaction_multihop`
questions landed mostly on the development side, the audit would lose the
stratum this pool was redrawn to recover. The first worksheet row makes the
point on its own: `rg-4825` came seeded as `keyword_rule_2hop` and is a
chain of two *New Way Forward* redirecting a *Ral's Outburst*.

The pass is cheap by design — **one field**, the stratum. E-007 measures
citation coverage and support, not retrieval recall, so it needs no
`gold_path`, no `gold_cr_rules`, no `vector_should`. The worksheet carries
question text and therefore lives under `data/interim/` (gitignored); only
`id -> stratum` goes back to the committed pool.

**Classified the same day, and the result is itself a finding.**
`interaction_multihop` 26, `negative_temporal` 15, `keyword_rule_2hop` 1,
`rulings_2hop` 0 — with **31 of the 42 labels changed** from the seeded
value. RulesGuru `complexity` is not a weak signal for traversal depth; it
is noise, demonstrated independently for the second time after Phase 1.

`rulings_2hop` came back empty again, exactly as in the golden set. Two
independent annotation passes now agree that judge questions are not
answered by "a card's official ruling citing a rule" — the same conclusion
ADR-006 reached from the corpus side when it cut `CITES_RULE` back to
explicit citations. Worth naming as a replication: the decision was made on
corpus evidence, and question-side evidence arrived later and agreed.

The uncomfortable consequence, faced before generating rather than after:
41 of the 42 questions sit in the two strata where Phase 4 measured
retrieval weakest. Most subgraphs will be labelled `insufficient`, which is
what this pool was redrawn to produce — but it also means coverage and
support will rest on however few questions can actually be answered, with a
real risk of fewer than 10 clusters. So the contingency is registered now,
with a number attached: if `sufficient` + `partial` lands below 12 on the 32
audit questions, the pool is topped up before any answer is generated.
Discovering that after generating would leave only bad options, and picking
the threshold after seeing the count is how a contingency becomes a
rationalisation.

## 2026-08-10 — Phase 5 opened; the audit sample comes from outside the golden set

Phase 4 closed with every deliverable present and no carry-over. The one
deferral — fuzzy and embedding linking — is recorded below with its trigger,
not left implicit.

Phase 5's DoD asks for "a sample of **30 answers** audited against the
RulesGuru answer key", and that collides with the split Phase 4 froze. The
golden set holds 77 questions, 30 of them from RulesGuru, split 20
development / 57 evaluation. Those 30 straddle both sides, so auditing 30
answers against the RulesGuru key necessarily spends evaluation questions
that E-001 has not run on yet — and the development split is both too small
(20) and already seen by Phase 4's iteration.

Decision: **draw a fresh pool of 30 RulesGuru questions that never entered
the golden set**, disjoint from both splits. `build_golden_pool.py` already
pulls and appends unseen ids under the licence posture the golden set uses
(ids versioned, text cached and gitignored). This keeps the DoD literal —
30 answers, RulesGuru key — at the cost of one fetch, and it is the cheaper
option by a wide margin: the alternative spends a split that exists exactly
once.

Registered before any code: **E-007** (citation coverage and support) and
**E-008** (parametric leakage, measured with fictional cards in a disposable
namespace).

E-007 carries one scoring rule that had to be settled before the first
answer is generated, because getting it wrong would corrupt the whole
phase: **a refusal counts as correct when the subgraph lacks the
evidence.** Phase 4 measured `interaction_multihop` rule recall at 0.12, so
for those questions there is nothing to answer from. An audit that scored
refusals as failures would push the prompt toward answering from parametric
knowledge — rewarding precisely the failure E-008 exists to detect.

**Both entries were red-teamed the same day, before any generation, and
both were rewritten.** The first versions would have passed while measuring
very little:

- **The audit had a degenerate route to a pass.** A refusal contains no
  factual claims, so 30 refusals give coverage 100% (0/0) and a DoD marked
  met. The refusal rule was right; the guard that has to accompany it was
  never written. Fixed by labelling subgraph **sufficiency before any answer
  is read** — the same ordering E-003a enforces in code — and by making
  non-zero *over-refusal* on a sufficient subgraph block the DoD regardless
  of coverage.
- **"Factual claim" was undefined**, and the person who segments is the
  person who writes the prompt. The denominator of the phase's only
  threshold was being chosen by the interested party. Fixed by mechanical
  segmentation frozen with a hash before any citation is re-attached, an
  exclusion rate reported beside coverage that voids it above 20%, and
  [claim-annotation-guide.md](claim-annotation-guide.md) putting connective
  and inferential sentences explicitly **inside** the denominator — which is
  exactly where the entry predicts round 1 will fail.
- **The roadmap DoD has two clauses and I had quoted one.** "citações
  sustentam a frase" was dropped on the grounds that no threshold for
  support was pre-registered. The reasoning about not inventing thresholds
  post hoc was right; the premise was false, since the clause *was*
  pre-registered in the same sentence. Fixed with a pre-committed *reading*
  rather than an invented number: support's interval must clear a
  shuffled-citation control, which is the only thing separating "the
  citations support the sentences" from "any citation looked plausible to
  this judge".
- **No iteration budget and no held-out split**, on the sample whose only
  job is to produce a verdict. Phase 3 had this discipline (3 documented
  rounds on a frozen subset) and Phase 5 dropped it. Now 40 drawn, 10 for
  prompt development, 30 touched exactly once.
- **No ceiling on a brand-new hand-made gold**, in a project whose own
  written default is score → ceiling → decomposition. E-003a measured this
  annotator at 0.815 against themself, on the same wrong-leaf axis E-007
  predicts as its commonest failure. A blind re-audit of 8 of the 30 is now
  registered.

Two more that would have cost real work: nothing pinned the model,
temperature or prompt version — the exact omission that already retired
three Phase 3 iterations — and E-008 never verified that the fictional
evidence actually reached the model, so a *retrieval* miss would have been
scored as a leak and answered with prompt changes.

The generalizable part: **the red-team pass is worth most before the sample
is drawn, not before the run.** Four of the fixes changed what gets drawn
and what gets labelled first, and none of them would have been available
once the answers existed.

## 2026-08-10 — The close audit found a promise the code was not keeping

Walking the Phase 4 deliverable checklist to close the phase turned up a
gap that no test could have found, because nothing was ever asserted about
it: the roadmap, [ADR-005](adr/adr-005-templates-first-text2cypher-second.md)
and `CLAUDE.md` all promise "syntax check via **EXPLAIN** before
execution", and `text2cypher.py` shipped without it. String checks,
citable-column checks and a read transaction — but nothing that asks the
server whether the Cypher is valid at all.

Decision: implement it before the PR rather than carry it, because the
missing layer is the one that turns *invalid Cypher* into a named refusal
instead of an exception. Every other failure in this stack has a name; this
one crashed.

Implementing it exposed a second defect that had been latent since the
module was written. The system prompt instructed the model to **use
parameters** for values, and `evidence()` executes with an empty parameter
map — so a model that obeyed produced `$name` with nothing to bind it, and
the driver's `ParameterMissing` propagated out of retrieval. The tests
never caught it because every fake generator in the suite wrote literals.
Three changes: `unbound_parameter` is now a validation refusal, the prompt
asks for literals and says why nothing binds a parameter here, and both the
plan and the execution are guarded so any server error becomes
`explain:<Reason>` / `execution:<Reason>`.

The generalizable part is the one worth keeping: **the deliverable audit is
a test the test suite cannot run.** A promise made in an ADR and not kept in
code produces no failing assertion — only a reader comparing the two finds
it, and only if the close ritual forces the comparison.

## 2026-08-10 — Fuzzy and embedding linking deferred: nothing is failing

The Phase 4 deliverable specified query-time linking as *exact → fuzzy →
embedding*, covering nicknames like "Bolt". What shipped is exact +
normalized + a capitalization gate; `Lexicon.build` accepts an alias table
but no alias source is loaded, and there is no edit-distance or embedding
stage.

Deferred rather than built, on evidence: E-006's 1–2 hop entity recall is
**1.000** on the 20 development questions without any of those layers, so
there is no measured failure for them to fix. Adding a retrieval layer that
nothing is asking for is the same mistake this phase already inherited from
`crossref.py` — a component with no caller is a component nobody measured.

What this leaves genuinely untested is nicknames: the development split
contains none, so "Bolt" is not known to work or known to fail. Recorded as
a limitation of the measurement, not as a passing result. The trigger for
building the layer is a question that names a card the exact path misses —
Phase 6's evaluation split may supply one, and if it does, the layer gets
built against a real failure instead of an anticipated one.

## 2026-08-09 — Six percent of card names were ambiguous, and none of it was ambiguity

One development question came back `AMBIGUOUS`: *Doubling Season*
resolved to two `oracle_id`s. Chasing it found the general case —
**2,196 of 36,268 multi-word card names resolve to more than one id**, and
the cause is not language.

- **2,116 are `art_series` prints.** Collectible art cards are named
  `"X // X"`, and both faces normalize onto the real card's name.
- **80 are tokens**, which share a name with the card that makes them.

Neither is a rules entity. Left in, six percent of card names come back as
"I cannot confirm what this names" and the question containing them is
refused — a linking policy behaving exactly as designed, on data that
should never have reached it.

Filtering those layouts out drops collisions to **25 of 33,448** and lifts
E-006's 1–2 hop entity recall from 0.967 to **1.000**, with
`keyword_rule_2hop` going 0.67 → 1.00 and the last ambiguous question
disappearing. All 20 development questions now resolve.

The filtering lives in a new `build_card_lexicon` at the retrieval call
site, **not** inside `Lexicon.build`. That constructor is what the Phase 3
ingestion linker used and what E-003 measured; changing a measured
component from underneath its published result is how a number quietly
stops meaning what it says.

Which raises the uncomfortable part, recorded rather than acted on: the
ingestion linker used the **unfiltered** lexicon, so those same collisions
would have pushed real multi-word card names into the pending-homonym path
and on to LLM disambiguation. That is a plausible contributor to E-003's
multiword linking F1 of 0.760 against a predicted 0.95. It is not a
correction — E-003's split is spent and its figure stands as reported — and
it goes to E-005 as a hypothesis with a fresh sample. The temptation to
re-run Phase 3 "now that we know" is precisely what the spent-split rule
exists to refuse.

## 2026-08-09 — E-006 came back at 0.067, and the prediction said why

The Phase 4 DoD's entity-recall criterion, registered as E-006 before the
first run, carried an instruction with it: *if entity recall on the 1–2
hop strata comes back low, suspect the harness before the templates.*

It came back at **0.067** against a 0.9 floor. Two harness bugs, both
invisible to review and both caught only because that sentence existed:

1. **The router passed the wrong casing.** `Keyword.display_name` is
   "Trample"; the graph keys on the normalized `name`, "trample". Every
   `definition_1hop` question returned `NO_MATCH` — a traversal that runs
   perfectly and matches nothing.
2. **Legality was never wired.** The router emitted `card_keyword_rules`
   and `card_rulings` for a card and never `card_legality`, and no
   traversal emitted the *card itself* as evidence. So `legality_1hop`
   scored 0 on questions the graph answers with a single typed edge.

After fixing both: **0.967, PASS.** `definition_1hop` and `legality_1hop`
at 1.00, 19 of 20 questions resolved, 1 ambiguous, **none silent**,
latency p95 0.57 s against the 2 s criterion.

Recording the 0.067 rather than only the 0.967 is the point. It belongs to
a broken harness, and a reader who sees only the passing number learns
nothing about how close the phase came to reporting a false failure of
the *templates*.

A third fix came out of the same run and is a design decision, not a bug:
a question naming a format ("is this legal in Modern?") no longer routes
to text retrieval when its card has no keywords. Legality is answered
completely by one typed edge; treating the missing rule-graph seed as a
gap would have bolted eight lexical rule hits onto the answer and called
them evidence.

And the number that did not move: `interaction_multihop` rule recall
**0.06**. Three independent methods now agree — `reachability.py` on the
graph, `eval_rule_search.py` on the text, and E-006 end to end. That
convergence is the Phase 4 finding, not a defect still to be fixed.

## 2026-08-09 — Valid Cypher that kills the server, found by running it

Seven of the eight template traversals ran against the loaded graph on
the first try. The eighth, `card_interaction`, returned
`Neo.TransientError.General.MemoryPoolOutOfMemoryError`.

Isolating clause by clause put it on one line:

```
OPTIONAL MATCH (a)-[:HAS_KEYWORD]->(k:Keyword)<-[:HAS_KEYWORD]-(b)
```

The surprise is that it fails **regardless of how many keywords the two
cards have** — *Humility* and *Opalescence* have none between them, and it
still exhausts the pool. The planner expands through the `Keyword` hub,
where `flying` alone carries thousands of edges. And `$limit` cannot save
it: the blowup happens before aggregation, so the bound is applied to a
result set that was never produced.

The fix stages each `OPTIONAL MATCH` behind a `WITH ... collect(...)` and
replaces the two-sided pattern with an intersection of the two keyword
sets. Both pairs now return in ~0.5–0.7 s, and the full set of eight runs
between 9 ms and 685 ms, comfortably inside the phase's 2 s p95 criterion.

This is the roadmap's registered risk — "interaction subgraphs explode
(keywords and rules that are very connected)" — arriving exactly where it
was predicted. What is worth recording is that **no amount of reading
would have caught it.** The query is valid, its bound is present, and the
review-level invariants the unit tests enforce (read-only, `$limit`,
bounded expansion, declared parameters) all passed on the version that
killed the server. Only execution against a real planner on real
cardinalities said otherwise, which is the argument for integration
fixtures rather than a mocked driver.

Two smaller findings from the same run, both now pinned by tests:
`collect(DISTINCT {number: sub.number})` over a missed `OPTIONAL MATCH`
yields `[{number: null}]` rather than `[]`, which would have become
citations reading `rule:None`; and the row-to-evidence mapping is now
declared beside each query as `Emit` entries, with a test asserting every
column it names is one the query returns — so a `RETURN` edited without
its mapping fails loudly instead of quietly emitting nothing.

## 2026-08-09 — The split caught me within the hour, and the dev data says no

Building ADR-007's text-retrieval half, three golden-set questions were
inspected to see what lexical search over CR text returns. The
*Humility* × *Opalescence* one came back with 604.3 and 710.2 — nothing
about layers — and the diagnosis looked clean: `cite_search`'s stopword
list, tuned for ruling→rule matching, strips "ability"/"abilities", which
is the single most diagnostic term for layer 6. Rebuilding the index
without those stopwords lifted 613.4b — an actual gold rule — into the
top ten.

**That question is in the frozen evaluation set.** Changing a retrieval
parameter because it fixes an evaluation question is fitting the
retriever to the test, which is precisely what the split drawn this
morning exists to prevent. It caught the case within the hour of being
created, which is the argument for drawing splits before writing code
rather than after.

Recorded for the record, since inspecting is not free: the retrieval
output of `hand-humility-opalescence`, `hand-deathtouch-trample` and one
targeting question was seen on 2026-08-09. **No parameter was changed as
a result.** The hypothesis was re-derived on the development split
instead.

**And the dev split refused it.** Over the 15 dev questions carrying gold
rules, the lighter stopword list changes nothing at all — 8 of 15 with it
and 8 of 15 without, identical per stratum. What *does* help is expanding
the query with the oracle text of the cards the question names: 6 of 15 →
**8 of 15**, the gain landing on `keyword_rule_2hop` (0/1 → 1/1) and
`interaction_multihop` (1/8 → 2/8). Only the measured change ships.

**The finding that matters is the one that went the wrong way.**
`interaction_multihop` reaches a gold rule in **2 of 8** dev questions
even with expansions. ADR-007 assumed text retrieval would cover the
stratum the graph cannot seed; on this evidence it does not. Reaching the
layer system means knowing that two continuous effects must be ordered,
and that is not a vocabulary overlap with anything either card says — the
same wall, from the other side.

The response is to report it, not to keep adding mechanisms until
something scores. Embeddings are the obvious next lever and Phase 3
already dropped that stage once; adding it now, against a stratum whose
difficulty is now measured twice, would be reaching for a result rather
than testing a hypothesis. It goes to the backlog with its own
registration.

## 2026-08-09 — Hybrid retrieval adopted, and the golden set split before any template

Option 2 taken (ADR-007): the graph resolves entities and answers the
structural strata, text retrieval reaches CR rules where the graph cannot
seed. Forced by the reachability measurement rather than chosen — option 1
has no material for the 15 `interaction_multihop` questions whose cards
carry no keyword, and option 3 is the inference E-003 measured at 0.125.

**The confound this creates is the part worth recording.** E-001 was
designed as graph vs. vector. A hybrid arm measured only against the
vector baseline could win entirely on its text component — which *is* the
Project 1 pipeline — and be presented as evidence about the graph. E-001
now runs three arms: vector (A), graph-only (B), hybrid (C). B vs A is
the registered prediction and is not renegotiated; C vs B is what the
text adds. Without the third arm the hybrid's number would be
uninterpretable, and the temptation would be to report it anyway.

**The golden set is split before a single traversal exists.** Twenty
questions (seed `20260809`, stratified) are frozen as the Phase 4
development subset; the other 57 are E-001's evaluation set. This was a
pre-existing hole in the roadmap — Phase 4 was to build templates against
the questions Phase 6 scores — and it is only cheap to fix before the
first template. `scripts/split_golden.py` refuses to redraw, because a
split that can be redrawn after the fact is not a split.

Cost accepted and written down: `keyword_rule_2hop` has 3 questions, so
the split leaves 1 dev and 2 evaluation, and no per-stratum claim about
it is reportable from either side. The alternative — leaving all 3 in
evaluation — would mean writing that stratum's template with nothing to
develop against, trading a reporting limitation for a contamination risk.
The limitation is the better trade.

`docs/hypothesis.md` was **not** edited. Its a-priori predictions stand;
a dated section records the reachability evidence and says plainly that
prediction 2 now looks unlikely for arm B. Recording evidence against a
prediction is not the same as editing the prediction, and the difference
is the whole point.

## 2026-08-09 — Measured the bridge instead of arguing it; implicit cross-refs dropped

Two Phase 4 decisions, one of them correcting me.

**Implicit CR cross-references are dropped**, not carried. `extraction/
crossref.py`, its schema and its gate support stay in the tree as
unwired code; nothing calls them and nothing will in Phase 4. The reason
is the one Phase 3 just paid for: an inferred edge is worth what its
measurement says, and measuring this one means another annotation round
against another hand-made gold. The phase that just spent XL effort
learning that the *first* inferred edge scored 0.125 is not the phase to
add a second on faith. If it returns, it returns with its own
pre-registration and its own gold.

**The reachability claim was asserted, not measured — and the
measurement changes the argument.** Closing Phase 3 I wrote that
`interaction_multihop`'s rules have "no deterministic edge from any
card", inferred from chapter families. That tested direct edges only. It
said nothing about multi-hop paths through `REFERENCES` and the CR tree,
which is exactly what a traversal would use. `scripts/reachability.py`
now measures it, seeding from each question's entities and expanding k
hops through the undirected union of cross-references and the tree — the
architecture's best case, deliberately.

| stratum | k=2 | k=4 | k=6 | median ball at k=6 | no seed |
|---|---|---|---|---|---|
| `definition_1hop` | **100%** | 100% | 100% | 2228 | 0/15 |
| `keyword_rule_2hop` | **100%** | 100% | 100% | 2544 | 0/3 |
| `interaction_multihop` | 10% | 21% | 38% | 1515 | **15/30** |
| `negative_temporal` | 13% | 33% | 47% | 2206 | 3/9 |

The conclusion survives, for a better reason than the one I gave. At k=2
the graph reaches **every** gold rule of the 1–2 hop strata inside ~200
rules — it is at ceiling there. On `interaction_multihop` it reaches 38%
only by k=6, and a k=6 ball holds 1515 of 3308 rules: reaching almost
half the document is not retrieval, it is loading the corpus.

The decisive column is the last one. **Fifteen of the thirty
`interaction_multihop` questions produce no seed at all** — 56 of the
golden set's gold entities are cards with no keyword abilities
(*Humility*, *Opalescence*). No traversal depth helps a card with no edge
into the rule graph, and no new deterministic bridge can be built for
them either: what connects *Humility* to the layer system is what its
text *means*, which is inference. That is the same inference E-003
measured at 0.125.

So option 1 (another deterministic bridge) has no material for half the
stratum, and option 3 (a re-registered inferred path) is the thing just
measured and rejected. Recorded before the choice, so the choice is
forced by the data rather than by preference.

## 2026-08-09 — Phase 4 opened with one decision blocking the first line of code

Gate check on Phase 3: every deliverable exists. One carry-over,
explicitly carried rather than dropped — implicit CR cross-references
(`extraction/crossref.py`) are built, schema'd and gated but never wired
into the pipeline. They enter Phase 4 as a task, or they get dropped with
a dated entry; not left ambiguous.

The phase does not start with `retrieval/templates.py`. It starts with
the architectural question Phase 3 left: with `CITES_RULE` reduced
(ADR-006), `interaction_multihop` needs 61 CR rules of which only 8 are
keyword rules, and nothing deterministic connects a card to the rest.
Two Phase 4 deliverables depend on the answer — the `carta→rulings→regras`
traversal in the ≥7 templates now reaches 25 of 77,999 rulings, and the
`interação carta×carta` traversal was to lean on shared rulings and
common rules.

Recorded so the choice is not made by accident while writing a template:
the options are another deterministic bridge, text retrieval for rules
with the graph supplying entity structure, or a re-registered inferred
path. The second reframes E-001 as a test of the *combination* rather
than of traversal alone, which changes what the project claims — it is a
legitimate answer, but not one to slide into unannounced.

Phase 4's Entity Recall criterion (≥0.9 on 1–2 hop questions) is a
measurement and gets registered in `experiments/registry.md` before it
runs, not after.

## 2026-08-09 — Phase 3 closed on a failed DoD, deliberately

Both Phase 3 thresholds failed: linking F1 0.634 against 0.90, citations
0.125 against 0.75. The roadmap allows the thresholds to be adjusted
"with justification in the ADR", and they were **not** adjusted. E-003
was pre-registered; moving a threshold after seeing the result is
adjusting the ruler, and the option existing in the roadmap does not make
it honest to use. The phase closes with the DoD marked as failed rather
than met.

What makes that defensible instead of merely disappointing is that the
two comfortable explanations were measured and excluded rather than
argued: the gold's ceiling (E-003a, 0.815) and the composition of the
disagreements (E-003b, 40/40 model error, bound ≤0.091 on anything else).
G3 then fired as registered and the schema was reduced (ADR-006).

Deliverable audit: everything in the roadmap's Phase 3 list exists except
two items carried forward rather than dropped. Implicit CR
cross-references (`extraction/crossref.py`) were built and gated but
never wired into the pipeline — no unmeasured LLM edge ever reached the
graph, which is the right outcome by accident rather than by design.
`notes/phase3-extraction.md` stops at 2026-07-20 and does not yet cover
the CR migration, the annotation-split run, the retired iterations, the
temperature defect, E-003a/E-003b, or the reduction; its Lessons Learned
and Failed Attempts are the author's to write.

Also found while writing ADR-006, and worth its own line: **ADR-003
already required that a cited rule number be present in its evidence
span.** The gate checked that only when the span happened to contain a
number, which made the requirement vacuous for exactly the inferred
citations it was meant to constrain. The written contract was right and
the implementation had drifted from it; E-003 measured the cost of the
drift. The reduction brings the code back in line with the ADR as much as
it narrows the schema.

## 2026-08-09 — Schema reduced: CITES_RULE now means "the ruling says so"

G3's registered consequence, executed. `(:Ruling)-[:CITES_RULE]->(:Rule)`
is produced deterministically by `extraction/explicit_citations.py` from
rule numbers the ruling states, and the gate rejects anything inferred as
`citation_not_explicit`. The LLM extractor still runs behind
`--llm-citations`, and its output no longer reaches the graph; the
permissive gate survives as `--legacy-citation-gate`, which the CLI
refuses to combine with `--load`.

The design choice worth recording is *where* the guarantee lives. It
would have been easier to stop calling the extractor. Putting the rule in
the gate instead means the property holds for any future caller,
including one that reintroduces an LLM path without reading this entry —
and E-003 is precisely the measurement of what the same guarantee is
worth when it lives in a prompt (F1 0.125).

Three things the reduction cost, measured rather than assumed:

1. **Coverage collapses, as designed.** 6 gated citation edges over the
   125 annotated rulings; overall citation F1 falls from 0.125 to
   **0.047**. Worth stating plainly because it is the opposite of score
   shopping: the mandated change makes the headline number worse, and the
   number is reported anyway.
2. **Precision is not 1.0 either — 0.667 on the `explicit` stratum**
   (tp=4 fp=2 fn=1). One of the two misses is the interesting one: a
   ruling writes "(704.5w)", and the August 2026 CR moved that
   state-based action to `704.5x` while reusing `704.5w` for something
   else. The gold migrated with the text; **the ruling is a historical
   document and cannot be migrated**. The number still resolves, so no
   existence check can catch it. This is the same silent displacement
   that moved `initiative` off 725.1, now showing up in the deterministic
   path — the reduced schema has its own version hazard, and it is not
   fixable by parsing harder.
3. **The free preview is now the whole citation product**, so the dry run
   writes its gated triples instead of requiring an API spend to obtain a
   file that costs nothing to compute.

## 2026-08-09 — The reduction does not break E-001's paths; something else might

Checked before Phase 4 rather than discovered in Phase 8. Two findings,
from the 77 golden-set rows:

**No gold path depends on the removed edge.** Zero of 77 `gold_path`
values name `CITES_RULE` or a `Ruling` node; the edges they do name are
`DEFINED_BY` (25) and `HAS_KEYWORD` (1). So the reduction breaks nothing
that was written down.

**But that is because most of them do not name edges at all.** Only
**23 of 77** `gold_path` values are written as traversals; the rest are
prose describing the semantic route. And the rule families they require
split sharply by stratum:

| stratum | gold rules | reachable from a card deterministically? |
|---|---|---|
| `definition_1hop` (15) | 15/15 keyword 701–702 | yes, `Keyword-[:DEFINED_BY]->Rule` |
| `keyword_rule_2hop` (3) | 4/4 keyword | yes |
| `legality_1hop` (20) | none — card properties | n/a |
| `interaction_multihop` (30) | 8 of 61 keyword; 33 in the 600s, 7 in the 500s, 6 in the 700s, 5 in the 300s | **no** |
| `negative_temporal` (9) | 3 of 15 keyword | mostly no |

`interaction_multihop` is the stratum carrying the central hypothesis —
the `vector_should: fail` questions — and roughly 87% of the CR rules it
needs sit in chapters with no deterministic edge from any card.
`CITES_RULE` was going to be that bridge. It is gone, and it was never
good enough to be it anyway (F1 0.125).

No decision taken here; the options are named so Phase 4 chooses
deliberately: find another deterministic bridge; accept that rules are
reached by text retrieval while the graph supplies entity structure —
which reframes E-001 as a test of the combination, not of traversal
alone; or reopen an inferred path with a different design and its own
pre-registration. The third is the one that must not happen quietly.

## 2026-08-09 — E-003b: 40/40 against the model, and why that needs a caveat

The 40 sampled disagreements all came back `gold_right`. The registered
prediction — `both_defensible` the largest bucket after `gold_right` —
is falsified, and cleanly: the bucket is empty. `gold_wrong` is also
empty, so no label changes and the 10% cap is nowhere near.

Two corrections to the reporting had to be made before the number could
be recorded, and both are the kind that would have been embarrassing to
leave in:

1. **The interval was a lie.** A percentile bootstrap resamples observed
   values; a sample with no variation resamples to itself and prints
   `[1.000, 1.000]`. That reads as certainty and means "not seen yet".
   `report` now detects unanimity and prints a rule-of-three bound
   instead — at most 0.091 for everything other than model error, over
   33 clusters. `metrics.rule_of_three_upper` holds the implementation
   and the test that pins the degenerate case documents it as a trap.
2. **The judge wrote the gold.** Unanimity in one's own favour is
   exactly what a lenient self-judge produces, and the design cannot
   separate that from being right. Rather than hand-wave it, the
   asymmetry is now measured and printed: 9 of the 40 cases are a wrong
   *leaf*, not a wrong rule (`608.2` for gold `608.2b`, `704.5g` for
   `704.5d`/`704.5f`, siblings under `702.131`, `702.33`, `702.179`,
   `701.54`) — and E-003a found precisely that to be the annotator's own
   commonest way of disagreeing with themself. All 9 were judged model
   error. One standard for the model, another absorbed as ceiling.

The reason this does not sink the result is that the objection was
already priced. The family score grants full leniency about depth by
construction, and there the model reads 0.252 against a family ceiling
of 0.902 — about a quarter of what is attainable. Granting every
depth case to the model changes the size of the finding, not its sign.
What would settle it is a second, independent judge; a bigger sample
would only shrink the sampling error, which was never the binding
uncertainty. Registered as future work rather than attempted.

Decision: stop at 40. The rule-of-three bound of 0.091 already excludes
both alternative explanations, and doubling the sample would move it to
roughly 0.04 — a difference no decision depends on. Phase 3's negative
result is now supported by three measurements instead of one: the score
(0.125), the ceiling (0.815), and the composition (40/40 model error).

Also checked, because the author asked whether the CR upgrade could have
contaminated any of this: it could not, and the check is mechanical
rather than argued. All 125 annotation rows carry `cr_version =
"August 7, 2026"`, the same release the extractor was grounded on, and
**0 of the 267 disagreements cite a rule number absent from that CR** —
version skew would surface there first. Of the 4 citations the August
migration remapped, one lands inside the sample (`310.10` -> `310.11`),
judged with the current rule text on screen. Recorded because "we
changed the corpus mid-experiment" is the kind of thing a reader should
not have to take on trust.

## 2026-08-09 — The ceiling came back at 0.815: the gold is not the story

E-003a reported the same day it was registered. Agreement F1 **0.815
[0.679, 0.938]** primary, **0.902 [0.800, 0.980]** family, 14 of 20
rulings identical. No decision rule fires — it was registered as a
measurement, not a test — but it closes the question it was asked.

The comfortable hypothesis was that a single-annotator gold under a
liberal "governing rule" instruction was too noisy to measure against,
and that some of the 0.125 was the ruler rather than the system. It is
not. For the gold to explain that score the annotator would have to
disagree with themself about seven times in eight; they disagree once in
four, and mostly about depth.

The useful part is the *shape* of the 6 disagreements, not the F1: 3 are
granularity (`303.4a` vs `303.4`, `706.2b` dropped with `706.2` kept,
`603.7b` vs `603.7c`), 2 are one pass citing an extra rule without
contradicting the other, 1 is a real conflict (`709.4` vs `202.3d`).
Choosing which *area* of the CR governs a ruling is reproducible;
choosing the *leaf* is where the interpretation lives. That is the same
distinction the family metric was added to expose on 2026-08-08, now
confirmed on the annotator instead of on the model — and it retroactively
justifies reporting both scores rather than one.

Consequence for the author's lexical search tool: bag-of-words over rule
text is well matched to finding the governing *area*, and structurally
blind to depth — a parent and its subrule share nearly the same bag, so
term overlap cannot separate `706.2` from `706.2b`. The tool is not
failing at that; the representation has no signal there. Recorded because
it predicts where a retrieval-augmented citation experiment (E-004) would
and would not help.

Decision: stop investing in the ceiling (a wider sample would tighten an
interval that would have to move by ~0.5 to matter) and proceed to
E-003b. E-003b's registered prediction was deliberately left unamended
even though E-003a is weak evidence against it — a prediction edited
after seeing adjacent data is not a prediction.

## 2026-08-09 — The gold gets a ceiling before the disagreements get read

E-003 reports citation F1 0.125 against a gold written once, by one
person, under an instruction to cite the rule that *governs* the
interaction. That number is currently read against 1.0, which assumes
the task has one right answer. The author's objection is the reason it
may not: two rules can both support a ruling, and choosing between them
is interpretation, not lookup.

Two measurements registered, in this order (E-003a, E-003b):

1. **Intra-annotator agreement.** 20 rulings, seed `20260809`,
   stratified proportionally, re-cited into a blinded copy that carries
   the ruling text and mentions but no `cited_rules`
   (`scripts/reannotate.py`). Pass 2 uses the *same* tools as pass 1 —
   a better tool would measure the tool, not the annotator. Scored with
   the E-003 citation metric unchanged, so the ceiling and the score sit
   on one scale. `rule_family` moved from the scorer into
   `evaluation/metrics.py` for exactly that reason: two copies could
   drift, and a drifting definition would stop the ceiling from bounding
   the score.
2. **Composition of the disagreements**, by seeded sample rather than
   exhaustively, into four buckets: `gold_right`, `both_defensible`,
   `gold_wrong`, `unclear`. Reported as four proportions with intervals.

The ordering is binding, and it is the part worth recording: agreement
must be measured *before* any disagreement is inspected. Re-reading
rulings that were just re-litigated against the model's output is recall,
not an independent second pass, and it would silently inflate the
ceiling.

Also recorded: sampling was chosen for (2) by *changing the goal*, not
by doing less of the same work. Adjudicating a sample would leave the
gold half-patched and make both the pre- and post-adjudication figures
uninterpretable. Estimating what the gap is *made of* is sound on a
sample, needs no cap, and answers the question that motivated the
request. The pre-registered adjudication rule (2026-08-08) is untouched
and still governs any actual change to a label — including its 10% cap,
above which the honest response is to void and re-annotate rather than
patch.

A same-day second pass is memory, not judgement; `reannotate.py compare`
prints the days elapsed since the draw and labels a same-day figure as an
optimistic bound.

## 2026-08-09 — The dev iterations were run at a sampling temperature; pinned to 0

`LlmClient` never set `temperature`, so both providers sampled at their own
default and no run was reproducible. It surfaced by accident: the *same*
configuration, re-run while diagnosing linking, scored citation F1 **0.167 and
then 0.114** — a spread as wide as the differences between the three prompt
iterations it was supposed to be measuring. With 15 citation-annotated dev
rulings, run-to-run noise and treatment effect are the same size.

Temperature is now pinned to 0 by default. Re-measured there, the best
configuration scores citation F1 **0.057 [0.000, 0.176]** primary and
**0.250 [0.067, 0.437]** family — below the 0.167 that iteration 3 appeared to
reach. The 0.167 was a favourable sample, not an improvement.

This does not rescue the iteration series; it retires it. The ordering
0.054 → 0.118 → 0.000 → 0.167 cannot be attributed to the prompt changes, and
the honest summary is that no prompt iteration was shown to help. It does not
change gate G3 either — every figure is far below the 0.5 infeasibility line,
and the reproducible one is the lowest of them. If anything the conclusion is
firmer than when it was made.

Linking, meanwhile, improved on a deterministic fix. A match sitting inside a
longer occurrence of the host card's own name — "Legion" inside "Kemba's
Legion" — is a tokenization error the greedy scan should have consumed, and
suppressing it took one false positive with no true positive lost: F1 **0.706 →
0.727 [0.476, 0.889]**, tp=12 fp=6 fn=3. Still below the 0.9 threshold.

Two broader versions of that rule were built, measured and rejected, both
because the annotations contradicted them. Suppressing any surface that is a
substring of the host name would drop "The Ring" on the host *Call of the
Ring*; suppressing any surface that *prefixes* a host face would drop "Brutal
Cathar" and "Moonrage Brute" on the host *Brutal Cathar // Moonrage Brute*.
Both are gold mentions. The measured attempt cost two true positives to win
two, F1 0.706 → 0.690, and was cut back to the narrow form.

A third idea died the same way. Four of the seven linking false positives are
game vocabulary that is also a card name — *Frog*, *Vehicle*, *Max speed*, *X* —
and a type/keyword stoplist would remove them. But two of the three false
negatives are the same shape — *Shapeshifter*, *The Ring* — and the gold calls
those genuine mentions. The trade is symmetric, so the class is not separable
deterministically and no stoplist was written.

## 2026-08-08 — E-003 iterations 2–3 and the G3 decision: citations are infeasible at target

Iteration 2 dropped the keyword rule directory from the citation grounding and
added a three-step instruction (name the concept, pick the chapter, then the
rule). It made things worse — primary F1 **0.118 → 0.000** — while doing exactly
what it was designed to do: the chapter collapse ended, predictions spreading
over 608, 702, 704, 701, 612, 603 instead of piling onto 702 and 608. The
directory was anchoring correct answers, not merely biasing; removing it spread
the errors instead of fixing them.

That iteration bundled two changes, which was an experimental-hygiene mistake:
with both moving at once, neither was attributable. Iteration 3 isolated them by
restoring the directory and keeping the three-step instruction, and it is the
best configuration measured: primary F1 **0.167 [0.000, 0.333]**, family F1
**0.312 [0.121, 0.529]** — the first interval in this series that excludes zero.
So the instruction helped (0.118 → 0.167 with the directory held constant) and
the directory removal was the whole of the damage.

**Gate G3 fires on the pre-registered rule.** Citation F1 is 0.167 after three
documented prompt iterations, against a 0.5 infeasibility line and a 0.75 pass
threshold: `CITES_RULE` extraction by a single grounded LLM call does not reach
the target, and E-003's decision rule says reduce the schema and report the
negative result rather than keep tuning. This was predicted at registration —
"`CITES_RULE` F1 predicted below linking F1" — though not this far below.

Linking is untouched by every citation change, as it should be: F1 **0.706
[0.444, 0.868]** across all four runs, below the 0.9 threshold, with the false
positives in the homonym (4) and multiword (3) strata. It is neither trivial nor
infeasible under G3, and it has had no iterations of its own.

The obvious remedy for citations — retrieving candidate rules for the model, as
`cite_search.py` does for the annotator — is deliberately **not** attempted here.
That tool helped build the gold, so feeding it to the system under measurement
would make agreement a family resemblance rather than a result. It is also an
architecture change, not a prompt change, and so outside E-003's registered
configuration. Registered as a future experiment instead.

All figures above are dev-split, 15 citation-annotated rulings, intervals wide
and mostly including zero. They are diagnosis and a gate decision, not results.
The annotation split has still never been touched.

## 2026-08-08 — E-003 prompt iteration 1, on dev: the depth hypothesis was mostly wrong

First dev run (prompt v1, grounded, 15 citation-annotated rulings) gave a
primary citation F1 of **0.054** — 1 true positive against 16 false positives
and 19 false negatives. Inspecting the pairs suggested a depth problem: gold
`608.2b` against predicted `608.2`, gold `702.33d` against `702.33`. The prompt
contained the licence for exactly that — *"If unsure between two numbers, cite
the parent rule you are sure of, with lower confidence."* A parent citation is
not a safer answer, it is a different one, so the instruction converted possible
hits into certain misses. Iteration 1 (`EXTRACTOR_VERSION` v1 → v2) replaced it:
pick the likelier subrule and lower the confidence instead of retreating.

Result: primary F1 **0.054 → 0.118**, family F1 **0.207**. The change helped and
the diagnosis was still mostly wrong. If depth were the main failure, the family
score would be high and the gap between the two would carry the error; instead
the family score is also near the floor, with 14 false negatives. The extractor
is not naming the right rule at the wrong depth — it is not finding the right
rule at all, and it collapses onto chapters 702 and 608 while the gold spreads
across 509, 707, 616, 614. Recorded because the wrong hypothesis is the useful
part: the remaining budget should not be spent on depth.

Linking is unchanged by the citation prompt, as expected: F1 **0.706
[0.444, 0.868]**, tp=12 fp=7 fn=3, with the false positives concentrated in the
homonym (4) and multiword (3) strata — the direction E-003 predicted, at a level
below the 0.9 threshold.

All figures are dev-split diagnosis over 15 rulings with intervals that include
zero. They are not results; the annotation split remains untouched.

## 2026-08-08 — Scryfall bulk ETL: read three formats rather than force a re-download

Scryfall retired `download_uri` (one uncompressed JSON array) in favour of
`jsonl_download_uri` (gzipped JSONL). `etl/download.py` raised
`KeyError: 'download_uri'` before resolving anything, so re-ingestion was
impossible — a silent break, since nothing re-downloads on a normal working
day and the failure only appears when you try.

The reader (`etl/bulk.py`) accepts gzipped JSONL, plain JSONL, *and* the legacy
array, and `bulk_path` prefers the newest format that exists on disk. The
alternative — cut over to JSONL only and re-download — was rejected for the
same reason the CR upgrade was handled carefully on the same day: a 180 MB
oracle bulk already on disk is real work, and stranding it in the middle of the
citation pass would trade a latent bug for an immediate one. Format is detected
from the first non-whitespace character, not from the file name, because the
name is only a convention.

Two things improve as a side effect. JSONL is streamed record by record instead
of held whole in memory (the legacy array still cannot be, which is an argument
for letting the next download replace it), and the compressed artifact is ~24 MB
against ~180 MB. The resolver now also warns and skips when an entry exposes no
known download key, rather than dying — the next contract change should degrade,
not crash.

Deliberately *not* done: re-downloading now. The rulings snapshot would jump
mid-annotation, which is the corpus-consistency problem this same day's CR entry
argues against. The download happens after the citation pass closes.

## 2026-08-08 — CR upgraded mid-annotation; citations migrated by text, not by number

The corpus was internally inconsistent: the CR snapshot was effective
2026-02-27 while the Scryfall rulings snapshot was 2026-07-17, so rulings
for sets released in between could cite rules that did not exist in our
CR. This surfaced during the manual citation pass as a ruling whose
governing rule was simply absent. Upgraded to the 2026-08-07 CR at 64/155
rulings reviewed rather than after, because the mismatch is structural and
would otherwise have hit the remaining 91 as well — and because a gold with
half its labels authored against one CR and half against another cannot be
read: a low `CITES_RULE` F1 would not distinguish model error from version
artifact.

Numbers are not a safe anchor. Measured between the two versions: 111 rules
added, 70 removed, and three silent displacements that a number-based
migration would have corrupted — `initiative` moved 725.1/725.2 to
726.1/726.2 to make room for `monarch`, so the old numbers still resolve
but now mean something else entirely; `310.10` shifted to `310.11` and
`704.5w` to `704.5x`. The migration in `scripts/cr_migrate.py` is therefore
anchored on rule *text*: the annotator chose a rule by what it says, so the
tool relocates that choice to wherever the text now lives, and only when the
match is near-exact and clearly better than at the original number.

Result: of 79 distinct cited rules, 71 unchanged, 4 relocated (5 citations
remapped, `migrated_from` kept on each), 4 edited in place with no semantic
change (`205.3g` and `205.3m` gained new types, `506.4` gained "or
protector", `702.142a` was reworded editorially), 0 orphaned. No manual
decision was lost. `edited` and `orphaned` are never auto-applied — guessing
there would corrupt the gold silently, which is the one failure this whole
apparatus exists to prevent.

Provenance added as the durable fix: every draft row now carries
`cr_version`, without which no future migration is auditable. Prior CR kept
as `data/raw/comprehensive_rules-20260227.txt`.

Two collateral findings, both from the same "living documentation" class.
The Scryfall bulk ETL is broken — the API replaced `download_uri` with
`jsonl_download_uri` and now serves JSONL, so `etl/download.py` raises
`KeyError` and nothing can currently be re-ingested. And the 2026-08-07 CR
replaced empty separator lines with lines holding U+00A0; the parser
survives it, but `normalize()` folds NBSP so formatting churn is never read
as a text change.

## 2026-07-21 — `cited_rules` interpreted liberally: cite the governing rule

After the full 155-ruling annotation, the gold held only 6 citations,
all in the 5 "explicit" rulings that literally print a rule number; every
other ruling — including the guide's own Crib Swap worked example that
should cite 608.2b — was left empty. That is a conservative reading of
"the rule the ruling turns on", and against a near-empty citation gold
the extractor's inferred citations would all score as false positives,
measuring nothing. Decision: cite the rule that *governs* the interaction
even when the ruling states no number, because recovering the unstated
rule is the entire premise of `CITES_RULE` (Phase 2 measured that rulings
almost never cite numbers). Requires a citation pass over ~150 rulings.
The annotation guide and worksheet were updated to make the liberal
reading explicit and to help find numbers by grepping the CR rather than
from memory. The alternative — declaring CITES_RULE genuinely sparse —
was rejected: the sparsity was an annotation artifact, not a measurement.

## 2026-07-20 — Multi-word card names are not unambiguous; capitalization gate added

The first linking measurement against 24 dev annotations disproved a
design premise: the linker treated any multi-word name match as certain,
but "card draw", "deal damage", "too many", "max speed" are real card
names *and* ordinary English phrases, giving 8 false positives
(multiword precision 0.47). Fix: require at least one capitalized word in
the match — not the initial, so "the Ring" survives its lowercase
article. Overall F1 0.69 -> 0.83, no true positive lost. The three
residual false positives are capitalized-but-generic names (Nicol Bolas,
Soul Shatter, Max Speed), which are the LLM stage's job. The frozen
sample's strata labels predate this change and are kept as the sampling
record, not re-derived. Finding surfaced only because the annotation
recorded the negatives — evidence for why the manual gold is the phase's
core work.

## 2026-07-20 — Grounding fixed hallucinated numbers and induced a topical bias

Round 2 (keyword directory in the system prompt) did what it was
designed to do: nonexistent rule numbers fell from 7 of 31 to 1 of 21.
It also did something it was not designed to do: **all 21 citations
became 701/702 keyword rules**, losing the correct procedural citations
round 1 produced (601.2c, 608.2, 613.1). A prompt whose only rule
inventory is keyword names is a prompt that asks for keywords.

Decision: keep grounding, but lead the block with the full CR chapter
map (146 chapters) and name the procedural chapters explicitly, so the
model sees the whole document rather than one wing of it. Recorded
because the lesson generalizes past this prompt: the metric that
improved (gate rejection rate) was not the metric that mattered, and
only inspecting the *shape* of the output caught it. Every prompt round
now reports the distribution of cited rule families, not just error
rates.

## 2026-07-20 — Correction: 25 rulings (3 cards) cite rule numbers, not 1

The Phase 3 sampling stratifier re-measured with the pattern
`\b\d{3}\.\d+[a-z]?\b` and found **25 of 77,999** rulings carrying an
explicit CR number — all from 3 cards whose rulings enumerate the
704.5x state-based actions in the form "(704.5g)". The Phase 2 pattern
missed parenthesized citations and undercounted by 24. The decision
stands unchanged — 0.03% coverage concentrated on 3 cards is not a
deterministic component worth building on — but the number in
[golden-set.md](golden-set.md) and [evaluation.md](evaluation.md) was
wrong and is now corrected. Lesson recorded: a measurement that feeds a
decision gets its pattern reviewed like code, because the number
outlives the script that produced it.

## 2026-07-19 — Literature reading anchored to decisions

Adopted a research scaffold: every source must name the project
decision it informs before getting a full reading note; otherwise it
goes to an ideas parking lot. Reading order is decision order (survey
→ what *not* to build → closest published design → extraction
roadmap), not textbook order. Experiments pre-register in
[../experiments/registry.md](../experiments/registry.md) before
running.
