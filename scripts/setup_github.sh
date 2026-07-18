#!/usr/bin/env bash
# One-shot GitHub remote setup: labels -> milestones -> Phase 0 issues.
#
# Prerequisites:
#   1. Install GitHub CLI:  https://cli.github.com/   (Windows: winget install GitHub.cli)
#   2. Authenticate:        gh auth login
#   3. Have an 'origin' remote pointing at the GitHub repo.
#
# Usage:
#   bash scripts/setup_github.sh                 # auto-detect repo from origin
#   REPO=brunoramosmartins/graphrag-mtg-rules bash scripts/setup_github.sh
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) not found. Install it and run 'gh auth login' first." >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run 'gh auth login'." >&2
  exit 1
fi

export REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "Target repository: $REPO"
echo

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.github/setup" && pwd)"
bash "$DIR/labels.sh"
echo
bash "$DIR/milestones.sh"
echo
read -r -p "Create Phase 0 issues now? [y/N] " ans
if [[ "${ans:-}" =~ ^[Yy]$ ]]; then
  bash "$DIR/issues.sh"
else
  echo "Skipped issues. Run '.github/setup/issues.sh' later to create them."
fi
echo
echo "GitHub setup complete."
