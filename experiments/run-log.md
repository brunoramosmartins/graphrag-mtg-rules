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

### 2026-08-10 — generation round 1, development subset (prompt `p5-a1`)

10 answers, ~$0.01. **7 answered, 3 refused.** Refusal behaviour against the
frozen sufficiency labels was clean:

| sufficiency | n | behaviour |
|---|---|---|
| `sufficient` | 3 | 3 answered — **zero over-refusal** |
| `insufficient` | 2 | 2 refused — **zero unsupported answering** |
| `partial` | 5 | 4 answered, 1 refused — both correct by the registered rule |

**Three unresolvable citation handles, and only one is a fabrication:**

- `ruling:64146c8d7bb54c70da3bf95e60124` against the real
  `64146c8ff8d7bb54c70da3bf95e60124` — a **transcription** error on 32 random
  hex characters, pointing at the right ruling;
- `ruling:702.16f` — a rule number written into the `ruling:` namespace, a
  **format** error;
- `rule:701.7` — a real CR rule that is not in the context. The only genuine
  `evidence_absent`.

Coverage and support were **not** measured this round; the diagnosis above is
mechanical (handle resolution and the frozen sufficiency labels) and needed no
claim labelling. Recorded as a deviation from "each round records coverage,
support and refusal": rounds that fail on an instrument defect are diagnosed
from mechanical signals, and the claim pass runs when the instrument is sound.

**Instrument fix, not a prompt patch.** Rulings are now shown in the context
under a short ordinal (`[ruling:3]`) because a model cannot reliably copy a
32-character hex id, and scoring a mistyped id as a fabricated citation fills
a measurement of *grounding* with noise from *typing*. Rule numbers keep their
own value — short, meaningful, and the project's differentiator. A correctly
copied real id still resolves. Prompt version `p5-a1` -> `p5-a2`.

## 2026-08-10 — `card_core`: 164 → 195 cards, and 32 labels reopened

Found by hand-reading one sufficiency case rather than by any metric.
*Guardian of the Guildpact* linked correctly, exists in the graph, and
appeared in no subgraph: it has zero rulings, and every card traversal
reached the node through a relationship. A card with no rulings and no
keywords contributed nothing at all — not even its oracle text.

| | before | after |
|---|---|---|
| distinct cards reaching a subgraph | 164 | 195 |
| median evidence items per question | 30.0 | 30.5 |
| outcomes | 42 resolved | 42 resolved |

The residual gap is repeated mentions, not a defect: **264 card traversals
planned, 195 distinct cards**, 27 questions naming the same card more than
once (rg-1186: 13 calls, 6 cards). Retrieval re-run to
`runs/e007_retrieval.jsonl`; **evidence changed on 42 of 42 questions**.

**Reopened the audit side only** — 32 labels — keeping the 10 development
labels marked stale. Re-labelled composition, still before any answer on
that side was generated:

| | `sufficient` | `partial` | `insufficient` |
|---|---|---|---|
| before | 5 | 20 | 7 |
| after | 4 | 19 | 9 |

21 of 32 unchanged, 7 of the 11 moves away from sufficiency. The prediction
that oracle text would convert `partial` into `sufficient` was wrong, and
is recorded as wrong. Contingency re-checked against the unchanged floor:
23 against 12, does not fire.

**The generation guard fired on this and was comparing the wrong thing.**
It compared the serialized context; what a sufficiency label describes is
the evidence — these nodes, this text, these paths — not its formatting.
It now compares `evidence_fingerprint()` over `kind|key|text|template|
path|distance`. That check earned its keep immediately: when rulings moved
to short handles, **0 of 42 fingerprints differed while 41 contexts did**,
so the labels provably still held and no re-labelling was spent on a
presentation change.

**Round 3 queued (`p5-a2` → `p5-a3`), one change only.** `p5-a2` explained
what happens to an unresolvable handle, naming the `UNVERIFIED` marker, and
round 2's answers started writing `[UNVERIFIED]` themselves — a token the
audit machinery emits became something the model could assert about itself.
The sentence is replaced by the instruction that actually helps: if no
handle supports the sentence, do not write it. This is the last of the
three registered iteration rounds; the audit side runs on whatever `p5-a3`
measures.
