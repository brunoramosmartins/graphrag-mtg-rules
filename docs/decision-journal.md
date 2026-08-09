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
