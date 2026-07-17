#!/usr/bin/env bash
# Bootstrap the Phase 0 branch and commit, then print the push + PR commands.
# The AUTHOR runs this — Claude never commits/pushes (see .claude/CLAUDE.md).
#
# It does NOT push automatically; it stops after committing and shows you the
# exact commands to review and run.
#
# Usage:  bash scripts/git_bootstrap.sh
set -euo pipefail

BRANCH="phase-0/foundation"

# Safety: refuse to run with a dirty index you didn't expect.
current="$(git rev-parse --abbrev-ref HEAD)"
echo "Current branch: $current"

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "Branch $BRANCH already exists — checking it out."
  git checkout "$BRANCH"
else
  echo "Creating branch $BRANCH."
  git checkout -b "$BRANCH"
fi

# Stage everything that isn't gitignored (.claude/, roadmap-*.md, notes/ are excluded).
git add -A
echo
echo "Staged changes:"
git status --short

echo
echo "Committing..."
git commit -m "chore(foundation): Phase 0 — ADRs, licensing gate, scaffold, compose

Add the Phase 0 foundation: hypothesis, ADRs 001-005, licensing gate
(G1) and contingency gates, data-sources analysis, Python package
scaffold with Neo4j smoke test, minimal docker-compose (Neo4j), CI
(lint + unit + Neo4j integration), issue/PR templates, and GitHub
setup scripts. Repo carries the Fan Content Policy notice.

Internal planning material (.claude/, roadmap, notes/) is gitignored."

echo
echo "Committed on $BRANCH. Next steps (review, then run):"
echo
echo "  # push the branch"
echo "  git push -u origin $BRANCH"
echo
echo "  # open the PR (requires gh; https://cli.github.com/)"
echo "  gh pr create \\"
echo "    --title 'chore(foundation): Phase 0 — ADRs, licensing gate, scaffold, compose' \\"
echo "    --body 'Phase 0 deliverables. See docs/ and the roadmap.' \\"
echo "    --milestone 'Phase 0 — Foundation & Licensing' \\"
echo "    --label 'phase:0,type:infrastructure'"
echo
echo "  # tag the milestone once merged"
echo "  git tag v0.1-foundation && git push origin v0.1-foundation"
