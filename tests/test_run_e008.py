"""E-008's rule and its guards, without a database.

The parts worth pinning are the ones a reader cannot check by looking at
the output: that a retrieval miss leaves the leak denominator, that
refusing everything fails rather than passes, and that the discriminator
each answer is judged against was authored before the answers existed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_e008


def coding(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "coding.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def probe(probe_id: str, outcome: str, *, present: bool = True, split: str = "held_out") -> dict:
    return {
        "probe_id": probe_id,
        "construct": "contradiction",
        "split": split,
        "question": "q",
        "answer": "a",
        "graph_says": "g",
        "memory_says": "m",
        "evidence_present": present,
        "outcome": outcome,
        "comment": "",
    }


def run_report(path: Path) -> int:
    return run_e008.report(argparse.Namespace(coding=path))


class TestTheFixtureIsWrittenFirst:
    """`graph_says` decides the code, so it cannot be written afterwards."""

    def test_every_probe_declares_what_each_source_would_say(self) -> None:
        fixture = run_e008.load_fixture(Path("data/fixtures/e008_constructs.json"))
        for row in fixture["probes"]:
            assert row["graph_says"].strip()
            assert row["memory_says"].strip()
            assert row["needs"]

    def test_the_registered_probe_counts_hold(self) -> None:
        """3 constructs x 4 held out, plus a 6-probe development set."""
        fixture = run_e008.load_fixture(Path("data/fixtures/e008_constructs.json"))
        held = [p for p in fixture["probes"] if p["split"] == "held_out"]
        dev = [p for p in fixture["probes"] if p["split"] == "dev"]
        assert len(held) == 12
        assert len(dev) == 6
        assert {p["construct"] for p in held} == {"contradiction", "keyword", "fictional_ruling"}

    def test_no_fictional_name_announces_itself(self) -> None:
        """A namespaced name tells the model the card is fake, and a model that
        spots the fiction and refuses is coded as a grounding failure."""
        fixture = run_e008.load_fixture(Path("data/fixtures/e008_constructs.json"))
        for card in fixture["cards"]:
            assert run_e008.TAG not in card["name"].lower()


class TestTheRule:
    def test_one_leak_sinks_the_claim(self, tmp_path: Path, capsys) -> None:
        rows = [probe(f"p{i}", "followed_graph") for i in range(11)] + [probe("p11", "leak")]
        run_report(coding(tmp_path, rows))
        assert "does NOT hold" in capsys.readouterr().out

    def test_refusing_everything_fails(self, tmp_path: Path, capsys) -> None:
        """Zero leaks with nothing followed is the degenerate pass this blocks."""
        rows = [probe(f"p{i}", "refused") for i in range(12)]
        run_report(coding(tmp_path, rows))
        out = capsys.readouterr().out
        assert "does NOT hold" in out
        assert "refusing everything is not grounding" in out

    def test_a_clean_run_states_its_bound_and_no_more(self, tmp_path: Path, capsys) -> None:
        rows = [probe(f"p{i}", "followed_graph") for i in range(12)]
        run_report(coding(tmp_path, rows))
        out = capsys.readouterr().out
        assert "Both registered conditions hold" in out
        assert "0.250" in out
        assert "NOT 'no parametric leakage'" in out

    def test_intra_context_conflict_is_not_a_leak(self, tmp_path: Path, capsys) -> None:
        """Siding with oracle text against an injected ruling still follows the graph.

        Ten followed and two conflicts clears the floor at 0.833, and the run
        is clean — a conflict that counted as a leak would sink it instead.
        """
        rows = [probe(f"p{i}", "followed_graph") for i in range(10)]
        rows += [probe("p10", "intra_context_conflict"), probe("p11", "intra_context_conflict")]
        run_report(coding(tmp_path, rows))
        out = capsys.readouterr().out
        assert "LEAK" not in out
        assert "Both registered conditions hold" in out

    def test_a_retrieval_miss_leaves_the_denominator(self, tmp_path: Path, capsys) -> None:
        """Scoring a miss as a leak would iterate the prompt against a retrieval bug."""
        rows = [probe(f"p{i}", "followed_graph") for i in range(10)]
        rows += [probe("p10", "leak", present=False), probe("p11", "leak", present=False)]
        run_report(coding(tmp_path, rows))
        out = capsys.readouterr().out
        assert "retrieval misses 2" in out
        assert "Both registered conditions hold" in out

    def test_the_development_split_never_reaches_the_rule(self, tmp_path: Path, capsys) -> None:
        rows = [probe(f"p{i}", "followed_graph") for i in range(12)]
        rows += [probe("d0", "leak", split="dev")]
        run_report(coding(tmp_path, rows))
        assert "Both registered conditions hold" in capsys.readouterr().out

    def test_an_uncoded_held_out_probe_stops_the_report(self, tmp_path: Path) -> None:
        rows = [probe(f"p{i}", "followed_graph") for i in range(11)] + [probe("p11", "")]
        with pytest.raises(SystemExit, match="uncoded"):
            run_report(coding(tmp_path, rows))


class TestTheLoaderCannotAdoptRealNodes:
    """The incident: MERGE on an existing key adopts instead of creating.

    A fictional rule 702.184 stamped its text and the fixture tag onto the
    real keyword *Station*, and teardown then deleted it along with
    702.184a and 702.184b. Three real CR rules and eight relationships,
    gone by design working exactly as written.
    """

    def test_fictional_rules_sit_outside_the_cr_numbering(self) -> None:
        fixture = run_e008.load_fixture(Path("data/fixtures/e008_constructs.json"))
        for rule in fixture["rules"]:
            assert int(rule["number"].split(".")[0]) >= 799

    def test_every_fictional_key_is_distinctive(self) -> None:
        """Names a real corpus could hold are what the collision check is for."""
        fixture = run_e008.load_fixture(Path("data/fixtures/e008_constructs.json"))
        assert all(c["oracle_id"].startswith("e008-") for c in fixture["cards"])
        assert all(r["ruling_id"].startswith("e008-") for r in fixture["rulings"])

    @pytest.mark.integration
    def test_a_pre_existing_key_stops_the_load(self) -> None:
        from graphrag_mtg.graph.connection import driver_session

        fixture = {
            "cards": [], "keywords": [], "rulings": [],
            "rules": [{"number": "pytest-e008-collide", "text": "t", "level": 2}],
        }
        with driver_session() as session:
            session.run("CREATE (r:Rule {number: 'pytest-e008-collide'})")
            try:
                assert run_e008.collisions(session, fixture) == ["Rule pytest-e008-collide"]
            finally:
                session.run("MATCH (r:Rule {number: 'pytest-e008-collide'}) DETACH DELETE r")

    @pytest.mark.integration
    def test_a_free_key_passes(self) -> None:
        from graphrag_mtg.graph.connection import driver_session

        fixture = {
            "cards": [], "keywords": [], "rulings": [],
            "rules": [{"number": "pytest-e008-free", "text": "t", "level": 2}],
        }
        with driver_session() as session:
            assert run_e008.collisions(session, fixture) == []
