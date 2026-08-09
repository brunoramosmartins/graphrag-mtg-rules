# Measuring a system against hand-made annotations

A protocol, written to be lifted into another project. The results that
produced it are in [evaluation.md](evaluation.md) and
[../experiments/registry.md](../experiments/registry.md); this file is
the method, deliberately separated from them so it can travel.

## The problem it solves

An F1 against a hand-made gold set gets read against 1.0. That reading is
almost always wrong, and it fails in both directions:

- **Too harsh.** If the annotator would not agree with themself, no system
  can reach 1.0, and the "gap" you are chasing partly does not exist.
- **Too kind.** If the task is easy and the gold is clean, a mediocre
  score is worse than it looks, and blaming "annotation noise" is an
  excuse rather than a finding.

You cannot tell which case you are in from the score alone. Three
measurements are needed, and their order matters.

## The three measurements

### M1 — the score

The ordinary evaluation, run under pre-registration: thresholds fixed
before any run, the evaluation split touched exactly once, iteration
confined to a development split.

### M2 — the ceiling (intra-annotator agreement)

The annotator re-labels a random subsample **blind** — same items, same
tools, their own earlier labels hidden — and the two passes are scored
against each other **with the metric M1 uses**. That last point is what
makes it useful: the ceiling and the score land on one scale, so
"the system scored 0.125, the annotator against themself scored 0.815"
is a sentence with meaning.

Two constraints that are easy to get wrong:

- **Same tools.** If the second pass uses a better lookup than the first,
  you have measured the tool, not the annotator.
- **Time.** A same-day second pass is recall, not independent judgement,
  and inflates the ceiling. If you cannot wait, say so in the write-up
  and treat the figure as an optimistic bound.

Micro-F1 is symmetric under swapping the two passes, so which one is
called "gold" is presentation only.

### M3 — the composition of the gap

Sample the disagreements between system and gold and sort each into
exactly one bucket:

| bucket | meaning |
|---|---|
| `gold_right` | the gold is right, the system is wrong — system error |
| `both_defensible` | the system's answer also holds — an artifact of exact match |
| `gold_wrong` | the gold is wrong on its own terms under the written guide |
| `unclear` | parked, and counted, rather than forced |

Report four proportions with intervals. **This is measurement, not
repair.** A sample cannot patch a gold — a half-patched gold makes both
the pre- and post-correction figures meaningless — so sampling here works
only because the goal changed from *fixing* to *estimating what the gap is
made of*.

`both_defensible` is the bucket people forget, and it is the one that
decides how to read a low score. Without it, "the metric is too strict"
and "the model is wrong" collapse into the same number.

### The order is binding: M2 before M3

Reading disagreements first contaminates the blind second pass. Someone
who has just re-argued twenty items against a system's output is
remembering, not judging, and the ceiling comes out too high. In this
repo the constraint is enforced in code — `scripts/adjudicate.py` refuses
to show a case until the blind pass in `scripts/reannotate.py` is
complete — because a rule that depends on remembering it is not a rule.

## Rules that keep each measurement honest

- **Touch the evaluation split once.** After it is spent, no tuning may be
  justified by it. Improvements found there become hypotheses for a *new*
  experiment with a fresh sample, registered as such.
- **Mechanism independence.** A tool that helped *build* the gold must not
  be fed to the system under measurement. Otherwise agreement is family
  resemblance rather than correctness.
- **Absent gold is not empty gold.** An item nobody labelled has no gold to
  be right or wrong against, and must be excluded from the denominator.
  Scoring it as "gold = ∅" turns every prediction there into a false
  positive and quietly destroys precision.
- **Score what ships.** If a gate, filter, or threshold stands between the
  model and the product, score what passes it. Scoring intermediate
  candidates credits the system for proposals it never delivers.
- **Pin every source of randomness.** Sampling temperature left unset made
  two runs of one configuration differ by as much as the effects being
  compared here; the whole iteration series had to be retired as
  unattributable. An experiment cannot attribute a change it cannot
  reproduce.
- **Pre-register the adjudication rule, with a cap.** Before any result is
  seen: what makes a label objectively wrong, that every change is logged,
  that both pre- and post-adjudication figures are reported with
  pre-adjudication as the headline, and a ceiling (10% here) above which
  the gold is declared unreliable and re-annotated rather than patched.
- **Secondary metrics go beside the primary, never in place of it.**
  Loosening the primary key after seeing that the errors are of a
  particular shape is fitting the ruler to the result.
- **A prediction edited after seeing adjacent data is not a prediction.**
  When M2 landed as weak evidence against M3's registered prediction, the
  prediction stayed as written and was scored as written.

## Reporting traps, all met in practice

- **The bootstrap lies on unanimous samples.** A percentile bootstrap
  resamples observed values, so a sample with no variation resamples to
  itself and prints `[1.000, 1.000]`. That reads as certainty and means
  "not observed yet". Report `3/n` (rule of three) instead, over clusters.
- **Cluster by document, not by item.** Several errors from one document
  are correlated; resampling items treats them as independent evidence and
  reports an interval that is too narrow.
- **Self-judging needs its asymmetry measured.** When the person who wrote
  the gold judges the disagreements, unanimity in their own favour is what
  a *lenient* judge produces, and no amount of extra sampling separates
  that from being right — only an independent judge does. What you *can*
  do is measure a specific asymmetry: here, how many disagreements were of
  the same kind the annotator produced against themself in M2, and how
  those were judged. Print it beside the result.
- **Sample size is the wrong lever more often than it looks.** With 40/40
  unanimous, doubling the sample moves the bound from ~0.09 to ~0.04 and
  changes no decision. The binding uncertainty was the judge, not the
  count.

## On Krippendorff's α and friends

α, Cohen's κ, Scott's π and Fleiss' κ all answer *reliability*: how much
agreement exceeds what chance would produce. That is a different question
from *validity*: whether the labels are right. Three consequences worth
stating before anyone reaches for them:

- **Reliability cannot show one annotator is "better" than another.**
  Coders who consistently apply the same wrong rule agree perfectly.
  Ranking a human pool against a model on α alone measures who is more
  self-consistent, not who is more correct. A claim of "better" needs a
  validity criterion independent of both — an adjudicator, or a written
  guide applied by someone with no stake, which is what M3 is for.
- **A deterministic system scores ≈1 by construction.** An LLM re-run at
  temperature 0 reproduces itself exactly, so its "reliability" is a
  property of the sampler, not of its judgement. Comparing that to human
  α is not a comparison. If a model is to be compared on reliability at
  all, it has to be re-run under the variation a human faces —
  paraphrased prompt, reordered options, a fresh session — and even then
  the number bounds nothing about correctness.
- **Check that the two α values measure the same construct.** Agreement
  *between different people* (inter-rater) and agreement *of one rater
  with themself over time* (intra-rater) are different quantities, and
  reporting one against the other as though they were comparable is a
  common slip.

**Why this project does not use α.** Not on principle — it simply buys
nothing here. The label is a *set* drawn from ~2,600 CR rules, so expected
chance agreement is indistinguishable from zero and the chance correction
does no work, while costing the one property that mattered: M2 had to be
expressed in the same metric as M1 so the ceiling could bound the score.
Micro-F1 between two passes does that; α does not. In a project with a
small closed category set, several coders, and missing labels — the
setting α was designed for — the trade goes the other way, and M2 should
be an α.

## What it costs

Budget from this project, for one 125-item evaluation set:

| step | cost |
|---|---|
| M2, blind re-annotation | 20 items re-labelled by hand |
| M3, disagreement judging | 40 sampled cases read and classified |
| tooling | two scripts (`reannotate.py`, `adjudicate.py`), reusing the existing metric module |

Both steps are one-off per evaluation set, and both are cheap next to
building the gold in the first place. The reason to do them is not rigour
for its own sake: without M2 the score has no ceiling, and without M3 a
low score cannot be told apart from a strict metric.

## Where the instances live

| | this repo |
|---|---|
| M1 | `scripts/eval_extraction.py`; E-003 in the registry |
| M2 | `scripts/reannotate.py` (`draw` / `compare`); E-003a |
| M3 | `scripts/adjudicate.py` (`sample` / `worksheet` / `judge` / `report`); E-003b |
| intervals | `src/graphrag_mtg/evaluation/metrics.py` |
| the rules above | [../experiments/registry.md](../experiments/registry.md), [decision-journal.md](decision-journal.md) |
