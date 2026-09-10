# Smoke fixtures

The corpus `run_eval.py run --smoke` indexes. It exists so the evaluation
pipeline can run end to end in CI with **no API key, no Neo4j, and no
`data/raw/`** — none of which a pull request can have.

## What is in here, and why it is shaped this way

| file | what it is |
|---|---|
| `cards.json` | **Synthetic** cards in Scryfall's record shape. |
| `rulings.json` | **Synthetic** rulings against those cards. |
| `golden/authored_v0.jsonl` | Five authored questions with their answer keys inline. |
| `golden/split.json` | Puts all five on the development side. |

The Comprehensive Rules half is `tests/fixtures/cr_excerpt.txt`, the same
excerpt the CR parser's golden-file tests use — small enough for fair use,
and already in the repo.

**The cards are invented, not sampled.** The project's licensing rule is
that no bulk card data is committed, and the honest way to keep a fixture
on the right side of that is for it to contain no real card at all. It
also makes the fixture's purpose unmistakable to a reader: nothing here is
evidence about Magic, so nothing here can be mistaken for a measurement.

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
