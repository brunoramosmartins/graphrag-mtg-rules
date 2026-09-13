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
- **Grounding, not retrieval.** Six of the graph arm's seven refusals land on
  that stratum. Dropping them halves the deficit.
- **The MetaQA calibration predicted it** months earlier — see §4.

<!-- write: the synthesis. A question names cards and player verbs; a rule is
     written in defined terms. Nothing in the design bridges the register. -->

---

## 4. The borrowed benchmark predicted the domain finding

**Mechanism.** <!-- write: calibrating on a benchmark with an answer key
     before claiming anything on your own corpus — and what it buys beyond
     bug-finding. -->

**Our instance.** MetaQA, 2026-09-02: conditional on the answer being present
in the evidence the model received, correctness falls to **0.339** at three
hops. The registration said that if this prediction failed, the finding would
be about generation and would transfer to the MTG side. It failed, and it did.

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
