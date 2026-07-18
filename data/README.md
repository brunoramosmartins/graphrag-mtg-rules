# data/

| Directory | Committed? | Contents |
|---|---|---|
| `raw/` | **No** (gitignored) | Downloaded sources: Scryfall bulk, CR text, MTR/IPG, card images. Arrive via `etl/download.py` with SHA-256 verification. **Never committed** (Fan Content Policy + Scryfall guidelines). |
| `interim/` | **No** (gitignored) | Processed/intermediate artifacts and fetch samples (`scripts/fetch_samples.py`). |
| `golden/` | **Yes** (if license permits) | The judge-curated golden set. Per gate G1, if RulesGuru question-content redistribution is not clearly permitted, this holds **question IDs + a fetch script** (`ids_v0.jsonl`), not the question text. Decided in Phase 1. |

See [`../docs/data-sources.md`](../docs/data-sources.md) for the full
licensing analysis (gate G1).
