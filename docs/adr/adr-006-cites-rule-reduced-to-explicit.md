# ADR-006 — `CITES_RULE` reduced to explicit citations

- **Status:** Accepted
- **Date:** 2026-08-09
- **Deciders:** Bruno Ramos Martins
- **Supersedes:** the `APPLIES_RULE` clause of
  [ADR-003](./adr-003-deterministic-parse-plus-llm-extraction.md);
  the rest of ADR-003 stands.

## Context

ADR-003 assigned three jobs to the LLM: ruling→card linking, ruling→rule
(`APPLIES_RULE`, canonically `CITES_RULE`), and implicit CR
cross-references. It also set a threshold — `APPLIES_RULE` F1 ≥ 0.75 —
and gate **G3**: if the edge proved infeasible after three documented
prompt iterations, reduce the schema and report the negative result.

E-003 measured it against 125 manually annotated rulings, one blinded
run, cascade v2 / prompt v3 / temperature 0:

- citation **F1 0.125 [0.073, 0.180]** (tp=19 fp=121 fn=146) against 0.75;
- the same edge scored on rule *family* only: 0.252 [0.188, 0.323].

Two follow-ups excluded the obvious alternative explanations rather than
arguing them away. **E-003a** (intra-annotator agreement, 20 rulings
re-cited blind, same metric) put the ceiling at **0.815 [0.679, 0.938]**,
so the gap is not an unreliable gold. **E-003b** (40 sampled
disagreements classified) came back **40/40 model error**, with
`both_defensible` empty, so the gap is not a too-strict metric either;
the rule-of-three bound puts everything other than model error at ≤0.091.

A finding from implementing this ADR is worth recording. ADR-003 already
required that a cited rule number be "present in the evidence span". The
gate as built checked that only *when the span happened to contain a
number* — a permissive reading that made the requirement vacuous for
exactly the inferred citations it was meant to constrain. The written
contract was right; the implementation had drifted from it, and E-003
measured the cost of the drift.

## Decision

- **`(:Ruling)-[:CITES_RULE]->(:Rule)` is deterministic.**
  `extraction/explicit_citations.py` emits one candidate per rule number
  the ruling text states, with the number occurrence itself as the
  evidence span.
- **The gate refuses inferred citations.**
  `gate_candidates(require_explicit_citations=True)` — the ship default —
  rejects any citation whose rule number is absent from its own span,
  under the reason `citation_not_explicit`. The guarantee lives in the
  gate, not in the prompt and not in the caller, so it holds for a future
  caller who reintroduces an LLM path without reading this ADR.
- **The LLM path survives for reproduction only.** `--llm-citations`
  runs the extractor; `--legacy-citation-gate` restores the permissive
  check so E-003's recorded figure stays reproducible. The CLI refuses to
  combine `--legacy-citation-gate` with `--load`.
- **The edge's meaning narrows accordingly**, and the ontology says so:
  *the ruling names this rule*, not *this rule governs this ruling*.
- **Linking is untouched.** G3 fired on citations. `MENTIONS` failed its
  own threshold (F1 0.634 against 0.90) but sits above the infeasibility
  line, and is the subject of E-005.

## Rationale

- The registered rule fired. Keeping the edge because it might improve
  later would have made the pre-registration decorative.
- At F1 0.125 roughly seven of every eight inferred edges were wrong. A
  graph that cites wrongly is worse than one that stays silent, because
  it looks grounded — and citation is this project's whole claim.
- The alternative explanations were measured and excluded before the
  reduction, not asserted after it.

## Consequences

- **Coverage collapses by design:** 25 of 77,999 rulings (0.03%), 6 gated
  edges over the 125 annotated ones. Overall citation F1 falls from 0.125
  to **0.047** — the mandated change makes the headline number worse, and
  the number is reported anyway.
- **Precision is not 1.0 either: 0.667** on the `explicit` stratum.
  A new limitation the reduction introduces: **ruling text goes stale and
  cannot be migrated.** One ruling writes "(704.5w)"; the August 2026 CR
  moved that state-based action to `704.5x` and reused `704.5w`. The gold
  migrated with the rule text via `scripts/cr_migrate.py`; a ruling is a
  historical document and cannot. The number still resolves, so no
  existence check catches it — the same silent displacement that moved
  `initiative` off 725.1.
- **Phase 4 inherits an open architectural question.** No golden-set
  `gold_path` names `CITES_RULE` (0 of 77), so nothing written down
  breaks. But `interaction_multihop` — the stratum carrying the central
  hypothesis — needs 61 CR rules of which only 8 are keyword rules, and
  the rest have no deterministic edge from any card. `CITES_RULE` was to
  be that bridge. Phase 4 chooses between another deterministic bridge,
  text retrieval for rules with the graph supplying entity structure
  (which reframes E-001 as a test of the combination), or a re-registered
  inferred path.
- **Implicit CR cross-references remain unbuilt.** `extraction/crossref.py`
  exists and the gate supports the edge, but it was never wired into the
  pipeline, so no unmeasured LLM edge has ever reached the graph. It is
  carried forward rather than dropped.
- **Positive:** citations now cost nothing, so the free dry run produces
  every `CITES_RULE` edge the graph will get, and writes them.
