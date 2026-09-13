# Handover to P3 — agentic RAG

**Written 2026-09-13.** This is the body of the P3 kickoff issue, versioned
here so the handover survives the issue and so its claims sit under the same
review as the rest of `docs/`. An earlier draft proposed decomposition on a
premise withdrawn the same day; this replaces it.

---

## What P2 hands over, and what it takes back

P2 (`graphrag-mtg-rules`) compared graph traversal against a vector baseline on
57 judge-level questions, evaluation split opened once on 2026-09-12.

**The headline stands.** Vector 0.60, graph 0.61, hybrid 0.65; the registered
primary analysis returns `inconclusive` on all four strata, adjusted *p* =
1.0000; and the direction runs against the thesis on `interaction_multihop`
(0.27 graph against 0.41 vector, n = 22), the stratum the hypothesis was
written about.

**The explanation does not.** On 2026-09-13 the sentence P2 repeated most —
*"generation is the bottleneck, not retrieval"* — was withdrawn at three hops,
along with the calibration figures that carried it. The conditioning clause
*"conditional on the answer being present in the evidence the model received"*
was operating as *"an accepted answer string was reachable"*, and **126 of 137
questions in that cell (92%) had been accepted on a one-step chain**. The model
had been refusing contexts that genuinely did not answer the question, and the
harness scored those refusals as generation failures.

**So an earlier draft of this issue proposed decomposition on a premise that no
longer exists.** What follows replaces it. The new premise is better supported
and points somewhere narrower.

## What replaced it, measured

Three entries, registered and run 2026-09-13, zero model calls between them.
Full detail in P2's `experiments/registry.md` (E-015, E-016, E-017) and
`docs/evaluation.md`.

| finding | figure |
|---|---|
| At the shipped budget, retrieval delivers a three-hop chain on | **3 of 100** |
| At sixteen times the budget, nothing else changed | **65 of 100** |
| The chain's own cost | **~90 tokens** of a 6,000-token budget |
| Best oracle-free eviction policy, against 0.030 shipped | **0.120** — the registered bar was +0.20, so nothing was adopted |
| Typed expansion: median three-hop context | **193,797 → 5,676 tokens** (30.6×) |
| …and it then fits the shipped budget on | **48 of 92** questions |
| Of the 44 that do not fit, passing through `has_genre` or `release_year` at the middle hop | **39** |

**The three-hop problem is hub traversal.** Not depth, not generation. A chain
of three person-shaped relations is cheap at any depth; one genre or one year
in the middle builds a haystack the budget then trims from the wrong end.

## The hypothesis P3 should register, and the one it should not

**Should not:** *"decomposition helps because the model cannot chain three
facts."* That is the withdrawn premise. Nothing in P2 measures it.

**Should:** an agent that can **see the size of an intermediate result set and
act on it** outperforms single-shot retrieval on multi-hop questions, because
the failure it addresses is a hub in the middle of the walk rather than depth.

Concretely, a decomposing router issues one hop at a time, so it observes that
the middle expansion returned 493 entities instead of 22 — and can filter,
rank, or ask again before spending the budget. Single-shot retrieval cannot,
because by the time it has a subgraph the trimming has already happened.

### The falsifier, and register it before any code

**If the agent wins by an equal margin on one-hop questions, distrust the
result.** There is no intermediate set to observe there and no hub to route
around, so an equal gain means the effect is the extra calls, the longer
reasoning budget, or self-consistency — not decomposition. That outcome
invalidates the mechanism even while improving the score.

### And the cheaper thing that has to be ruled out first

**Typed expansion is worth 30× and needs no agent at all.** A
`WHERE type(r) = $relation` gets most of the way, and P2's E-017 branch 3
explicitly refused to hand P3 a build direction on a 0.522 fit rate.

So P3's **first** registered experiment should be typed expansion, not an
agent, and the agent should be justified only by what typing leaves on the
table. Building a planner for a problem a Cypher clause already solved is the
failure mode this handover exists to prevent. The reading that motivated the
Microsoft GraphRAG ADR in P2 applies here too: read it to decide what *not* to
build.

## Non-negotiable constraints inherited from P2

Each of these cost P2 something to learn.

1. **P2's evaluation split is spent.** P3 draws its own, seeded, ids written
   once, and **publishes how many times it was opened**. P2's was opened once,
   on 2026-09-12.
2. **Size the design for the stratum the hypothesis is about.** P2 spread 57
   questions across five strata; exact McNemar needed 6 discordant pairs and
   the largest discordance anywhere was 5. Compute the detectable effect before
   the run and budget the multi-hop stratum to reach it.
3. **Write the effect size that would justify acting, before the run.** In
   twenty-four hours P2's registered bars refused two statistically significant
   results, and were right both times — once at *p* = 0.023 with a gain of
   0.090 against a bar of 0.20, once at a 0.522 fit rate against a bar of 0.80.
   A significant difference is not the same question as a difference worth
   shipping.
4. **Render one case before quoting a number built on it.** The defect above
   survived five months, three published documents and a funded follow-up
   because every figure was an aggregate and nobody printed a prompt.
5. **An oracle-conditioned figure is never a system score**, and must be
   labelled wherever it is quoted. P2 has two precedents: `reduce_to_k` keeping
   a chain it was handed, and E-017 reading relations off a gold answer.
6. **Ask what else would make a check return what it just returned.** A guard
   that passes for two different reasons is the same defect as one that cannot
   fail, and it is harder to see because nobody inspects a pass.
7. **Every denominator stated as N-of-M**, written out in words before it is
   computed. P2 hit that defect five times.
8. **The generation span carries the prompt and the completion.** P2 shipped
   `input.value` / `output.value` and a prompt hash on 2026-09-13; a trace that
   shows what an answer cited and not what the model saw cannot falsify a claim
   about what the model saw.

## Definition of Done

- [ ] Typed expansion registered and run **before** any agent is designed, with
      its own decision rule
- [ ] The agent hypothesis, decision rule, power calculation, effect-size bar
      and falsifier registered in P3's `experiments/registry.md` before any arm
      runs
- [ ] Split drawn and frozen, seed recorded, ids only, opening count published
- [ ] Agent and single-shot arms run on the same questions at a matched token
      budget
- [ ] Paired analysis with correction; three-valued verdict
      (supported / refuted / inconclusive)
- [ ] Falsifier checked and reported whether or not it fired
- [ ] At least one rendered case per arm — prompt, evidence, completion —
      included in the write-up rather than only aggregates
- [ ] Result written to P3's `docs/evaluation.md`, quoting P2's figures as the
      prior and linking back to this issue

## Links

- P2 repository: https://github.com/brunoramosmartins/graphrag-mtg-rules
- `experiments/registry.md` — E-012's 2026-09-13 amendment (the withdrawal),
  E-015, E-016, E-017
- `docs/evaluation.md` — "What three hops actually costs"
- `docs/decision-journal.md` — the four dated entries of 2026-09-13
