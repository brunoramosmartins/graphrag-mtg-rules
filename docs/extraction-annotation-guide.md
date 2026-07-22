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
- `data/interim/extraction_annotations_draft.jsonl` — **where you work**
  (gitignored). Generate it with
  `python scripts/prefill_extraction_annotations.py`: every ruling
  arrives with deterministic linker seeds — exact/loose mentions filled
  in, homonym candidates marked `"target_oracle_id": "UNDECIDED"` — and
  `cited_rules` deliberately empty (seeding those from any model would
  grade the extractor against itself).
- `data/golden/extraction_annotations.jsonl` — the committed result:
  offsets + ids only plus short verbatim quotes (licence: no bulk ruling
  text in the repo). Never edited by hand — produced by
  `python scripts/check_extraction_annotations.py --publish`, which
  refuses rows with broken offsets, unknown rule numbers, or leftover
  `UNDECIDED` sentinels.

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
- `target_oracle_id: "UNDECIDED"` — the prefilled state of every homonym
  seed. Replace each with an oracle_id or `null`; the publish script
  rejects leftovers.

Seeded exact/loose mentions are usually right — confirm, don't trust.
The seeds only speed up precision checking: **read the full text anyway**,
because mentions the scanner *missed* are exactly what makes recall
measurable, and only you can add those.

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

**Interpretation: liberal (decided 2026-07-21, see the decision journal).**
Cite the CR rule that *governs* the interaction the ruling describes, even
when the ruling never states the number. A ruling about a spell fizzling
because its only target became illegal cites `608.2b`, though it says
"the spell won't resolve" in players' language. This is the whole premise
of `CITES_RULE`: the rulings are written without numbers, and the value is
recovering the rule they lean on. Under-citing (leaving the governing rule
blank because it was not spelled out) makes the gold measure nothing.

For each rule the ruling *turns on*:

- `rule_number` — the most specific rule that carries the point; the
  lettered leaf (`613.4b`) beats the parent (`613.4`). Look numbers up in
  the CR text; never cite from memory. Layer-system trap: layer 7b is
  `613.4b`, **not** `613.7` (see the golden-set guide, step 4).
- `start`/`end` — the passage that invokes the rule (usually one clause,
  never the whole ruling). `quote` repeats it verbatim, trimmed to the
  clause.
- Empty `cited_rules` is correct **only** when the ruling turns on no rule
  at all — a pure restatement of card text with no interaction ("This
  triggers once per turn."). If you can name the governing rule, cite it.
- Two to three rules is a lot for one ruling. At four, re-read: you are
  probably citing scenery.

**Finding the number without memorizing the CR.** The ruling's language
points at a chapter; grep it:

```bash
# a targeting/resolution ruling -> chapter 608 (resolving spells)
grep -nE "^608\.[0-9]+" data/raw/comprehensive_rules.txt | head
# a keyword -> look the keyword up, then its 701/702 rule
grep -niE "^70[12]\.[0-9]+\. Trample" data/raw/comprehensive_rules.txt
```

Common chapters: 601 casting, 608 resolving, 613 layers, 700–704
state-based actions / keywords, 509 combat. The worksheet prints the host
card's keywords so you know which keyword rules might apply.

Finish every session with the guard:

```bash
python scripts/check_cr_citations.py
```

## Step 3 — verify

Set `verified: true` only when: every offset round-trips
(`text[start:end] == surface`/`quote`), every cited number exists in the
downloaded CR, and every homonym occurrence got an explicit yes/no
(`target_oracle_id` set or null).

## Worked example

A real `homonym` row from the dev split (host card: Crib Swap).

> If the target creature is an illegal target by the time Crib Swap tries
> to resolve, the spell won't resolve. No player will create a
> Shapeshifter token.

The prefill produced one mention and no citations:

```json
{"surface": "Shapeshifter", "start": 133, "end": 145,
 "target_oracle_id": "UNDECIDED", "seed": "surface",
 "candidates": [{"oracle_id": "2bb2f9ed-…", "name": "Shapeshifter"}, … 6 total]}
```

Three decisions, in order:

1. **"Crib Swap" is absent from the mentions — correct.** It is the host
   card, and `MENTIONS` means *another* card. Nothing to do.
2. **"Shapeshifter" → `null`.** Six real cards carry that name, but here
   the word is a **creature type** on a token, not a card being named.
   This is the single most common homonym pattern in the corpus, and the
   negative is as valuable as any positive: it is what stops the linker
   from scoring a false positive for free.
3. **`cited_rules`** — the ruling is about a spell failing to resolve
   because its only target became illegal. That is rule `608`'s territory;
   the leaf about a spell with no legal targets is what carries the point.
   Look the number up in the CR (never from memory), quote the clause it
   rests on, and record the offsets:

```json
{"rule_number": "608.2b", "start": 0, "end": 76,
 "quote": "If the target creature is an illegal target by the time Crib Swap tries to resolve"}
```

Then set `"annotator": "brm"` and `"verified": true`, and run the checker.

**Two habits worth keeping.** Check offsets in a REPL rather than by eye
(`text[133:145] == "Shapeshifter"`), and when a ruling turns on nothing
citable, leave `cited_rules` empty — an honest empty list is a correct
annotation, and roughly a quarter of rulings deserve one.

## Session plan (anti-burnout, from the roadmap)

Three sessions of ~2 hours: (1) all `multiword` + `plain` rows — fast,
builds calibration; (2) `homonym` rows — the slow, valuable tail;
(3) `explicit` rows + a re-pass over anything marked in `notes`. The dev
split (30 rulings) is annotated in session 1 as warm-up: it doubles as
the prompt-iteration set, and its labels are never reported as results.

## What this feeds

- `evaluation/metrics.py` (`evaluate_by_stratum`) — linking and citation
  P/R/F1 with bootstrap CIs, stratified by the sampling strata.
- **E-003 in `experiments/registry.md`** — registered 2026-07-20, after
  the sample froze and before any extractor run. Order: sample →
  register → annotate → run. **Blinding rule:** never run the extractor
  on the annotation split before labels are published — the dev split
  alone drives prompt iteration.
