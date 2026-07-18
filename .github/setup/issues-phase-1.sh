#!/usr/bin/env bash
# Create the Phase 1 issues (one per deliverable). Run once.
# Requires: gh (authenticated), labels.sh and milestones.sh already run.
# REPO defaults to the current repo's origin.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
MILESTONE="Phase 1 — Ontology & Golden Set"
echo "Creating Phase 1 issues on $REPO ..."

create() {
  local title="$1" labels="$2" body="$3"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" \
    --milestone "$MILESTONE" --body "$body" >/dev/null
  echo "  issue: $title"
}

create "[Phase 1] Confirm RulesGuru API endpoint + question-content license (G1→G2)" \
  "phase:1,type:data,gate:contingency,priority:critical" \
  "## Context
The one open item carried over from Gate G1. The sample fetch confirmed
that \`rulesguru.net\` 301-redirects to \`rulesguru.org\`, and that
\`https://rulesguru.org/api/questions/\` now returns 404 — the API path
changed. Both the current endpoint and the **license of the question
content** must be settled before the golden set is built, since they
decide whether we version questions or only IDs + a fetch script.

## Tasks
- [ ] Identify the current RulesGuru question endpoint (payload + method)
- [ ] Fix \`scripts/fetch_samples.py\` (rulesguru) to hit the real endpoint
- [ ] Read the RulesGuru repo LICENSE + any content notice; record the
      question-content license verdict
- [ ] Update \`docs/data-sources.md\`: close the open G1 item; set the
      golden-set versioning decision (questions vs. IDs + fetch)

## Definition of Done
- [ ] \`python scripts/fetch_samples.py --source rulesguru\` saves a real sample
- [ ] docs/data-sources.md records the license verdict + versioning decision"

create "[Phase 1] etl/download.py with SHA-256 verification" \
  "phase:1,type:data,priority:high" \
  "## Context
Incremental, idempotent ingestion (Project-1 standard): reloads must be
safe. Scryfall bulk is daily; CR/MTR/IPG update on WotC's cadence.

## Tasks
- [ ] Download Scryfall bulk (oracle_cards, rulings), CR txt, MTR/IPG pdf
- [ ] SHA-256 change detection; skip re-download when hash matches
- [ ] Descriptive User-Agent + polite rate limiting for Scryfall
- [ ] Everything lands in data/raw/ (gitignored); nothing committed

## Definition of Done
- [ ] One command downloads + verifies all sources; re-run is a no-op when unchanged
- [ ] Hashes recorded; \`--limit\`/dry-run friendly for cost discipline"

create "[Phase 1] Ontology v1 + graph/schema.py (constraints, indexes, layouts)" \
  "phase:1,type:graph,priority:high" \
  "## Context
Fix the ontology **from the questions, not the other way around**. Only
what a golden-set question uses enters the schema. Stack/turn structure
stay as CR text, NOT nodes.

## Tasks
- [ ] docs/ontology.md v1 (nodes, relations, properties; versioned v0→v1)
- [ ] graph/schema.py: constraints + indexes as code
- [ ] Layout modeling decision: double-faced, split, adventure, meld
      (Card vs. Printing)

## Definition of Done
- [ ] Ontology covers 100% of the golden-set questions (table-test in notes/)
- [ ] schema.py applies cleanly; no node models the CR stack/turn structure"

create "[Phase 1] Golden set v0 — 60–80 stratified judge questions (Gate G2)" \
  "phase:1,type:data,gate:contingency,priority:critical" \
  "## Context
Curate the golden set v0 from RulesGuru: stratified sampling by
difficulty/topic, with hops and gold-entities annotated. This is the
project's ground truth for the graph-vs-vector comparison.

## Tasks
- [ ] data/golden/questions_v0.jsonl (or ids_v0.jsonl + fetch, per G1 verdict)
- [ ] 60–80 questions across strata: 1-hop definition, 1-hop legality,
      2-hop keyword→rule, 2-hop rulings, multi-hop interaction, negative/temporal
- [ ] Freeze the snapshot with cards resolved; store the snapshot hash
- [ ] Each multi-hop question: written justification of why vector RAG should fail
- [ ] 1-hop strata present where vector is expected to tie (evaluation honesty)

## Definition of Done
- [ ] **Gate G2:** ≥ 60 stratified questions with reliable answer key; else fallback plan recorded
- [ ] Every question has hops + gold-entities; snapshot hash committed"

create "[Phase 1] Annotation guide — hops, gold-entities, gold-path" \
  "phase:1,type:documentation,priority:normal" \
  "## Context
Make the golden-set annotation reproducible and consistent.

## Tasks
- [ ] Document how to mark hops, gold-entities, and the gold-path per question
- [ ] Worked examples for each stratum

## Definition of Done
- [ ] A second annotator could reproduce the labels from the guide alone"

create "[Phase 1] Exploration notebook — bulk stats + CR parse sample" \
  "phase:1,type:data,priority:normal" \
  "## Context
Explore the real data to prove the ontology is buildable before locking it.

## Tasks
- [ ] Bulk statistics: card / face / keyword counts
- [ ] Sample of the CR parse (structure only; no CR text committed)

## Definition of Done
- [ ] Download + exploratory parse reproducible by one command"

create "[Phase 1] Normalization tests — Æ/accents, faces, mana cost" \
  "phase:1,type:data,priority:normal" \
  "## Context
Card-name and cost normalization must be correct before linking (feeds
the card-name linking cascade, ADR-004).

## Tasks
- [ ] Normalize names with Æ / accents; multi-face cards; mana cost parsing
- [ ] Unit tests in tests/ (no live Neo4j)

## Definition of Done
- [ ] tests/ cover the normalization edge cases; pytest green"

echo "Done."
