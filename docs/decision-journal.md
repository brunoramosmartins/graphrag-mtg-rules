# Decision Journal

Dated entries, written the day the decision is made. Entries
reconstructed from git history after the fact are marked
*(retrospective, written 2026-07-19)*. Architectural decisions get a
full ADR in [docs/adr/](adr/); the journal records the smaller,
dated calls that an ADR would be too heavy for — and points at the
evidence that forced each one.

---

## 2026-07-17 — Domain choice gated by motivation and licensing *(retrospective, written 2026-07-19)*

MTG rules chosen as the domain (ADR-001) with an explicit licensing
gate before any data touched the repo: Fan Content Policy compliance,
no bulk data committed, Scryfall attribution. Contingency gates
defined up front so an abandoned phase fails loudly instead of
lingering. Embodied in `9cd111d`.

## 2026-07-17 — Neo4j property graph over RDF *(retrospective, written 2026-07-19)*

Property graph (ADR-002): the ontology is small and typed, queries are
path-shaped, and Cypher templates are auditable. A written comparison
with RDF/OWL was not produced at decision time — parked as a possible
TIL, not re-litigated.

## 2026-07-18 — Curate, don't author, the golden set *(retrospective, written 2026-07-19)*

Golden set sourced from judge-curated RulesGuru questions rather than
self-authored ones, with `vector_should` predictions (fail/lose/tie)
recorded per question **before** any system runs. The `tie` stratum is
deliberate: a hypothesis that cannot lose anywhere is not a
hypothesis. Embodied in `ddca2bf`; source of truth in
[evaluation.md](evaluation.md).

## 2026-07-19 — Deterministic backbone; LLM only for the residual *(retrospective, written 2026-07-19)*

Phase 2 build decisions, each forced by measurement rather than taste:

- `subtree()` walks parent links, not number prefixes — `613.4b` does
  not start with `613.4.` (caught by a failing test).
- `mana_value()` refuses combined multi-face costs — 209 adventure
  cards would silently get a wrong value (caught by cross-checking
  against Scryfall `cmc`).
- Keywords keyed on normalized names — Scryfall's `"First strike"` vs
  the CR glossary's `"First Strike"` silently split every keyword into
  two nodes, leaving `Card → Keyword → Rule` empty while node counts
  looked healthy.
- Load reports use Neo4j result counters, not row counts — `0 created`
  on a reload is direct idempotency evidence.
- `PRUNE_STALE_RULES` keyed on `source_sha256` — `MERGE` never
  deletes, so withdrawn rules survived a CR update until pruned.

## 2026-07-19 — `rulings_2hop` deferred to Phase 3 on evidence *(written same day; measurement corrected 2026-07-20, see below)*

Measured: 1 of 77,999 rulings contains a CR rule number (and it is
about a store locator). `CITES_RULE` therefore has no deterministic
component — the edge can only come from validated LLM extraction,
which is exactly Phase 3's job. The stratum moves there instead of
being faked here.

## 2026-07-20 — G3 assessed on the dev split: proceed, iterate to grounded mode

First extraction run (open mode, gpt-4o-mini, 30 dev rulings, ~$0.01):
31 candidates, 2 fabricated quotes killed by the parser, 7 of 31
(23%) citing **plausible but nonexistent** rule numbers — all caught by
the gate's existence check. Spans and concepts look right; the numbers
are invented (e.g. 702.74b for connive, which is 701.50). Neither
trivial nor infeasible under E-003's decision rule, so Phase 3 proceeds
as designed: round 2 grounds the prompt in candidate rules retrieved
from the graph. What the gate cannot catch — existing-but-wrong numbers
— is exactly what the manual annotations will measure.

## 2026-07-21 — Lexical CR search aids the citation pass without contaminating the gold

The liberal citation pass requires naming the CR rule each ruling invokes,
which by hand means grepping 3,000+ rules. Built `cite_search.py`: a
deterministic TF-IDF ranking of CR rules by term overlap with a ruling, so
the annotator reads ~8 candidates instead of the whole document (for the
Crib Swap example it ranks 608.2b first; for connive, 701.50b first).

Why this is allowed where an LLM suggester would not be: the distinction is
"accelerate the search" vs "generate the answer". The tool ranks candidates;
the human reads the actual rule text and decides which one *governs*. It is
lexical, so it shares no mechanism with the LLM extractor under evaluation,
nor with the semantic retrieval the vector baseline will use — gold
citations found with its help do not correlate with either system, so the
CITES_RULE F1 and the Phase 6 baseline comparison stay honest. An LLM
suggester was rejected precisely because it would grade the extractor
against a gold it helped write. Embedding retrieval was deferred to Phase 4
for the same correlation reason plus its infrastructure cost.

## 2026-08-08 — Scryfall bulk ETL: read three formats rather than force a re-download

Scryfall retired `download_uri` (one uncompressed JSON array) in favour of
`jsonl_download_uri` (gzipped JSONL). `etl/download.py` raised
`KeyError: 'download_uri'` before resolving anything, so re-ingestion was
impossible — a silent break, since nothing re-downloads on a normal working
day and the failure only appears when you try.

The reader (`etl/bulk.py`) accepts gzipped JSONL, plain JSONL, *and* the legacy
array, and `bulk_path` prefers the newest format that exists on disk. The
alternative — cut over to JSONL only and re-download — was rejected for the
same reason the CR upgrade was handled carefully on the same day: a 180 MB
oracle bulk already on disk is real work, and stranding it in the middle of the
citation pass would trade a latent bug for an immediate one. Format is detected
from the first non-whitespace character, not from the file name, because the
name is only a convention.

Two things improve as a side effect. JSONL is streamed record by record instead
of held whole in memory (the legacy array still cannot be, which is an argument
for letting the next download replace it), and the compressed artifact is ~24 MB
against ~180 MB. The resolver now also warns and skips when an entry exposes no
known download key, rather than dying — the next contract change should degrade,
not crash.

Deliberately *not* done: re-downloading now. The rulings snapshot would jump
mid-annotation, which is the corpus-consistency problem this same day's CR entry
argues against. The download happens after the citation pass closes.

## 2026-08-08 — CR upgraded mid-annotation; citations migrated by text, not by number

The corpus was internally inconsistent: the CR snapshot was effective
2026-02-27 while the Scryfall rulings snapshot was 2026-07-17, so rulings
for sets released in between could cite rules that did not exist in our
CR. This surfaced during the manual citation pass as a ruling whose
governing rule was simply absent. Upgraded to the 2026-08-07 CR at 64/155
rulings reviewed rather than after, because the mismatch is structural and
would otherwise have hit the remaining 91 as well — and because a gold with
half its labels authored against one CR and half against another cannot be
read: a low `CITES_RULE` F1 would not distinguish model error from version
artifact.

Numbers are not a safe anchor. Measured between the two versions: 111 rules
added, 70 removed, and three silent displacements that a number-based
migration would have corrupted — `initiative` moved 725.1/725.2 to
726.1/726.2 to make room for `monarch`, so the old numbers still resolve
but now mean something else entirely; `310.10` shifted to `310.11` and
`704.5w` to `704.5x`. The migration in `scripts/cr_migrate.py` is therefore
anchored on rule *text*: the annotator chose a rule by what it says, so the
tool relocates that choice to wherever the text now lives, and only when the
match is near-exact and clearly better than at the original number.

Result: of 79 distinct cited rules, 71 unchanged, 4 relocated (5 citations
remapped, `migrated_from` kept on each), 4 edited in place with no semantic
change (`205.3g` and `205.3m` gained new types, `506.4` gained "or
protector", `702.142a` was reworded editorially), 0 orphaned. No manual
decision was lost. `edited` and `orphaned` are never auto-applied — guessing
there would corrupt the gold silently, which is the one failure this whole
apparatus exists to prevent.

Provenance added as the durable fix: every draft row now carries
`cr_version`, without which no future migration is auditable. Prior CR kept
as `data/raw/comprehensive_rules-20260227.txt`.

Two collateral findings, both from the same "living documentation" class.
The Scryfall bulk ETL is broken — the API replaced `download_uri` with
`jsonl_download_uri` and now serves JSONL, so `etl/download.py` raises
`KeyError` and nothing can currently be re-ingested. And the 2026-08-07 CR
replaced empty separator lines with lines holding U+00A0; the parser
survives it, but `normalize()` folds NBSP so formatting churn is never read
as a text change.

## 2026-07-21 — `cited_rules` interpreted liberally: cite the governing rule

After the full 155-ruling annotation, the gold held only 6 citations,
all in the 5 "explicit" rulings that literally print a rule number; every
other ruling — including the guide's own Crib Swap worked example that
should cite 608.2b — was left empty. That is a conservative reading of
"the rule the ruling turns on", and against a near-empty citation gold
the extractor's inferred citations would all score as false positives,
measuring nothing. Decision: cite the rule that *governs* the interaction
even when the ruling states no number, because recovering the unstated
rule is the entire premise of `CITES_RULE` (Phase 2 measured that rulings
almost never cite numbers). Requires a citation pass over ~150 rulings.
The annotation guide and worksheet were updated to make the liberal
reading explicit and to help find numbers by grepping the CR rather than
from memory. The alternative — declaring CITES_RULE genuinely sparse —
was rejected: the sparsity was an annotation artifact, not a measurement.

## 2026-07-20 — Multi-word card names are not unambiguous; capitalization gate added

The first linking measurement against 24 dev annotations disproved a
design premise: the linker treated any multi-word name match as certain,
but "card draw", "deal damage", "too many", "max speed" are real card
names *and* ordinary English phrases, giving 8 false positives
(multiword precision 0.47). Fix: require at least one capitalized word in
the match — not the initial, so "the Ring" survives its lowercase
article. Overall F1 0.69 -> 0.83, no true positive lost. The three
residual false positives are capitalized-but-generic names (Nicol Bolas,
Soul Shatter, Max Speed), which are the LLM stage's job. The frozen
sample's strata labels predate this change and are kept as the sampling
record, not re-derived. Finding surfaced only because the annotation
recorded the negatives — evidence for why the manual gold is the phase's
core work.

## 2026-07-20 — Grounding fixed hallucinated numbers and induced a topical bias

Round 2 (keyword directory in the system prompt) did what it was
designed to do: nonexistent rule numbers fell from 7 of 31 to 1 of 21.
It also did something it was not designed to do: **all 21 citations
became 701/702 keyword rules**, losing the correct procedural citations
round 1 produced (601.2c, 608.2, 613.1). A prompt whose only rule
inventory is keyword names is a prompt that asks for keywords.

Decision: keep grounding, but lead the block with the full CR chapter
map (146 chapters) and name the procedural chapters explicitly, so the
model sees the whole document rather than one wing of it. Recorded
because the lesson generalizes past this prompt: the metric that
improved (gate rejection rate) was not the metric that mattered, and
only inspecting the *shape* of the output caught it. Every prompt round
now reports the distribution of cited rule families, not just error
rates.

## 2026-07-20 — Correction: 25 rulings (3 cards) cite rule numbers, not 1

The Phase 3 sampling stratifier re-measured with the pattern
`\b\d{3}\.\d+[a-z]?\b` and found **25 of 77,999** rulings carrying an
explicit CR number — all from 3 cards whose rulings enumerate the
704.5x state-based actions in the form "(704.5g)". The Phase 2 pattern
missed parenthesized citations and undercounted by 24. The decision
stands unchanged — 0.03% coverage concentrated on 3 cards is not a
deterministic component worth building on — but the number in
[golden-set.md](golden-set.md) and [evaluation.md](evaluation.md) was
wrong and is now corrected. Lesson recorded: a measurement that feeds a
decision gets its pattern reviewed like code, because the number
outlives the script that produced it.

## 2026-07-19 — Literature reading anchored to decisions

Adopted a research scaffold: every source must name the project
decision it informs before getting a full reading note; otherwise it
goes to an ideas parking lot. Reading order is decision order (survey
→ what *not* to build → closest published design → extraction
roadmap), not textbook order. Experiments pre-register in
[../experiments/registry.md](../experiments/registry.md) before
running.
