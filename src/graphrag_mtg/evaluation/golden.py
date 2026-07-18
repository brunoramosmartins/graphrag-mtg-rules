"""Golden-set data model, loader, and snapshot hashing (Gate G2).

The golden set is versioned as one JSON object per line in
``data/golden/ids_v0.jsonl``. RulesGuru-sourced rows carry **no question
text** (license: eval-only, IDs + fetch; see docs/data-sources.md);
Scryfall-generated and hand-authored rows carry their full text because
that content is ours. See docs/golden-set.md for the design.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path("data/golden/ids_v0.jsonl")


class Stratum(str, Enum):
    """The six question strata (see docs/golden-set.md)."""

    legality_1hop = "legality_1hop"
    definition_1hop = "definition_1hop"
    keyword_rule_2hop = "keyword_rule_2hop"
    rulings_2hop = "rulings_2hop"
    interaction_multihop = "interaction_multihop"
    negative_temporal = "negative_temporal"


class Source(str, Enum):
    """Where a question comes from (drives what may be committed)."""

    rulesguru = "rulesguru"
    scryfall = "scryfall"
    authored = "authored"


class VectorExpectation(str, Enum):
    """A-priori prediction of how the vector baseline should do."""

    tie = "tie"
    lose = "lose"
    fail = "fail"


# Strata whose whole point is that the answer is a path, so a claim of
# graph advantage must be justified in writing.
_REASON_REQUIRED_STRATA = {Stratum.interaction_multihop, Stratum.negative_temporal}


class GoldenQuestion(BaseModel):
    """One annotated golden-set question.

    Attributes:
        id: Stable id (``rg-<n>`` / ``scry-<n>`` / ``hand-<n>``).
        source: Origin; ``rulesguru`` rows must not carry inline text.
        stratum: One of the six strata.
        hops: Number of reasoning hops (>= 1).
        question: Inline question text (only for scryfall/authored).
        answer: Inline answer text (only for scryfall/authored).
        gold_entities: Card names / keywords the answer depends on.
        gold_cr_rules: CR rule numbers on the gold path (e.g. ``613.7c``).
        gold_path: Prose description of the traversal.
        vector_should: A-priori prediction for the vector baseline.
        vector_should_reason: Why — required for fail / interaction / negative.
        rulesguru_url: Canonical link (attribution) for RulesGuru rows.
        snapshot_sha256: Hash of resolved content at curation time.
        verified: True once a human has reviewed the annotation.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    source: Source
    stratum: Stratum
    hops: int = Field(ge=1)
    question: str | None = None
    answer: str | None = None
    gold_entities: list[str] = Field(default_factory=list)
    gold_cr_rules: list[str] = Field(default_factory=list)
    gold_path: str | None = None
    vector_should: VectorExpectation
    vector_should_reason: str | None = None
    rulesguru_url: str | None = None
    snapshot_sha256: str | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _check_invariants(self) -> GoldenQuestion:
        # License guard: never commit RulesGuru question/answer text.
        if self.source == Source.rulesguru and (self.question or self.answer):
            raise ValueError(
                f"{self.id}: RulesGuru rows must not carry inline question/answer "
                "text (license: IDs + fetch only)."
            )
        # Our own content must actually carry the question.
        if self.source in (Source.scryfall, Source.authored) and not self.question:
            raise ValueError(f"{self.id}: {self.source.value} rows require a `question`.")
        # A claimed graph advantage on a path question must be justified —
        # enforced at the gate (a *verified* row must be complete); skeleton
        # rows awaiting annotation are allowed to omit it.
        needs_reason = self.vector_should == VectorExpectation.fail or self.stratum in _REASON_REQUIRED_STRATA
        if self.verified and needs_reason and not self.vector_should_reason:
            raise ValueError(
                f"{self.id}: a verified row with stratum={self.stratum.value} / "
                f"vector_should={self.vector_should.value} requires `vector_should_reason`."
            )
        return self


def load_golden(path: Path | str = DEFAULT_PATH) -> list[GoldenQuestion]:
    """Load and validate a golden-set JSONL file.

    Blank lines and ``//`` comment lines are ignored. Raises
    ``pydantic.ValidationError`` on the first malformed record.
    """
    text = Path(path).read_text(encoding="utf-8")
    out: list[GoldenQuestion] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        out.append(GoldenQuestion.model_validate_json(stripped))
    return out


def dump_golden(questions: list[GoldenQuestion], path: Path | str) -> None:
    """Write questions as one compact JSON object per line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [q.model_dump_json() for q in questions]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def content_sha256(content: str) -> str:
    """Return the hex SHA-256 of a resolved question's content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def snapshot_hash(questions: list[GoldenQuestion]) -> str:
    """Freeze the whole set: a stable hash over ``(id, snapshot_sha256)``.

    Independent of ordering, so re-serializing the set does not change the
    hash; changes only when an id is added/removed or its resolved content
    hash changes (upstream drift).
    """
    joined = "\n".join(
        f"{q.id}:{q.snapshot_sha256 or ''}" for q in sorted(questions, key=lambda q: q.id)
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def counts_by_stratum(questions: list[GoldenQuestion]) -> dict[str, int]:
    """Return the number of questions per stratum (for G2 tracking)."""
    counts = {s.value: 0 for s in Stratum}
    for q in questions:
        counts[q.stratum.value] += 1
    return counts


def resolved_content(question: dict) -> str:
    """Canonical string of a RulesGuru question dict, for snapshot hashing.

    Uses the stable API fields so procedural card substitution is captured.
    """
    return json.dumps(
        {
            "id": question.get("id"),
            "questionSimple": question.get("questionSimple"),
            "answerSimple": question.get("answerSimple"),
            "includedCards": [c.get("name") for c in question.get("includedCards", [])],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
