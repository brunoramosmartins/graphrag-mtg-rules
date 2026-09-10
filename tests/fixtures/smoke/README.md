# Smoke fixtures

The corpus `run_eval.py run --smoke` indexes. It exists so the evaluation
pipeline can run end to end in CI with **no API key, no Neo4j, and no
`data/raw/`** — none of which a pull request can have.

## What is in here, and why it is shaped this way

| file | what it is |
|---|---|
| `cards.json` | **Synthetic** cards in Scryfall's record shape. |
| `rulings.json` | **Synthetic** rulings against those cards. |
| `golden/authored_v0.jsonl` | Six authored questions with their answer keys inline. |
| `golden/split.json` | Puts all six on the development side. |

The Comprehensive Rules half is `tests/fixtures/cr_excerpt.txt`, the same
excerpt the CR parser's golden-file tests use — small enough for fair use,
and already in the repo. Arms B and C also need it *in the graph*:
`scripts/load_smoke_graph.py` merges the same three cards and the same
excerpt through the real loader statements.

**The cards are invented, not sampled.** The project's licensing rule is
that no bulk card data is committed, and the honest way to keep a fixture
on the right side of that is for it to contain no real card at all. It
also makes the fixture's purpose unmistakable to a reader: nothing here is
evidence about Magic, so nothing here can be mistaken for a measurement.

## Why the questions are shaped the way they are

The six are not six variations on one thing. Between them they have to
reach every branch the harness can take, or a passing smoke stops meaning
anything:

| | what it reaches |
|---|---|
| `sm-1` | `keyword_definition` — the glossary-to-rule traversal |
| `sm-2` | `NO_ENTITIES` — the named-failure path, before the database is touched |
| `sm-3` | keyword **and** card traversals on one question |
| `sm-4` | `card_interaction`, the traversal whose first version killed the server |
| `sm-5` | `card_legality`, which runs only when a format is named |
| `sm-6` | **no graph seed** — arm B returns `NO_SEED`, arm C routes to its text half |

`sm-6` is the one that earns the most attention. Arm C is arm B plus a
text retriever, and that retriever fires only where the router sends it.
The first five questions all seeded the rule graph, which made arm B and
arm C produce identical output while both passed — the Phase 6 mislabel
with a green badge on it. `tests/test_run_eval_run.py` now asserts that
some fixture question is seedless and some other one is not, so the
property cannot quietly go away again.

That also means one of the three cards must carry keyword abilities and
another must not: `has_graph_seed` turns on exactly that distinction, and
a fixture whose cards were all one kind could not produce both branches
however the questions were written.

## What a smoke run proves, and what it does not

It proves the **wiring**: corpus build, retrieval, budget enforcement,
context serialization, prompt assembly, citation expansion, judging,
verdict files, the report, and the figures all execute and agree about
their formats.

It proves **nothing about answer quality**. The generator and the judge
are both fakes — the generator cites the first handle in the context it
was handed, and the judge returns a fixed label. Every row a smoke run
writes carries `"smoke": true` and `"model": "smoke-fake"`, and its files
are named `runs/smoke_*` rather than `runs/e001_*`, so a synthetic figure
cannot be picked up as a real one by a later analysis.

Model quality is measured by E-001 on real questions with a real judge,
and that judge is itself gated on the correctness ceiling. CI is not part
of that chain and must never look like it is.
