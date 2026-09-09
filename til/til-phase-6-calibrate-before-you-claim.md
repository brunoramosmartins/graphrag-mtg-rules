# Calibrate before you claim — five failure modes a GraphRAG evaluation hides

**Phase 6 · 2026-09-02**

Before running our GraphRAG system against its real corpus, we ran the same
machinery on [MetaQA](https://github.com/yuyuz/MetaQA) — a movie knowledge
graph with 135k triples over 43k entities, and 1/2/3-hop questions with an
answer key. The idea was borrowed, not invented: reproduce something known
before claiming something new.

It found five defects before a single domain question was scored. None of
them would have announced itself on the domain corpus. Every one would have
produced a plausible number.

This is the catalogue, written to be portable — the mechanism first, our
instance second, and how to detect it in a system that is not ours.

---

## 1. The renderer silently drops evidence it does not recognise

**Mechanism.** Retrieval produces evidence objects with a `kind`. The
function that serialises them into the prompt loops over a hardcoded list of
kinds. Anything else is dropped — no error, no warning, no notice in the
context. Retrieval reports success, the prompt is built, the model answers
from nothing.

**Our instance.** `serialize()` looped over the five kinds of our domain
ontology. The calibration retrieved a sixth kind. 206 evidence items per
subgraph, none of them rendered.

**How it was caught, which is the uncomfortable part.** A cost estimate that
looked too small: 141k input tokens for 500 calls whose contexts should have
held thousands of facts. The system prompt alone accounted for nearly all of
it. There was no test, no assertion and no log line between retrieval and
the prompt.

**Detection, generally.** Assert that every retrieved item appears in the
rendered context — count in, count out, fail on a mismatch. In a system
whose premise is that no claim goes uncited, evidence vanishing between
retrieval and prompt is the worst failure shape available: the model is
forced to answer from memory in exactly the place you promised it could not.

---

## 2. A tuned constant crosses a corpus boundary

**Mechanism.** Retrieval carries constants — a per-type cap, a token budget,
a top-k, a similarity threshold. Each was chosen against one corpus. Moved
to another, the same value can mean something completely different.

**Our instance.** A per-`(template, kind)` cap of 25 exists to stop a hub
entity returning thousands of items. In our domain graph, evidence has five
kinds, so the cap trims hubs and nothing else. On the calibration graph,
evidence has *one* kind — so the cap became a hard ceiling of 75 items
total, and the token budget it was supposed to work alongside never bound at
all. The cap deleted the answer after the traversal had found it, on a
quarter of the 2-hop questions.

**Detection.** For each limiting mechanism, record which one actually binds
on each query. If one of them never fires across a whole run, it is not
protecting you — something upstream is already cutting harder.

**And the trap on the way out.** Re-deriving the constant must not be a
sweep against your metric. State a criterion that never looks at the score —
ours was *"the token budget should bind, the cap should not"* — and accept
what it gives you. It gave us a worse 3-hop number, and we kept it.

---

## 3. The retrieval ceiling is measured on something the model never sees

**Mechanism.** "Did retrieval find the answer?" is measured over what the
traversal touched. The model receives what survives the budget, the caps and
the trimming. The two numbers can differ enormously, and the first one
flatters the system.

**Our instance.** Traversal reached the answer entity in 500 of 500 2-hop
questions. What the model actually received held it in 421. Reported
naively, retrieval was perfect and generation looked terrible.

**Detection.** Report two ceilings, always: *walked* and *shown*. Only the
second bounds end-to-end accuracy. The gap between them is your own
machinery deleting evidence, and it belongs in the results, not in a
footnote.

---

## 4. Distance-first trimming deletes exactly what multi-hop questions need

**Mechanism.** When context overflows, a common policy is to drop the
farthest evidence first — near evidence is usually more relevant. On a
multi-hop question the answer *is* at the frontier. The policy is optimised
for the query type that needs it least.

**Our instance.** At 3 hops the budget removed the distance-3 layer on
essentially every question. What survived was the 45% of questions whose
answer happened to also be reachable within 2 hops: measured, 226 of 500
were shallow-reachable, and 213 of the 224 survivors came from that set.
**The system answered the 3-hop questions that were not really 3-hop.**

**Detection.** Cross-tabulate accuracy against the depth at which the gold
answer sits, and check whether your trimming policy correlates with that
depth. If your evaluation set has a multi-hop stratum, this is where its
score goes to die — and it will read as "the graph hypothesis failed"
rather than "the budget policy is wrong for this query type".

**We did not fix it.** A calibration exists to measure the machinery that
ships; redesigning the machinery to pass its own calibration measures
nothing. The behaviour was published as a result.

---

## 5. A grounding prompt with a missing section refuses instead of answering

**Mechanism.** Grounded-generation prompts usually carry four ideas: answer
only from the evidence, cite every claim, walk the reasoning step by step,
and refuse when the evidence runs out. Drop the third and keep the fourth,
and a model that needs two facts chained will resolve the first, fail to
look for the second, and refuse — politely, confidently, and constantly.

**Our instance.** Adapting the prompt to a neutral domain, we removed the
*walk the reasoning* section along with the domain vocabulary, and asked for
the answer entity "and nothing else", which removes the room to compose. The
result: 2-hop accuracy of **0.074**, with 452 of 463 misses being refusals —
on questions whose answer was in the context. At 1-hop, where the answer was
present *every time*, it still refused 90 times in 500.

**The tell was in the shape, not the score.** Zero fabricated citations in
1000 answers: the grounding half of the contract was working perfectly while
the answering half never engaged. A low score with clean citations and a
high refusal rate is a prompt problem, not a retrieval or knowledge problem.

**Detection.** Split misses into *refused* and *answered wrongly* before
diagnosing anything. They have opposite causes and opposite fixes. And log
the raw completion — we had not, and had to spend again to see what the
model was actually saying.

---

## The discipline that made the rest of it work

Four rules did more for this phase than any implementation choice:

1. **A floor that does not depend on the literature.** We registered "1-hop
   Hits@1 ≥ 0.90" before anything ran, on the argument that a single typed
   edge lookup against an unambiguous KB is not hard. It came in at 0.786,
   and because the rule said *below the floor, chase it as a defect and do
   not write it up*, defect #5 was found instead of published.

2. **The published band could not decide anything, and we said so.** Taken
   as `[min, max]` across cited systems, the 3-hop band was `[48.9, 100]` —
   a floor from a 2016 baseline and a ceiling at saturation. Any result
   lands "inside the band". Narrowed to primary-sourced figures it became
   `[91.4, 100]`, and we recorded that narrowing it made our own registered
   prediction easier to confirm.

3. **Prompt iteration never touches the registered questions.** Repairs run
   on a development draw from the complement of the frozen subset, with the
   round budget fixed *before* seeing whether the repair worked. A prompt
   tuned until the test set improves is a number reporting its own tuning.

4. **Every constant that changed was changed by a stated criterion, and the
   criterion never looked at the score.** Twice this produced a worse
   number. Both were kept.

---

## The one-line version

A calibration benchmark is not there to give you a number to publish. It is
there to be a corpus where extraction and entity linking **cannot** be the
explanation — so that when something breaks, the failure has nowhere to
hide. Ours broke five times, and each break was in code the domain
evaluation depends on.

If your calibration run passes clean on the first attempt, be suspicious of
the calibration, not pleased with the system.

---

*Repo: [graphrag-mtg-rules](https://github.com/brunoramosmartins/graphrag-mtg-rules)
· pre-registration and every amendment in `experiments/registry.md`, dated
reasoning in `docs/decision-journal.md`.*
