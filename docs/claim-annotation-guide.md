# Claim annotation guide (E-007)

How to label a generated answer so that **a second annotator reaches the
same labels from this document alone**. Companion to the E-007 entry in
[`../experiments/registry.md`](../experiments/registry.md), which defines
the metrics and the decision rules; this one is the procedure.

Written **before** the first answer is generated. That ordering is the
whole point: the denominator of E-007's only threshold is decided here,
and a denominator chosen after seeing which sentences came back uncited
is not a measurement.

## Why this document has to exist

E-007's threshold reads "100% of factual claims carry a citation". The
same person writes the prompt, reads the answers, decides where claims
begin and end, and decides which of them are factual. Without a rule
fixed in advance, coverage reaches 100% the moment every uncited
sentence is reclassified as not-a-claim — and the number would mean
nothing while looking excellent.

## Step 0 — the segmentation is mechanical and comes first

```bash
python scripts/audit_answers.py segment --run <run-id>
```

The script strips every citation marker, splits the remaining text into
sentences, writes one worksheet row per sentence, and prints the file's
sha-256. **Record that hash in the run log before doing anything else.**

You do not adjust the segmentation. If a sentence was split badly, note
it in the row's `comment` and label it anyway; a segmentation you can
edit after reading the citations is a segmentation that adapts to the
result.

Citations are re-attached to the worksheet only after the hash is
recorded, so labelling in Step 1 happens on the sentence alone.

## Step 1 — `factual` or `non_factual`

**A sentence is `factual` if it asserts anything about a card, a rule, a
ruling, or what happens in a game.** That is the whole test. When in
doubt, label `factual` — the bias is deliberate, because every exclusion
shrinks the denominator of the metric being reported.

`factual`, including the cases that feel like they should not be:

- direct assertions — *"Humility removes all abilities."*
- **connective and inferential sentences** — *"So the creature is still a
  1/1."* This is the class the E-007 prediction expects round 1 to fail
  on. An inference drawn from two cited facts is still a claim about the
  game, and it is **in the denominator**. If it needs evidence to be
  true, it needs a citation.
- conditionals whose branches are claims — *"If the ability resolves
  first, the token is exiled."*
- statements about a rule's scope or ordering — *"Layer 6 applies before
  layer 7b."*
- quantities, timings, and zone changes.

`non_factual`, and this list is exhaustive — anything not on it is
`factual`:

- restating the question — *"You're asking what happens when Humility is
  on the battlefield."*
- meta-commentary about the evidence itself — *"The retrieved context
  does not include a ruling on this."*
- an explicit refusal or an explicit hedge about scope — *"I can't answer
  this from the rules I have."*
- pure discourse glue with no assertion — *"Here's how it works."*

Two traps worth naming:

- **A hedge is not an exemption.** *"It probably stays a 1/1"* asserts
  something about the game. `factual`.
- **An attributed claim is still a claim.** *"The ruling says the token
  is exiled"* asserts what the ruling says. `factual`.

The `non_factual` **exclusion rate is reported beside coverage**. Above
20%, the coverage figure is void — at that point the metric is measuring
this document rather than the answers.

## Step 2 — `cited`

Mechanical. Does the sentence carry a citation marker produced by
`generation/citations.py`? Yes or no. Nothing about quality here.

Coverage = `cited` over `factual`.

## Step 3 — `support`, for cited factual claims only

Read **only** the cited evidence, then ask: does it say what the sentence
says?

- `supported` — the evidence states it, or the sentence is a direct
  restatement of it.
- `unsupported` — it does not, and one of the taxonomy codes below says
  how.

The taxonomy is mandatory on every `unsupported` row. Without it, E-007's
prediction about *where* support fails cannot be scored, and the entry
says so.

| code | meaning |
|---|---|
| `wrong_leaf` | right rule family, wrong subrule — 608.2 for 608.2b |
| `right_evidence_wrong_reading` | the cited evidence is the right one, read incorrectly |
| `unrelated_evidence` | the citation points somewhere that does not bear on the sentence |
| `evidence_absent` | cites a handle that is not in the retrieved subgraph at all |
| `claim_not_in_evidence` | the evidence is fine and simply does not contain this claim |

**Do not consult your own Magic knowledge here.** Support asks whether
the *cited evidence* carries the claim, not whether the claim is true.
A true sentence with a citation that does not support it is
`unsupported`, and catching exactly that is the reason this column
exists.

## Step 4 — `correctness`, separately

Only after Steps 1–3 are complete for the whole answer, compare against
the RulesGuru answer key.

- `correct` / `incorrect` against the key.
- `key_stale` — the claim is correct under CR 2026-08-07 but disagrees
  with the key. Counted separately and excluded from the correctness
  denominator. RulesGuru answers were written against whatever CR was
  current at the time, and this project has already been displaced twice
  this way (`704.5w` → `704.5x`; initiative off 725.1). An answer key is
  a historical document; it cannot be migrated any more than a ruling
  can.

Correctness is **not part of the Phase 5 DoD** and is never traded
against coverage in the write-up.

## Refusals

An answer that refuses contributes **zero** factual claims. That is
correct and intended — and it is also why the refusal alone can never
carry the verdict. What decides whether a refusal was right is the
sufficiency label in `data/golden/e007_sufficiency.json`, frozen before
any answer was read:

- refusal on `insufficient` → correct behaviour;
- refusal on `sufficient` → **over-refusal**, a grounding failure, and
  non-zero over-refusal blocks the Phase 5 DoD regardless of coverage;
- answering on `insufficient` → **unsupported answering**, the
  parametric-leak surface E-008 tests directly.

Do not revisit a sufficiency label while auditing an answer. If one looks
wrong, note it and leave it — that file was frozen precisely so this
judgement could not follow the result.

## The blind re-audit (M2)

Eight of the thirty answers are re-audited blind: fresh worksheet,
segmentation regenerated from the citation-stripped text, your original
labels hidden, days elapsed printed with the result.

It happens **before any support disagreement is inspected**. Reading the
disagreements first contaminates the second pass, which is the same rule
`adjudicate.py` enforces in code for E-003a/E-003b.

The point is not agreement for its own sake. E-003a measured this
annotator's ceiling at **0.815, not 1.0**, with the disagreement
concentrated on choosing the leaf — the same axis where E-007 predicts
its commonest support failure. A support figure reported without a
ceiling is reported against a 1.0 that does not exist.
