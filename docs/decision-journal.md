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
