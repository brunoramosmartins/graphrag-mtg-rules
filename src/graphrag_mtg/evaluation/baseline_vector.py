"""Arm A: the vector baseline, built to be hard to beat.

The roadmap's risk register marks a strawman baseline **critical**, and
names the mitigation: build it with the real pipeline and good-faith
tuning, and review it as though defending the vector side. Everything
awkward in this module comes from that instruction.

What the pins fix, and what this implements:

  * **Pin 2 — hybrid, not dense-only.** Lexical and dense, fused. The CR
    has exact-token semantics (`613.4b`) and terms of art whose
    ordinary-English embedding misleads (`flying`, `protection`,
    *Humility*), and a dense retriever is built to collapse exactly those
    distinctions. Dense-only and lexical-only run as **ablations** and are
    published whatever they say.
  * **Pin 3 — chunking follows the CR's own hierarchy**, with fixed-size
    windows as a registered ablation (`corpus.window_chunks`).
  * **Pin 4 — a reranker behind a flag**, swept on the development split,
    reported on and off. Its absence would not make the baseline
    dismissible; the absence of the experiment would.
  * **Pin 13 — iterative retrieval is a protocol variable**, on and off,
    published, and offered to every arm that can accept it. Arm B is
    single-shot by construction today and that is declared rather than
    quietly enjoyed here.
  * **Budget parity — matched on token budget**, since that is the
    constraint both arms face at generation, with item counts reported
    beside it.

Fusion is **reciprocal rank fusion**, not a weighted score sum. BM25
scores and cosine similarities live on incomparable scales, so any
weighted sum needs a normalisation constant — and a constant chosen after
seeing which arm it favours is the thing pin 7 exists to prevent. RRF
needs one parameter, it is the published default, and it reads ranks.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from graphrag_mtg.evaluation.bm25 import Bm25Index
from graphrag_mtg.evaluation.corpus import Document
from graphrag_mtg.evaluation.dense import DenseIndex, Encoder

#: RRF's damping constant, at its published default. Untuned, and pin 7
#: governs any change: a tuned value arrives as a swept artefact with the
#: sweep published, never as a constant someone adjusted.
RRF_K = 60

#: How deep each half is read before fusion. Larger than the final `k` on
#: purpose — a document ranked 30th by one half and 2nd by the other is
#: exactly what fusion exists to recover, and a shallow read throws it
#: away before the fusion can see it.
CANDIDATE_DEPTH = 100

#: Tokens the retrieved context may occupy. Matched to the graph arms'
#: `subgraph.DEFAULT_TOKEN_BUDGET`, per the registered budget-parity rule:
#: token budget is the constraint both arms actually face at generation,
#: and item counts are reported beside it rather than matched.
DEFAULT_TOKEN_BUDGET = 6000


@dataclass
class Retrieved:
    """What arm A hands to generation, with everything the audit needs.

    Attributes:
        documents: The passages, in the order they were fused.
        mode: `hybrid`, `dense` or `lexical` — which ablation ran.
        rounds: How many retrieval rounds fired. 1 unless iterative.
        considered: Documents fused before the budget trimmed anything.
        truncated: Documents dropped by the token budget. Reported per
            arm per question, the way `dropped`/`capped` are for the
            graph arms — an arm that silently truncates is an arm whose
            recall figure means something different from its neighbour's.
        tokens: Estimated tokens of the kept context.
    """

    documents: list[Document]
    mode: str = "hybrid"
    rounds: int = 1
    considered: int = 0
    truncated: int = 0
    tokens: int = 0

    @property
    def doc_ids(self) -> list[str]:
        return [document.doc_id for document in self.documents]

    def rule_numbers(self) -> list[str]:
        """Rule numbers present in the context, for pin 6's grading."""
        seen: list[str] = []
        for document in self.documents:
            if document.rule_number and document.rule_number not in seen:
                seen.append(document.rule_number)
        return seen


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, k: int = RRF_K
) -> list[str]:
    """Fuse ranked id lists by reciprocal rank.

    Args:
        rankings: One ranked list of `doc_id`s per retriever.
        k: The damping constant. Larger flattens the contribution of top
            ranks; the published default is 60.

    Returns:
        Ids ordered by summed reciprocal rank, ties broken by id so a run
        is reproducible.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda doc_id: (-scores[doc_id], doc_id))


def estimate_tokens(text: str) -> int:
    """The chars/4 heuristic the rest of the project prints."""
    return len(text) // 4


def enforce_budget(
    documents: Sequence[Document], budget: int
) -> tuple[list[Document], int, int]:
    """Keep documents in rank order until the token budget is spent.

    Returns:
        The kept documents, the tokens they occupy, and how many were
        dropped. Truncation is returned rather than logged, because pin 11
        suppresses the notice that would otherwise tell the model — so the
        only place the trim can be seen is the run record.
    """
    kept: list[Document] = []
    tokens = 0
    for document in documents:
        cost = estimate_tokens(document.text)
        if tokens + cost > budget and kept:
            break
        kept.append(document)
        tokens += cost
    return kept, tokens, len(documents) - len(kept)


class Reranker:
    """What pin 4 requires exist behind a flag.

    Deliberately an interface with no default implementation rather than a
    stub that silently does nothing: a reranker that reorders by identity
    would let a run report `rerank=on` while nothing reranked, which is
    worse than not having built it.
    """

    def rerank(self, query: str, documents: Sequence[Document]) -> list[Document]:
        raise NotImplementedError


@dataclass
class VectorArm:
    """The retriever, with every registered ablation behind a flag.

    Attributes:
        documents: The corpus, positionally irrelevant — indexed by id.
        lexical: The BM25 half.
        dense: The vector half, or None when running the lexical ablation.
        encoder: Encodes the query. Required whenever `dense` is set.
        reranker: Pin 4's reranker, or None for the off state.
        token_budget: Budget parity with the graph arms.
    """

    documents: Sequence[Document]
    lexical: Bm25Index | None
    dense: DenseIndex | None = None
    encoder: Encoder | None = None
    reranker: Reranker | None = None
    token_budget: int = DEFAULT_TOKEN_BUDGET
    _by_id: dict[str, Document] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.lexical is None and self.dense is None:
            raise ValueError("arm A needs at least one half; both were None")
        if self.dense is not None and self.encoder is None:
            raise ValueError("a dense index without an encoder cannot embed a query")
        self._by_id = {document.doc_id: document for document in self.documents}

    @property
    def mode(self) -> str:
        if self.lexical is not None and self.dense is not None:
            return "hybrid"
        return "lexical" if self.lexical is not None else "dense"

    def _rankings(self, query: str, depth: int) -> list[list[str]]:
        rankings: list[list[str]] = []
        if self.lexical is not None:
            rankings.append([hit.doc_id for hit in self.lexical.search(query, k=depth)])
        if self.dense is not None and self.encoder is not None:
            vector = self.encoder.encode([query])[0]
            rankings.append([hit.doc_id for hit in self.dense.search(vector, k=depth)])
        return rankings

    def retrieve(
        self, question: str, *, depth: int = CANDIDATE_DEPTH, iterative: bool = False
    ) -> Retrieved:
        """Retrieve for one question.

        Args:
            question: The question, verbatim.
            depth: How deep each half is read before fusion.
            iterative: Pin 13's protocol variable. A second round is seeded
                with the rule numbers the first round surfaced, which is
                the affordance the hypothesis calls path-walking. Off by
                default; both states are published, and the graph's margin
                is reported against the **stronger** of the two.

        Returns:
            A :class:`Retrieved` carrying the context and the trim record.
        """
        rankings = self._rankings(question, depth)
        rounds = 1
        if iterative:
            first = reciprocal_rank_fusion(rankings)[:depth]
            seeds = [
                self._by_id[doc_id].rule_number
                for doc_id in first
                if self._by_id.get(doc_id) and self._by_id[doc_id].rule_number
            ]
            if seeds:
                followup = f"{question} {' '.join(dict.fromkeys(seeds[:10]))}"
                rankings.extend(self._rankings(followup, depth))
                rounds = 2

        fused = reciprocal_rank_fusion(rankings)
        documents = [self._by_id[doc_id] for doc_id in fused if doc_id in self._by_id]
        considered = len(documents)
        if self.reranker is not None:
            documents = self.reranker.rerank(question, documents)
        kept, tokens, truncated = enforce_budget(documents, self.token_budget)
        return Retrieved(
            documents=kept,
            mode=self.mode,
            rounds=rounds,
            considered=considered,
            truncated=truncated,
            tokens=tokens,
        )


def serialize(retrieved: Retrieved) -> str:
    """Render arm A's context in the shape the graph arms' contexts take.

    The generator prompt `p5-a3` was iterated against graph serializations
    and asks for `kind:key` citation handles. Pin 1's parity check compares
    the malformed-citation rate, refusal rate and answer length per arm on
    the dress rehearsal; handing arm A a differently-shaped context and
    then comparing citation quality would measure the adapter. So the
    handles are the same `kind:key` shape, drawn from the same corpus ids.

    No incompleteness notice is emitted, per pin 11 — for every arm.
    """
    if not retrieved.documents:
        return "NO EVIDENCE (nothing retrieved)."
    by_kind: dict[str, list[Document]] = {}
    for document in retrieved.documents:
        by_kind.setdefault(document.kind, []).append(document)
    lines: list[str] = []
    for kind, group in by_kind.items():
        lines.append(f"## {kind}")
        for document in group:
            lines.append(f"[{document.doc_id}] {document.text}")
            lines.append(f"    via {retrieved.mode} retrieval: {document.title}")
    return "\n".join(lines)


def build_arm(
    documents: Sequence[Document],
    *,
    mode: str = "hybrid",
    vectors: Sequence[Sequence[float]] | None = None,
    encoder: Encoder | None = None,
    reranker: Reranker | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> VectorArm:
    """Assemble arm A in one of its three registered modes.

    Args:
        documents: The corpus from `evaluation.corpus.build_corpus`.
        mode: `hybrid` (pinned), or the `dense`/`lexical` ablations.
        vectors: Document vectors, required for `hybrid` and `dense`.
        encoder: Query encoder, required for `hybrid` and `dense`.
        reranker: Pin 4's reranker, or None.
        token_budget: Budget parity with the graph arms.

    Raises:
        ValueError: on an unknown mode, or a dense mode with no vectors.
            Silently degrading to lexical would publish an ablation under
            the hybrid's name.
    """
    if mode not in {"hybrid", "dense", "lexical"}:
        raise ValueError(f"unknown mode {mode!r} (expected hybrid, dense or lexical)")
    doc_ids = [document.doc_id for document in documents]
    lexical = (
        Bm25Index(doc_ids, (d.text for d in documents)) if mode in {"hybrid", "lexical"} else None
    )
    dense = None
    if mode in {"hybrid", "dense"}:
        if vectors is None or encoder is None:
            raise ValueError(f"mode {mode!r} needs vectors and an encoder")
        dense = DenseIndex(doc_ids, vectors)
    return VectorArm(
        documents=documents,
        lexical=lexical,
        dense=dense,
        encoder=encoder if dense is not None else None,
        reranker=reranker,
        token_budget=token_budget,
    )


def gold_rules_found(retrieved: Retrieved, gold: Iterable[str]) -> tuple[int, int]:
    """Pin 6's grading: gold rule numbers present in the retrieved context.

    Returns:
        `(found, wanted)`. `wanted` is 0 for `legality_1hop`, whose
        `gold_cr_rules` is empty by construction — pin 9 gives that
        stratum its own metric rather than pooling an undefined recall
        into rule-number recall.
    """
    wanted = list(dict.fromkeys(gold))
    present = set(retrieved.rule_numbers())
    return sum(1 for rule in wanted if rule in present), len(wanted)


def legality_fact_present(retrieved: Retrieved, oracle_id: str, fmt: str) -> str | None:
    """Pin 9's metric: the `(card, format, status)` fact in the context.

    Returns:
        The status arm A could read for that card and format, or None if
        the card's document never reached the context. Judged
        deterministically, reported under its own name, never pooled into
        rule-number recall.
    """
    for document in retrieved.documents:
        if document.kind == "card" and document.oracle_id == oracle_id:
            return document.legalities.get(fmt)
    return None
