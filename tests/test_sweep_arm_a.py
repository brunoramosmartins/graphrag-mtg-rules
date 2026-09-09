"""The tuning sweep: its grid, and the adoption rule that can decline.

Pin 7 permits tuning on the development split and requires the sweep
published. The failure mode of a sweep is not finding nothing — it is being
built so that it cannot.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sweep_arm_a
from sweep_arm_a import ADOPTION_MARGIN, DEFAULTS, GRID, cells, is_default


class TestGrid:
    def test_the_published_defaults_are_a_cell(self) -> None:
        # They are a cell in the grid, not the centre it is measured
        # against — otherwise "the defaults won" would be unfalsifiable.
        assert sum(1 for cell in cells() if is_default(cell)) == 1

    def test_cells_are_distinct(self) -> None:
        # A duplicate could win a tie against the defaults on nothing.
        keys = [tuple(sorted(cell.items())) for cell in cells()]
        assert len(keys) == len(set(keys))

    def test_dense_mode_collapses_the_lexical_parameters(self) -> None:
        # k1 and b do nothing when there is no BM25 half, so varying them
        # would inflate the grid with copies of one configuration.
        dense = [c for c in cells() if c["mode"] == "dense"]
        assert {c["k1"] for c in dense} == {DEFAULTS["k1"]}
        assert {c["b"] for c in dense} == {DEFAULTS["b"]}

    def test_single_ranking_modes_collapse_the_fusion_constant(self) -> None:
        # RRF has nothing to fuse when only one retriever ran.
        for mode in ("dense", "lexical"):
            single = [c for c in cells() if c["mode"] == mode]
            assert {c["rrf_k"] for c in single} == {DEFAULTS["rrf_k"]}

    def test_hybrid_keeps_every_parameter(self) -> None:
        hybrid = [c for c in cells() if c["mode"] == "hybrid"]
        assert {c["k1"] for c in hybrid} == set(GRID["k1"])
        assert {c["rrf_k"] for c in hybrid} == set(GRID["rrf_k"])

    def test_every_mode_is_represented(self) -> None:
        assert set(Counter(c["mode"] for c in cells())) == set(GRID["mode"])


class TestAdoptionRule:
    def test_the_margin_is_the_registered_one(self) -> None:
        # Fifteen questions cannot separate two cells that differ by one
        # gold rule; drifting off a default on noise is overfitting with
        # extra steps.
        assert ADOPTION_MARGIN == 2

    def test_is_default_needs_every_parameter_to_match(self) -> None:
        assert is_default(dict(DEFAULTS))
        assert not is_default({**DEFAULTS, "k1": 2.0})
        assert not is_default({**DEFAULTS, "iterative": True})

    def test_ties_sort_the_defaults_first(self) -> None:
        # The sort key the sweep applies: a cell only wins by being
        # strictly better, never by tying.
        default = {**DEFAULTS, "found": 10}
        other = {**DEFAULTS, "k1": 2.0, "found": 10}
        ranked = sorted([other, default], key=lambda r: (-r["found"], not is_default(r)))
        assert is_default(ranked[0])


class TestObjective:
    def test_the_grid_is_declared_not_derived(self) -> None:
        # A grid computed from the data is a grid chosen after seeing it.
        assert set(GRID) == {"k1", "b", "rrf_k", "depth", "mode", "iterative"}
        assert DEFAULTS["k1"] in GRID["k1"] and DEFAULTS["b"] in GRID["b"]

    def test_the_artefact_is_published_not_hidden(self) -> None:
        # Pin 7 requires the sweep published. runs/ is gitignored, so an
        # artefact written there would make "and here is the sweep" point
        # at nothing a reader can open.
        assert sweep_arm_a.DEFAULT_OUT.parts[0] == "docs"
