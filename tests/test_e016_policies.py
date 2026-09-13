"""E-016's four eviction policies, and the one property the contrast rests on.

Arm A claims to be what ships. If it is not, every other arm is measured
against a strawman and the entry answers nothing — so the first test here does
not check A against a description of `enforce_budget`, it checks A against
`enforce_budget`, on randomly generated pools.

The rest pin what each policy is *for*: B interleaves levels so a deep level
cannot be starved, D prefers evidence joined to what shallower levels reached,
R is reproducible from the entry rather than from the call site, and all four
pack identically so the only thing that differs between arms is the order.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e016_policies as pol
from graphrag_mtg.retrieval.subgraph import Evidence, Subgraph, enforce_budget


def item(key: str, distance: int, head: str = "", tail: str = "", pad: int = 0) -> Evidence:
    head = head or f"h{key}"
    tail = tail or f"t{key}"
    return Evidence(
        kind="triple",
        key=key,
        text=f"{head} | r | {tail}" + "x" * pad,
        template=f"metaqa_expand_{distance}",
        path="(:MQ_Entity)-[:R]->(:MQ_Entity)",
        distance=distance,
    )


# --- arm A must be the shipped policy, not a description of it ---------------


def test_arm_a_reproduces_enforce_budget_on_random_pools() -> None:
    """The property the whole contrast rests on.

    If A is not what ships, the other three arms are measured against a
    strawman and branch 1 would adopt a policy on a comparison that never
    happened.
    """
    rnd = random.Random(20260913)
    for _ in range(200):
        pool = [
            item(str(i), rnd.randint(1, 3), pad=rnd.randint(0, 40))
            for i in range(rnd.randint(1, 40))
        ]
        budget = rnd.randint(10, 400)
        subgraph = Subgraph(question="q", evidence=list(pool))
        enforce_budget(subgraph, budget)
        assert [e.key for e in subgraph.evidence] == [
            e.key for e in pol.apply_arm(pool, "A", budget)
        ]


def test_arm_a_keeps_the_nearest_evidence_first() -> None:
    pool = [item("far", 3), item("near", 1), item("mid", 2)]
    kept = pol.apply_arm(pool, "A", budget=pool[1].tokens)
    assert [e.key for e in kept] == ["near"]


# --- B: a deep level cannot be starved ---------------------------------------


def test_proportional_reaches_the_deepest_level_before_exhausting_the_shallowest() -> None:
    pool = [item(f"d1-{i}", 1) for i in range(10)] + [item("d3-0", 3)]
    order = pol.order_b(pool)
    # One from each level in turn, so the single deep item is second, not last.
    assert pool[order[0]].distance == 1
    assert pool[order[1]].distance == 3


def test_the_shipped_policy_would_starve_that_same_level() -> None:
    """The contrast, on one tiny pool: A ranks the deep item dead last."""
    pool = [item(f"d1-{i}", 1) for i in range(10)] + [item("d3-0", 3)]
    assert pol.order_a(pool)[-1] == 10


def test_proportional_keeps_retrieval_order_within_a_level() -> None:
    pool = [item("a", 1), item("b", 1), item("c", 1)]
    assert pol.order_b(pool) == [0, 1, 2]


def test_a_level_that_runs_out_does_not_stall_the_others() -> None:
    pool = [item("d1", 1), item("d2-0", 2), item("d2-1", 2), item("d2-2", 2)]
    order = pol.order_b(pool)
    assert sorted(order) == [0, 1, 2, 3]
    assert len(order) == 4


# --- D: joined evidence before loose evidence --------------------------------


def test_connectivity_puts_joined_evidence_ahead_of_loose_evidence() -> None:
    # Level 1 touches A and B. At level 2, "B->C" extends it; "X->Y" does not.
    pool = [
        item("l1", 1, head="A", tail="B"),
        item("loose", 2, head="X", tail="Y"),
        item("joined", 2, head="B", tail="C"),
    ]
    order = pol.order_d(pool)
    assert [pool[i].key for i in order] == ["l1", "joined", "loose"]


def test_connectivity_and_proportional_differ_only_inside_a_level() -> None:
    pool = [
        item("l1", 1, head="A", tail="B"),
        item("loose", 2, head="X", tail="Y"),
        item("joined", 2, head="B", tail="C"),
    ]
    b_levels = [pool[i].distance for i in pol.order_b(pool)]
    d_levels = [pool[i].distance for i in pol.order_d(pool)]
    assert b_levels == d_levels
    assert pol.order_b(pool) != pol.order_d(pool)


def test_the_shallowest_level_is_left_in_retrieval_order() -> None:
    """It hangs off the seed by construction, so there is nothing to join to."""
    pool = [item("a", 1), item("b", 1), item("c", 1)]
    assert pol.order_d(pool) == [0, 1, 2]


def test_connectivity_grows_across_more_than_one_level() -> None:
    # A->B at level 1, B->C at level 2, C->D at level 3: a full chain, plus
    # a level-3 item joined to nothing that must rank behind it.
    pool = [
        item("l1", 1, head="A", tail="B"),
        item("l2", 2, head="B", tail="C"),
        item("l3-loose", 3, head="P", tail="Q"),
        item("l3-joined", 3, head="C", tail="D"),
    ]
    order = pol.order_d(pool)
    assert order.index(3) < order.index(2)


# --- R: reproducible from the entry, not from the caller ---------------------


def test_random_is_reproducible() -> None:
    pool = [item(str(i), 1 + i % 3) for i in range(50)]
    assert pol.order_r(pool) == pol.order_r(pool)


def test_random_is_not_retrieval_order() -> None:
    pool = [item(str(i), 1 + i % 3) for i in range(50)]
    assert pol.order_r(pool) != list(range(50))


def test_the_seed_lives_in_the_module_so_a_rerun_sends_the_same_context() -> None:
    assert isinstance(pol.RANDOM_SEED, int)


# --- shared packing: the arms differ in order and in nothing else ------------


def test_every_arm_is_a_permutation_of_the_pool() -> None:
    pool = [item(str(i), 1 + i % 3) for i in range(30)]
    for arm, order in pol.ORDERS.items():
        assert sorted(order(pool)) == list(range(30)), arm


def test_every_arm_respects_the_budget() -> None:
    pool = [item(str(i), 1 + i % 3, pad=i) for i in range(40)]
    for arm in pol.ARMS:
        kept = pol.apply_arm(pool, arm, budget=300)
        assert sum(e.tokens for e in kept) <= 300


def test_kept_evidence_comes_back_in_retrieval_order() -> None:
    pool = [item(str(i), 3 - i % 3) for i in range(20)]
    for arm in pol.ARMS:
        kept = pol.apply_arm(pool, arm, budget=200)
        positions = [pool.index(e) for e in kept]
        assert positions == sorted(positions), arm


def test_a_budget_that_fits_everything_keeps_everything() -> None:
    pool = [item(str(i), 1 + i % 3) for i in range(10)]
    for arm in pol.ARMS:
        assert len(pol.apply_arm(pool, arm, budget=10**9)) == 10


def test_an_empty_pool_is_not_an_error() -> None:
    for arm in pol.ARMS:
        assert pol.apply_arm([], arm, budget=6000) == []


def test_an_unknown_arm_is_refused_rather_than_silently_defaulted() -> None:
    with pytest.raises(ValueError):
        pol.apply_arm([item("a", 1)], "C", budget=6000)
