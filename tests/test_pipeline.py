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
        # The inferred citation is proposed and then refused: since the
        # 2026-08-09 schema reduction the gate requires the rule number to
        # appear in the candidate's own span, and this one's says "This".
        edges = {(t.edge_type, t.target_key) for t in report.gated}
        assert edges == {("MENTIONS", "gg-1"), ("MENTIONS", "opt-1")}
        assert report.gate_rejected["citation_not_explicit"] == 1

    def test_the_permissive_gate_still_admits_an_inferred_citation(self) -> None:
        """E-003 predates the reduction and must stay reproducible."""

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
            extract_fn=extract_fn,
            require_explicit_citations=False,
        )
        assert ("CITES_RULE", "702.19e") in {(t.edge_type, t.target_key) for t in report.gated}


class TestExplicitCitations:
    """The whole of CITES_RULE after the reduction — and it costs no API."""

    def stated(self) -> list[dict]:
        return [{"comment": "Put a counter on it (601.2c).", "oracle_id": "host-3"}]

    def test_a_stated_rule_number_becomes_an_edge_without_any_llm(self) -> None:
        report = run_pipeline(
            self.stated(),
            lexicon=lexicon(),
            known_rules=KNOWN_RULES,
            known_cards=KNOWN_CARDS,
            linker_only=True,
        )
        assert report.explicit_citations == 1
        (triple,) = report.gated
        assert (triple.edge_type, triple.target_key) == ("CITES_RULE", "601.2c")

    def test_a_ruling_naming_no_rule_yields_no_citation(self) -> None:
        report = run_pipeline(
            rulings(),
            lexicon=lexicon(),
            known_rules=KNOWN_RULES,
            known_cards=KNOWN_CARDS,
            linker_only=True,
        )
        assert report.explicit_citations == 0
        assert all(t.edge_type != "CITES_RULE" for t in report.gated)

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
