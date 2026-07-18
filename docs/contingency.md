# Contingency Gates (G1–G4)

Failing a gate is **not** failing the project — it triggers a
pre-registered exit plan. Each gate becomes an explicit check in the
Definition of Done of its phase.

| Gate | When | Failure condition | Exit plan |
|---|---|---|---|
| **G1 — Licensing** | Phase 0 | Fan Content Policy, Scryfall guidelines, or the RulesGuru question license make the intended design unworkable (e.g. a use the project requires is prohibited). | **Plan B: D&D 5e via the SRD** (Creative Commons, zero IP risk); analogous ontology (spells, conditions, classes, rules). The scaffold is domain-agnostic, so no code is lost. |
| **G2 — Golden set** | Phase 1 | RulesGuru + rulings do not allow assembling ≥ 60 stratified questions with a trustworthy answer key. | Supplement with public RPG / Judge Q&A; if still insufficient, Plan B. |
| **G3 — Extraction** | Phase 3, week 1 | Extraction/linking turns out trivial (F1 > 0.95 with no effort) or infeasible (F1 < 0.5 after 3 iterations) — the phase is either empty or impossible. | **Trivial:** shift weight to implicit CR cross-refs and linking in ambiguous rulings. **Infeasible:** reduce the schema and document it as an honest negative result. |
| **G4 — Last resort** | Any | Motivation or feasibility collapse. | The Project-1-style v1 roadmap (corporate ownership network) remains valid and detailed; ~90% of the structure is portable. |

## G1 status (Phase 0)

The per-source verdict lives in [`data-sources.md`](./data-sources.md).
Summary of the Phase 0 evaluation:

- **Scryfall bulk** — OK with attribution (non-commercial, no bulk in
  repo). Verdict recorded in `data-sources.md`.
- **WotC Comprehensive Rules / MTR / IPG** — OK under the Fan Content
  Policy for non-commercial fan use; **not redistributed** in the repo
  (download script only).
- **RulesGuru questions** — verdict + versioning decision (content vs.
  IDs + fetch script) recorded in `data-sources.md`.
- **MetaQA** — OK for academic/research use (calibration only).

G1 verdict: **proceed with Magic** (Plan B held in reserve). Any change
to the sources' terms flips this gate and activates Plan B without loss
of scaffold work.

## How gates connect to the DoD

- Phase 0 DoD → **G1** evaluated and documented.
- Phase 1 DoD → **G2** evaluated (≥ 60 stratified questions).
- Phase 3 DoD → **G3** evaluated in week 1 on a 30-ruling sample.
- **G4** is always available and requires no advance work.
