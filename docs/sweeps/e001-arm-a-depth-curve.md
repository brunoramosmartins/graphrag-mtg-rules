> **Superseded — read [README.md](README.md) first.** This artefact reports what
> its own margin rule says. The registered stopping rule, applied across all
> four artefacts, adopts **nothing**: the objective is degenerate in depth.
> This banner is a hand-added pointer; no data below it was edited.

# E-001 arm A — good-faith tuning sweep — depth curve with a stopping rule: saturation adopts, monotone rise refutes the objective

**depth curve with a stopping rule: saturation adopts, monotone rise refutes the objective**

Pin 7's artefact. Published whatever it says. Registered before it ran:
the objective is gold-rule recall on the development questions carrying
gold rules, ties break toward the published defaults, and a margin under
2 gold rules keeps the defaults.

- questions: **15** of 20 (the five `legality_1hop` carry no gold rule)
- gold rules available: **26**
- cells: **25**, no LLM call, 248s (the published defaults scored as a baseline outside the grid)
- corpus: `9a6fecc2adfb`, encoder `text-embedding-3-small`

## Result

- published defaults: **9/26**
- best cell: **19/26**  (`k1=1.2 b=0.4 rrf_k=60 depth=12800 mode=hybrid iterative=False`)
- margin: **+10** gold rules

**Adopted.** The margin reaches the registered 2.

## Top 15 cells

| found | k1 | b | rrf_k | depth | mode | iterative |
|---|---|---|---|---|---|---|
| 19/26 | 1.2 | 0.4 | 60 | 12800 | hybrid | False |
| 19/26 | 1.2 | 0.4 | 10 | 12800 | hybrid | False |
| 19/26 | 1.2 | 0.4 | 30 | 12800 | hybrid | False |
| 19/26 | 1.2 | 0.4 | 60 | 12800 | hybrid | True |
| 19/26 | 1.2 | 0.4 | 10 | 12800 | hybrid | True |
| 19/26 | 1.2 | 0.4 | 30 | 12800 | hybrid | True |
| 17/26 | 1.2 | 0.4 | 60 | 6400 | hybrid | True |
| 17/26 | 1.2 | 0.4 | 10 | 6400 | hybrid | True |
| 17/26 | 1.2 | 0.4 | 30 | 6400 | hybrid | True |
| 16/26 | 1.2 | 0.4 | 60 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 60 | 3200 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 60 | 6400 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 10 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 30 | 1600 | hybrid | False |
| 16/26 | 1.2 | 0.4 | 60 | 1600 | hybrid | True |

## By mode, best cell in each

| mode | best found | at |
|---|---|---|
| hybrid | 19/26 | `k1=1.2 b=0.4 rrf_k=10 depth=12800 iterative=False` |

## Known defect of the objective

Rule recall is close to blind on `interaction_multihop`: the
answer-bearing evidence there is a Scryfall ruling, which carries no CR
number and therefore scores zero however well it was retrieved. This
sweep is driven mostly by the other strata, and that is stated rather
than discovered. No second objective was invented to fix it — choosing a
metric after watching the registered one read low is what pin 7 forbids,
and it would be the same move whether or not it favoured arm A.
