"""Turning a recorded evidence path into nodes and edges.

Separate from `demo.py` because it is the only real logic the demo has and it
must be testable without the app extra installed. `demo.py` imports streamlit
at module scope; a test that has to work around that is a test that gets
skipped, and this parser decides whether the demo draws a true graph.

The distinction it exists for: `retrieval.pipeline` records a `path` on every
piece of evidence, and **not every path is a path**. Text-retrieved evidence
carries a sentence, a traversal that produced none carries a placeholder, and
both are non-empty strings in the same field as a real traversal.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

#: A traversal step, kept by `re.split` so direction survives the split.
STEP = re.compile(r"(<-\[:[^\]]+\]-|-\[:[^\]]+\]->)")
NODE = re.compile(r"\(:(?P<label>\w+)(?:\s*\{(?P<name>[^}]*)\})?\)")

#: The relation name inside a step. Read with a pattern rather than stripped
#: of its punctuation: `strip` takes a *set* of characters, so a relation
#: legitimately starting or ending with one of them would lose it silently.
RELATION = re.compile(r"\[:(?P<name>[^\]]+)\]")

#: Path strings that are prose rather than traversals.
NOT_A_PATH = ("hybrid retrieval", "lexical retrieval", "vector", "(no path recorded)")


class HasPath(Protocol):
    path: str
    key: str


def has_path(item: HasPath) -> bool:
    """Whether this evidence came from a traversal at all."""
    return bool(item.path) and not any(mark in item.path for mark in NOT_A_PATH)


def parse_path(
    path: str, fallback_key: str
) -> tuple[list[tuple[str, str]], list[tuple[int, int, str]]]:
    """Nodes and directed edges from a recorded path string.

    `retrieve` writes paths like
    ``(:Keyword {Trample})-[:DEFINED_BY]->(:Rule {702.19})``.

    Args:
        path: The recorded path.
        fallback_key: Name for an anonymous terminal such as ``(:Ruling)`` —
            the evidence key, or every ruling in one answer collapses into a
            single node and the graph shows one edge where there are ten.

    Returns:
        ``(nodes, edges)`` where a node is ``(label, name)`` and an edge is
        ``(source index, target index, relation)``. Prose returns
        ``([], [])`` rather than a guess.
    """
    parts = STEP.split(path)
    nodes: list[tuple[str, str]] = []
    edges: list[tuple[int, int, str]] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            match = NODE.search(part)
            if not match:
                return [], []
            name = (match["name"] or "").strip() or fallback_key
            nodes.append((match["label"], name))
        else:
            step = RELATION.search(part)
            if not step:
                return [], []
            relation = step["name"]
            left, right = len(nodes) - 1, len(nodes)
            edges.append((right, left, relation) if part.startswith("<-")
                         else (left, right, relation))
    return nodes, edges


#: What each node label is called for a reader who does not know the schema.
FRIENDLY = {
    "Card": "card",
    "Rule": "rule",
    "Ruling": "official ruling",
    "Keyword": "keyword",
    "Format": "format",
}

#: The hover card is rendered by vis.js inside the canvas and is **clipped**
#: at the widget boundary — a long ruling came out ending mid-sentence in the
#: first screenshot. So the tooltip identifies the node and the panel under
#: the graph reads it. A tooltip is a label, not a document.
TOOLTIP_CHARS = 110


@dataclass(frozen=True)
class GraphNode:
    """One node as the viewer meets it, not as the schema names it.

    `id` keeps the schema identity so edges join correctly; `label` is what is
    drawn. They differ because a ruling's identity is a 32-character UUID and
    drawing that teaches the viewer nothing — the first screenshot read
    `539a01a4ff17f48d5e9e…`, the node reciting its primary key.

    `text` is carried so the page can show the whole thing on click without
    searching the evidence list again for a node it already has.
    """

    id: str
    label: str
    kind: str
    title: str
    seed: bool
    text: str = ""


def _title(kind: str, label: str, text: str) -> str:
    """A one-line hover card: what this is, and enough to recognise it.

    Named by its **label**, never by its key — "official ruling — Ruling 1",
    not "official ruling — 539a01a4ff17f48d5e9e5ee063d3e3ba". Making the label
    friendly and leaving the UUID in the tooltip fixes half the problem and
    looks like all of it.
    """
    head = FRIENDLY.get(kind, kind)
    body = " ".join((text or "").split())
    if len(body) > TOOLTIP_CHARS:
        body = body[:TOOLTIP_CHARS].rsplit(" ", 1)[0] + "… (click to read)"
    return f"{head} — {label}\n\n{body}" if body else f"{head} — {label}"


def build_graph(
    evidence: Iterable
) -> tuple[list[GraphNode], list[tuple[str, str, str]]]:
    """Nodes and edges for the whole subgraph, ready to draw.

    Two facts make this more than a loop over `parse_path`.

    **A path's last node is the evidence item itself.** Traversals are
    recorded ending at what they retrieved, so the terminal node is where
    the item's text belongs — which is what gives rulings and rules a
    tooltip worth hovering.

    **A seed is what `distance` says it is, not what position says.** The
    first node of a path looks like a starting point and often is not: rule
    701.6 heads the path `(:Rule {701.6})-[:HAS_SUBRULE*]->(:Rule)` while
    having been reached one hop earlier through `DEFINED_BY`. Marking it as
    something the question named would draw the traversal as starting where
    it did not. `distance == 0` is the recorded fact and is the one used.
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    rulings: dict[str, int] = {}

    for item in evidence:
        if not has_path(item):
            continue
        parsed, links = parse_path(item.path, item.key)
        if not parsed:
            continue
        ids: list[str] = []
        for position, (kind, name) in enumerate(parsed):
            node_id = f"{kind}:{name}"
            ids.append(node_id)
            terminal = position == len(parsed) - 1
            if kind == "Ruling":
                # An ordinal, not a UUID: readable, stable within one answer,
                # and it matches how the context hands rulings to the model.
                label = f"Ruling {rulings.setdefault(name, len(rulings) + 1)}"
            elif kind == "Rule":
                label = f"Rule {name}"
            else:
                label = name
            text = item.text if terminal else ""
            candidate = GraphNode(
                id=node_id,
                label=label,
                kind=kind,
                title=_title(kind, label, text),
                seed=terminal and getattr(item, "distance", 1) == 0,
                text=text,
            )
            existing = nodes.get(node_id)
            if existing is None:
                nodes[node_id] = candidate
            else:
                # Seen from two paths: keep whichever visit knows more. A node
                # that is a seed on one path stays a seed, and text already
                # collected is not overwritten by a later visit that passed
                # through without retrieving it.
                nodes[node_id] = GraphNode(
                    id=node_id,
                    label=existing.label,
                    kind=kind,
                    title=existing.title if existing.text else candidate.title,
                    seed=existing.seed or candidate.seed,
                    text=existing.text or candidate.text,
                )
        for left, right, relation in links:
            if left < len(ids) and right < len(ids):
                edge = (ids[left], ids[right], relation)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
    return list(nodes.values()), edges


def widest_level(nodes: list[GraphNode], edges: list[tuple[str, str, str]]) -> int:
    """How many nodes sit on the most crowded rank of a left-to-right layout.

    In a hierarchical layout the canvas height is set by the widest rank, not
    by the node count: eight nodes arranged three-deep need four rows, not
    eight. Sizing by the total produced a canvas twice as tall as the drawing
    and a screenful of white space under it.

    Depth is measured from the nodes with no incoming edge — the roots of the
    drawn tree, which is what vis.js ranks from. A cycle cannot lengthen the
    walk because each node is ranked once, on first arrival.
    """
    if not nodes:
        return 0
    targets = {target for _, target, _ in edges}
    children: dict[str, list[str]] = {}
    for source, target, _ in edges:
        children.setdefault(source, []).append(target)

    depth = {node.id: 0 for node in nodes if node.id not in targets}
    frontier = list(depth)
    if not frontier:  # every node has a parent: take an arbitrary start
        frontier = [nodes[0].id]
        depth[frontier[0]] = 0
    while frontier:
        nxt: list[str] = []
        for node_id in frontier:
            for child in children.get(node_id, []):
                if child not in depth:
                    depth[child] = depth[node_id] + 1
                    nxt.append(child)
        frontier = nxt

    counts: dict[int, int] = {}
    for node in nodes:
        rank = depth.get(node.id, 0)
        counts[rank] = counts.get(rank, 0) + 1
    return max(counts.values())
