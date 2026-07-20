#!/usr/bin/env bash
# Create the Phase 2 issues (one per deliverable). Run once.
# Requires: gh (authenticated), labels.sh and milestones.sh already run.
# REPO defaults to the current repo's origin.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
MILESTONE="Phase 2 — Graph Backbone"
echo "Creating Phase 2 issues on $REPO ..."

create() {
  local title="$1" labels="$2" body="$3"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" \
    --milestone "$MILESTONE" --body "$body" >/dev/null
  echo "  issue: $title"
}

create "[Phase 2] etl/cards.py — oracle cards, faces, legalities to Pydantic models" \
  "phase:2,type:data,priority:high" \
  "## Context
Build the structured half of the deterministic backbone from the Scryfall
oracle bulk: one node per oracle identity, with faces modeled as faces of
the same identity (double-faced, split, adventure). Meld handling was
deferred in the Phase 1 ontology and stays a documented limitation for now.
Strict Pydantic parsing so a silent Scryfall schema change breaks loudly.

## Tasks
- [ ] Card / CardFace models mirroring \`docs/ontology.md\` (oracle_id, name,
      mana_cost, mana_value, type_line, oracle_text, colors, color_identity, layout)
- [ ] Reuse \`etl/normalize.py\` for name/face/mana-cost normalization
- [ ] Legality edges (HAS_LEGALITY {status}) from the \`legalities\` map
- [ ] Skip non-playable layouts (art_series, token) per the exploration findings
- [ ] Provenance on every row: source bulk file + sha256

## Definition of Done
- [ ] All 38k oracle cards parse; multi-face cards expand to faces
- [ ] Strict validation: an unexpected field/shape raises, never silently drops
- [ ] Unit tests in tests/ over layout + legality edge cases (no live Neo4j)"

create "[Phase 2] etl/cr_parser.py — deterministic CR tree + explicit REFERENCES" \
  "phase:2,type:data,priority:critical" \
  "## Context
The heart of the deterministic layer: parse the Comprehensive Rules txt
into a numbered \`Rule\` tree (number, level, text) with HAS_SUBRULE edges,
plus explicit \`REFERENCES\` edges from \"see rule 704.5\"-style citations
via regex. The LLM only adds what the parser cannot (Phase 3). The CR ships
UTF-8 **with a BOM** (use utf-8-sig) and the glossary is its own section
shape — both were found in the Phase 1 exploration.

## Tasks
- [ ] Tokenize the numbered tree: 3-digit rule, dotted sub-rule, lettered leaf
- [ ] HAS_SUBRULE parent/child edges from the numbering alone
- [ ] Explicit REFERENCES edges by regex over \"see rule N\" / \"rule N\"
- [ ] Handle the glossary section as its own case (keyword definitions)
- [ ] Golden-file test: a frozen small CR excerpt in tests/fixtures/ with
      the expected tree (fair-use sized)

## Definition of Done
- [ ] Parser covers 100% of the numbered rules in the current CR
      (expected count vs. obtained — the exploration found 3,120)
- [ ] Golden-file tests pass; parsing is fully deterministic (no LLM)
- [ ] No CR text is committed — only the frozen fixture excerpt"

create "[Phase 2] graph/loader.py — idempotent MERGE, incremental by source hash" \
  "phase:2,type:graph,priority:high" \
  "## Context
Load the backbone into Neo4j with idempotent MERGE in batches, incremental
by source hash (Project-1 standard adapted): the daily Scryfall bulk and the
quarterly CR reload must be safe to re-run. Cypher lives in named constants /
templates.py, never inline f-strings.

## Tasks
- [ ] Batched MERGE for Card/CardFace/Format/Rule/Keyword/Ruling + edges
- [ ] Skip a source whose sha256 matches the last load (manifest reuse)
- [ ] Cypher in named constants; parameterized, never f-string-built
- [ ] notes/phase2-backbone.md: node/edge counts by type, CR tree depth, top keywords
- [ ] @pytest.mark.integration tests against the CI Neo4j service container

## Definition of Done
- [ ] Full re-run creates no duplicates; unchanged source = no-op (proven by test)
- [ ] Update simulation: load a prior CR then the current one yields the correct
      graph with no manual rebuild
- [ ] schema.py constraints/indexes applied before load"

create "[Phase 2] Sanity check — 6 golden questions answered by manual Cypher" \
  "phase:2,type:eval,priority:normal" \
  "## Context
Prove the backbone answers the structural 1–2 hop strata before any LLM
retrieval exists. Manual Cypher, not the pipeline — this is the backbone
acceptance test.

## Tasks
- [ ] 6 golden-set questions (legality, keyword to rule, card to rulings)
      answered by hand-written Cypher in a notebook or script
- [ ] Each query traces the gold_path from the golden set

## Definition of Done
- [ ] All 6 sanity questions return the correct answer via manual Cypher
- [ ] Queries reference the golden-set ids they satisfy"

create "[Phase 2] Generate rulings_2hop questions from the Scryfall rulings corpus" \
  "phase:2,type:data,priority:high" \
  "## Context
Carried from Phase 1. The annotation pass showed RulesGuru is an
interaction-puzzle corpus: none of its 30 rows is a card to official ruling
to rule lookup, so the \`rulings_2hop\` stratum is empty. Its real source is
the 77,999 Scryfall rulings the downloader already fetches — a generator
like the legality one can build it once the backbone loads rulings.

## Tasks
- [ ] Generator analogous to scripts/generate_legality_questions.py, over
      data/raw/scryfall_rulings.json
- [ ] Prefer rulings that cite a CR rule so the gold path is Card to Ruling to Rule
- [ ] Validate with scripts/check_cr_citations.py

## Definition of Done
- [ ] >= 10 verified rulings_2hop questions in the golden set
- [ ] docs/golden-set.md distribution updated"

create "[Phase 2] definition_1hop from the CR glossary — restores the tie stratum" \
  "phase:2,type:eval,gate:contingency,priority:critical" \
  "## Context
Carried from Phase 1. No stratum currently predicts \`tie\`. Without one, a
reported graph win is not falsifiable — the evaluation needs strata where the
vector baseline should draw. \`definition_1hop\` (\"what does <keyword> do?\")
is the natural one: the answer lives in a single CR glossary passage, so both
retrievers should find it. Depends on the cr_parser glossary output.

## Tasks
- [ ] Extract keyword definitions from the parsed CR glossary (702.x + glossary)
- [ ] Generate definition_1hop questions with vector_should=tie
- [ ] Update docs/golden-set.md distribution

## Definition of Done
- [ ] >= 10 verified definition_1hop questions, all vector_should=tie
- [ ] docs/evaluation.md records why a tie stratum is required for falsifiability"

echo "Done."
