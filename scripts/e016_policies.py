#!/usr/bin/env python
"""E-016's four eviction policies, as pure functions over retrieved evidence.

They live here rather than in `graphrag_mtg.retrieval` on purpose: nothing has
measured them yet, and shipping a policy before its entry runs is what the
registration exists to prevent. Branch 1 moves the winner into
`enforce_budget` as an option, off by default, *after* the run.

**Every policy is a selection order — best first — and nothing else.** The
budget is then applied by one shared routine, so the only thing that differs
between arms is which items a policy would rather keep. That is the registered
claim, and expressing it this way makes it structurally true instead of
something the code has to be trusted about.

**Every policy is oracle-free.** `metaqa.reduce_to_k` keeps the answer chain
because it is handed the answer; nothing here may be. The ceiling registered
for E-016 — the chain is in the retrieved pool on 92 of 100 questions and costs
about 90 tokens of a 6,000-token budget — is what an oracle would score. The
gap between that and any arm below is the price of not knowing which 90 tokens
matter.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from graphrag_mtg.retrieval.subgraph import Evidence

#: Fixed here rather than passed in, so a re-run of arm R sends the same
#: context. A random arm whose seed lives at the call site is a random arm
#: whose result cannot be reproduced from the entry.
RANDOM_SEED = 20260913

ARMS = ("A", "B", "D", "R")


def endpoints(item: Evidence) -> tuple[str, str]:
    """The two entities one triple-evidence item joins."""
    head, _, tail = item.text.split(" | ")
    return head, tail


def by_level(evidence: Sequence[Evidence]) -> dict[int, list[int]]:
    """Indices grouped by hop distance, each in retrieval order."""
    levels: dict[int, list[int]] = {}
    for index, item in enumerate(evidence):
        levels.setdefault(item.distance, []).append(index)
    return levels


# ── the four selection orders ────────────────────────────────────────────────


def order_a(evidence: Sequence[Evidence]) -> list[int]:
    """Arm A — what ships today, expressed as a selection order.

    `enforce_budget` evicts by `(-distance, -index)`, so it prefers to keep the
    nearest evidence and, within a distance, the earliest to arrive. Reversing
    its eviction order gives exactly that preference. `test_e016_policies.py`
    pins this against the shipped function rather than against this docstring.
    """
    return sorted(range(len(evidence)), key=lambda i: (evidence[i].distance, i))


def order_b(evidence: Sequence[Evidence]) -> list[int]:
    """Arm B — proportional: each hop distance gets an equal share.

    Round-robin across levels: the first item of every level, then the second
    of every level, and so on. Triple evidence is near-uniform in size, so
    equal counts are equal token shares to within a few percent — stated here
    because it is an approximation and not an identity.

    A level that runs out simply stops contributing; the remaining levels carry
    on, which is the "leftover" pass the registration describes rather than a
    separate phase.
    """
    levels = by_level(evidence)
    order: list[int] = []
    for rank in range(max((len(v) for v in levels.values()), default=0)):
        for distance in sorted(levels):
            if rank < len(levels[distance]):
                order.append(levels[distance][rank])
    return order


def order_d(evidence: Sequence[Evidence]) -> list[int]:
    """Arm D — connectivity first: prefer evidence that extends what is kept.

    A chain is a connected path, so evidence hanging off something already kept
    is chain-shaped without anyone knowing which chain. Within each level, items
    joined to an entity the shallower levels reached come before items that are
    not; levels are then interleaved exactly as arm B interleaves them, so the
    only difference between B and D is the ordering *inside* a level.

    The connected set is grown from the whole of each shallower level rather
    than from the part that survives the budget. That is an approximation, and
    it is the honest direction for one: it can only call an item connected that
    a stricter rule would call unconnected, so D is never credited with a
    discrimination it did not make.
    """
    levels = by_level(evidence)
    touched: set[str] = set()
    ordered_levels: dict[int, list[int]] = {}
    for distance in sorted(levels):
        if not touched:
            # The shallowest level present hangs off the seed by construction,
            # so there is nothing yet to be connected *to*: retrieval order.
            ordered_levels[distance] = list(levels[distance])
        else:
            joined = [i for i in levels[distance] if set(endpoints(evidence[i])) & touched]
            loose = [i for i in levels[distance] if not set(endpoints(evidence[i])) & touched]
            ordered_levels[distance] = joined + loose
        for index in levels[distance]:
            touched.update(endpoints(evidence[index]))

    order: list[int] = []
    for rank in range(max((len(v) for v in ordered_levels.values()), default=0)):
        for distance in sorted(ordered_levels):
            if rank < len(ordered_levels[distance]):
                order.append(ordered_levels[distance][rank])
    return order


def order_r(evidence: Sequence[Evidence]) -> list[int]:
    """Arm R — random at a recorded seed. The control, and the falsifier.

    If R matches B and D within their intervals then nothing the designed
    policies do matters, and the only thing that helped was ceasing to evict by
    descending distance. That is a smaller claim and it is the one that gets
    reported.
    """
    order = list(range(len(evidence)))
    random.Random(RANDOM_SEED).shuffle(order)
    return order


ORDERS = {"A": order_a, "B": order_b, "D": order_d, "R": order_r}


# ── applying a budget to a selection order ───────────────────────────────────


def keep_within(evidence: Sequence[Evidence], order: Sequence[int], budget: int) -> list[Evidence]:
    """Keep the longest prefix of ``order`` that fits ``budget``, in retrieval order.

    This matches `enforce_budget`'s semantics rather than greedy packing: it
    stops at the first item that does not fit instead of skipping it and
    carrying on. The difference is small and it is a difference, so it is fixed
    here once and shared by all four arms — a contrast where the arms also
    differ in how they pack is not a contrast about ordering.

    Args:
        evidence: The retrieved evidence, in retrieval order.
        order: Indices, best first.
        budget: Token ceiling.

    Returns:
        The kept items, in the order retrieval produced them.
    """
    kept: set[int] = set()
    running = 0
    for index in order:
        cost = evidence[index].tokens
        if running + cost > budget:
            break
        kept.add(index)
        running += cost
    return [item for index, item in enumerate(evidence) if index in kept]


def apply_arm(evidence: Sequence[Evidence], arm: str, budget: int) -> list[Evidence]:
    """One arm's kept evidence at one budget."""
    if arm not in ORDERS:
        raise ValueError(f"unknown arm {arm!r}; the registered arms are {ARMS}")
    return keep_within(evidence, ORDERS[arm](evidence), budget)
