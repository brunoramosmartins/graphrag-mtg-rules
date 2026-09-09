> **Superseded — read [README.md](README.md) first.** This artefact reports what
> its own margin rule says. The registered stopping rule, applied across all
> four artefacts, adopts **nothing**: the objective is degenerate in depth.
> This banner is a hand-added pointer; no data below it was edited.

# E-001 arm A — good-faith tuning sweep

Pin 7's artefact. Published whatever it says. Registered before it ran:
the objective is gold-rule recall on the development questions carrying
gold rules, ties break toward the published defaults, and a margin under
2 gold rules keeps the defaults.

- questions: **15** of 20 (the five `legality_1hop` carry no gold rule)
- gold rules available: **26**
- cells: **588**, no LLM call, 5840s
- corpus: `9a6fecc2adfb`, encoder `text-embedding-3-small`

## Result

- published defaults: **9/26**
- best cell: **16/26**  (`k1=1.2 b=0.4 rrf_k=60 depth=1600 mode=hybrid iterative=False`)
- margin: **+7** gold rules

**Adopted.** The margin reaches the registered 2.

## Top 15 cells

| found | k1 | b | rrf_k | depth | mode | iterative |
|---|---|---|---|---|---|---|
| 16/26 | 1.2 | 0.4 | 60 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 10 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 30 | 1600 | hybrid | False |
| 16/26 | 0.9 | 0.4 | 60 | 1600 | hybrid | False |
| 16/26 | 1.6 | 0.4 | 60 | 1600 | hybrid | False |
| 16/26 | 2.0 | 0.4 | 60 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 60 | 1600 | hybrid | True |
| 16/26 | 0.9 | 0.4 | 10 | 1600 | hybrid | False |
| 16/26 | 1.6 | 0.4 | 10 | 1600 | hybrid | False |
| 16/26 | 2.0 | 0.4 | 10 | 1600 | hybrid | False |
| 16/26 | 0.9 | 0.4 | 30 | 1600 | hybrid | False |
| 16/26 | 1.6 | 0.4 | 30 | 1600 | hybrid | False |
| 16/26 | 2.0 | 0.4 | 30 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 10 | 1600 | hybrid | True |
| 16/26 | 1.2 | 0.4 | 30 | 1600 | hybrid | True |

## By mode, best cell in each

| mode | best found | at |
|---|---|---|
| hybrid | 16/26 | `k1=0.9 b=0.4 rrf_k=10 depth=1600 iterative=False` |
| dense | 13/26 | `k1=1.2 b=0.75 rrf_k=60 depth=400 iterative=True` |
| lexical | 14/26 | `k1=0.9 b=0.4 rrf_k=60 depth=1600 iterative=False` |

## Known defect of the objective

Rule recall is close to blind on `interaction_multihop`: the
answer-bearing evidence there is a Scryfall ruling, which carries no CR
number and therefore scores zero however well it was retrieved. This
sweep is driven mostly by the other strata, and that is stated rather
than discovered. No second objective was invented to fix it — choosing a
metric after watching the registered one read low is what pin 7 forbids,
and it would be the same move whether or not it favoured arm A.
