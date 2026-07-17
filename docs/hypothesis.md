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
