# The p-value said yes and the registered effect size said no

**Cross-phase · drafted 2026-09-13**

> **SKELETON.** Both instances are real, verified, and happened within
> twenty-four hours of each other. Prose not written. This one is the shortest
> of the four and may be the most useful, because the mechanism is one number
> written down before a run and everything else follows from it.

<!-- write: opening. A significant result is an invitation, and the thing that
     decides whether you accept it is a number you wrote before you had the
     result. Without it, "p < 0.05" is the only quantity in the room and it
     will win every argument it is in. -->

---

## The shape

<!-- write: state it once, abstractly. Significance answers "is this
     difference distinguishable from zero", which is a question about the
     sample. Whether it is worth acting on is a question about the world, and
     the design cannot answer it after the fact because by then the answer is
     visible and the threshold is negotiable. So the threshold is fixed first,
     alongside the test, and it is allowed to overrule the test. -->

---

## Two instances, one day apart

### 1. A trim policy that was significantly better and not nearly good enough

Four eviction policies, oracle-free, trimming an identical retrieved pool at
the shipped token budget. The comparison was paired by construction.

| arm | chain reach |
|---|---|
| shipped | 0.030 [0.010, 0.085] |
| proportional | 0.100 [0.055, 0.174] — adjusted *p* = 0.0391 |
| **connectivity first** | **0.120** [0.070, 0.198] — adjusted *p* = 0.0234 |
| random, fixed seed | 0.010 [0.002, 0.054] |

Both designed arms beat what ships. The best beats **random** at
+11/−0, *p* = 0.00098, so the improvement was not an artefact of merely
perturbing the policy.

**The registered rule asked for a gain of 0.20. The best arm returned 0.090.**
Nothing was adopted.

<!-- write: the honest counterfactual. "Significantly better than production,
     and better than chance, p = 0.023" is a sentence that gets a change
     merged. It would have closed a seventh of the gap it was aimed at, on a
     ceiling of 0.650 — and the code it changed is on the hot path of every
     query. -->

**Why the bar was right, arithmetically.** The budget holds about 200 items; an
equal share gives the deepest hop roughly 66 slots against 1,000 candidates.
Ordering decides *which* 66. It cannot make 66 cover 1,000. The nine points
were the whole of what ordering could ever buy, and the registered bar had
already said nine points was not the problem being solved.

### 2. A ceiling that was large and still short of the bar

The next entry asked whether typing a graph walk — following the relation the
question is about instead of every relation — puts a three-hop chain inside the
budget. It cut the median context from **193,797 tokens to 5,676**, a 30.6×
reduction, and the median then fit the budget **by three hundred tokens**.

Fit rate: **0.522**. The registered bar for "build on this" was 0.80.

<!-- write: this one is the harder case to hold, and the more instructive.
     A 30x reduction is a genuinely large engineering result and it is very
     tempting to call it a mandate. The rule said branch 3 — report it, carry
     it as a prior, decide nothing — and the reason that was right is in the
     next paragraph. -->

Because the entry also found *where the other half went*: of the questions that
did not fit, **39 of 44 passed through one of two hub relations** out of nine.
A build direction taken on the 0.522 would have aimed at depth. The thing to
aim at was hubs, and only the refusal left room to notice.

---

## What makes the number credible

<!-- write: 3-4 portable rules. Candidates:
     - the bar is written in the same document as the test, before the data
       exists, and dated;
     - it is expressed in the units of the decision it governs — "worth
       changing shipped behaviour for" — not in units of significance;
     - the entry says in advance what happens in the middle band, so a
       middling result is not read as whichever half is convenient;
     - a bar that has never refused anything is not evidence of good design;
     - and the tell that it is real: it refuses a result the author wanted. -->

---

## What this is not

<!-- write: guard the piece against the obvious misreading. This is not "ignore
     p-values" or "effect size beats significance". The test still decides
     whether the difference is real; both instances above ran one and reported
     it. The claim is narrower: the test cannot decide whether a real
     difference is worth acting on, that decision needs a number in the units
     of the action, and that number is only trustworthy if it predates the
     result. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
