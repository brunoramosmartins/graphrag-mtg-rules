# A denominator is a claim about what counts

**Cross-phase · drafted 2026-09-12**

> **SKELETON.** Four real instances from one experiment, all verified; prose
> not written. The point is that the same defect arrived four times wearing
> four different costumes, and each time it decided the answer.

<!-- write: opening. Precision is hits over something. The something is a
     decision about what a retrieval *unit* is, and whoever picks it picks
     the winner. -->

---

## Four costumes, one defect, one experiment

### 1. Passage versus rule item

A fixed-size window containing the gold rule and four irrelevant ones scores
**1 relevant item**. A graph returning those same five rules as five items
scores **1/5**. Identical content, opposite verdicts.

Caught in the 2026-08-15b amendment, before E-010 ran. Fix: decompose a
retrieved unit into the CR rule numbers it contains, and judge relevance per
number.

### 2. Rule numbers versus everything retrieved

The fix above introduced the next one. Rule-number precision reads arm A as
the **most** precise retriever (0.420 vs 0.223). Token-normalised precision
reads it as **3.7× worse** (0.030 vs 0.112).

Why: arm A's payload on those questions is 133 cards and 375 rulings against
56 rules. A denominator of rule numbers asks *"of the few rules it brought,
how many were gold"* and ignores everything else it charged the budget for.

<!-- write: the two figures disagree in direction, and that disagreement is
     the result rather than a tie to be split. -->

### 3. Scorable-by-the-key versus relevant

The deterministic proxy scores relevance by `gold_cr_rules`, which **cannot
score a card or a ruling**. The human pass, judging against the answer key,
reads the same comparison at 0.400 vs 0.452 — a 1.13× gap where the proxy saw
3.5×.

So the proxy penalises an arm for retrieving a **kind of evidence its own
oracle cannot credit**, and its gap is an upper bound.

### 4. N versus N-of-M

The per-question mean printed "over N questions". N differs per arm, because
it counts only questions where that arm retrieved at least one rule number —
so the mean was taken over *whichever questions the arm chose to speak about*,
flattering whichever stayed silent most.

Printed as N-of-M it says: **arm A retrieves no CR rule number at all on 17 of
42 questions.** B misses 8, C misses 4.

<!-- write: the fix was one line of formatting, and it surfaced a fact about
     the system that three months of measurement had not. -->

---

## The related trap: a metric that cannot see the failure

Entity recall is `|gold ∩ retrieved| / |gold|`, so a spurious entity **cannot
lower it**. Phase 4's headline metric read 1.000 with three linking defects
present and 1.000 with them fixed.

<!-- write: a metric structurally incapable of seeing the failure mode you
     care about is not a weak metric, it is the wrong one — and it will look
     healthy right up to the point it matters. -->

---

## Detection

<!-- write: 4-5 portable rules. Candidates:
     - write the denominator down in words before computing it: "of the X
       that Y, how many Z" — then ask who chose X;
     - if two defensible denominators disagree in *direction*, report both and
       say which one the registration named;
     - prefer the unit-size-invariant quantity (here: tokens) when arms spend
       the same budget differently;
     - a denominator that varies per arm is a denominator the arm selected;
     - check whether your headline metric can move in the bad direction at
       all. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
