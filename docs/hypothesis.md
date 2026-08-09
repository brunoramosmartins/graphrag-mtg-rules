# Hypothesis (v0.2)

> Judge-level Magic: The Gathering rules questions — card interactions,
> keyword→rule→ruling chains, deck legality — are **not** answerable by
> vector RAG, because the answer is not contained in any single passage:
> it is a **path** between cards, numbered rules, and rulings.
> Representing the official knowledge (Scryfall oracle data, the
> Comprehensive Rules parsed as a tree with cross-references, rulings
> linked by **metrics-validated** LLM extraction) as a graph with an
> explicit ontology, and answering by traversal with **path + rule-number
> citations**, produces answers that are correct, traceable, and
> auditable where the Project 1 vector pipeline — applied to the *same*
> textual corpus — fails in a measurable way. The machinery is first
> **calibrated on an academic multi-hop QA benchmark (MetaQA)** to
> separate "the pipeline works" from "the domain is hard".

## Central axis

The vector pipeline retrieves **what is written**; the graph retrieves
**what is connected**. In Magic, a judge's answer is literally a path:
card → rule → exception → ruling. And a path can be cited — by rule
number.

## What the project actually claims (and what it does not)

Some judge questions require **reasoning over** the retrieved rules, not
only retrieval. The claim is deliberately split so it stays honest:

- **The graph retrieves the right context** — measured by *Entity
  Recall* and *Path Recall* (Phase 6).
- **The LLM reasons over that context** — measured by *Answer
  Correctness given sufficient context* (Phase 6).

Phase 6 separates these two layers explicitly; that separation is what
prevents overclaiming.

## Predicted result (declared a priori, to be falsified in Phase 6)

Per-stratum win-rate of GraphRAG vs. the vector baseline:

| Stratum | Expectation |
|---|---|
| 1-hop definition ("what does deathtouch do?") | **Tie** — the answer is a passage; vector is fine. |
| 1-hop legality ("is X legal in Standard today?") | Graph wins — a `LEGAL_IN` edge with status vs. hoping some text says it. |
| 2-hop (keyword→rule, card→rulings→rules) | Graph wins. |
| Multi-hop interaction (Humility × Opalescence) | Graph wins by a large margin. |
| Negative / temporal (deck legality, ban timing) | Graph wins; the negative answer cites the exact violated edges. |

If the graph does **not** win where predicted, that is a reportable
result, not a failure to hide — the limitations section is mandatory.

## Falsifiable predictions

1. On 1-hop definition questions, vector recall@k ≈ graph entity recall.
2. On multi-hop interaction questions, graph Path Recall ≫ vector
   passage coverage of the gold path.
3. MetaQA Hits@1 per hop falls within plausible KGQA literature ranges;
   any divergence is analyzed in writing (the "visnights" standard).

See `docs/evaluation.md` (source of truth, authored in Phase 6) for the
full metric definitions.

## Interim evidence, 2026-08-09 — nothing above is edited

Everything above stays as declared. This section records evidence that
arrived in Phase 4 and bears on prediction 2, because hiding it until
Phase 6 would be worse than reporting it early, and rewriting the
prediction to match it would be worse than either.

`scripts/reachability.py` measured whether the deterministic graph can
reach each question's gold CR rules from its gold entities, expanding k
hops through `REFERENCES` plus the CR tree. On `definition_1hop` and
`keyword_rule_2hop` it reaches **100%** at k=2 inside ~200 rules. On
`interaction_multihop` it reaches 38% only at k=6, where the ball holds
1515 of 3308 rules — and **15 of those 30 questions produce no seed at
all**, because their cards have no keyword abilities (*Humility*,
*Opalescence*).

**Prediction 2** — graph Path Recall ≫ vector passage coverage on
multi-hop interaction — therefore looks unlikely **for the graph-only
arm**. It is left standing and will be scored as written in Phase 6.

The architectural response is [ADR-007](adr/adr-007-hybrid-retrieval-graph-entities-text-rules.md):
the graph supplies entities and the structural strata, text retrieval
supplies rules where the graph cannot seed. That changes what the system
is, so E-001 now runs three arms — vector (A), graph-only (B), hybrid (C)
— because a hybrid measured only against vector could win on its text
component alone and prove nothing about the graph. **B vs A is the
prediction above.** C vs B is what the text component adds.

The claim this project ends up making is narrower than the one at the
top of this file and better supported: the graph is at ceiling where the
question's entities carry structure, and structurally incapable where
they do not. What connects *Humility* to the layer system is what its
text means — inference, which E-003 measured at F1 0.125.
