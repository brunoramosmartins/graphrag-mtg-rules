> **Superseded — read [README.md](README.md) first.** This artefact reports what
> its own margin rule says. The registered stopping rule, applied across all
> four artefacts, adopts **nothing**: the objective is degenerate in depth.
> This banner is a hand-added pointer; no data below it was edited.

# E-001 arm A — good-faith tuning sweep — does b=0.4 help at defensible depths, or only at degenerate ones?

**does b=0.4 help at defensible depths, or only at degenerate ones?**

Pin 7's artefact. Published whatever it says. Registered before it ran:
the objective is gold-rule recall on the development questions carrying
gold rules, ties break toward the published defaults, and a margin under
2 gold rules keeps the defaults.

- questions: **15** of 20 (the five `legality_1hop` carry no gold rule)
- gold rules available: **26**
- cells: **72**, no LLM call, 504s
- corpus: `9a6fecc2adfb`, encoder `text-embedding-3-small`

## Result

- published defaults: **9/26**
- best cell: **13/26**  (`k1=1.2 b=0.4 rrf_k=60 depth=400 mode=hybrid iterative=True`)
- margin: **+4** gold rules

**Adopted.** The margin reaches the registered 2.

## Top 15 cells

| found | k1 | b | rrf_k | depth | mode | iterative |
|---|---|---|---|---|---|---|
| 13/26 | 1.2 | 0.4 | 60 | 400 | hybrid | True |
| 13/26 | 1.2 | 0.4 | 10 | 400 | hybrid | True |
| 13/26 | 1.2 | 0.4 | 30 | 400 | hybrid | True |
| 12/26 | 1.2 | 0.75 | 60 | 400 | hybrid | True |
| 12/26 | 1.2 | 0.75 | 10 | 400 | hybrid | True |
| 12/26 | 1.2 | 0.75 | 30 | 400 | hybrid | True |
| 12/26 | 1.2 | 1.0 | 60 | 400 | hybrid | True |
| 12/26 | 1.2 | 1.0 | 10 | 400 | hybrid | True |
| 12/26 | 1.2 | 1.0 | 30 | 400 | hybrid | True |
| 10/26 | 1.2 | 0.75 | 60 | 400 | hybrid | False |
| 10/26 | 1.2 | 0.75 | 10 | 400 | hybrid | False |
| 10/26 | 1.2 | 0.75 | 30 | 400 | hybrid | False |
| 10/26 | 1.2 | 0.4 | 60 | 400 | hybrid | False |
| 10/26 | 1.2 | 1.0 | 60 | 400 | hybrid | False |
| 10/26 | 1.2 | 0.75 | 10 | 200 | hybrid | True |

## By mode, best cell in each

| mode | best found | at |
|---|---|---|
| hybrid | 13/26 | `k1=1.2 b=0.4 rrf_k=10 depth=400 iterative=True` |

## Known defect of the objective

Rule recall is close to blind on `interaction_multihop`: the
answer-bearing evidence there is a Scryfall ruling, which carries no CR
number and therefore scores zero however well it was retrieved. This
sweep is driven mostly by the other strata, and that is stated rather
than discovered. No second objective was invented to fix it — choosing a
metric after watching the registered one read low is what pin 7 forbids,
and it would be the same move whether or not it favoured arm A.
