#!/usr/bin/env bash
# Create the phase milestones. Idempotent: skips a milestone that already exists.
# Requires: gh (authenticated). REPO defaults to the current repo's origin.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "Creating milestones on $REPO ..."

milestones=(
  "Phase 0 — Foundation & Licensing"
  "Phase 1 — Ontology & Golden Set"
  "Phase 2 — Graph Backbone"
  "Phase 3 — LLM Extraction"
  "Phase 4 — Graph Retrieval"
  "Phase 5 — Grounded Generation"
  "Phase 6 — Evaluation"
  "Phase 7 — Observability & CI"
  "Phase 8 — Release"
)

existing="$(gh api "repos/$REPO/milestones?state=all" --paginate -q '.[].title' 2>/dev/null || true)"

for title in "${milestones[@]}"; do
  if grep -Fxq "$title" <<< "$existing"; then
    echo "  exists: $title"
    continue
  fi
  gh api "repos/$REPO/milestones" -f title="$title" >/dev/null
  echo "  milestone: $title"
done
echo "Done."
