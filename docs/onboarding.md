# Onboarding — from a clean machine, timed

*Measured 2026-09-10, Phase 7.*

Every figure below was produced by running the thing it describes, on an
empty Neo4j and an empty `data/` directory. **No number here is a target
that was aimed at**; they are what happened, published because a
reproducibility claim with no clock attached is not a claim.

## The two paths

```bash
cp .env.example .env                 # set NEO4J_PASSWORD and CR_TXT_URL
docker compose --profile app up -d --wait
docker compose exec app python scripts/bootstrap.py
```

The second run of that last command is the warm path. Every step is
idempotent by construction: the download skips sources whose hash the
manifest already records, the loader skips sources whose hash the graph
already carries, and the schema statements are `IF NOT EXISTS`.

| step | cold | warm |
|---|---:|---:|
| download — 29.5 MB over three files | 3.7 s | 0.0 s (skipped) |
| schema — 9 constraints and indexes | 2.7 s | 0.3 s |
| graph — 34,937 cards · 3,308 rules · 78,179 rulings | 136.1 s | 0.2 s |
| first answer — retrieval over a golden question | 31.2 s | 26.2 s |
| **total** | **173.7 s** | **26.7 s** |

Building the image first is a further **68.8 s** with no layer cache.

Both columns are the container. From a host venv the warm path is
**11.2 s**, because the mount that carries the 24 MB compressed card bulk
into the container is the slow part of it — on Docker Desktop for Windows,
reading that file across the bind mount is most of the answer step.

## Which arm each path covers

The bootstrap builds the **graph**. That is what arms B and C retrieve
from, and arm C is the shipped system, so the paths above are the shipped
system's onboarding.

**Arm A is not on this path, on purpose.** It is a vector baseline over a
separate ~116,000-document index, and building it costs one embedding API
call per document — about twenty minutes and roughly $0.17 at
`text-embedding-3-small` prices. `python scripts/run_eval.py index` is
where it lives, and it prints its own estimate before spending anything.
An onboarding that quietly took twenty minutes and real money would be a
worse first impression than one that says which arm it just made ready.

The **LLM-extracted edges are also not on this path.** `CITES_RULE` and
`MENTIONS` come from `extraction.pipeline`, which sends rulings through a
model and a gate. Without them retrieval works and reaches fewer rules
from a ruling; the bootstrap says so rather than leaving you to interpret
Neo4j's warnings about relationship types it has never seen.

## The container's code is a build artifact, not a mount

Only `./data` and `./runs` are bind-mounted. `src/`, `scripts/` and `tests/`
are `COPY`ed at build time, so **editing a file on the host does not change
what `docker compose exec app` runs** — it keeps running the code the image
was built from, with no warning that the two have diverged. Rebuild after a
code change:

```bash
docker compose --profile app up -d --build app
```

The bind mounts are deliberate and the copies are too: the sources and the
run artefacts are the same bytes the host venv reads, so nobody downloads
196 MB twice, while the code in the image is pinned to whatever produced it.
The cost is this failure mode, which is the same shape as any other stale
binding — the thing you edited is not the thing that ran, and nothing fails
to tell you so. It surfaces as an `unrecognized arguments` error for a flag
you are looking at in your editor.

## What is compute and what is your connection

Publishing a download time as a project fact would be publishing a fact
about the connection it was measured on. Split accordingly:

**Bandwidth-bound, and yours will differ.** 29.5 MB of sources (24.6 MB
oracle cards, 5.4 MB rulings, 1.0 MB Comprehensive Rules — all
compressed), plus the images: `neo4j:5-community` at 968 MB and this
project's own at 381 MB, pulled or built once.

**Compute-bound, and roughly portable.** The 136 s graph load is
`UNWIND`/`MERGE` producing 119,174 nodes and 912,499 relationships against
a 1 GB-heap Neo4j. The 68.8 s image build is mostly resolving and
installing wheels. The 26–31 s first answer is dominated by reading and
parsing the card bulk to build the linker's lexicon, which happens once
per process.

## The one manual step, and why it cannot be automated

`CR_TXT_URL` must be set by hand. WotC's rules page is JS-rendered, so the
link cannot be scraped, and **the file is replaced every release without a
redirect** — the URL in a months-old manifest returns 404 rather than the
new document. This was not a hypothesis: the cold run above first failed
that way, on a URL that had worked three days earlier.

Open <https://magic.wizards.com/en/rules>, copy the TXT link, and put it in
`.env`. The downloader now reports a dead CR URL with that instruction
instead of an `httpx` traceback.

## What "warm" is worth

The warm path is warm until Scryfall publishes. **Scryfall regenerates its
bulk daily**, so a run on the following day fetches ~30 MB, the card hash
changes, and the loader reloads all three sources — about 140 s, not 27.
Any vector index built over the previous corpus also stops matching, since
its cache is keyed on a hash of the indexed text.

That is the loader behaving correctly; a graph quietly serving yesterday's
cards would be worse, and this project's standard has said since Phase 0
that reloads are hash-driven and idempotent. What it means for onboarding
is that the honest claim is **"cold once, warm until the sources move"**,
with a shelf life of about a day rather than of a release cycle. Pass
`--no-download` to hold the corpus you have.
