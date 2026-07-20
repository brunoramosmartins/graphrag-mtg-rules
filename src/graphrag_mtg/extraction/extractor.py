"""Few-shot extraction of (:Ruling)-[:CITES_RULE]->(:Rule) candidates.

Explicit rule numbers appear in only 25 of 77,999 rulings (3 cards),
so this extractor asks the model to *infer* which CR rule a ruling's
language invokes — and then makes the inference auditable: every citation
must return a **verbatim quote** from the ruling, which is located in the
source text to become the offset-addressed evidence span the gate
demands. A quote the source does not contain is dropped on the spot and
counted; it never becomes a candidate.

Two operating modes, chosen per call:

- **open** — the model proposes rule numbers from its own knowledge of
  the CR. Cheap, hallucination-prone; the gate's existence check is the
  only net. Used for the week-1 G3 assessment on the 30-ruling dev sample.
- **grounded** — the prompt includes candidate rules (number + text
  snippet) retrieved from the graph via the host card's keywords and the
  glossary. The model may only cite from that closed list. This is the
  mode the F1 target is expected to need; prompt iterations are logged in
  `notes/phase3-extraction.md`.

CLI (prints the cost estimate and refuses to spend without ``--yes``):

    python -m graphrag_mtg.extraction.extractor --limit 30 --yes
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from graphrag_mtg.extraction.llm import LlmClient, estimate_cost
from graphrag_mtg.extraction.schemas import EvidenceSpan, LinkMethod, RuleCitation

CITATIONS_CANDIDATES_PATH = Path("data/interim/citations_candidates.jsonl")

EXTRACTOR_VERSION = "v1"

SYSTEM_PROMPT = """\
You extract Comprehensive Rules citations from official Magic: The Gathering rulings.

Given one ruling, return a JSON array (possibly empty) of objects:
  {"rule_number": "<CR number like 613.4b>",
   "quote": "<verbatim substring of the ruling that invokes this rule>",
   "rationale": "<one sentence: why this passage means this rule>",
   "confidence": <0.0-1.0>}

Hard requirements:
- "quote" must be copied character-for-character from the ruling text.
- Cite the most specific rule that carries the point (a lettered leaf like
  702.19b beats its parent 702.19).
- Only cite rules the ruling actually turns on. An empty array is a good
  answer for a ruling that just restates card text.
- Never invent rule numbers. If unsure between two numbers, cite the parent
  rule you are sure of, with lower confidence.
Return the JSON array and nothing else."""

# Few-shot examples use invented rulings (no WotC text) about real rule
# numbers, so the format is demonstrated without pasting corpus text into
# every prompt.
FEW_SHOTS = """\
Example ruling: "Trample damage is assigned only after lethal damage is \
assigned to all blockers."
Example output: [{"rule_number": "702.19e", "quote": "assigned only after \
lethal damage is assigned to all blockers", "rationale": "Restates the \
trample assignment rule for combat damage.", "confidence": 0.9}]

Example ruling: "This card's ability doesn't change its name."
Example output: []"""


@dataclass
class ExtractionReport:
    """What one extraction run produced, and what it dropped on the floor."""

    candidates: list[RuleCitation] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)

    def merge(self, other: ExtractionReport) -> None:
        self.candidates.extend(other.candidates)
        self.dropped.update(other.dropped)


def build_prompt(text: str, candidate_rules: list[tuple[str, str]] | None = None) -> str:
    """Assemble the per-ruling prompt (open or grounded mode)."""
    parts = [FEW_SHOTS]
    if candidate_rules:
        listing = "\n".join(f"- {number}: {snippet}" for number, snippet in candidate_rules)
        parts.append(
            "Candidate rules — cite ONLY from this list (empty array if none apply):\n" + listing
        )
    parts.append(f'Ruling: "{text}"')
    return "\n\n".join(parts)


def parse_response(ruling_id: str, text: str, raw: Any) -> ExtractionReport:
    """Turn a model response into schema-valid candidates with real spans.

    The model reports a quote; only the source text can say where (or
    whether) it occurs. Anything that fails — quote missing from the
    source, malformed item, bad rule-number shape — is counted under a
    named reason so prompt iteration is driven by data, not vibes.
    """
    report = ExtractionReport()
    if not isinstance(raw, list):
        report.dropped["response_not_a_list"] += 1
        return report
    for item in raw:
        if not isinstance(item, dict):
            report.dropped["item_not_an_object"] += 1
            continue
        quote = str(item.get("quote", ""))
        start = text.find(quote) if quote else -1
        if start < 0:
            report.dropped["quote_not_in_source"] += 1
            continue
        try:
            citation = RuleCitation(
                ruling_id=ruling_id,
                rule_number=str(item.get("rule_number", "")),
                span=EvidenceSpan(start=start, end=start + len(quote), text=quote),
                rationale=str(item.get("rationale", "")) or "(none given)",
                method=LinkMethod.LLM,
                confidence=float(item.get("confidence", 0.0)),
            )
        except (ValidationError, TypeError, ValueError):
            report.dropped["schema_invalid"] += 1
            continue
        report.candidates.append(citation)
    return report


def extract_citations(
    ruling_id: str,
    text: str,
    client: LlmClient,
    *,
    candidate_rules: list[tuple[str, str]] | None = None,
) -> ExtractionReport:
    """Run one ruling through the extractor (one API call)."""
    prompt = build_prompt(text, candidate_rules)
    try:
        raw = client.complete_json(prompt, system=SYSTEM_PROMPT)
    except ValueError:
        report = ExtractionReport()
        report.dropped["unparseable_response"] += 1
        return report
    return parse_response(ruling_id, text, raw)


# ── CLI ──


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulings", type=Path, default=Path("data/raw/scryfall_rulings.json"))
    parser.add_argument("--limit", type=int, default=30, help="extract from at most N rulings")
    parser.add_argument("--ids", type=Path, default=None, help="JSON file of ruling ids to keep")
    parser.add_argument("--out", type=Path, default=CITATIONS_CANDIDATES_PATH)
    parser.add_argument("--yes", action="store_true", help="actually spend after the estimate")
    args = parser.parse_args()

    from graphrag_mtg.config import get_settings
    from graphrag_mtg.graph.loader import ruling_id as make_ruling_id

    with args.rulings.open(encoding="utf-8") as fh:
        rulings = json.load(fh)
    keep: set[str] | None = None
    if args.ids is not None:
        keep = set(json.loads(args.ids.read_text(encoding="utf-8")))

    selected: list[tuple[str, str]] = []
    for raw in rulings:
        rid = make_ruling_id(raw)
        if keep is not None and rid not in keep:
            continue
        selected.append((rid, raw.get("comment", "")))
        if keep is None and len(selected) >= args.limit:
            break

    model = get_settings().llm_model
    prompts = (build_prompt(text) for _, text in selected)
    estimate = estimate_cost(prompts, model=model, system=SYSTEM_PROMPT)
    print(f"Model {model}: {estimate}")
    if not args.yes:
        print("Dry run (pass --yes to extract).")
        return 0

    client = LlmClient(model=model)
    report = ExtractionReport()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for rid, text in selected:
            one = extract_citations(rid, text, client)
            report.merge(one)
            for candidate in one.candidates:
                out.write(candidate.model_dump_json() + "\n")

    print(
        f"{len(report.candidates):,} candidates from {len(selected):,} rulings "
        f"-> {args.out}. Dropped: {dict(report.dropped) or 'nothing'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
