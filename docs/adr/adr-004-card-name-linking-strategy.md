# ADR-004 — Card-name linking strategy (cascade)

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Bruno Ramos Martins

## Context

Card names must be resolved in two places: **ingestion time** (linking a
ruling's text to the card(s) it mentions) and **query time** (resolving
a user's phrasing — including community nicknames like "Bolt" for
Lightning Bolt or "Sad Robot" for Solemn Simulacrum — to graph nodes).
Magic makes this genuinely hard: many cards are named after common
English words ("Opt", "Fear", "Terror", "Counterspell"), names contain
special characters (Æ, accents), and layouts split one oracle identity
across multiple faces.

## Decision

Resolve names with a **cascade**, cheapest and most precise first,
falling back to fuzzier and more expensive steps only as needed:

1. **Exact match** against normalized oracle names (case-folded, Æ/accent
   normalized, punctuation-normalized).
2. **Fuzzy / alias match** — edit distance + a curated community alias
   list ("Bolt", "Sad Robot", …).
3. **Embedding match** — BGE-M3 (reused from Project 1) over card
   names/aliases, for near-misses and paraphrases.
4. **LLM disambiguation** — only for the residual ambiguous tail (e.g. a
   homonym like "Fear" that could be the keyword or the card), with an
   evidence span required at ingestion time.

Normalization rules are unit-tested (Æ, accents, faces, mana cost).
Unresolved query-time mentions ask the user to disambiguate in the demo
rather than guessing silently.

## Rationale

- **Precision-first ordering** keeps cost and error low: exact match
  resolves the overwhelming majority; the LLM is reserved for the hard
  tail, which is exactly where the measured value lives (see ADR-003,
  gate G3).
- Aliases are a real user need in Magic and cheap to encode as data.

## Consequences

- **Positive:** cheap, testable, and the failure mode is an explicit
  disambiguation prompt, never a silent wrong link.
- **Negative / accepted:** the alias list needs occasional maintenance;
  some rare nicknames may fall through to disambiguation — acceptable
  and documented.
- **Metrics:** linking quality is reported stratified by difficulty; the
  F1 that matters is the tail (homonyms, implicit references), not the
  easy exact-match cases.
