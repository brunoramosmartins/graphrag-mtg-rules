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

### 2026-08-10 — sufficiency re-frozen after the audit-side re-label

`data/golden/e007_sufficiency.json`, 42 labels, still **before any answer
on the audit side was generated**.

    sha-256  534547ed84547aac1bb6fd2074f2de01d190da4cdd8138a8f58645d9fd40f5d0
    previous c8cafaf69c1dbb62c268dfdf2995a14e68d7165bf7179b6f8d6d559fcadc76f4

Overall: `partial` 24, `insufficient` 11, `sufficient` 7. The ten
development labels inside this hash are the ones carried over from the
previous freeze and are marked stale in the file — they describe the
pre-`card_core` subgraphs, and the reason is recorded with the previous
hash in the same file.

### 2026-08-10 — generation, round 3 (`p5-a3`) on the development side

10 questions, `gpt-4o-mini` @ temperature 0, ~$0.01. Mechanical read only —
the claim pass is a separate step and has not run.

| | round 1 | round 2 | round 3 |
|---|---|---|---|
| citations written | 31 | 21 | 34 |
| unresolvable handles | 3 | 1 | **0** |
| `[UNVERIFIED]` written by the model | — | yes | **no** |

Namespaces cited in round 3: `ruling` 15, `card` 11, `rule` 6, `keyword` 2.
The card citations are new and are `card_core` evidence — the oracle text
that used to be absent is now being cited.

Refusals against the frozen sufficiency labels: **2 refusals, both on the
2 `insufficient` questions; all 3 `sufficient` answered.** Zero
over-refusal, zero answering where the evidence was labelled absent.

**Read with the caveat that these ten labels are stale**: they describe
the pre-`card_core` subgraphs and are marked as such in the file. The
development side is where the prompt was iterated, so it carries no
threshold — this is the instrument reporting itself sound, not a result.
The three registered prompt rounds are spent; the audit side runs once on
`p5-a3` with no further iteration.

### 2026-08-10 — claim worksheet segmented (development side)

10 answers -> **118 rows**, `data/golden/e007_claims.jsonl`.

    sha-256  c4bcec635f0fc1227de0a738f318260701f0d6375e52fed304f2f33a9ad537de

Recorded before a single label was written, and before the annotator was
told anything about the rows — including how many carry a citation, which
is the numerator of coverage. Knowing that split while deciding which
sentences are `factual` is precisely the pressure the exclusion rule and
the 20% void exist to remove.

### 2026-08-10 — development-side claim pass (descriptive; no verdict)

118 rows labelled, worksheet `c4bcec635f0f`, sufficiency `534547ed8454`.

    coverage   0.361 = 35/97   exclusions 21/118 = 0.178
    support    0.429 [0.265, 0.595]   9 clusters, 35 cited claims
    failures   claim_not_in_evidence 15, right_evidence_wrong_reading 4,
               unrelated_evidence 1, wrong_leaf 0, evidence_absent 0
    refusals   over-refusal 0, unsupported answering 0, correct refusal 2

The development split is where the prompt was iterated; it carries no
threshold and no branch of the decision rule is evaluated on it. Logged as
a peek in [../docs/decision-journal.md](../docs/decision-journal.md) with
the numbers seen and the sentence that no decision is taken from them.

`wrong_leaf` is **zero of 20 unsupported rows** — the failure E-007
predicted would dominate. `claim_not_in_evidence` is 15. Scored on the
audit, not here.

**Support cannot be read on the audit until the shuffled-citation control
exists.** The registry commits the second DoD clause to a comparison
against that control and to nothing else, so a support interval reported
without it has no pre-committed reading.

### 2026-08-10 — generation, audit side (32 questions) — and one loss

`p5-a3`, temperature 0, ~$0.02. **28 answered, 4 refused** (rg-119,
rg-2027, rg-1973, rg-1766). No claim has been labelled yet.

**The development answers were destroyed by this run.** `generate` wrote
to a single default path for both sides, `runs/` is gitignored, and the
audit run overwrote the ten development answers. What survives: the
labelled worksheet (118 rows, hash `c4bcec635f0f`, now
`data/golden/e007_claims_dev.jsonl`) and every figure it produced, already
in this log. What does not: the answer text those labels described, so the
development rows can no longer be re-read or re-derived, and no control
can be built for that side.

Nothing about the audit is compromised — its answers are the file that
survived, generated after a freeze that was recorded before it. The
development side was the iteration split and carried no threshold, which
is the only reason this is a loss rather than a void run.

Fixed rather than noted: `generate` now writes `e007_answers_<side>.jsonl`
and refuses to overwrite an existing answers file without `--force`, and
the refusal fires before anything is read so a paid run cannot die after
the damage. Two tests pin it.

### 2026-08-10 — audit claim worksheet segmented

32 answers -> **411 rows**, `data/golden/e007_claims_audit.jsonl`.

    sha-256  3cdfdf85fb211aada77e43db37dd341cb8cb0637fcfe15482f90e7db321adb93

12.8 sentences per answer, against 11.8 on the development side — the same
shape, so the segmentation is behaving consistently across sides. Recorded
before any label exists, and before the annotator has been told how many
rows carry a citation.

**Control capped at two cited claims per answer** (registry amendment, same
day, before any support judgement existed). 411 rows put the full control
near 240 blind slots on top of the real support pass, and a control that
does not get finished measures nothing. Every answer that can contribute a
pair still does — the bootstrap resamples questions, so the interval lives
on the cluster count. The deviation is conservative: a smaller sample
widens both arms, and the clause needs the real arm's lower bound to clear
the control's upper bound.

### 2026-08-10 — mid-labelling: the exclusion rate may void coverage

    bare list-marker rows   49 of 411 (11.9%), across 12 answers
    labelled                210 rows — 150 factual, 60 non_factual
    exclusions              38 artefact + 22 genuine = 0.286, void at 0.20

Written down before the pass is finished and before the outcome is known.
The segmenter is registered and frozen and is not being changed; the
annotator was given the number together with the instruction that it must
not move a single label. E-007d is registered for the successor question —
whether a list-aware claim unit measures the same thing — and explicitly
does not become E-007's result.

### 2026-08-10 — audit claim labels complete: coverage is VOID by one row

    411 rows   328 factual   83 non_factual
    exclusions 83/411 = 0.2019   void above 0.20   (0.20 x 411 = 82.2)

    of the 83 exclusions:
      bare list markers   47   (11.4% of all rows)
      genuine             36   ( 8.8% of all rows)

The registered rule voids the coverage figure and it is applied as
written. **One reclassification would clear it**, which is precisely why
none is made: a denominator that moves when the result is inconvenient is
what this threshold exists to prevent, and a rule is not worth less
because the margin is thin.

The diagnosis is unambiguous and is reported as a diagnosis, never as a
repaired figure: without the segmenter's list-marker rows the exclusion
rate would be 8.8%. That is what the void rule says it detects — the
metric measuring the segmentation rather than the answers. E-007d, which
asks whether a list-aware claim unit measures the same thing, was
registered **before this number existed**, with its reading committed in
advance.

Coverage itself has not been read yet: eight support judgements remain and
there is no reason to look at a figure before the pass that feeds it is
closed.

### 2026-08-10 — shuffled-citation control built

    seed        20260810
    cap         --per-answer 2
    slots       124 = 62 real + 62 shuffled
    clusters    31 of 31 answers holding cited claims — every one represented
    left out    59 cited claims, by the cap

Judged blind by slot, arm withheld, per-arm counts withheld until the last
slot. The real arm's support distribution exists in the worksheet and is
deliberately not being read or reported before the control pass closes:
an annotator who knows the real rate can aim the control at it, which is
the same reason `compare` refuses while any slot is open.

### 2026-08-10 — E-007 audit result

    coverage   0.369 = 121/328   exclusions 83/411 = 0.2019 VOID
    support    0.488 [0.400, 0.583]   31 clusters, 121 cited claims
    control    real 0.565 [0.435, 0.694]   shuffled 0.161 [0.065, 0.274]
    failures   claim_not_in_evidence 45, right_evidence_wrong_reading 9,
               evidence_absent 4, unrelated_evidence 4, wrong_leaf 0
    refusals   over-refusal 0 | unsupported answering 8 | correct refusal 1
               partial: 3 refused / 16 answered

DoD **not met on clause 1** (coverage 0.369 against 1.0, budget spent),
**met on clause 2** (real lower bound 0.400 or 0.435 depending on which
interval the registered sentence means, both above the control's 0.274),
over-refusal gate clear at zero.

The headline risk is not in the DoD at all: **8 of 9 `insufficient`
subgraphs were answered rather than refused.** No threshold covers it by
design, and it is exactly the surface E-008 tests.

Full verdict and scored predictions in the registry entry.
