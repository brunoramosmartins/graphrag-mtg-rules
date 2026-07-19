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

**Phase 0 — Foundation & Licensing.** Scaffold, ADRs, licensing gate
(G1), and a minimal Neo4j compose are in place. Roadmap: Phases 0→8
(vector→graph→agentic trilogy). See [`docs/`](docs/).

## Quickstart

```bash
# 1. Environment
py -3.11 -m venv .venv        # any Python >= 3.11
source .venv/Scripts/activate # Windows Git Bash; use .venv/bin/activate on *nix
pip install -e ".[dev]"

# 2. Configuration
cp .env.example .env          # set NEO4J_PASSWORD

# 3. Database
docker compose up -d --wait   # Neo4j on bolt://localhost:7687 (Browser: :7474)
                              # --wait blocks until healthy; Bolt needs ~30s and
                              # connecting sooner fails the handshake, not the config
python scripts/smoke_neo4j.py # verifies the driver can reach Neo4j

# 4. Checks
ruff check .
pytest -m "not integration"

# 5. Licensing-gate sanity (confirms sources still resolve)
python scripts/fetch_samples.py
```

## Repository layout

```
docs/          hypothesis, data-sources (G1), contingency (G1–G4), ADRs 001–005
src/graphrag_mtg/   Python package (etl · graph · extraction · retrieval · generation · evaluation · observability)
scripts/       smoke_neo4j.py · fetch_samples.py · setup_github.sh · git_bootstrap.sh
tests/         unit tests (+ @integration against Neo4j)
data/          raw/ & interim/ gitignored; golden/ versioned per license
.github/       issue/PR templates, CI, remote-setup scripts
docker-compose.yml   Neo4j (app + Phoenix added in Phase 7)
```

## Documentation

- [Hypothesis](docs/hypothesis.md) — the v0.2 thesis and a-priori predictions
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
