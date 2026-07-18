# Golden-set annotation guide

How to annotate a golden-set row so that a **second annotator reaches the
same labels from this document alone**. Companion to
[`golden-set.md`](golden-set.md), which defines the strata and the record
schema; this one is the procedure.

## What you are (and are not) annotating

For RulesGuru rows you are **classifying**, not judging Magic.

- **Not yours to verify:** the answer. It is judge-curated — that is the
  whole reason we use RulesGuru.
- **Yours to verify:** our labels — `stratum`, `hops`, `gold_entities`,
  `gold_cr_rules`, `gold_path` — and then `verified: true`.

The full question and answer text lives in
`data/interim/golden_cache/rg-<id>.json` (gitignored). The committed row
in `data/golden/ids_v0.jsonl` never contains that text, by licence.

## Step 0 — open the pair

```bash
# the row you are annotating
grep '"rg-6370"' data/golden/ids_v0.jsonl

# the full text behind it
python -c "import json;d=json.load(open('data/interim/golden_cache/rg-6370.json',encoding='utf-8'));print(d['questionSimple']);print();print(d['answerSimple'])"
```

## Step 1 — `stratum`

**Ignore the seeded value.** It was derived from RulesGuru `complexity`,
and that heuristic is systematically wrong: `complexity` measures how hard
the question is to *answer*, not how many graph hops it needs. Reclassify
from scratch.

Read the **question shape**, and use RulesGuru `tags` as the strongest
hint:

| If the question… | Stratum | Tag hints |
|---|---|---|
| asks whether a card is legal in a format | `legality_1hop` | — |
| asks what one keyword does, nothing else | `definition_1hop` | `Evergreen keywords` |
| needs one keyword's rule plus a sub-rule or cross-reference | `keyword_rule_2hop` | `Evergreen keywords`, `Non-evergreen keywords` |
| is answered by a card's official ruling citing a rule | `rulings_2hop` | `Resolving objects` |
| composes **two or more effects/permanents** whose result no single rule states | `interaction_multihop` | `Layers`, `Continuous effects`, `Replacement effects`, `Combat` |
| turns on something **not** happening, or on timing/order | `negative_temporal` | `Zone-changes`, `Turn structure`, `Timing` |

**Tie-breaker.** If two or more permanents/effects must be reasoned about
*together*, it is `interaction_multihop` — even when RulesGuru calls it
Simple. Interaction is about composition, not difficulty.

## Step 2 — `hops`

Count the **edges a graph traversal would need**, not the sentences in the
answer.

- `1` — one lookup (card → format; keyword → its rule).
- `2` — one lookup plus one step (keyword → rule → sub-rule; card →
  ruling → rule).
- `3+` — two or more effects composed, or a rule reached through another
  rule's cross-reference.

When torn between 2 and 3, ask: *does answering require holding two
separate rules in play at once?* If yes, `3`.

## Step 3 — `gold_entities`

Seeded from RulesGuru `includedCards` and usually correct. Fix only to:

- **add** a keyword or ability the answer turns on (`mentor`, `trample`)
  when it isn't a card name;
- **remove** a card that appears in the scenario but has no bearing on
  the answer (procedural filler).

## Step 4 — `gold_cr_rules`

Seeded from RulesGuru `citedRules`, which is reliable **when present** —
but it is often empty, and then you fill it.

Rules of thumb:

- Cite the **most specific rule that carries the answer** — the lettered
  leaf (`613.4b`) beats the parent (`613`).
- Two to four rules is normal. If you need six, the question is probably
  `interaction_multihop` and you may be over-citing; keep the ones the
  gold path actually traverses.
- Beware the layer system's numbering, which trips everyone up:

  | | |
  |---|---|
  | `613.1a–g` | defines layers 1–7 |
  | `613.2` | sublayers **of layer 1** (copy) |
  | `613.3` | CDAs within layers 2–6 |
  | **`613.4a–d`** | **sublayers of layer 7** (7a CDA, 7b set, 7c modify, 7d switch) |
  | `613.7` | **timestamp** order within a layer or sublayer |

  Layer 7b is `613.4b`, **not** `613.7`. This mistake was in four of our
  own authored rows before the guard caught it.

Always finish with the guard:

```bash
python scripts/check_cr_citations.py
```

It fails if a cited rule does not exist in the downloaded CR — cheap
insurance, and it re-runs after every quarterly CR release.

## Step 5 — `gold_path`

One line describing the traversal the graph must perform, in the
ontology's vocabulary ([`ontology.md`](ontology.md)). Not prose about the
ruling — the *path*:

```
(:Card {Inkmoth Nexus})-[:HAS_KEYWORD]->(:Keyword)-[:DEFINED_BY]->(:Rule {613.4b})
```

If you cannot write a path, the ontology may be missing an edge. That is
a schema bug, not an annotation problem — raise it against the ontology
issue rather than inventing a path.

## Step 6 — `vector_should` (+ reason)

Our **a-priori** prediction, recorded before any run. Be conservative:
over-claiming graph advantage is the failure mode that would discredit
the whole evaluation.

| Value | Use when |
|---|---|
| `tie` | the answer is stated in one passage; both retrievers should find it |
| `lose` | the graph edge is cleaner, but the text could still work |
| `fail` | the answer is a **path**; no single passage states it |

`vector_should_reason` is **required** when the value is `fail` or the
stratum is `interaction_multihop` / `negative_temporal`. Write what a
passage-retriever would be missing — not "the graph is better".

## Step 7 — `verified`

Set `true` only when steps 1–6 are done and the guard passes. What
`verified` means per origin is spelled out in
[`golden-set.md`](golden-set.md#files-shards).

---

## Worked examples

Three real rows, each teaching a different correction.

### rg-6370 — reclassify the stratum

> Amir animates Inkmoth Nexus and attacks with it. Nathaly then flashes in
> Dress Down. What does Inkmoth Nexus look like?
> **Answer:** a 1/1 Blinkmoth Land Artifact Creature with no abilities;
> ability-changing effects apply in timestamp order.

- Seeded as `keyword_rule_2hop`, hops 2 — **wrong**.
- Tags are `Abilities, Layers, Continuous effects`; two continuous effects
  (animation, Dress Down) resolve by timestamp. That is composition.
- **`stratum: interaction_multihop`, `hops: 3`.**
- `gold_cr_rules`: seeded `613.3`, `613.7`. Timestamp (`613.7`) is right;
  the ability-removal layer is layer 6, so `613.1f` fits better than
  `613.3` (which is about CDAs in layers 2–6).
- `vector_should: fail` — "the resulting characteristics come from
  applying two continuous effects in timestamp order; no passage states
  what this permanent looks like."

### rg-2711 — reclassify, and notice the replacement effect

> Angel of Vitality, a Brutal Cathar that exiled Aerith Gainsborough, and
> an Aerial Assault killing the Cathar. How many +1/+1 counters does
> Aerith end with?
> **Answer:** one — Aerith returns before Aerial Assault finishes
> resolving; Angel of Vitality replaces the life-gain event.

- Seeded as `rulings_2hop`, hops 2 — **wrong**. It is not a card→ruling
  lookup; it composes a zone-change timing rule with a replacement effect.
- **`stratum: interaction_multihop`, `hops: 3`.**
- `gold_cr_rules` seeded `610.3`, `700.1`, `614.1a` — good, keep.
- `gold_entities`: drop cards that are only scenery; keep the ones the
  answer turns on.

### rg-539 — stratum right, citations missing

> Six creatures with mentor attack; the triggers are ordered; how much
> damage? **Answer:** 23, resolving the mentor triggers in order.

- Seeded `interaction_multihop`, hops 3 — **correct**, keep.
- `citedRules` came back **empty**, so `gold_cr_rules` is `[]`. Fill it:
  the mentor keyword's rule plus the trigger-ordering rule. Look the
  numbers up in the CR text rather than guessing:

  ```console
  $ grep -nE "^702\.[0-9]+\. Mentor" data/raw/comprehensive_rules.txt
  4965:702.134. Mentor
  ```

  So mentor is `702.134` (with `702.134a` giving the actual trigger
  wording — prefer the lettered leaf, per step 4). Add the rule covering
  the order simultaneous triggers are put on the stack, and you are done.

- Then re-run `python scripts/check_cr_citations.py`.

---

## Consistency checklist

Before marking a batch `verified`:

- [ ] Stratum re-derived from the question shape, not from the seeded value
- [ ] `hops` counts traversal edges, not answer sentences
- [ ] Most-specific CR rules cited; layer-7 sublayers are `613.4a–d`
- [ ] `gold_path` written in ontology vocabulary
- [ ] `vector_should_reason` present for every `fail` / interaction / negative row
- [ ] `python scripts/check_cr_citations.py` exits 0
- [ ] `pytest -m "not integration"` still green (the loader validates every row)
