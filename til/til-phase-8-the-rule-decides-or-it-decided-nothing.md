# The rule decides, or it decided nothing

**Phase 8 · 2026-09-12**

> **SKELETON.** Facts, structure and every number are in place; the prose is
> not written. Each `<!-- write: -->` marks a paragraph to fill. The existing
> TILs use a "we" voice, mechanism first, our instance second.

<!-- write: one paragraph opening on the result. The hypothesis this whole
     project was built to test came back inconclusive on all four strata. Say
     it plainly and without apology, because the point of the piece is that
     this outcome was reachable in advance. -->

---

## The result

| | vector (A) | graph (B) | hybrid (C) |
|---|---|---|---|
| 57 evaluation questions | 0.60 [0.47, 0.71] | 0.61 [0.48, 0.73] | 0.65 [0.52, 0.76] |

Primary family — B vs A, exact McNemar, Holm-corrected over the four strata
with n ≥ 7 — **`inconclusive` on all four**, adjusted *p* = 1.0000 throughout.

<!-- write: why a table of three near-identical numbers is worth a post. -->

---

## 1. "Inconclusive" only means something if you sized the design first

**Mechanism.** A null result reads as "we found nothing" unless the reader
knows what the design could have detected. That number has to be computed
before the data exists, or it becomes an excuse chosen to fit.

**Our instance.** Exact McNemar needs 6 discordant pairs one way for raw
*p* < 0.05; Holm's strictest step needs 8:0. The largest discordance observed
anywhere was **5**. Both facts were written into `experiments/registry.md` in
**August**, including the sentence that `negative_temporal` (n = 7) could not
reach the strictest step even at 7 of 7.

**Detection, generally.** <!-- write: how to tell a pre-computed power claim
     from a post-hoc one. Hint: the date on the file, and whether the number
     is stated as a threshold or as a consolation. -->

---

## 2. A falsifier that can only fire in one direction is still worth naming

**Mechanism.** <!-- write: a pre-registered falsifier tells you which result
     should make you distrust the instrument rather than celebrate. -->

**Our instance.** `definition_1hop` was declared the falsifier in **July
2026**: if the graph won there too, distrust the harness. The graph does win
there — 0.91 against 0.73 — and nowhere near significance, so the alarm does
not sound. The August amendment had already recorded that at n = 11 the
stratum was *unpowered for equivalence*, and that the falsifier could only
ever have fired in the "graph wins here too" direction.

**Detection, generally.** <!-- write. -->

---

## 3. The direction ran against the thesis, and the reason was measured

**Our instance.** `interaction_multihop` — 22 of the 57, the stratum the
hypothesis was written about — reads **B − A = −0.136**. The graph wins on
one-hop strata, where the answer is a typed edge, and loses where it has to
walk.

Three measurements say why:

- **Vocabulary, not topology.** On the failure-selected population, the graph
  retrieves 7 of the 64 rules the keys require; a lexical index over all 3,308
  rules does *worse* at a realistic context size.
- **Declining, not reasoning wrong.** Six of the graph arm's seven refusals
  land on that stratum. Dropping them halves the deficit.
- **The MetaQA calibration predicted it** months earlier — see §4, and see
  what §4 had to withdraw in the process.

<!-- write: the synthesis. A question names cards and player verbs; a rule is
     written in defined terms. Nothing in the design bridges the register. -->

---

## 4. The borrowed benchmark predicted the domain finding — and then withdrew half of it

**Mechanism.** <!-- write: calibrating on a benchmark with an answer key
     before claiming anything on your own corpus — and what it buys beyond
     bug-finding. The sharpest version of the argument is that the answer key
     is what lets you audit your own harness, which is the part that paid off
     here and is not the part anyone advertises. -->

**Our instance, as published on 2026-09-11.** MetaQA: conditional on the answer
being present in the evidence the model received, correctness falls to **0.339**
at three hops. The registration said that if this prediction failed, the finding
would be about generation and would transfer to the MTG side. It failed, and it
appeared to.

**What happened on 2026-09-13.** Before paying for the follow-up built on that
sentence, we rendered one scored case. A three-hop question — *"the movies
written by the screenwriter of The Best Intentions were directed by who"* —
whose sixteen-item context held hop one and **eleven films released in 1992**.
Nothing about what Bergman wrote. Nothing about who directed those films. The
model refused. The grounding prompt instructs a refusal when the evidence is
insufficient, so it was obeying, and the harness had scored it as a generation
failure.

The chain search accepted any path to an accepted answer **string**. Bergman is
in the answer set because he directed some of his own screenplays, so a one-step
`written_by` edge satisfied a question asking `directed_by`. **126 of the 137
questions in that cell — 92% — were one-step chains.** E-002's condition is
weaker still and splits 213 / 11 the same way.

So the three-hop figure is withdrawn, and with it the sentence this project
repeated most. What survives is the clean half: at one and two hops the chains
match their declared depth on every question, correctness is **0.890 → 0.672**,
and of the 82 two-hop failures **39 are refusals and 19 are unparseable output
against 24 wrong entities** — fewer than one in three is a reasoning error.

<!-- write: the honest reframe. "The model cannot chain three facts" was never
     measured. What is measured is narrower and more interesting: handed a
     complete two-step chain in a sixteen-item context, the model mostly does
     not get the answer wrong — it declines, or it writes something the parser
     cannot read. Beyond two hops nobody knows, and this retriever reaches a
     genuine three-step chain on 3% of three-hop questions. -->

**Detection, generally.** <!-- write: the conditioning clause is the claim.
     "Conditional on the answer being present in the evidence" was operating
     as "an accepted string was reachable". Write the condition out in words,
     then render one case that satisfies it and check that it is the case you
     meant. -->

<!-- write: and the part that belongs to this piece's argument — pre-registration
     did every job it was pointed at here, including recording three predictions
     and scoring all three wrong. It cannot protect a quantity nobody rendered.
     That is not an argument against registering; it is the boundary of what
     registering buys, and the boundary is worth naming as precisely as the
     benefit. -->

> This section is the reason the piece exists in its current form. The first
> draft had it as a clean prediction-comes-true story. Rendering one case cost
> an afternoon and removed the cleanest paragraph in the TIL.

---

## 5. Four gates fired against the result we wanted

<!-- write: a short framing sentence. -->

| gate | registered | fired |
|---|---|---|
| pairwise head-to-head | before any pair existed: withdraw above 0.20 order disagreement | 0.333 and 0.368 → **withdrawn** on both contrasts involving the vector arm |
| judge validation | threshold = lower bound of the human's own ceiling (0.720) | 0.727 [0.598, 0.827] → **published ungated** |
| blinding of the precision pass | withdraw the blind claim above 0.70 | 0.778 → **withdrawn** |
| budget confound | 3× median item count at matched tokens | 3.38× → retrieval comparison **budget-confounded** |

The blinding one is the interesting one: a classifier seeing **only the kind**
of each evidence item identifies the producing arm 72% of the time on held-out
slots. <!-- write: the arms return different kinds of evidence, and that
     difference *is* the treatment — so item-level blinding here is
     unachievable rather than merely unachieved. -->

---

## What this transfers

<!-- write: 3-5 bullets, portable, nothing MTG-specific. Candidates:
     - compute the detectable effect before the run, and publish it whether or
       not it flatters you;
     - name the result that should make you distrust your own instrument;
     - a gate written after the number exists is not a gate;
     - a benchmark with an answer key predicts your domain failure mode;
     - "inconclusive" is a finding when the design was sized, and an excuse
       when it was not. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
