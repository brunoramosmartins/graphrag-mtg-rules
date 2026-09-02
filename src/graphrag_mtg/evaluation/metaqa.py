"""MetaQA adapter — reading the benchmark, and keeping it out of the graph.

E-002 calibrates the *generic spine* of this project — typed traversal from
a seeded entity, the subgraph budget, citable evidence, grounded generation
— against a benchmark that has an answer key. It does not calibrate the
pipeline: the linker resolves card names against a Scryfall lexicon and
every retrieval template is written in ``Card`` / ``Keyword`` / ``Rule``, and
none of that runs on a movie KG. The registry entry states the narrow claim.

Nothing here downloads anything. MetaQA is an academic dataset with its own
licence; the caller supplies a local directory and this module reads it,
asserting the format loudly rather than guessing at it.

Expected layout (MetaQA "vanilla" release)::

    <root>/kb.txt                      head|relation|tail per line
    <root>/1-hop/vanilla/qa_test.txt   question with [entity]<TAB>ans1|ans2
    <root>/2-hop/vanilla/qa_test.txt
    <root>/3-hop/vanilla/qa_test.txt

Labels and relationship types are **prefixed** on load (``MQ_Entity``,
``MQ_DIRECTED_BY``) so that a misconfigured connection cannot match a Magic
pattern, and the loader refuses a database that already holds anything.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from graphrag_mtg.generation.answerer import REFUSAL
from graphrag_mtg.retrieval.subgraph import Evidence

if TYPE_CHECKING:
    from neo4j import Session

#: Citation markers, stripped before an answer line becomes a prediction.
_CITATION = re.compile(r"\[[^\]]*\]")

#: Prefix carried by every MetaQA label and relationship type. A foreign KB
#: of this size shares a server with the production graph; the prefix is the
#: cheap half of keeping them apart, the separate database is the other half.
PREFIX = "MQ_"

#: Node label for every MetaQA entity. The benchmark's KB is untyped — a
#: movie, a person and a genre are all just strings joined by relations —
#: so inventing types here would be modelling, not adapting.
ENTITY_LABEL = f"{PREFIX}Entity"

HOPS = (1, 2, 3)


@dataclass(frozen=True)
class Triple:
    """One KB edge, verbatim from ``kb.txt``."""

    head: str
    relation: str
    tail: str

    @property
    def rel_type(self) -> str:
        """The Cypher relationship type, prefixed and upper-cased."""
        return PREFIX + "".join(
            ch if ch.isalnum() else "_" for ch in self.relation
        ).upper()


@dataclass(frozen=True)
class Question:
    """One benchmark question with its seed entity and full answer set.

    Attributes:
        qid: Stable id, ``mq-<hop>-<line>``; the line number is the identity
            because MetaQA ships no ids of its own.
        hops: 1, 2 or 3 — the reasoning depth the question set declares.
        text: The question with the seed entity's brackets removed.
        seed: The entity named in brackets, which is where traversal starts.
        answers: Every accepted answer. Hits@1 is scored against the whole
            set, not against the first element — several MetaQA questions
            are genuinely multi-answer and scoring against one of them would
            silently penalise correct output.
    """

    qid: str
    hops: int
    text: str
    seed: str
    answers: tuple[str, ...]


class MetaQAFormatError(ValueError):
    """The files on disk are not the layout this adapter was written for."""


def read_kb(path: Path) -> list[Triple]:
    """Parse ``kb.txt`` into triples.

    Args:
        path: The ``kb.txt`` file.

    Returns:
        Every triple, in file order, duplicates preserved — deduplication is
        the loader's job and doing it here would hide a corrupt file.

    Raises:
        MetaQAFormatError: If a non-empty line does not hold exactly three
            pipe-separated fields.
    """
    triples: list[Triple] = []
    for number, line in enumerate(_lines(path), start=1):
        parts = line.split("|")
        if len(parts) != 3 or not all(part.strip() for part in parts):
            raise MetaQAFormatError(
                f"{path}:{number}: expected 'head|relation|tail', got {line!r}"
            )
        triples.append(Triple(*(part.strip() for part in parts)))
    if not triples:
        raise MetaQAFormatError(f"{path} holds no triples.")
    return triples


def read_questions(path: Path, hops: int) -> list[Question]:
    """Parse one ``qa_*.txt`` file.

    Args:
        path: The question file.
        hops: The reasoning depth this file's directory declares, carried
            onto every question so the per-hop report never has to infer it.

    Returns:
        The questions in file order.

    Raises:
        MetaQAFormatError: If a line lacks its tab separator, its bracketed
            seed entity, or its answers.
    """
    questions: list[Question] = []
    for number, line in enumerate(_lines(path), start=1):
        question, _, answers = line.partition("\t")
        if not answers:
            raise MetaQAFormatError(
                f"{path}:{number}: expected 'question<TAB>answers', got {line!r}"
            )
        start, end = question.find("["), question.find("]")
        if start < 0 or end < start:
            raise MetaQAFormatError(
                f"{path}:{number}: no bracketed seed entity in {question!r}"
            )
        parsed = tuple(a.strip() for a in answers.split("|") if a.strip())
        if not parsed:
            raise MetaQAFormatError(f"{path}:{number}: no answers in {line!r}")
        questions.append(
            Question(
                qid=f"mq-{hops}-{number}",
                hops=hops,
                text=question.replace("[", "").replace("]", "").strip(),
                seed=question[start + 1 : end].strip(),
                answers=parsed,
            )
        )
    if not questions:
        raise MetaQAFormatError(f"{path} holds no questions.")
    return questions


def question_path(root: Path, hops: int, split: str = "test") -> Path:
    """Locate one hop's question file inside a MetaQA release."""
    return root / f"{hops}-hop" / "vanilla" / f"qa_{split}.txt"


def sample(
    questions: Sequence[Question], n: int, seed: int
) -> list[Question]:
    """Draw the registered subset, or refuse to pretend one was drawn.

    Args:
        questions: The full split for one hop.
        n: How many to draw. Drawing more than exist is an error rather
            than a silent full-set return, because the registered n is what
            the interval is computed against.
        seed: The registered seed.

    Returns:
        ``n`` questions, in a stable order.

    Raises:
        ValueError: If fewer than ``n`` questions exist.
    """
    if len(questions) < n:
        raise ValueError(
            f"asked for {n} questions, the split holds {len(questions)}. "
            "The registered subset size is what every interval is computed "
            "against; silently returning fewer changes the experiment."
        )
    drawn = random.Random(seed).sample(list(questions), n)
    return sorted(drawn, key=lambda q: q.qid)


def freeze(questions: Sequence[Question], path: Path, *, seed: int) -> None:
    """Write the drawn subset **as ids**, refusing to overwrite one that exists.

    Two disciplines meet in this function.

    A redraw after a number exists is the failure `split_golden.py` was
    written to prevent, and E-002 registers the same rule: the file is
    written once and never rewritten.

    And only the ids are written. MetaQA is somebody else's dataset under
    somebody else's licence, so the same posture the golden set takes with
    RulesGuru applies here — version the identifiers, materialise the text
    from the local release at run time, redistribute nothing. It also keeps
    the committed artefact small enough to read.
    """
    if path.exists():
        raise SystemExit(
            f"{path} already exists. The subset is frozen; redrawing it after "
            "a result exists is choosing the sample that suits the result."
        )
    payload = {
        "purpose": "E-002 MetaQA calibration subset",
        "seed": seed,
        "n_per_hop": {
            str(h): sum(1 for q in questions if q.hops == h) for h in HOPS
        },
        "note": (
            "Question ids only. Text and answers are read from the local "
            "MetaQA release at run time; this project redistributes neither."
        ),
        "ids": [q.qid for q in questions],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_frozen(path: Path, root: Path, *, split: str = "test") -> list[Question]:
    """Re-materialise a frozen subset from the local release.

    Args:
        path: The frozen id list.
        root: The MetaQA release directory the ids are read against.
        split: Which question split the ids were drawn from.

    Returns:
        The questions, in the frozen order.

    Raises:
        MetaQAFormatError: If an id in the subset is not in the release —
            which means the release on disk is not the one the subset was
            drawn from, and every number computed against it would be
            against a different sample.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    ids: list[str] = list(raw["ids"])
    wanted_hops = sorted({int(qid.split("-")[1]) for qid in ids})

    available: dict[str, Question] = {}
    for hops in wanted_hops:
        for question in read_questions(question_path(root, hops, split), hops):
            available[question.qid] = question

    missing = [qid for qid in ids if qid not in available]
    if missing:
        raise MetaQAFormatError(
            f"{len(missing)} frozen id(s) are not in the release at {root} "
            f"(first: {missing[0]}). The subset was drawn from a different "
            "release; scoring against this one would score a different sample."
        )
    return [available[qid] for qid in ids]


#: Version of the E-002 generation prompt, recorded on every answer.
PROMPT_VERSION = "e002-a1"

#: The grounding contract, carried over from `generation/answerer.py` with
#: everything domain-specific removed. What E-002 calibrates is this shape —
#: answer only from the evidence, cite the handle, refuse when it is not
#: there — not the Magic instructions the shipped prompt wraps it in. The
#: single-line answer format exists because Hits@1 scores one entity: asking
#: for prose and then guessing which noun was the answer would measure the
#: parser, not the spine.
SYSTEM = f"""You answer questions from retrieved graph evidence.

THE EVIDENCE IS YOUR ONLY SOURCE.
The context lists facts as `head | relation | tail`. If a fact is not in the
context, you do not know it — even if you are certain. An answer built on
what you remember is a wrong answer in this system, however correct it
happens to be.

ANSWER FORMAT.
First line: the answer entity, exactly as it is spelled in the context, and
nothing else — no sentence, no label, no punctuation around it. If several
entities answer the question, write the single best one.
Second line: the citation markers for the facts that support it, copied from
the context in square brackets, e.g. `[triple:4; triple:9]`.

WHEN THE EVIDENCE IS NOT ENOUGH.
Reply exactly `{REFUSAL}` on the first line, followed by one sentence naming
what is missing. This is a correct answer, not a failure. Do not fill a gap
with a plausible entity.
"""

#: Uniqueness constraint, applied before the load. Without it `MERGE` scans
#: the label for every one of 43k entities and the load never finishes.
CONSTRAINT_ENTITY_NAME = (
    f"CREATE CONSTRAINT mq_entity_name IF NOT EXISTS "
    f"FOR (e:{ENTITY_LABEL}) REQUIRE e.name IS UNIQUE"
)

#: One hop out from a frontier. Traversal is undirected: MetaQA's relations
#: are directed but its questions are not — "what movies did X direct" walks
#: `directed_by` backwards — and a directed expansion answers none of them.
EXPAND_FRONTIER = f"""
UNWIND $names AS name
MATCH (a:{ENTITY_LABEL} {{name: name}})-[r]-(b:{ENTITY_LABEL})
RETURN DISTINCT startNode(r).name AS head, type(r) AS relation, endNode(r).name AS tail
"""


def triple_evidence(triples: Sequence[Triple], distance: int, start: int) -> list[Evidence]:
    """Turn KB triples into citable evidence for the shared subgraph budget.

    Args:
        triples: The edges collected at this distance from the seed.
        distance: Hops from the seed entity, which is what
            :func:`~graphrag_mtg.retrieval.subgraph.enforce_budget` trims by
            when the context does not fit.
        start: Ordinal of the first handle, so numbering is continuous
            across levels.

    Returns:
        One :class:`Evidence` per triple, keyed by ordinal. The handle is an
        ordinal rather than the triple's text for the reason rulings are:
        a model asked to copy a long string into a citation gets it wrong,
        and that would fill the measurement of grounding with typing noise.
    """
    return [
        Evidence(
            kind="triple",
            key=str(start + offset),
            text=f"{t.head} | {t.relation} | {t.tail}",
            template=f"metaqa_expand_{distance}",
            path=f"(:{ENTITY_LABEL} {{{t.head}}})-[:{t.rel_type}]->(:{ENTITY_LABEL} {{{t.tail}}})",
            distance=distance,
        )
        for offset, t in enumerate(triples)
    ]


def parse_prediction(text: str) -> str | None:
    """The entity a generated answer asserts, or ``None`` if it refused.

    The rule is fixed here, and tested, before any answer has been read —
    the same discipline :func:`hits_at_1` follows. Deciding later how
    generously to read the model's output is deciding the score.

    Args:
        text: The raw completion.

    Returns:
        The first line, with citation markers and surrounding punctuation
        removed, or ``None`` when the answer is a refusal or is empty.
    """
    if not text or REFUSAL.lower() in text.lower():
        return None
    for line in text.splitlines():
        stripped = _CITATION.sub("", line).strip().strip('".,;:')
        if stripped:
            return stripped
    return None


def hits_at_1(predicted: str | None, question: Question) -> bool:
    """Whether a prediction counts as correct against the whole answer set.

    Comparison is case-insensitive and whitespace-normalised, which is the
    scoring rule fixed here — in the adapter, tested — rather than settled
    later while looking at which failures it would rescue.
    """
    if not predicted:
        return False
    wanted = {_norm(a) for a in question.answers}
    return _norm(predicted) in wanted


# ─────────────────────────────────────────────────────────────────────────────
# Loading — the E-008 lesson, at four orders of magnitude more nodes
# ─────────────────────────────────────────────────────────────────────────────

MERGE_ENTITIES = f"""
UNWIND $names AS name
MERGE (e:{ENTITY_LABEL} {{name: name}})
"""

COUNT_ALL = "MATCH (n) RETURN count(n) AS nodes"

COUNT_PREFIXED = f"MATCH (n:{ENTITY_LABEL}) RETURN count(n) AS nodes"


def edge_statement(rel_type: str) -> str:
    """Cypher for one relationship type.

    The type cannot be parameterised in Cypher, so it is interpolated — and
    is therefore built by :attr:`Triple.rel_type`, which admits only
    alphanumerics and underscores after the ``MQ_`` prefix. Nothing derived
    from a question or a user string reaches this function.
    """
    if not rel_type.startswith(PREFIX) or not rel_type[len(PREFIX):].replace("_", "").isalnum():
        raise ValueError(f"refusing to interpolate an unvetted type: {rel_type!r}")
    return f"""
UNWIND $rows AS row
MATCH (h:{ENTITY_LABEL} {{name: row.head}})
MATCH (t:{ENTITY_LABEL} {{name: row.tail}})
MERGE (h)-[:{rel_type}]->(t)
"""


def display_relation(rel_type: str) -> str:
    """Recover the KB's relation name from the prefixed Cypher type.

    ``MQ_DIRECTED_BY`` -> ``directed_by``. The inverse of
    :attr:`Triple.rel_type`, and lossy in the same place: a relation whose
    name held punctuation comes back with underscores. MetaQA's nine
    relations are all plain snake_case, so nothing is lost on this KB.
    """
    stripped = rel_type[len(PREFIX):] if rel_type.startswith(PREFIX) else rel_type
    return stripped.lower()


def entity_names(triples: Sequence[Triple]) -> list[str]:
    """Every distinct entity in the KB, sorted for a reproducible load."""
    return sorted({t.head for t in triples} | {t.tail for t in triples})


def by_relation(triples: Sequence[Triple]) -> dict[str, list[dict[str, str]]]:
    """Group triples by prefixed relationship type, for batched loading."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for triple in triples:
        grouped.setdefault(triple.rel_type, []).append(
            {"head": triple.head, "tail": triple.tail}
        )
    return grouped


def assert_database_is_empty(session: Session) -> None:
    """Refuse to load into a database that already holds anything.

    E-002 registers a *separate database*, not a namespace. This is the
    check that makes the registration true at runtime: if the session is
    pointing at the Magic corpus, the count is in the hundred thousands and
    the load stops before writing one node. E-008's incident began with a
    `MERGE` that found something already there.

    Args:
        session: A session already opened against the intended target. The
            message names the requirement rather than a specific knob,
            because the isolation mechanism — a second database or a second
            instance — is a deployment decision this module does not make.

    Raises:
        SystemExit: If the target holds any node at all.
    """
    nodes = session.run(COUNT_ALL).single()["nodes"]
    if nodes:
        raise SystemExit(
            f"refusing to load MetaQA: the target already holds {nodes} node(s). "
            "E-002 requires a separate, empty target — a namespace inside the "
            "Magic graph is what deleted three real CR rules in E-008. Point the "
            "connection at an empty MetaQA database or instance and re-run."
        )


def _lines(path: Path) -> Iterator[str]:
    if not path.exists():
        raise MetaQAFormatError(
            f"No MetaQA file at {path}. This adapter downloads nothing — "
            "supply a local MetaQA release with --metaqa-dir."
        )
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield line.strip()


def _norm(value: str) -> str:
    return " ".join(value.split()).casefold()
