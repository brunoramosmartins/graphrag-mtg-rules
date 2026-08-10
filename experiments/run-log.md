# Run Log

What actually ran, in the order it ran, with the identifiers needed to tell
whether two numbers came from the same thing.

[registry.md](registry.md) holds the *design* of each experiment — its
hypothesis, configuration and decision rule, written before the run. This
file holds the *events*: the draw that was frozen, the hash of a labelling
pass, the model a batch was generated with, the cost it incurred. A figure
whose run is not here cannot be reproduced, and a rerun that disagrees with
its entry is a bug report before it is a result.

Append only. Entries are never edited after the fact; a correction is a new
entry that says what it corrects.

Artifacts under `runs/` and `data/interim/` are gitignored — they carry CR
rule text and card oracle text, which the Fan Content Policy forbids
committing. Everything here is reproducible from the committed ids plus a
re-run.

---

## E-007 — citation coverage and support

### 2026-08-10 — audit pool drawn

Two passes of `scripts/build_golden_pool.py`, both excluding
`ids_v0.jsonl`, `authored_v0.jsonl` and `definitions_v0.jsonl`:

| pass | filter | fetched | new |
|---|---|---|---|
| 1 | plan defaults, levels 0–2, count 16 | 46 | 30 |
| 2 | `interaction_multihop`, complexity `Intermediate`+`Complicated`, levels 0–2, count 28 | 28 | 12 |

**42 questions** in `data/golden/e007_audit_pool.jsonl`; text cached under
`data/interim/e007_cache/`. Card-name overlap with the golden set: **9 of
42**, touching Blood Moon, Dress Down, Glass Golem, Hardened Scales, Ral's
Outburst, Magus of the Moon, Strionic Resonator, Yixlid Jailer.

Two earlier dry runs settled which axis to widen: judge level 0–3 with
`Complicated` returned the same 3 questions and 0 new; complexity
`Intermediate`+`Complicated` returned 14 new of 20.

### 2026-08-10 — strata assigned by hand

`scripts/classify_pool.py`, 42 decided, **31 labels changed** from the
complexity-seeded value. Achieved: `interaction_multihop` 26,
`negative_temporal` 15, `keyword_rule_2hop` 1, `rulings_2hop` **0**.

### 2026-08-10 — 10/32 split frozen

`scripts/split_golden.py draw --n 10 --seed 20260810` ->
`data/golden/e007_split.json`.
Development: `interaction_multihop` 6, `negative_temporal` 4.
Audit: `interaction_multihop` 20, `negative_temporal` 11,
`keyword_rule_2hop` 1.

### 2026-08-10 — retrieval, run twice

First run: 32 `resolved`, **10 `no_match`**; 51 cards in subgraphs against
245 planned card traversals. Investigating the first case by hand found
three linking defects (see the decision journal for the day). Retrieval was
**re-run after the fix, before any sufficiency label was written**:

| | before | after |
|---|---|---|
| outcomes | 32 resolved / 10 no_match | **42 resolved / 0** |
| cards in subgraph | 51 | 164 |
| rulings | 196 | 657 |
| median evidence items | 11.5 | 30 |

E-006 was re-run on the golden-set development split with the same fix and
is **unchanged** from its published table, so the Phase 4 figures stand.

### 2026-08-10 — sufficiency labelled and frozen

`data/golden/e007_sufficiency.json`, 42 labels, frozen **before any answer
was generated**.

    sha-256  c8cafaf69c1dbb62c268dfdf2995a14e68d7165bf7179b6f8d6d559fcadc76f4

Overall: `partial` 25, `insufficient` 9, `sufficient` 8.
Audit side: `sufficient` 5, `partial` 20, `insufficient` 7 — above the
registered floor of 12 answerable, so the contingency did not fire.

### 2026-08-10 — generation, round 1 estimate (dry run)

`run_e007.py generate --side dev --dry-run`:
`gpt-4o-mini` @ temperature 0, prompt `p5-a1`, `max_tokens` 700,
`token_budget` 6000, `kind_cap` 25, `rule_search` on, `text2cypher` off,
oracle-text expansions on.
10 calls, ~35,299 input + ~7,000 output tokens, **~$0.01**.
