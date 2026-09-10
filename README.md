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

**Phase 7 — Observability, Infra & CI.** The pipeline runs end to end:
the graph, retrieval, grounded generation, a three-arm evaluation with
confidence intervals, OpenTelemetry spans on every stage, and CI that
exercises all three arms with no API key. Phase 8 packages it — demo,
README, release. Roadmap: Phases 0→8 (vector→graph→agentic trilogy).

The results are not a headline yet, and
[`docs/evaluation.md`](docs/evaluation.md) says why: the MetaQA
calibration failed its floor and the divergence is analysed rather than
buried, the judge is not gated because no label reaches n ≥ 30, and the
57-question evaluation split is still closed. What is measured, and every
limitation that bounds it, is written down before any claim is made.

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

## Repository layout

```
docs/          hypothesis, data-sources (G1), contingency (G1–G4), ADRs 001–005
src/graphrag_mtg/   Python package (etl · graph · extraction · retrieval · generation · evaluation · observability)
scripts/       smoke_neo4j.py · fetch_samples.py · setup_github.sh · git_bootstrap.sh
tests/         unit tests (+ @integration against Neo4j)
data/          raw/ & interim/ gitignored; golden/ versioned per license
.github/       issue/PR templates, CI, remote-setup scripts
docker-compose.yml   Neo4j by default; `app` and `phoenix` behind compose profiles
Dockerfile           the application container (ETL, retrieval, evaluation)
```

## Documentation

- [Onboarding](docs/onboarding.md) — the cold and warm paths, timed, and what each covers
- [Hypothesis](docs/hypothesis.md) — the v0.2 thesis and a-priori predictions
- [Evaluation](docs/evaluation.md) — metrics, results, and every limitation that bounds them
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
