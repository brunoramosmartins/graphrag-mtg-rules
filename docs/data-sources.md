# Data Sources & Licensing (Gate G1)

This document is the **licensing gate (G1)** for Phase 0. No ingestion
pipeline is written until every source below has a verdict:
**OK**, **OK-with-restriction**, or **BLOCKED**.

> **Reconfirm before ingestion.** URLs and terms are recorded as
> evaluated on **2026-07-17**. Run `python scripts/fetch_samples.py`
> (Phase 0 smoke) to confirm the URLs still resolve and the formats
> still match before any bulk download. Terms of use can change; the
> gate is re-evaluated whenever they do.

## Required compliance notice (goes to README + demo footer)

> *Unofficial Fan Content permitted under the Fan Content Policy. Not
> approved/endorsed by Wizards. Portions of the materials used are
> property of Wizards of the Coast. ©Wizards of the Coast LLC.*

Plus attribution to **Scryfall** for card data and images. This project
is **strictly non-commercial**.

---

## Per-source table

| Source | Content | Role | Format | Verdict | Repo-versioning decision |
|---|---|---|---|---|---|
| **Scryfall bulk data** | Oracle cards, faces, sets, legalities, official rulings | Structured backbone + rulings corpus | JSON (daily), free | **OK-with-restriction** | Never commit bulk; download script + SHA-256 |
| **WotC Comprehensive Rules** | ~300 pp, hierarchical numbering, cross-refs | Rule tree + extraction corpus | Official TXT | **OK-with-restriction** | Never redistribute; download script only |
| **WotC MTR / IPG** | Tournament rules & infractions | Additional text layer (vector in P3) | PDF | **OK-with-restriction** | Never redistribute; download script only |
| **RulesGuru (API)** | ~1.5k judge questions with answers, difficulty, topic | Curated golden set | API / JSON | **OK-with-restriction (pending confirm)** | See decision below |
| **Cranial Insertion (archive)** | ~20 yrs of judge Q&A | Secondary **private** validation | web | **OK for private manual use only** | Never redistribute; link only |
| **MetaQA** | 400k 1/2/3-hop questions over a movie KG | Machinery calibration (Phase 6) | Public download | **OK (academic)** | Not committed; fetched on demand |

---

## Source detail

### Scryfall bulk data
- **URLs.** Bulk index: `https://api.scryfall.com/bulk-data`
  (returns download URLs for `oracle_cards`, `default_cards`,
  `rulings`, etc.). Guidelines: `https://scryfall.com/docs/api`.
- **Terms (as evaluated).** Free to use with **attribution**; requires
  polite rate limiting (a small delay between requests) and a
  descriptive `User-Agent`. Card **images** carry their own usage
  guidelines (attribution, no implying endorsement).
- **Verdict: OK-with-restriction.** Attribute Scryfall; do **not**
  commit bulk files or images; download via `etl/download.py` with
  hash verification.

### WotC Comprehensive Rules
- **URL.** Rules landing page:
  `https://magic.wizards.com/en/rules` (links the current CR **TXT**).
- **Terms (as evaluated).** Copyright WotC. Non-commercial fan use is
  covered by the **Fan Content Policy**
  (`https://company.wizards.com/en/legal/fancontentpolicy`).
- **Verdict: OK-with-restriction.** Do **not** redistribute the CR text
  in the repo. A small, frozen excerpt may live in `tests/fixtures/`
  for parser golden-file tests (fair-use-sized). Full text arrives via
  download script.

### WotC MTR / IPG
- **URL.** WPN / judge resources on the WotC sites (PDF).
- **Verdict: OK-with-restriction.** Same treatment as the CR: download
  script, no redistribution. Optional in the critical path (CR +
  rulings can carry the project if MTR/IPG are cut).

### RulesGuru
- **URLs.** Site: `https://rulesguru.org`. Source:
  `https://github.com/KingSupernova31/RulesGuru`. It exposes a
  question API used by the site.
- **Terms (as evaluated).** The application code is open-source. The
  **license of the question content specifically** must be confirmed
  from the repo's `LICENSE` and any content notice — **this is the one
  open item of G1.**
- **Decision (safe default until confirmed):** version **question IDs +
  a fetch script only** (`data/golden/ids_v0.jsonl` + fetch), never the
  question text. The answer key remains fully usable locally. If the
  content license clearly permits redistribution, we may switch to
  committing `questions_v0.jsonl` — recorded here when confirmed.
- **Verdict: OK-with-restriction (pending explicit confirmation in
  Phase 1, feeding gate G2).**

### Cranial Insertion
- **URL.** `https://www.cranialinsertion.com`.
- **Verdict: private manual validation only.** Never redistribute;
  cite with a link when used to spot-check an answer.

### MetaQA
- **Source.** Zhang et al., 2018 (AAAI) — movie-KG multi-hop QA.
- **Verdict: OK** for academic/research use; used only to calibrate the
  pipeline in Phase 6. Not committed; fetched on demand.

---

## G1 outcome

**Proceed with Magic.** All required sources are OK or
OK-with-restriction under a non-commercial fan project that does not
redistribute WotC text/data or Scryfall bulk. The single open item
(RulesGuru question-content license) has a safe default (IDs + fetch)
that does not block the design. **Plan B (D&D 5e SRD, CC-licensed)**
stays in reserve per [`contingency.md`](./contingency.md); the scaffold
is domain-agnostic, so activating it loses no infrastructure work.
