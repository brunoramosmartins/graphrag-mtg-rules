# Changelog

Phase tags mark the roadmap's checkpoints; `v1.0.0` is the release. Dates are
the day the work was finished, not the day it was tagged.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project versions by roadmap phase rather than by semantic API surface —
it is a study, not a library, and nothing here is imported by anyone else.

## [1.1.0] — 2026-09-13

**A claim this project had repeated for months was withdrawn, and what replaced
it was measured the same day.** Nothing in 1.0.0 is deleted; 1.0.0's headline
result stands untouched. What changed is a sentence about *why* it came out
that way, and the sentence was wrong.

### Withdrawn

- **"Generation is the bottleneck, not retrieval" is withdrawn at three hops**,
  along with the figures that carried it (E-002's 0.339, E-012's 0.511). The
  conditioning clause — *"conditional on the answer being present in the
  evidence the model received"* — was operating as *"an accepted answer string
  was reachable"*, which is a weaker and different thing.
- Found by rendering **one** scored case before paying for the follow-up
  experiment built on it: a three-hop question whose context held hop one and
  eleven films released in 1992. The model refused, correctly, and the harness
  scored that as a generation failure. **126 of the 137 questions in that cell
  (92%) were accepted on a one-step chain.**
- **E-014 was suspended before its first call**, unspent, because it was
  registered to interrogate the measurement that had just been withdrawn.
- **E-001 is untouched** — different corpus, different scorer, and
  `answer_path` has no part in it. So are the one-hop and two-hop columns,
  whose chains match their declared depth on every question.

### The replacement, measured

Three entries registered and run on 2026-09-13, none of them spending a token.

- **E-015**: at the shipped budget, retrieval delivers a three-hop chain on
  **3 of 100** questions; at sixteen times the budget, **65 of 100**.
  `enforce_budget` evicts by descending distance, so the first thing it
  discards is the hop the answer lives on. Amends E-012's holding that the
  distance-first trim is not a hazard — that holding was inferred from a size
  null measured on cells where the chain had already been reinstated.
- **E-016**: four oracle-free eviction policies over an identical pool. Two
  beat the shipped trim significantly and beat random decisively, moving reach
  0.030 → 0.120. **The registered bar asked for 0.20 and nothing was adopted.**
- **E-017**: typing the walk cuts the median three-hop context from
  **193,797 tokens to 5,676** — 30.6× — and the median then fits the budget by
  three hundred tokens, for half the questions. Of the 44 that do not fit,
  **39 pass through `has_genre` or `release_year` at the middle hop.**

**The position this leaves:** what three hops costs is neither depth nor
generation. It is **traversing a hub**.

### Added

- `scripts/e014_inspect.py` — rebuilds the exact prompt for a scored cell from
  the frozen split, the graph and the deterministic reduction rule, and prints
  it beside the answer key and the outcome. Verifies the rebuild against a
  recorded hash where one exists, and says the case is a reconstruction where
  one does not. This is what found the defect above.
- `scripts/run_e015.py`, `scripts/run_e016.py`, `scripts/e016_policies.py`,
  `scripts/run_e017.py` — the three entries, all retrieval-only.
- The `generation` span now carries `input.value`, `output.value` and a
  SHA-256 of exactly what was sent. It has been registered as an `LLM` span —
  the kind Phoenix renders with a prompt and a completion — since Phase 7, and
  both fields were empty, so the trace said what an answer *cited* and never
  what the model was looking at.
- Runs record `raw` and `prompt_sha256`, so an unparseable completion and a
  wrong answer stop being the same row on disk.

### Changed

- `metaqa.answer_path` requires a chain of the **declared depth**, and `hops`
  is keyword-only and required: a caller that does not say how deep the chain
  must be is the defect, so there is no default to fall into. Against the
  confirmatory split the repair leaves the one-hop and two-hop exclusion counts
  byte-identical and cuts three-hop from 137 usable questions to 10.
- `docs/evaluation.md` marks each withdrawn cell in place rather than deleting
  a number, and carries the three entries that replaced them.
- The README states the withdrawal — what the old claim was, the case that
  exposed it, and what survives — instead of quietly swapping the figure.

### Fixed

- `run_e012.py` refuses a run in which **every** question was excluded. An
  unloaded MetaQA instance accepts Bolt, resolves no seed, and printed
  `900 question(s), 900 excluded` before exiting 0 — word for word what a
  legitimate run prints.
- `app/paths.py` read a relation with `strip()` over a character *set*, so a
  relation beginning or ending with one of `<>-[]:` would have lost it
  silently. No relation in the schema does today, which is what made the
  defect patient.

### Known limitations, added

- **No figure from E-015, E-016 or E-017 is a correctness score.** Chain reach
  says the evidence could support an answer, never that one would be right.
- **E-017's relation sequence comes from the gold chain**, so it bounds what
  typing would buy *if something chose correctly*. Nothing there chose, and
  E-016 is the precedent for that price: its ceiling was 0.920 and the best
  oracle-free arm returned 0.120.
- **Three hops is no longer measurable on the existing splits.** Requiring a
  real three-step chain leaves 10 usable questions of 300, so any future
  three-hop generation claim needs a fresh frozen draw.

## [1.0.0] — 2026-09-12

The evaluation split was opened once and the study answered its own question.
**The hypothesis was not confirmed**, and the release ships that finding with
the machinery that makes it trustworthy.

### The result

- E-001 on the 57-question evaluation split: judge-scored correctness
  **0.60 / 0.61 / 0.65** for vector / graph / hybrid.
- The registered primary analysis — B vs A, exact McNemar, Holm-corrected over
  the four strata with n ≥ 7 — returns **`inconclusive` on all four**, adjusted
  *p* = 1.0000 throughout.
- The direction runs against the thesis: the graph leads on the one-hop
  strata and the **vector baseline leads on `interaction_multihop`**, the
  stratum the hypothesis was written about.
- The distance to significance was computed in August and confirmed in
  September: the test needs 6 discordant pairs one way, the largest
  discordance observed is 5.

### Added

- Live Streamlit demo (`app/`) against Neo4j: a question, the grounded answer,
  and the subgraph that produced it. Hierarchical left-to-right layout, nodes
  ringed when the question named them, Scryfall card images by URL, and a
  report of how much of the retrieved evidence the answer actually cited.
- `scripts/e001_analysis.py` — applies E-001's registered decision rule
  (Holm-corrected exact McNemar, three-valued per-stratum verdict, TOST on the
  declared falsifier) with validity guards that hard-fail before printing.
- `scripts/e010_analysis.py` — E-010 part (a) under its registered rule, with
  a paired cluster bootstrap over questions.
- `scripts/verify_legality_keys.py` — E-001 pin 10, which had been registered
  as mandatory and never implemented: re-verifies every legality answer key
  against the Scryfall bulk the run will read, exiting non-zero on drift.
- `scripts/run_e009.py`, `scripts/run_e010.py`, `scripts/run_e013.py`,
  `scripts/error_taxonomy.py`, `scripts/audit_key_fidelity.py` — the Phase 8
  measurement harnesses.
- README: the result above the fold, an architecture diagram, a limitations
  section, and a three-command reproduction path that spends nothing.

### Changed

- `run_eval.py` accepts the evaluation split behind `--open-the-evaluation-split`
  and a dated journal entry, and its report footers now read from the side
  actually run rather than claiming the development split.
- E-010 part (b) runs on the evaluation split, where it was always registered
  to run, and applies its own 3× budget gate rather than leaving it to be
  remembered.
- Judge published **ungated** (0.727 [0.598, 0.827] against a 0.720 threshold)
  under the registered `sufficiency` precedent, with its ceiling beside it.
- Precision published **unblinded**: the pre-registered blinding check failed
  at 0.778, and a classifier seeing only the *kind* of each evidence item
  reaches 0.722 on held-out slots. The arms return different kinds of
  evidence and that difference is the treatment, so item-level blinding is
  withdrawn as achievable rather than retried.

### Fixed

- `--help` crashed on a cp1252 console; a test now pins every CLI docstring.
- Phoenix's healthcheck used `CMD-SHELL` against a distroless image with no
  `/bin/sh`, which reported identically to the service being down.
- Span `paths` and `evidence.keys` were not index-aligned.
- An arithmetic mismatch in E-010 part (b)'s first write-up: item counts over
  20 questions quoted beside a total over 15.

### Known limitations

Carried deliberately, each with its reason in
[`docs/evaluation.md`](docs/evaluation.md): n = 57 cannot reach the registered
threshold at these effect sizes; the judge is not validated; the retrieval
comparison is budget-confounded at 3.38×; precision was judged by one
annotator, unblinded; `legality_1hop` is unmeasured for precision; E-010's
reliability ceiling has not run.

## [0.8.0] — 2026-09-10 — `v0.8-observability-ci`

OpenTelemetry spans on every pipeline stage with OpenInference span kinds,
Phoenix as viewer, Docker Compose profiles, and CI exercising all three arms
with no API key.

## [0.7.0] — 2026-09-09 — `v0.7-evaluation`

Three-arm evaluation harness, judge, rubric frozen by hash, confidence
intervals, paired tests, and the correctness ceiling.

## [0.6.0] — 2026-08-15 — `v0.6-grounded-generation`

Grounded answering with mandatory citations, refusal when the subgraph carries
nothing, and mechanical detection of fabricated citations.

## [0.5.0] — 2026-08-09 — `v0.5-graph-retrieval`

Named Cypher templates, entity linking, routing, token and per-kind budgets,
and validated Text2Cypher as the long-tail layer.

## [0.4.0] — 2026-08-09 — `v0.4-llm-extraction`

LLM relation extraction behind `extraction/gate.py` — schema, evidence span,
confidence, dedupe — with the metrics that validated it.

## [0.3.0] — 2026-07-19 — `v0.3-graph-backbone`

Neo4j schema, constraints, and idempotent loaders with SHA-256 change
detection.

## [0.2.0] — 2026-07-18 — `v0.2-ontology-and-golden-set`

The explicit ontology and the judge-curated golden set, split 20/57 and
frozen.

## [0.1.0] — untagged

Scaffold, licensing gate G1, and the Comprehensive Rules parser with
golden-file tests.
