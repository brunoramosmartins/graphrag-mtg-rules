"""Extraction metrics, part 1: P/R/F1 with confidence intervals.

House rule (study discipline §5): no bare proportions. Every headline
number here comes with a bootstrap confidence interval, resampled over
*documents* (rulings), because predictions within one ruling are not
independent — a ruling the linker misreads tends to produce several
correlated errors at once.

Items are hashable tuples chosen by the caller, e.g. ``(ruling_id,
oracle_id)`` for linking or ``(ruling_id, rule_number)`` for citations —
the metrics are agnostic. Pure stdlib on purpose: the core dependency set
stays light, and 120 annotated rulings do not need numpy.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass

DEFAULT_RESAMPLES = 2000
DEFAULT_SEED = 13


@dataclass(frozen=True)
class PRF:
    """Precision / recall / F1 with the raw counts they came from."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


@dataclass(frozen=True)
class Interval:
    """A point estimate with its percentile-bootstrap interval."""

    point: float
    low: float
    high: float
    n_docs: int

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}] (n={self.n_docs} docs)"


DocPair = tuple[frozenset[Hashable], frozenset[Hashable]]  # (predicted, gold)


def prf(predicted: frozenset[Hashable], gold: frozenset[Hashable]) -> PRF:
    """P/R/F1 for one document."""
    return micro_prf([(predicted, gold)])


def micro_prf(pairs: Sequence[DocPair]) -> PRF:
    """Micro-pooled P/R/F1: counts summed over documents, then divided.

    Micro (not macro) because the golden annotations are sparse — many
    rulings carry one or zero gold items, and averaging per-document F1
    over those would let empty documents dominate.
    """
    tp = fp = fn = 0
    for predicted, gold in pairs:
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(precision, recall, f1, tp, fp, fn)


def bootstrap_ci(
    pairs: Sequence[DocPair],
    statistic: Callable[[Sequence[DocPair]], float],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    alpha: float = 0.05,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Percentile bootstrap over documents.

    Args:
        pairs: One (predicted, gold) pair per document.
        statistic: Maps a sample of pairs to a number (e.g.
            ``lambda p: micro_prf(p).f1``).
        n_resamples: Bootstrap draws.
        alpha: Two-sided miss probability (0.05 -> 95% CI).
        seed: Fixed by default — a CI that changes between runs on the
            same data is a bug report, not randomness.

    Returns:
        Point estimate on the full sample plus the percentile interval.
    """
    if not pairs:
        return Interval(point=0.0, low=0.0, high=0.0, n_docs=0)
    rng = random.Random(seed)
    n = len(pairs)
    stats = sorted(
        statistic([pairs[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples)
    )
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    return Interval(point=statistic(pairs), low=stats[lo_idx], high=stats[hi_idx], n_docs=n)


SUBRULE_LETTERS = "abcdefghijkmnpqrstuvwxyz"  # the CR skips l and o


def rule_family(number: str) -> str:
    """Drop a rule's trailing subrule letter: ``"702.33d"`` -> ``"702.33"``.

    Used only by the secondary citation score. Naming `608.2` where the gold
    says `608.2b` is the right rule at the wrong depth, and exact match counts
    that twice against — once as a miss, once as a spurious edge. Collapsing to
    the family separates "wrong rule" from "right rule, wrong leaf", which are
    different failures needing different fixes.

    Lives here rather than in a script because two different measurements use
    it — the E-003 score and the intra-annotator ceiling it is read against.
    Two copies could drift, and then the ceiling would no longer bound the
    score.
    """
    return number.rstrip(SUBRULE_LETTERS)


def by_family(scored: Mapping[str, Iterable[Hashable]]) -> dict[str, frozenset[Hashable]]:
    """Re-key ``(ruling_id, rule_number)`` items onto their rule family."""
    return {
        rid: frozenset((r, rule_family(str(n))) for r, n in items) for rid, items in scored.items()
    }


def cluster_proportion_ci(
    clusters: Sequence[Sequence[bool]],
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    alpha: float = 0.05,
    seed: int = DEFAULT_SEED,
) -> Interval:
    """Proportion of true flags, bootstrapped over clusters rather than items.

    Same reason the P/R/F1 intervals resample documents: several
    disagreements can come from one ruling, and they are not independent
    — misreading a ruling produces a run of correlated errors. Resampling
    items would treat those as separate evidence and report an interval
    that is too narrow.

    Args:
        clusters: One sequence of flags per cluster (e.g. per ruling).
        n_resamples: Bootstrap draws.
        alpha: Two-sided miss probability (0.05 -> 95% CI).
        seed: Fixed, so the interval is a property of the data.

    Returns:
        The pooled proportion with its percentile interval; ``n_docs`` is
        the number of clusters, not the number of items.
    """
    flat = [flag for cluster in clusters for flag in cluster]
    if not flat:
        return Interval(point=0.0, low=0.0, high=0.0, n_docs=0)

    def proportion(sample: Sequence[Sequence[bool]]) -> float:
        items = [flag for cluster in sample for flag in cluster]
        return sum(items) / len(items) if items else 0.0

    rng = random.Random(seed)
    n = len(clusters)
    stats = sorted(
        proportion([clusters[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples)
    )
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    return Interval(
        point=sum(flat) / len(flat), low=stats[lo_idx], high=stats[hi_idx], n_docs=n
    )


def rule_of_three_upper(n_clusters: int) -> float:
    """95% upper bound on the rate of an event not seen in ``n`` clean trials.

    The companion to :func:`cluster_proportion_ci`, and the reason it needs
    one. A percentile bootstrap resamples the observed values, so a sample
    with no variation — 40 verdicts that all came out the same way —
    resamples to itself every time and reports ``[1.000, 1.000]``. That is
    arithmetically correct and rhetorically false: it reads as certainty
    when the data only ever said "not seen yet".

    ``3/n`` is the standard bound for zero events in n trials. Pass the
    number of *clusters*, not items, for the same reason the intervals
    resample documents.
    """
    return 3.0 / n_clusters if n_clusters else 1.0


@dataclass(frozen=True)
class McNemar:
    """A paired before/after comparison on the same items.

    Attributes:
        improved: Items the first round got wrong and the second got right.
        regressed: Items the first got right and the second got wrong.
        p_value: Exact two-sided binomial p over the discordant pairs.
        n_pairs: Items compared.
    """

    improved: int
    regressed: int
    p_value: float
    n_pairs: int

    @property
    def discordant(self) -> int:
        return self.improved + self.regressed

    def __str__(self) -> str:
        return (
            f"+{self.improved}/-{self.regressed} of {self.n_pairs} paired, "
            f"p={self.p_value:.3f}"
        )


def mcnemar(before: Sequence[bool], after: Sequence[bool]) -> McNemar:
    """Exact McNemar test for two rounds scored on the same items.

    E-007 iterates a prompt and re-scores the *same* development questions,
    which makes round-over-round a paired comparison — and the registry's
    reporting rules require a paired test for one. An unpaired proportion
    comparison here would throw away the pairing and understate a real
    improvement while overstating a coincidental one.

    Only discordant pairs carry information: items both rounds got right,
    or both got wrong, say nothing about which round is better. The exact
    binomial is used rather than the chi-square approximation because the
    discordant count on 10 development questions will be small, which is
    exactly where the approximation misbehaves.

    Args:
        before: Per-item outcome in the earlier round.
        after: Per-item outcome in the later round, same order.

    Returns:
        A :class:`McNemar`. With no discordant pairs the p-value is 1.0 —
        no evidence of a difference, which is not the same as evidence of
        no difference.

    Raises:
        ValueError: If the two sequences are not the same length, since
            that means they are not paired.
    """
    if len(before) != len(after):
        raise ValueError(f"unpaired sequences: {len(before)} vs {len(after)}")
    improved = sum(1 for b, a in zip(before, after, strict=True) if not b and a)
    regressed = sum(1 for b, a in zip(before, after, strict=True) if b and not a)
    n = improved + regressed
    if n == 0:
        return McNemar(0, 0, 1.0, len(before))
    smaller = min(improved, regressed)
    tail = sum(math.comb(n, k) for k in range(smaller + 1)) / (2**n)
    return McNemar(improved, regressed, min(1.0, 2 * tail), len(before))


@dataclass(frozen=True)
class StratumReport:
    """P/R/F1 with CIs for one stratum (or the overall pool)."""

    stratum: str
    counts: PRF
    precision: Interval
    recall: Interval
    f1: Interval


def evaluate_by_stratum(
    predicted_by_doc: Mapping[str, frozenset[Hashable]],
    gold_by_doc: Mapping[str, frozenset[Hashable]],
    *,
    stratum_by_doc: Mapping[str, str] | None = None,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> list[StratumReport]:
    """Full report: overall pool first, then each stratum.

    Documents present in the gold mapping but absent from predictions
    count as empty predictions (their gold items become false negatives) —
    a system that skips a hard document does not get to drop it from the
    denominator. Predicted-only documents are ignored: they were not
    annotated, so nothing can be said about them.
    """
    docs = sorted(gold_by_doc)
    pairs_by_stratum: dict[str, list[DocPair]] = {"overall": []}
    for doc in docs:
        pair = (predicted_by_doc.get(doc, frozenset()), gold_by_doc[doc])
        pairs_by_stratum["overall"].append(pair)
        if stratum_by_doc is not None:
            stratum = stratum_by_doc.get(doc, "unstratified")
            pairs_by_stratum.setdefault(stratum, []).append(pair)

    reports = []
    for stratum, pairs in pairs_by_stratum.items():
        reports.append(
            StratumReport(
                stratum=stratum,
                counts=micro_prf(pairs),
                precision=bootstrap_ci(
                    pairs, lambda p: micro_prf(p).precision, n_resamples=n_resamples, seed=seed
                ),
                recall=bootstrap_ci(
                    pairs, lambda p: micro_prf(p).recall, n_resamples=n_resamples, seed=seed
                ),
                f1=bootstrap_ci(
                    pairs, lambda p: micro_prf(p).f1, n_resamples=n_resamples, seed=seed
                ),
            )
        )
    return reports
