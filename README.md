# graphrag-mtg-rules

**The graph that resolves the stack** — a GraphRAG system that answers
judge-level *Magic: The Gathering* rules questions by traversing a
knowledge graph and citing the path it took.

> *Part 2 of a 3-project RAG series:*
> **[rag-pix-regulation](https://github.com/brunoramosmartins/rag-pix-regulation) (vector) → graphrag-mtg-rules (graph) → agentic-rag (router, upcoming).**

---

## The problem

Vector RAG answers questions whose answer is *written somewhere*:
retrieve the passage, cite it, done. But a whole class of rules
questions has no such passage — the answer is a **path** through the
system:

> *"I control Humility and Opalescence — what happens?"*

Nobody wrote that answer down. It emerges only by traversing
card → ruling → the layer system (CR 613) → sub-rules → timestamps.
This project represents the official knowledge — Scryfall oracle data,
the **Comprehensive Rules** parsed as a numbered tree with
cross-references, and official rulings linked by metrics-validated LLM
extraction — as a graph with an **explicit ontology**, and answers by
**traversal with path + rule-number citations**.

The claim is measured, not asserted: the pipeline is first **calibrated
on an academic multi-hop benchmark (MetaQA)**, then run **head-to-head
against a vector baseline** (the Project 1 pipeline over the same text)
on a **judge-curated golden set** (RulesGuru). See
[`docs/hypothesis.md`](docs/hypothesis.md).

## The result

**The hypothesis was not confirmed.** On the 57-question evaluation split,
opened once on 2026-09-12, judge-scored answer correctness is:

| | vector (A) | graph (B) | hybrid (C) |
|---|---|---|---|
| **all 57 questions** | **0.60** [0.47, 0.71] | **0.61** [0.48, 0.73] | **0.65** [0.52, 0.76] |
| `definition_1hop` (11) | 0.73 | **0.91** | **0.91** |
| `legality_1hop` (15) | 0.80 | **0.93** | **0.93** |
| `interaction_multihop` (22) | **0.41** | 0.27 | 0.36 |

The registered analysis — B vs A, exact McNemar, Holm-corrected over the four
strata with n ≥ 7 — returns **`inconclusive` on all four**. Adjusted *p* =
1.0000 throughout. The three arms are indistinguishable at this sample size.

And the direction runs the wrong way. The graph is ahead on the one-hop
strata, where the answer is a typed edge; **the vector baseline is ahead on
`interaction_multihop`** — the 22-question stratum this project's thesis was
written about. That is the opposite of the registered stratification.

Three measurements say why, and each is registered:

- **The gap is vocabulary, not topology.** On the 26 questions the pipeline
  had already failed, the graph retrieves 7 of the 64 rules the answer keys
  require — and a plain lexical index over all 3,308 rules does *worse* at a
  realistic context size (6/64), reaching only 12/64 when pulled to a hundred
  rules per question. A question names cards and player verbs; a rule is
  written in defined terms, and nothing here bridges the register. *(That
  population was selected for being hard, so this says what nothing reaches
  **there** — it is not an estimate of retrieval quality overall.)*
- **The weak link is the model declining, not the model reasoning wrong.**
  Calibrating on MetaQA first: at a matched 16-item context with the complete
  two-step chain *verified* present, correctness is **0.672** against 0.890 at
  one hop — and of those 82 failures, **39 are refusals and 19 are unparseable
  output, against 24 wrong entities.** Fewer than one failure in three is a
  reasoning error. The same shape reappeared here: six of the graph arm's seven
  refusals land on `interaction_multihop`, and removing them halves its
  deficit.
- **The retrieval comparison is budget-confounded**, by a 3× rule set before
  the split opened. At matched token budget the vector arm keeps a median of
  40.5 items against the graph's 12.0 — 3.38×. So the headline retrieval
  figure is the token-normalised one: **A 0.030, B 0.112**.

Two more results are negative in a way worth reading: the pairwise
head-to-head is **withdrawn** on both contrasts involving the vector arm, by a
pre-registered gate on how often the judge reverses itself when the two
answers swap places (0.333 and 0.368, against a 0.20 limit); and the judge
itself is **published ungated** at 0.727 [0.598, 0.827] agreement against a
0.720 threshold, with its own ceiling beside it.

Every number above was predicted, bounded, or gated in
[`experiments/registry.md`](experiments/registry.md) **before** the run that
produced it. [`docs/evaluation.md`](docs/evaluation.md) is the source of truth
and carries the limitations that bound each one.

**One of them was withdrawn, and the withdrawal is on the record.** The second
bullet used to quote a three-hop figure and conclude that generation, not
retrieval, was the bottleneck — the project's most-repeated sentence. Before
paying for the follow-up experiment built on it, we rendered a single scored
case: a three-hop question whose context held hop one and eleven unrelated
films. The model refused, correctly, and the harness had scored that as a
generation failure. The cause was a chain search that accepted any path to an
accepted answer *string* rather than one that answers the question, and **126
of the 137 questions in that cell (92%) were one-step chains**. The three-hop
column is withdrawn, the follow-up was suspended unspent, and the one- and
two-hop columns — whose chains match their declared depth on every question —
are what the bullet now quotes. The repair, the measurement and what survives
are in the 2026-09-13 amendments to E-002 and E-012.

## Why Magic

The Comprehensive Rules are a genuine dense-regulatory-text proxy —
hierarchical numbering (601.2b), cross-references, exceptions that
override general rules, quarterly updates — with something no corporate
corpus offers publicly: a **ground truth validated by experts at scale**
(judge-curated questions) and an **academic calibration benchmark**. The
techniques transfer 1:1 to legal, regulatory, and fraud domains; Magic
was chosen because it lets us *measure the truth*. Full rationale in
[`docs/adr/adr-001-domain-choice-magic.md`](docs/adr/adr-001-domain-choice-magic.md).

## Status

**Phase 8 — Demo, README & Release.** The pipeline runs end to end: the
graph, retrieval, grounded generation, a three-arm evaluation with confidence
intervals, OpenTelemetry spans on every stage, a live demo, and CI that
exercises all three arms with no API key. The evaluation split was opened once
and the result is above. Roadmap: Phases 0→8 (vector→graph→agentic trilogy).

**What this project is actually a demonstration of.** The graph did not beat
the baseline, and the interesting part is that this is knowable. The
hypothesis was registered in July with its falsifier named; the decision rule
was pinned in August before any arm ran; the split was drawn, frozen, and
touched once. When the answer came back inconclusive there was nothing left to
negotiate — which is the whole point of writing the rule down first. A system
that can only report a win is not an evaluation.

## Quickstart

Docker and nothing else. Timings are measured, not aspirational — see
[`docs/onboarding.md`](docs/onboarding.md).

```bash
cp .env.example .env
# Set NEO4J_PASSWORD, and CR_TXT_URL to the TXT link on
# https://magic.wizards.com/en/rules — that page is JS-rendered, so the
# link cannot be resolved automatically, and WotC replaces the file every
# release without a redirect, so an old URL 404s.

docker compose --profile app up -d --wait
docker compose exec app python scripts/bootstrap.py
```

**~2 min 54 s** from an empty database to a cited answer, plus about a
minute to build the image. Running it again is **~27 s**: every step is
idempotent, so the first run is the cold path and the rest are warm.

That builds the **graph**, which is what the shipped system retrieves
from. The vector baseline it is compared against is a separate index that
costs an embedding call per document — `python scripts/run_eval.py index`,
which prints its estimate before spending anything.

<details>
<summary>Working from a host venv instead</summary>

```bash
py -3.11 -m venv .venv        # any Python >= 3.11
source .venv/Scripts/activate # Windows Git Bash; use .venv/bin/activate on *nix
pip install -e ".[dev]"

cp .env.example .env          # set NEO4J_PASSWORD
docker compose up -d --wait   # Neo4j alone on bolt://localhost:7687 (Browser: :7474)
                              # --wait blocks until healthy; Bolt needs ~30s and
                              # connecting sooner fails the handshake, not the config
python scripts/smoke_neo4j.py # verifies the driver can reach Neo4j
python scripts/bootstrap.py   # same four steps, ~11s warm

ruff check .
pytest -m "not integration"
python scripts/fetch_samples.py   # licensing-gate sanity
```

</details>

## The demo

![The demo answering "What does deathtouch do?": the question is picked from the development split, retrieval returns 8 evidence items in 321 tokens with outcome RESOLVED, the subgraph draws Deathtouch linked by DEFINED_BY to rule 702.2 and on to its six subrules, the evidence list shows 8 traversed and 0 text-retrieved, and the generated answer cites 6 of the 8 items.](docs/images/demo.gif)

*Arm C against a live Neo4j, `What does deathtouch do?` from the development
split. The keyword the question named is ringed; `DEFINED_BY` reaches rule
702.2; `HAS_SUBRULE*` walks down to its six subrules. Eight citable nodes, each
with the path that reached it — and the answer cites six of them.*

A question, the answer it produced, and the subgraph that produced it — live
against Neo4j, not a replay.

```bash
pip install -e ".[app]"
docker compose up -d --wait
streamlit run app/demo.py
```

Three things it is built not to do, because each would make it prettier and
less true:

- **It does not draw an edge it does not have.** Text-retrieved evidence has
  no traversal — its recorded path is a sentence, not a path — so it is listed
  apart from the graph instead of being wired into it.
- **It does not spend a token without being asked.** Retrieval is free and
  runs on the button; generation is a second button that shows the context
  size first.
- **It reports how much of its own evidence the answer used.** On the worked
  example below it is 1 of 8 retrieved items — the grounding finding, visible
  where a reader meets it rather than buried in a table.

Nodes are ringed when the question named them, so the picture shows where the
walk started and how far it got. Card evidence carries its Scryfall image and
a link out; no card image is ever stored in this repository.

## Architecture

```mermaid
flowchart LR
    subgraph ingest["Ingestion — idempotent, SHA-256 change detection"]
        SC["Scryfall bulk<br/>cards · rulings"]
        CR["Comprehensive Rules<br/>parsed as a numbered tree"]
        EX["LLM extraction<br/>behind extraction/gate.py"]
    end

    subgraph store["Neo4j — explicit ontology"]
        G[("Card · CardFace · Format<br/>Keyword · Rule · Ruling")]
    end

    subgraph retrieve["Retrieval — one span per stage"]
        L["linking<br/>mentions → nodes"]
        R["routing<br/>which templates to run"]
        T["traversal<br/>named Cypher templates"]
        TS["text search<br/>TF-IDF or dense"]
        B["budget<br/>token cap, per-kind cap"]
    end

    A["generation<br/>grounded, cites or refuses"]
    V["evaluation<br/>3 arms · CIs · paired tests"]

    SC --> G
    CR --> G
    CR --> EX --> G
    G --> L --> R
    R --> T --> B
    R -.->|only when routed| TS --> B
    B --> A --> V

    style G fill:#4c78a8,color:#fff
    style A fill:#e45756,color:#fff
    style V fill:#54a24b,color:#fff
```

Two constraints shape this more than any technique choice. **Nothing an LLM
extracted enters the graph without passing `extraction/gate.py`** — schema,
evidence span, confidence, dedupe — and the CR tree itself is parsed
deterministically, with the LLM adding only relations the parser cannot.
**Every stage is an OpenTelemetry span**, and a traversal span carries the walk
it made, which is what the next section shows.

## What a question does

Every stage is an OpenTelemetry span, and the span for a traversal carries
the walk it made. This is one question through the shipped arm, in Phoenix:

![A Phoenix trace of one question through arm C: the root span graphrag.query with linking, routing, four traversals, budget and generation beneath it; the selected traversal lists the evidence it added and the graph paths that reached it.](docs/images/trace-arm-c-traversal.png)

*Arm C (graph + text, routed), question `hand-humility-plus-counter` from
[`data/golden/authored_v0.jsonl`](data/golden/authored_v0.jsonl), text half in
`--mode lexical` — pin 2's registered ablation, chosen so the figure did not
need a vector index rebuilt over a corpus that changes daily. Corpus of
2026-09-10. `Total Cost $0` means token usage is not reported, not that the
run was free.*

The selected `traversal` is the point of the picture:

```
graphrag.template          keyword_definition
graphrag.evidence.keys     keyword:Counter · rule:701.6 · rule:701.6a · rule:701.6b
graphrag.paths             (:Keyword {Counter})
                           (:Keyword {Counter})-[:DEFINED_BY]->(:Rule {701.6})
                           (:Rule {701.6})-[:HAS_SUBRULE*]->(:Rule)
                           (:Rule {701.6})-[:HAS_SUBRULE*]->(:Rule)
```

One template resolved a keyword the question named, followed `DEFINED_BY` to
the rule that governs it, and walked `HAS_SUBRULE*` down to the subrules — four
citable nodes, each with the path that reached it. Those paths are what the
generated answer cites, which is what makes an answer checkable rather than
plausible.

The last two path lines are identical because that pattern does not name the
subrule it arrives at; `evidence.keys` at the same index does (`701.6a`,
`701.6b`). It is a known defect, left in place deliberately: the path string is
inside `evidence_sha256`, and E-007's sufficiency labels point at those hashes,
so repairing it is a deliberate re-fingerprint rather than a cosmetic edit.
See [the decision journal](docs/decision-journal.md).

**A trace names its arm.** The graph arms and the vector arm share exactly two
span names — `budget` and `generation`, which genuinely are the same operation —
and a test pins that intersection. Arm A never appears to walk; arms B and C
never appear to fuse. Phase 6 lost a run to a mislabel that every summary number
agreed with, and a viewer reproduces that failure the moment two arms name their
stages alike.

**Question text is withheld by default.** The golden set's RulesGuru questions
live in this repo as ids plus a gitignored fetch, and a trace is a thing that
gets screenshotted into a README. `--record-questions` opts in, and refuses a
batch whose rows keep their text in the cache.

<details>
<summary>Reproducing it</summary>

```bash
docker compose --profile observability up -d --wait   # Phoenix on :6006
python scripts/run_eval.py run --arm C --limit 1 --trace
```

`run` is the only command whose trace covers a whole question; every other
one is a single stage. Add `--tag <name>` for a run that is not the
experiment — it writes to `runs/<name>_*` instead of `runs/e001_*`, which is
what stops a trace capture from overwriting judged answers.

</details>

## Reproducing the result

The evaluation split is opened **once** — `run_eval.py` refuses
`--split-side eval` without an explicit flag and a dated journal entry, because
there is no second draw. The artefacts of that run are in `runs/` (gitignored);
these three commands reproduce the analysis from them, and none of them spends
a token:

```bash
python scripts/verify_legality_keys.py                          # the gate: answer keys still valid
python scripts/e001_analysis.py                                 # the registered decision rule
python scripts/run_e010.py proxy --side eval                    # precision, and the 3x budget gate
```

The development split runs freely and costs nothing to re-measure:
`python scripts/run_eval.py run --arm C --limit 1`.

## Limitations

Stated here because they bound every number above; the full list is in
[`docs/evaluation.md`](docs/evaluation.md).

- **n = 57.** Exact McNemar needs 6 discordant pairs one way to reach
  *p* < 0.05 and Holm's strictest step needs 8:0. The largest discordance
  observed anywhere is 5. This split could not have produced a confirmation at
  these effect sizes — which was computed and written down in August, not
  discovered afterwards.
- **The judge is not validated.** Agreement with a human is 0.727 [0.598,
  0.827] against a 0.720 threshold, so it is published descriptively with its
  ceiling beside it. It does read the supplied key rather than its own
  knowledge — a key-fidelity control over deliberately wrong keys scored 30/30
  — but `partial` and `incorrect` overlap textually and that is where both the
  judge and the human annotator are unstable.
- **The retrieval comparison is budget-confounded** at 3.38× median item
  count, so token-normalised precision is the headline retrieval figure.
- **Precision was judged by one annotator, unblinded.** The blinding claim was
  withdrawn by its own pre-registered rule: a classifier seeing only the
  *kind* of each evidence item identifies the producing arm 72% of the time.
  The arms return different kinds of evidence, and that difference is the
  treatment — so item-level blinding here is unachievable, not merely unachieved.
- **One stratum is unmeasured for precision.** A filter the human pass did not
  need removed all five `legality_1hop` questions from that sample.
- **The demo runs a registered ablation**, TF-IDF rather than the dense hybrid
  text half, and says so on screen.

## Repository layout

```
docs/          hypothesis, evaluation, decision journal, data-sources (G1), ADRs
experiments/   registry.md — every hypothesis, rule and amendment, dated
src/graphrag_mtg/   Python package (etl · graph · extraction · retrieval · generation · evaluation · observability)
app/           the Streamlit demo (demo.py) and its two pure helpers
scripts/       bootstrap · run_eval · the per-experiment harnesses and analyses
tests/         unit tests (+ @integration against Neo4j)
data/          raw/ & interim/ gitignored; golden/ versioned per license
runs/          gitignored run artefacts — the only copy of generated answers
.github/       issue/PR templates, CI, remote-setup scripts
docker-compose.yml   Neo4j by default; `app` and `phoenix` behind compose profiles
Dockerfile           the application container (ETL, retrieval, evaluation)
```

## Documentation

- [Onboarding](docs/onboarding.md) — the cold and warm paths, timed, and what each covers
- [Hypothesis](docs/hypothesis.md) — the v0.2 thesis and a-priori predictions
- [Evaluation](docs/evaluation.md) — metrics, results, and every limitation that bounds them
- [Changelog](CHANGELOG.md) — what each phase shipped, and what `v1.0.0` concludes
- [Experiment registry](experiments/registry.md) — every hypothesis, decision rule and
  amendment, dated; amendments are appended, never rewritten
- [Decision journal](docs/decision-journal.md) — the dated calls, including the ones
  that went against the author's own instrument
- [Annotation methodology](docs/annotation-methodology.md) — how a score against a
  hand-made gold is given a ceiling and a decomposition; written to be reused elsewhere
- [Data sources & licensing (Gate G1)](docs/data-sources.md)
- [Contingency gates G1–G4](docs/contingency.md)
- [Architecture Decision Records](docs/adr/README.md)

---

## Compliance

*Unofficial Fan Content permitted under the Fan Content Policy. Not
approved/endorsed by Wizards. Portions of the materials used are property
of Wizards of the Coast. ©Wizards of the Coast LLC.*

Card data and images are provided by **[Scryfall](https://scryfall.com)**.
This project is **strictly non-commercial**. Bulk card data, rules text,
and card images are **never** committed to this repository — they are
downloaded on demand with hash verification. Project source code is
licensed under the [MIT License](LICENSE).
