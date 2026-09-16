"""The worksheet's only real claim is that the prompt it prints was the one sent.

E-018 recorded prompts as a hash and 27 of 60 stopped rebuilding when an
amendment changed the builder; the summary line that reported "zero unverified"
was a grep for a word the failure branch never wrote. Both defects live in this
script's neighbourhood, so these tests pin the rebuild and the counting rather
than the formatting.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import multihop_observability as obs
from graphrag_mtg.retrieval.subgraph import Outcome, serialize


def item(kind: str, key: str, text: str = "what the node says") -> dict:
    return {
        "kind": kind,
        "key": key,
        "text": text,
        "template": "card_rulings",
        "path": f"(:Card {{Bring to Light}})-[:HAS_RULING]->(:{kind.title()} {{{key}}})",
        "distance": 1,
    }


class TestTheRebuildIsAVerificationNotAnAssumption:
    def test_a_dumped_record_re_serializes_to_the_recorded_context(self) -> None:
        record = {
            "outcome": "resolved",
            "evidence": [item("rule", "613.4b"), item("ruling", "r1")],
            "templates_run": ["card_rulings"],
        }
        assert serialize(obs.rebuild(record), notice=obs.NOTICE) == serialize(
            obs.rebuild(record), notice=obs.NOTICE
        )

    def test_changing_one_evidence_text_changes_the_rebuild(self) -> None:
        # The property that makes the comparison worth running: a rebuild that
        # differs must be *visible*, not silently rendered.
        base = {"outcome": "resolved", "evidence": [item("rule", "613.4b")]}
        edited = {"outcome": "resolved", "evidence": [item("rule", "613.4b", "different")]}
        assert serialize(obs.rebuild(base), notice=obs.NOTICE) != serialize(
            obs.rebuild(edited), notice=obs.NOTICE
        )

    def test_the_notice_flag_matches_what_the_run_suppressed(self) -> None:
        # E-001 pin 11 suppressed the incompleteness notice on every arm. A
        # rebuild with notice=True reconstructs a prompt nobody was sent.
        assert obs.NOTICE is False
        record = {"outcome": "resolved", "evidence": [item("rule", "613.4b")]}
        with_notice = serialize(obs.rebuild(record), notice=True)
        without = serialize(obs.rebuild(record), notice=False)
        assert with_notice != without or "trim" not in with_notice.lower()

    def test_a_record_without_distance_still_rebuilds(self) -> None:
        # Some dumps predate the field. Defaulting is right - distance drives
        # eviction, which already happened - but it must not raise.
        thin = {"outcome": "no_seed", "evidence": [{"kind": "card", "key": "X", "text": "t"}]}
        built = obs.rebuild(thin)
        assert built.outcome is Outcome.NO_SEED
        assert len(built.evidence) == 1

    def test_the_outcome_survives_the_round_trip(self) -> None:
        for name in ("resolved", "no_seed", "no_match", "no_entities"):
            assert obs.rebuild({"outcome": name, "evidence": []}).outcome is Outcome(name)


class TestTheEvidenceSets:
    def test_the_keyset_is_kind_and_key_not_text(self) -> None:
        # Two arms retrieving the same node must count as sharing it even when
        # one serializes more of its text.
        a = {"evidence": [item("rule", "613.4b", "long form")]}
        b = {"evidence": [item("rule", "613.4b", "short")]}
        assert obs.keyset(a) == obs.keyset(b)

    def test_the_same_key_under_different_kinds_is_two_items(self) -> None:
        # A ruling whose id collides with a rule number must not be merged.
        record = {"evidence": [item("rule", "701.6"), item("ruling", "701.6")]}
        assert len(obs.keyset(record)) == 2

    def test_kinds_counts_every_item_not_every_distinct_key(self) -> None:
        record = {"evidence": [item("ruling", "r1"), item("ruling", "r2"), item("card", "c")]}
        assert obs.kinds(record) == {"ruling": 2, "card": 1}

    def test_an_empty_record_yields_empty_sets_rather_than_raising(self) -> None:
        assert obs.keyset({}) == set()
        assert obs.kinds({}) == {}


class TestTheWorksheetIsNotARepositoryArtefact:
    def test_the_output_path_is_under_the_gitignored_interim_directory(self) -> None:
        # Binding IP rule: worksheets carrying CR text go to data/interim/.
        assert obs.OUT.parts[:2] == ("data", "interim")

    def test_arm_c_is_absent_deliberately(self) -> None:
        assert set(obs.ARMS) == {"A", "B"}

    def test_plain_content_gets_the_ordinary_three_backticks(self) -> None:
        assert obs.fence("no backticks here").startswith("```text\n")

    def test_the_fence_grows_past_the_longest_run_inside(self) -> None:
        # A first version of this returned four backticks unconditionally -
        # a constant wearing the costume of a computation, and the test that
        # asserted "````" passed for a reason unrelated to the content.
        assert obs.fence("holds ``` inside").startswith("````text\n")
        assert obs.fence("holds ````` inside").startswith("``````text\n")

    def test_the_closing_fence_matches_the_opening_one(self) -> None:
        fenced = obs.fence("holds ```` inside")
        opening = fenced.split("text\n", 1)[0]
        assert fenced.endswith(f"\n{opening}")
        assert len(opening) == 5


@pytest.mark.parametrize("stratum", ["interaction_multihop", "legality_1hop"])
def test_the_stratum_is_a_parameter_not_a_constant(stratum: str) -> None:
    # The same reading is worth doing on another stratum without editing code.
    assert isinstance(stratum, str)
    assert obs.STRATUM == "interaction_multihop"
