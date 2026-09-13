# A denominator is a claim about what counts

**Cross-phase · drafted 2026-09-12**

> **SKELETON.** Five real instances, all verified; prose not written. The
> point is that the same defect kept arriving in different costumes, and each
> time it decided the answer. The fifth arrived on 2026-09-13 and withdrew the
> project's most-quoted number.

<!-- write: opening. Precision is hits over something. The something is a
     decision about what a retrieval *unit* is, and whoever picks it picks
     the winner. -->

---

## Five costumes, one defect

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

### 5. An accepted answer versus an answerable question

The fifth arrived three months after this file was started, and it decided the
project's headline rather than a table in it.

Two experiments reported *"conditional on the answer being present in the
evidence the model received"*. That clause was operating as **"an accepted
answer string was reachable through the evidence"** — which is a different
claim, and returns a non-empty chain either way.

A three-hop question, *"the movies written by the screenwriter of The Best
Intentions were directed by who"*, was accepted on the one-step chain
`The Best Intentions | written_by | Ingmar Bergman`. Bergman is in the answer
set because he directed some of his own screenplays. The chain proves
`written_by`; the question asks `directed_by`. The model, shown hop one and
eleven films released in 1992, refused — as its grounding prompt instructs —
and was scored as a generation failure.

**126 of the 137 questions in that cell: 92%.** The weaker of the two
conditions required no chain at all and split 213 / 11.

<!-- write: this one is the argument for the whole file. The denominator here
     is not a number in a table, it is the *population the result is about* —
     and choosing it wrong did not shift a figure by a few points, it made the
     figure answer a question nobody asked. Note also that the first four
     costumes were caught by review and this one needed a rendered case: the
     defect had become invisible to reading because the code was correct for
     the sentence it was written against. -->

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
       all;
     - a conditioning clause is a denominator: render one case that satisfies
       it and check that it is the case the clause describes. Four of the five
       above were caught by reading; the fifth needed a case printed, because
       the code was correct for the sentence it had been written against. -->

---

## Lessons Learned

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->

## Failed Attempts

<!-- FIRST PERSON, written by the author. Not to be ghost-written. -->
