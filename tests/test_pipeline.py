"""End-to-end cascade orchestration with stubbed LLM stages (no network)."""

from __future__ import annotations

from graphrag_mtg.extraction.disambiguate import DisambiguationReport
from graphrag_mtg.extraction.extractor import ExtractionReport
from graphrag_mtg.extraction.linker import Lexicon
from graphrag_mtg.extraction.pipeline import run_pipeline
from graphrag_mtg.extraction.schemas import (
    CardMention,
    EvidenceSpan,
    LinkMethod,
    RuleCitation,
)

CARDS = [("Giant Growth", "gg-1"), ("Opt", "opt-1")]
KNOWN_CARDS = frozenset({"gg-1", "opt-1"})
KNOWN_RULES = frozenset({"601.2c", "702.19e"})


def lexicon() -> Lexicon:
    return Lexicon.build(CARDS)


def rulings() -> list[dict]:
    return [
        {"comment": "This works like Giant Growth in combat.", "oracle_id": "host-1"},
        {"comment": "You may Opt before combat.", "oracle_id": "host-2"},
    ]


class TestLinkerOnly:
    def test_deterministic_edges_gated_without_llm(self) -> None:
        report = run_pipeline(
            rulings(),
            lexicon=lexicon(),
            known_rules=KNOWN_RULES,
            known_cards=KNOWN_CARDS,
            linker_only=True,
        )
        assert report.rulings == 2
        assert report.resolved_mentions == 1  # "Giant Growth"; "Opt" is pending
        assert report.llm_resolved_mentions == 0
        (triple,) = report.gated
        assert triple.edge_type == "MENTIONS" and triple.target_key == "gg-1"


class TestFullCascade:
    def test_llm_stages_feed_the_gate(self) -> None:
        def disambiguate_fn(pending, text):
            # Resolve the "Opt" homonym as the card, high confidence.
            report = DisambiguationReport()
            for p in pending:
                report.resolved.append(
                    CardMention(
                        ruling_id=p.mention.ruling_id,
                        surface=p.mention.surface,
                        oracle_id=p.candidate_oracle_ids[0],
                        span=p.mention.span,
                        method=LinkMethod.LLM,
                        confidence=0.95,
                    )
                )
            return report

        def extract_fn(rid, text, cand_rules):
            report = ExtractionReport()
            if "Giant Growth" in text:
                report.candidates.append(
                    RuleCitation(
                        ruling_id=rid,
                        rule_number="702.19e",
                        span=EvidenceSpan(start=0, end=4, text=text[:4]),
                        rationale="trample",
                        confidence=0.9,
                    )
                )
            return report

        report = run_pipeline(
            rulings(),
            lexicon=lexicon(),
            known_rules=KNOWN_RULES,
            known_cards=KNOWN_CARDS,
            linker_only=False,
            disambiguate_fn=disambiguate_fn,
            extract_fn=extract_fn,
        )
        assert report.llm_resolved_mentions == 1
        assert report.citation_candidates == 1
        edges = {(t.edge_type, t.target_key) for t in report.gated}
        assert edges == {
            ("MENTIONS", "gg-1"),
            ("MENTIONS", "opt-1"),
            ("CITES_RULE", "702.19e"),
        }

    def test_low_confidence_homonym_is_gated_out(self) -> None:
        def disambiguate_fn(pending, text):
            report = DisambiguationReport()
            for p in pending:
                report.resolved.append(
                    CardMention(
                        ruling_id=p.mention.ruling_id,
                        surface=p.mention.surface,
                        oracle_id=p.candidate_oracle_ids[0],
                        span=p.mention.span,
                        method=LinkMethod.LLM,
                        confidence=0.3,  # below the gate threshold
                    )
                )
            return report

        report = run_pipeline(
            rulings(),
            lexicon=lexicon(),
            known_rules=KNOWN_RULES,
            known_cards=KNOWN_CARDS,
            linker_only=False,
            disambiguate_fn=disambiguate_fn,
            extract_fn=lambda rid, text, cand: ExtractionReport(),
        )
        assert report.gate_rejected["low_confidence"] == 1
        assert all(t.target_key != "opt-1" for t in report.gated)
