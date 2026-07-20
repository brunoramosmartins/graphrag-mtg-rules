# Extraction annotation guide (Phase 3)

How to annotate the frozen 120-ruling sample so that a second annotator
reaches the same labels from this document alone. Companion to
[`annotation-guide.md`](annotation-guide.md) (golden set); this one covers
the **extraction gold**: card mentions and rule citations inside ruling
text. These annotations are the denominator of every Phase 3 F1 — sloppy
spans here poison every number downstream.

## The files

- `data/golden/extraction_sample_ids.json` — the frozen draw (ids,
  strata, seed). Never edited after the draw.
- `data/interim/extraction_annotation_todo.jsonl` — the same rulings with
  full text (gitignored; regenerate with
  `python scripts/sample_rulings_for_annotation.py` if lost — the fixed
  seed reproduces the draw).
- `data/golden/extraction_annotations.jsonl` — **what you write.** One
  row per ruling, offsets + ids only plus short verbatim quotes (licence:
  no bulk ruling text in the repo).

## Row schema

```json
{
  "ruling_id": "ab12…",
  "oracle_id": "host-card-oracle-id",
  "stratum": "homonym",
  "mentions": [
    {"surface": "Opt", "start": 57, "end": 60, "target_oracle_id": "…"},
    {"surface": "Fear", "start": 102, "end": 106, "target_oracle_id": null}
  ],
  "cited_rules": [
    {"rule_number": "702.19e", "start": 0, "end": 64, "quote": "…"}
  ],
  "notes": "",
  "annotator": "brm",
  "verified": true
}
```

## Step 1 — mentions

Mark **every occurrence that could be read as a card name**, then decide
each one:

- `target_oracle_id` set — the ruling uses the word as that card's name.
- `target_oracle_id: null` — it looks like a card name but is ordinary
  English ("creatures with fear" is the keyword, not the card Fear).
  These negatives are what make tail precision measurable; do not skip
  them.

Rules of thumb:

- The host card's own name is **not** a mention (`MENTIONS` means
  *another* card). Annotate it only when the ruling names a *different*
  card that shares the name — which does not happen; skip hosts.
- Offsets are Python string offsets into the ruling's `text` exactly as
  stored (`text[start:end] == surface`). Check with a REPL, not by eye.
- "this creature", "the exiled card" and other anaphora are **not**
  mentions in v1 — note them in `notes`; they are the documented
  out-of-scope tail (revisited only if error analysis demands it).

## Step 2 — cited rules

For each rule the ruling actually *turns on* (not merely brushes past):

- `rule_number` — the most specific rule that carries the point; the
  lettered leaf (`613.4b`) beats the parent (`613.4`). Look numbers up in
  the CR text; never cite from memory. Layer-system trap: layer 7b is
  `613.4b`, **not** `613.7` (see the golden-set guide, step 4).
- `start`/`end` — the passage that invokes the rule (usually one clause,
  never the whole ruling). `quote` repeats it verbatim, trimmed to the
  clause.
- A ruling that just restates card text cites **nothing**. Empty
  `cited_rules` is a common, correct answer — these negatives keep the
  extractor honest.
- Two to three rules is a lot for one ruling. At four, re-read: you are
  probably citing scenery.

Finish every session with the guard:

```bash
python scripts/check_cr_citations.py
```

## Step 3 — verify

Set `verified: true` only when: every offset round-trips
(`text[start:end] == surface`/`quote`), every cited number exists in the
downloaded CR, and every homonym occurrence got an explicit yes/no
(`target_oracle_id` set or null).

## Session plan (anti-burnout, from the roadmap)

Three sessions of ~2 hours: (1) all `multiword` + `plain` rows — fast,
builds calibration; (2) `homonym` rows — the slow, valuable tail;
(3) `explicit` rows + a re-pass over anything marked in `notes`. The dev
split (30 rulings) is annotated in session 1 as warm-up: it doubles as
the prompt-iteration set, and its labels are never reported as results.

## What this feeds

- `evaluation/metrics.py` (`evaluate_by_stratum`) — linking and citation
  P/R/F1 with bootstrap CIs, stratified by the sampling strata.
- **E-003 in `experiments/registry.md`** — registered *after* this file
  is frozen and *before* the extractor runs on the annotation split.
  Order matters: sample → annotate → register → run.
