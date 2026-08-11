"""The E-007 claim unit: segmentation, labels, and the guards on the score.

The threshold of Phase 5 is "100% of factual claims carry a citation", so
the denominator decides the verdict. This module exists to take that
decision away from the person reading the answers.

Two properties do the work:

1. **Segmentation is mechanical and happens on citation-stripped text.**
   Where a sentence ends cannot depend on where a citation sits, and the
   worksheet is frozen with a hash before any citation is re-attached.
2. **Exclusions are counted and can void the score.** A `non_factual`
   label is the one lever that shrinks the denominator, so its rate is
   reported beside coverage and above :data:`EXCLUSION_VOID` the coverage
   figure is not reportable — at that point the metric is measuring the
   segmentation rather than the answers.

Scoring rules registered in `experiments/registry.md` (E-007) and the
labelling procedure in `docs/claim-annotation-guide.md`; this module is
their implementation and deliberately holds no policy of its own.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from graphrag_mtg.generation.citations import MARKER, handles, normalize_spacing

#: Above this share of `non_factual` rows the coverage figure is void.
EXCLUSION_VOID = 0.20

#: Sentence boundary: punctuation, **whitespace**, then something that can
#: open a sentence. Requiring the whitespace is what keeps `613.4 then`
#: intact — this corpus is full of numbers whose dots are not full stops,
#: and the dot inside `613.4` is followed by a digit, never a space. A
#: sentence that genuinely ends in a digit (`it is a 1/1.`) still splits,
#: which a naive "no dots after digits" guard would have broken.
#: ``\x00`` appears in the lookahead because :func:`segment_answer` puts a
#: sentinel where each citation marker was, and a sentence may open with
#: one.
_SENTENCE = re.compile("(?<=[.!?])\\s+(?=[\"'(\\[\x00]?[A-Z0-9])")


class Label(StrEnum):
    """Whether a segmented sentence counts toward coverage."""

    FACTUAL = "factual"
    NON_FACTUAL = "non_factual"
    UNLABELLED = "unlabelled"


class Support(StrEnum):
    """Whether the cited evidence carries the claim."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "n/a"  # uncited, or the row is not factual


class Failure(StrEnum):
    """How an unsupported citation failed. Mandatory on every unsupported row.

    Without this field E-007's prediction — that the commonest failure is
    the wrong subrule under the right rule — cannot be scored, and an
    unfalsifiable prediction is not a prediction.
    """

    WRONG_LEAF = "wrong_leaf"
    RIGHT_EVIDENCE_WRONG_READING = "right_evidence_wrong_reading"
    UNRELATED_EVIDENCE = "unrelated_evidence"
    EVIDENCE_ABSENT = "evidence_absent"
    CLAIM_NOT_IN_EVIDENCE = "claim_not_in_evidence"


class Sufficiency(StrEnum):
    """Whether the retrieved subgraph could answer the question at all.

    Labelled before any generated answer is read, and frozen. It is what
    makes "the refusal was correct" a fact about the evidence rather than
    a judgement made after seeing the refusal.
    """

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, deterministically.

    Deliberately simple: the same input must always produce the same rows,
    because the worksheet's hash is what the audit's integrity rests on.
    A sentence split badly is labelled as it stands and noted, never
    re-split after the fact.
    """
    return [part.strip() for part in _SENTENCE.split(text.strip()) if part.strip()]


#: Stands in for a citation marker while sentences are being split. Carries
#: no punctuation and no whitespace, so it cannot move a boundary.
_SENTINEL = "\x00"


def segment_answer(answer: str) -> list[tuple[str, bool]]:
    """Split an answer into ``(sentence, was_cited)`` pairs.

    The obvious implementation — split the stripped text, then separately
    split the original to recover which sentence had a marker — is wrong,
    because the two splits can disagree and the rows silently misalign.
    Instead each marker becomes a punctuation-free sentinel, so boundaries
    fall exactly where they fall in the stripped text, and the flag comes
    from the same chunk the sentence came from.

    Returns:
        One pair per sentence: the citation-free text, and whether the
        sentence carried at least one marker.
    """
    chunks = split_sentences(MARKER.sub(_SENTINEL, answer))
    return [
        (normalize_spacing(chunk.replace(_SENTINEL, "")), _SENTINEL in chunk)
        for chunk in chunks
        if normalize_spacing(chunk.replace(_SENTINEL, ""))
    ]


def segment_with_handles(answer: str) -> list[tuple[str, bool, list[str]]]:
    """:func:`segment_answer`, plus the handles each sentence cited.

    Row for row identical to :func:`segment_answer` — same split, same
    order, same exclusions — so a worksheet row can be shown next to the
    evidence it is judged against without re-deriving the segmentation and
    risking a different one. Markers belonging to a sentence that
    segmentation drops are consumed with it rather than sliding onto the
    next row.

    Returns:
        One triple per sentence: the citation-free text, whether it carried
        a marker, and every handle those markers named, in order.
    """
    bodies = deque(match.group(1) for match in MARKER.finditer(answer))
    rows: list[tuple[str, bool, list[str]]] = []
    for chunk in split_sentences(MARKER.sub(_SENTINEL, answer)):
        cited = [handle for _ in range(chunk.count(_SENTINEL)) for handle in handles(bodies.popleft())]
        sentence = normalize_spacing(chunk.replace(_SENTINEL, ""))
        if sentence:
            rows.append((sentence, _SENTINEL in chunk, cited))
    return rows


@dataclass
class ClaimRow:
    """One worksheet row: a sentence, and everything judged about it.

    Attributes:
        question_id: The question this answer belongs to — the cluster.
        index: Position of the sentence in the answer.
        sentence: The citation-stripped text, exactly as segmented.
        cited: Whether the original sentence carried a citation marker.
        label: Filled by the annotator in the labelling pass.
        support: Filled only for cited factual rows.
        failure: Mandatory when ``support`` is ``UNSUPPORTED``.
        comment: Free text — where a bad split is recorded rather than fixed.
    """

    question_id: str
    index: int
    sentence: str
    cited: bool = False
    label: Label = Label.UNLABELLED
    support: Support = Support.NOT_APPLICABLE
    failure: Failure | None = None
    comment: str = ""

    @property
    def counts_toward_coverage(self) -> bool:
        return self.label is Label.FACTUAL


def worksheet_hash(rows: Sequence[ClaimRow]) -> str:
    """Hash the segmentation, so a later edit is detectable.

    Covers the question id, position and sentence — the segmentation
    itself — and deliberately **not** the labels, which are supposed to
    change. Re-segmenting an answer after seeing its citations would
    change this hash, which is the point.
    """
    payload = "\n".join(f"{row.question_id}|{row.index}|{row.sentence}" for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Coverage:
    """Coverage with everything needed to read it honestly.

    Attributes:
        cited: Factual claims carrying a citation.
        factual: Factual claims in total — the denominator.
        excluded: Rows labelled `non_factual`.
        segmented: Every row, factual or not.
        clusters: Answers contributing at least one factual claim.
        answers: Answers segmented, including refusals with no claims.
    """

    cited: int
    factual: int
    excluded: int
    segmented: int
    clusters: int
    answers: int

    @property
    def rate(self) -> float | None:
        """``None`` when nothing was claimed — not 1.0, and not 0.0.

        A run of pure refusals produces zero factual claims, and 0/0 is
        undefined rather than perfect. Returning ``None`` is what stops
        "every answer refused" from rendering as coverage 100%, which is
        the degenerate pass this design was rebuilt to make impossible.
        """
        return self.cited / self.factual if self.factual else None

    @property
    def exclusion_rate(self) -> float:
        return self.excluded / self.segmented if self.segmented else 0.0

    @property
    def voided(self) -> bool:
        """Whether exclusions grew large enough to be measuring themselves."""
        return self.exclusion_rate > EXCLUSION_VOID

    def __str__(self) -> str:
        rate = "n/a (no factual claims)" if self.rate is None else f"{self.rate:.3f}"
        return (
            f"coverage {rate} = {self.cited}/{self.factual} claims over "
            f"{self.clusters} answering / {self.answers} answers; "
            f"excluded {self.excluded}/{self.segmented} ({self.exclusion_rate:.1%})"
            + (" — VOID" if self.voided else "")
        )


def coverage(rows: Iterable[ClaimRow]) -> Coverage:
    """Coverage over factual claims, with its denominators exposed."""
    rows = list(rows)
    factual = [row for row in rows if row.counts_toward_coverage]
    return Coverage(
        cited=sum(1 for row in factual if row.cited),
        factual=len(factual),
        excluded=sum(1 for row in rows if row.label is Label.NON_FACTUAL),
        segmented=len(rows),
        clusters=len({row.question_id for row in factual}),
        answers=len({row.question_id for row in rows}),
    )


def support_clusters(rows: Iterable[ClaimRow]) -> list[list[bool]]:
    """Per-question support flags, ready for a cluster bootstrap.

    Clustering is by question because claims inside one answer share a
    prompt, a subgraph and an error mode. Questions contributing no cited
    factual claim contribute no cluster — which is why the cluster count
    is printed everywhere rather than assumed to be the sample size.
    """
    buckets: dict[str, list[bool]] = {}
    for row in rows:
        if row.counts_toward_coverage and row.support is not Support.NOT_APPLICABLE:
            buckets.setdefault(row.question_id, []).append(row.support is Support.SUPPORTED)
    return [flags for _, flags in sorted(buckets.items())]


def failure_counts(rows: Iterable[ClaimRow]) -> dict[str, int]:
    """How the unsupported citations failed, by taxonomy code."""
    counts: dict[str, int] = {}
    for row in rows:
        if row.support is Support.UNSUPPORTED and row.failure is not None:
            counts[row.failure.value] = counts.get(row.failure.value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


@dataclass
class RefusalReport:
    """Refusals read against the frozen sufficiency labels.

    The two error directions are what keep the refusal rule from being a
    free pass. ``over_refusal`` is the only one carrying a DoD threshold —
    it is the case where the evidence was demonstrably present.
    """

    over_refusal: list[str] = field(default_factory=list)
    unsupported_answering: list[str] = field(default_factory=list)
    correct_refusal: list[str] = field(default_factory=list)
    partial_refused: list[str] = field(default_factory=list)
    partial_answered: list[str] = field(default_factory=list)

    @property
    def blocks_dod(self) -> bool:
        return bool(self.over_refusal)

    def __str__(self) -> str:
        return (
            f"over-refusal {len(self.over_refusal)} (DoD "
            f"{'BLOCKED' if self.blocks_dod else 'clear'}); "
            f"unsupported answering {len(self.unsupported_answering)}; "
            f"correct refusal {len(self.correct_refusal)}; "
            f"partial: {len(self.partial_refused)} refused / "
            f"{len(self.partial_answered)} answered"
        )


def classify_refusals(
    refused_by_question: dict[str, bool],
    sufficiency: dict[str, Sufficiency],
) -> RefusalReport:
    """Sort each answer into its refusal outcome against frozen labels.

    On a `partial` subgraph both a refusal and a hedged answer are correct
    behaviour — `subgraph.serialize()` itself invites the hedge — so those
    are counted and reported, never scored as errors. The threshold lives
    only on `sufficient`, where the evidence was there to be used.
    """
    report = RefusalReport()
    for question, refused in sorted(refused_by_question.items()):
        label = sufficiency.get(question)
        if label is Sufficiency.SUFFICIENT and refused:
            report.over_refusal.append(question)
        elif label is Sufficiency.INSUFFICIENT and refused:
            report.correct_refusal.append(question)
        elif label is Sufficiency.INSUFFICIENT and not refused:
            report.unsupported_answering.append(question)
        elif label is Sufficiency.PARTIAL:
            (report.partial_refused if refused else report.partial_answered).append(question)
    return report
