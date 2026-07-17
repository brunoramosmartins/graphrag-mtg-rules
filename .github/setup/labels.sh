#!/usr/bin/env bash
# Create the repository's labels. Idempotent (--force overwrites color/desc).
# Requires: gh (authenticated). REPO defaults to the current repo's origin.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "Creating labels on $REPO ..."

# label|color|description
labels=(
  "phase:0|ededed|Phase 0 — Foundation & Licensing"
  "phase:1|ededed|Phase 1 — Ontology & Golden Set"
  "phase:2|ededed|Phase 2 — Graph Backbone"
  "phase:3|ededed|Phase 3 — LLM Extraction"
  "phase:4|ededed|Phase 4 — Graph Retrieval"
  "phase:5|ededed|Phase 5 — Grounded Generation"
  "phase:6|ededed|Phase 6 — Evaluation"
  "phase:7|ededed|Phase 7 — Observability & CI"
  "phase:8|ededed|Phase 8 — Release"
  "type:data|1d76db|Data & ingestion"
  "type:graph|1d76db|Graph modeling / loading"
  "type:extraction|1d76db|LLM extraction & linking"
  "type:retrieval|1d76db|Retrieval / Cypher"
  "type:eval|1d76db|Evaluation"
  "type:infrastructure|1d76db|Infra / CI / observability"
  "type:documentation|0e8a16|Docs & ADRs"
  "gate:contingency|b60205|Contingency gate (G1–G4)"
  "priority:critical|b60205|Critical"
  "priority:high|d93f0b|High"
  "priority:normal|fbca04|Normal"
)

for entry in "${labels[@]}"; do
  IFS='|' read -r name color desc <<< "$entry"
  gh label create "$name" --color "$color" --description "$desc" --repo "$REPO" --force >/dev/null
  echo "  label: $name"
done
echo "Done."
