#!/usr/bin/env bash
# Create the Phase 0 issues (one per deliverable). Run once.
# Requires: gh (authenticated), labels.sh and milestones.sh already run.
# REPO defaults to the current repo's origin.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
MILESTONE="Phase 0 — Foundation & Licensing"
echo "Creating Phase 0 issues on $REPO ..."

create() {
  local title="$1" labels="$2" body="$3"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" \
    --milestone "$MILESTONE" --body "$body" >/dev/null
  echo "  issue: $title"
}

create "[Phase 0] Licensing gate G1 — verdict per source" \
  "phase:0,type:documentation,gate:contingency,priority:critical" \
  "## Context
Verify licenses before writing any ingestion pipeline (gate G1).

## Tasks
- [ ] Confirm Scryfall guidelines (attribution, rate limit, no bulk in repo)
- [ ] Confirm WotC Fan Content Policy covers non-commercial CR/MTR/IPG use
- [ ] Confirm the RulesGuru QUESTION-CONTENT license (open item)
- [ ] Record per-source verdict + golden-set versioning decision

## Definition of Done
- [ ] docs/data-sources.md has OK / OK-with-restriction / BLOCKED per source
- [ ] Sample download from each source succeeds (scripts/fetch_samples.py)"

create "[Phase 0] ADRs 001–005 accepted" \
  "phase:0,type:documentation,priority:high" \
  "## Context
Record the decisions that shape the project.

## Tasks
- [ ] ADR-001 domain choice (Magic) + gates
- [ ] ADR-002 Neo4j
- [ ] ADR-003 deterministic parse + LLM extraction
- [ ] ADR-004 card-name linking cascade
- [ ] ADR-005 templates first, text2cypher second

## Definition of Done
- [ ] All five ADRs status Accepted under docs/adr/"

create "[Phase 0] Scaffold + docker-compose + CI green" \
  "phase:0,type:infrastructure,priority:high" \
  "## Context
Stand up the repo scaffold with Project-1 standards active from commit 1.

## Tasks
- [ ] pyproject.toml + package skeleton; pip install -e . works
- [ ] docker-compose.yml brings up a healthy Neo4j with a persistent volume
- [ ] scripts/smoke_neo4j.py passes
- [ ] .github templates + ci.yml (lint + unit + integration)

## Definition of Done
- [ ] docker compose up -> Neo4j healthy; smoke test passes
- [ ] pytest tests/ and ruff check . pass; CI green"

create "[Phase 0] Initial README with problem + Fan Content notice" \
  "phase:0,type:documentation,priority:normal" \
  "## Context
Public entry point; carries the required compliance notice.

## Tasks
- [ ] Problem statement + trilogy cross-link
- [ ] Fan Content Policy notice + Scryfall attribution
- [ ] Quickstart (compose up, smoke test)

## Definition of Done
- [ ] README renders; notice present"

echo "Done."
