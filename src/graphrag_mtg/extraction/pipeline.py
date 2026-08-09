"""End-to-end extraction: rulings in, gated triples out (optionally loaded).

The connective tissue for Phase 3. Each ruling flows through the whole
cascade and only gate-approved edges survive:

    ruling text
      ├─ linker.scan_ruling ──────▶ resolved mentions (exact/loose)
      │                         └─▶ pending homonyms
      ├─ disambiguate ────────────▶ LLM yes/no on each homonym (1 call)
      ├─ explicit_citations ──────▶ CITES_RULE candidates (deterministic)
      ├─ extractor (--llm-citations, off) ─▶ inferred citations, for E-003
      └─ gate.gate_candidates ────▶ GatedTriple[]  (schema + span + confidence
                                     + existence + dedupe)

Citations are deterministic since the E-003 schema reduction
(2026-08-09): the inferred path measured F1 0.125 and gate G3's
registered rule fired. ``--llm-citations`` still runs the extractor, but
the gate rejects everything it infers as ``citation_not_explicit`` — the
flag reproduces the experiment, it does not reopen the edge.

The gate needs no Neo4j: ``known_rules`` comes from the parsed CR and
``known_cards`` from the oracle-cards file, so the expensive, auditable
part of the phase runs and is scored entirely offline. Writing to the
graph is a separate, explicit ``--load`` step (integration).

Cost discipline: one LLM call per ruling by default (disambiguation
only; citations no longer cost anything), a second with
``--llm-citations``, cost estimated and printed before any spend,
``--limit`` honoured, and ``--yes`` required to leave dry-run.

Usage:
    python -m graphrag_mtg.extraction.pipeline --ids data/golden/extraction_sample_ids.json
    python -m graphrag_mtg.extraction.pipeline --limit 50 --yes
    python -m graphrag_mtg.extraction.pipeline --limit 50 --yes --load
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, RULINGS_STEM, bulk_path, load_bulk
from graphrag_mtg.extraction.explicit_citations import explicit_citations
from graphrag_mtg.extraction.gate import DEFAULT_MIN_CONFIDENCE, GatedTriple, gate_candidates
from graphrag_mtg.extraction.linker import Lexicon, scan_ruling
from graphrag_mtg.extraction.schemas import ExtractionCandidate

GATED_TRIPLES_PATH = Path("data/interim/gated_triples.jsonl")


@dataclass
class PipelineReport:
    """What one pipeline run produced across every stage."""

    rulings: int = 0
    resolved_mentions: int = 0
    llm_resolved_mentions: int = 0
    homonyms_rejected: int = 0
    explicit_citations: int = 0
    citation_candidates: int = 0
    gated: list[GatedTriple] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    gate_rejected: Counter[str] = field(default_factory=Counter)

    def summary(self) -> str:
        by_type = Counter(t.edge_type for t in self.gated)
        return (
            f"{self.rulings} rulings -> {len(self.gated)} gated triples "
            f"({dict(by_type) or 'none'}).\n"
            f"  linking: {self.resolved_mentions} deterministic + "
            f"{self.llm_resolved_mentions} LLM-resolved, "
            f"{self.homonyms_rejected} homonyms judged not-a-card.\n"
            f"  citations: {self.explicit_citations} explicit (deterministic)"
            f"{f' + {self.citation_candidates} LLM-inferred' if self.citation_candidates else ''}"
            ".\n"
            f"  stage drops: {dict(self.dropped) or 'none'}.\n"
            f"  gate rejections: {dict(self.gate_rejected) or 'none'}."
        )


def run_pipeline(
    rulings: Iterable[dict],
    *,
    lexicon: Lexicon,
    known_rules: frozenset[str] | set[str],
    known_cards: frozenset[str] | set[str],
    linker_only: bool,
    disambiguate_fn=None,
    extract_fn=None,
    candidate_rules_fn=None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    require_explicit_citations: bool = True,
) -> PipelineReport:
    """Run every ruling through the cascade and gate the union of candidates.

    Args:
        rulings: Raw Scryfall ruling dicts (``comment``, ``oracle_id``).
        lexicon: Prebuilt card-name tables.
        known_rules: Rule numbers in the graph (from the parsed CR).
        known_cards: oracle_ids in the graph (from the cards file).
        linker_only: If true, skip both LLM stages — deterministic edges
            only, no API. Used for the free preview pass. Explicit
            citations still run: they cost nothing, so the free preview
            now produces every ``CITES_RULE`` edge the graph will ever
            get.
        disambiguate_fn: ``(pending, text) -> DisambiguationReport``.
        extract_fn: ``(ruling_id, text, candidate_rules) -> ExtractionReport``.
            Inferred citations, kept for reproducing E-003; the gate
            rejects them unless ``require_explicit_citations`` is False.
        candidate_rules_fn: ``(oracle_id) -> list[(number, snippet)]`` for
            grounded extraction, or None.
        min_confidence: Gate threshold.
        require_explicit_citations: See :func:`gate.gate_candidates`.

    Returns:
        A :class:`PipelineReport` whose ``gated`` list is the only legal
        input to `extraction.load.load_gated_triples`.
    """
    from graphrag_mtg.graph.loader import ruling_id as make_ruling_id

    report = PipelineReport()
    candidates: list[ExtractionCandidate] = []
    source_texts: dict[str, str] = {}

    for raw in rulings:
        text = raw.get("comment", "")
        rid = make_ruling_id(raw)
        source_texts[rid] = text
        report.rulings += 1

        resolved, pending = scan_ruling(rid, text, lexicon, host_oracle_id=raw.get("oracle_id"))
        report.resolved_mentions += len(resolved)
        candidates.extend(resolved)

        stated = explicit_citations(rid, text)
        report.explicit_citations += len(stated)
        candidates.extend(stated)

        if linker_only:
            continue

        if pending and disambiguate_fn is not None:
            dis = disambiguate_fn(pending, text)
            report.llm_resolved_mentions += len(dis.resolved)
            report.homonyms_rejected += dis.rejected_as_not_a_card
            report.dropped.update(dis.dropped)
            candidates.extend(dis.resolved)

        if extract_fn is not None:
            cand_rules = candidate_rules_fn(raw.get("oracle_id", "")) if candidate_rules_fn else None
            ext = extract_fn(rid, text, cand_rules)
            report.citation_candidates += len(ext.candidates)
            report.dropped.update(ext.dropped)
            candidates.extend(ext.candidates)

    result = gate_candidates(
        candidates,
        source_texts=source_texts,
        known_rules=known_rules,
        known_cards=known_cards,
        min_confidence=min_confidence,
        require_explicit_citations=require_explicit_citations,
    )
    report.gated = result.accepted
    report.gate_rejected = result.rejected
    return report


def _write_gated(path: Path, triples: list[GatedTriple]) -> None:
    """Serialize gated triples for inspection (not a graph-load path)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for t in triples:
            out.write(
                json.dumps(
                    {
                        "edge_type": t.edge_type,
                        "source_key": t.source_key,
                        "target_key": t.target_key,
                        "span_start": t.span_start,
                        "span_end": t.span_end,
                        "span_text": t.span_text,
                        "method": t.method,
                        "confidence": t.confidence,
                        "rationale": t.rationale,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _select(rulings: list[dict], ids_path: Path | None, split: str, limit: int) -> list[dict]:
    from graphrag_mtg.graph.loader import ruling_id as make_ruling_id

    if ids_path is not None:
        payload = json.loads(ids_path.read_text(encoding="utf-8"))
        keep = set(payload[split] if isinstance(payload, dict) else payload)
        return [r for r in rulings if make_ruling_id(r) in keep]
    return rulings[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulings", type=Path, default=bulk_path(RULINGS_STEM))
    parser.add_argument("--cards", type=Path, default=bulk_path(ORACLE_CARDS_STEM))
    parser.add_argument("--cr", type=Path, default=Path("data/raw/comprehensive_rules.txt"))
    parser.add_argument("--ids", type=Path, default=None, help="ids list or sample manifest")
    parser.add_argument("--split", choices=("dev", "annotation"), default="dev")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--llm-citations",
        action="store_true",
        help=(
            "also run the inferred-citation extractor (E-003 reproduction only; "
            "the gate rejects its output unless --legacy-citation-gate is given)"
        ),
    )
    parser.add_argument(
        "--legacy-citation-gate",
        action="store_true",
        help=(
            "accept inferred citations, as the gate did before the 2026-08-09 "
            "schema reduction. Reproduces E-003; never a load path."
        ),
    )
    parser.add_argument("--grounded", action="store_true", help="ground citation extraction")
    parser.add_argument(
        "--no-keyword-dir",
        action="store_true",
        help="drop the keyword rule directory from the grounding (E-003 iteration 2)",
    )
    parser.add_argument("--out", type=Path, default=GATED_TRIPLES_PATH)
    parser.add_argument("--yes", action="store_true", help="spend on the two LLM stages")
    parser.add_argument("--load", action="store_true", help="load gated triples into Neo4j")
    args = parser.parse_args()

    from graphrag_mtg.config import get_settings
    from graphrag_mtg.etl.cr_parser import parse_cr
    from graphrag_mtg.extraction.extractor import EXTRACTOR_VERSION

    cards = load_bulk(args.cards)
    lexicon = Lexicon.build((c["name"], c["oracle_id"]) for c in cards)
    known_cards = {c["oracle_id"] for c in cards}
    doc = parse_cr(args.cr)
    known_rules = set(doc.by_number)

    selected = _select(load_bulk(args.rulings), args.ids, args.split, args.limit)

    if args.legacy_citation_gate and args.load:
        print(
            "Refusing --legacy-citation-gate together with --load. That gate setting\n"
            "accepts inferred citations, measured at F1 0.125 (E-003); it exists to\n"
            "reproduce the experiment, not to put its output in the graph."
        )
        return 1

    if not args.yes:
        # Free preview: deterministic edges only, real gate, no API. Since
        # the schema reduction that includes every CITES_RULE edge a full
        # run would produce — citations no longer cost anything.
        report = run_pipeline(
            selected,
            lexicon=lexicon,
            known_rules=known_rules,
            known_cards=known_cards,
            linker_only=True,
            require_explicit_citations=not args.legacy_citation_gate,
        )
        n_pending = sum(
            len(scan_ruling(str(i), r.get("comment", ""), lexicon)[1])
            for i, r in enumerate(selected)
        )
        calls = report.rulings * (2 if args.llm_citations else 1)
        # ASCII only: this line reaches consoles that cannot encode "—" (cp1252).
        print("DRY RUN - deterministic stages only (no API spend).")
        print(report.summary())
        # Written even on the dry run: these edges are free and complete, and
        # requiring an API spend to obtain a file of deterministic triples
        # would be charging for arithmetic.
        _write_gated(args.out, report.gated)
        print(f"\nGated triples written to {args.out}.")
        print(
            f"\nCITES_RULE above is final: explicit citations are deterministic, so\n"
            f"--yes adds no citation edges. With --yes: ~{calls} LLM calls "
            f"({report.rulings} disambiguation over {n_pending} homonyms"
            f"{f' + {report.rulings} inferred citation' if args.llm_citations else ''})."
        )
        return 0

    # Full run: wire the LLM stages that are still on.
    from graphrag_mtg.extraction.disambiguate import disambiguate_ruling
    from graphrag_mtg.extraction.extractor import extract_citations
    from graphrag_mtg.extraction.llm import LlmClient

    client = LlmClient(model=get_settings().llm_model)

    extract_system = None
    candidate_rules_fn = None
    if args.grounded and args.llm_citations:
        from graphrag_mtg.extraction.grounding import candidate_rules_for_keywords, grounding_block

        extract_system = grounding_block(doc, include_keywords=not args.no_keyword_dir)
        keywords_by_oracle = {c["oracle_id"]: c.get("keywords", []) for c in cards}
        candidate_rules_fn = lambda oid: candidate_rules_for_keywords(  # noqa: E731
            keywords_by_oracle.get(oid, []), doc
        )

    from graphrag_mtg.extraction.extractor import SYSTEM_PROMPT

    def extract_fn(rid, text, cand_rules):
        return extract_citations(
            rid, text, client, candidate_rules=cand_rules, system=extract_system or SYSTEM_PROMPT
        )

    report = run_pipeline(
        selected,
        lexicon=lexicon,
        known_rules=known_rules,
        known_cards=known_cards,
        linker_only=False,
        disambiguate_fn=lambda pending, text: disambiguate_ruling(pending, text, client),
        extract_fn=extract_fn if args.llm_citations else None,
        candidate_rules_fn=candidate_rules_fn,
        require_explicit_citations=not args.legacy_citation_gate,
    )
    print(report.summary())
    _write_gated(args.out, report.gated)
    print(f"\nGated triples written to {args.out}.")

    if args.load:
        from graphrag_mtg.extraction.load import load_gated_triples
        from graphrag_mtg.graph.connection import driver_session

        with driver_session() as session:
            results = load_gated_triples(session, report.gated, version=EXTRACTOR_VERSION)
        for edge_type, batch in results.items():
            print(f"  loaded {edge_type}: {batch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
