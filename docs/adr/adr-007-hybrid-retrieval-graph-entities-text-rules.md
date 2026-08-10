# ADR-007 — Hybrid retrieval: the graph supplies entities, text supplies rules

- **Status:** Accepted
- **Date:** 2026-08-09
- **Deciders:** Bruno Ramos Martins
- **Follows:** [ADR-005](./adr-005-templates-first-text2cypher-second.md)
  (templates first) and [ADR-006](./adr-006-cites-rule-reduced-to-explicit.md)
  (the reduction that forced this question)

## Context

ADR-006 reduced `CITES_RULE` to explicit citations, removing the intended
ruling→rule bridge. Three options were recorded and none taken: another
deterministic bridge, text retrieval for rules with the graph supplying
entity structure, or a re-registered inferred path.

`scripts/reachability.py` measured what the *remaining* deterministic
structure reaches — seeding from each question's entities and expanding k
hops through the undirected union of `REFERENCES` and the CR tree, which
is the architecture's best case on purpose.

| stratum | k=2 | k=4 | k=6 | median ball at k=6 | no seed |
|---|---|---|---|---|---|
| `definition_1hop` | **100%** | 100% | 100% | 2228 | 0/15 |
| `keyword_rule_2hop` | **100%** | 100% | 100% | 2544 | 0/3 |
| `interaction_multihop` | 10% | 21% | 38% | 1515 | **15/30** |
| `negative_temporal` | 13% | 33% | 47% | 2206 | 3/9 |

Three readings, in order of weight:

1. **The graph is at ceiling on the structural strata.** At k=2 it
   reaches every gold rule of `definition_1hop` and `keyword_rule_2hop`
   inside roughly 200 rules. Nothing needs fixing there.
2. **Depth does not rescue `interaction_multihop`.** 38% coverage arrives
   only at k=6, where the ball holds 1515 of 3308 rules. Reaching half the
   Comprehensive Rules is not retrieval; it is loading the corpus, and it
   discriminates nothing.
3. **Half that stratum cannot start.** Fifteen of its thirty questions
   produce no seed at all, because 56 of the golden set's gold entities are
   cards with **no keyword abilities** — *Humility*, *Opalescence*,
   *Ghostly Prison*. No traversal depth helps a node with no edge, and no
   new deterministic bridge can be built for one either: what connects
   *Humility* to the layer system is what its text *means*. That is
   inference, and E-003 measured this project's inference of a governing
   rule at F1 0.125.

So option 1 has no material for half the stratum and option 3 is the
thing just measured and rejected.

## Decision

- **The graph resolves entities and answers the structural strata.**
  Card, Keyword, Rule and Ruling nodes; legality; the CR tree; validated
  `REFERENCES`. Template traversals (ADR-005) cover
  `definition_1hop`, `keyword_rule_2hop` and `legality_1hop`, where
  reachability is 100% inside small balls.
- **CR rules for questions the graph cannot seed are reached by text
  retrieval over rule text**, and the graph still supplies the entities,
  the cards' rulings, and whatever structure it does have.
- **The retrieved subgraph is one object** either way: nodes, edges,
  rulings and CR spans with a token budget and per-hub caps, so a citation
  looks the same regardless of which route produced it.
- **The graph-only arm is kept and measured**, not replaced. See the
  confound below — this is the part of the decision that costs something.
- **No inferred ruling→rule edge returns** without its own
  pre-registration and its own gold.

## The confound this decision creates, and how it is handled

E-001 was designed as *graph pipeline vs. vector baseline*. Making the
graph arm hybrid would compare **graph+text vs. vector** — and a win
could come entirely from the text component, which is the Project 1
pipeline wearing a different hat. That comparison would prove nothing
about the graph and would be easy to present as though it did.

E-001 therefore runs three arms, declared here and amended into the
registry before any run:

| arm | what it is | what it tests |
|---|---|---|
| **A** | vector baseline (Project 1 pipeline, same corpus) | the control |
| **B** | graph-only traversal | the project's original claim |
| **C** | hybrid (this ADR) | the system actually shipped |

B vs A is the thesis as written in `docs/hypothesis.md`. C vs A is the
product. **C vs B is what the text component adds**, and without it the
hybrid's number is uninterpretable. Three arms across five strata need a
multiple-comparison correction, which the registry's reporting rules
already require.

## Rationale

- The choice is forced by a measurement taken before it, not by
  preference. The measurement is committed (`scripts/reachability.py`) so
  the reasoning is reproducible rather than recounted.
- It converts a claim into a boundary: the graph is at ceiling on
  structural questions and structurally incapable on questions whose
  entities carry no keyword. A boundary with a negative in it is worth
  more than an unqualified win.
- The same seed test that routes a question here — *does this question's
  entities reach the rule graph at all?* — is the routing signal Project 3
  needs. Phase 4 leaves the trilogy an empirical basis for its agent
  instead of a hunch.

## Consequences

- **`docs/hypothesis.md` is not edited.** Its a-priori predictions stay as
  written and are falsified or confirmed in Phase 6. A dated section
  records that the reachability measurement is interim evidence bearing on
  prediction 2 (graph Path Recall ≫ vector on multi-hop), which now looks
  unlikely **for arm B** — recorded, not rewritten.
- **The golden set is split before any template exists.** 20 questions
  (seed `20260809`, stratified) become the Phase 4 development subset,
  frozen in `data/golden/phase4_dev_ids.json`; the other 57 are E-001's
  evaluation set and are touched once, in Phase 6. Without this, templates
  would be written against the questions that measure them.
- **`keyword_rule_2hop` is too small to survive the split**: 1 dev, 2
  evaluation. Neither side supports a per-stratum claim about it, and
  `docs/evaluation.md` must say so rather than report a proportion over 2.
- **Text retrieval over CR text is new surface** — chunking, indexing and
  its own failure modes — inside a phase already timeboxed on text2cypher.
  If both overrun, text2cypher is the registered cut (roadmap), not this.
- **Mechanism independence holds.** `cite_search.py` helped build the
  *extraction* gold, not the 77-question golden set, so lexical retrieval
  over CR text is not contaminated for E-001. Worth stating because the
  same tool was refused inside E-003 for exactly that reason.
