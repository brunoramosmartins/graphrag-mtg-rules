"""Turning traversal rows into citable evidence, per the template's own map.

The conversion is driven by :class:`~graphrag_mtg.retrieval.templates.Emit`
declarations that live beside each query, so a ``RETURN`` clause and its
mapping cannot drift apart unnoticed — a test asserts every column named
in a mapping is one the query returns.

Two behaviours here exist because Neo4j has them, and both were confirmed
against the loaded graph rather than assumed:

- **A missed ``OPTIONAL MATCH`` still collects.**
  ``collect(DISTINCT {number: sub.number, text: sub.text})`` over zero
  matches yields ``[{number: None, text: None}]``, not ``[]``. Passed
  through, that becomes a citation handle of ``rule:None`` — a footnote
  pointing at nothing. Entries with no key are dropped.
- **Rows repeat their scalar columns.** A card with four keywords returns
  the card's name four times. Deduplication is the subgraph's job
  (identity is ``(template, kind, key)``), so this module emits freely and
  lets `add_evidence` collapse it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from graphrag_mtg.retrieval.subgraph import Evidence
from graphrag_mtg.retrieval.templates import Emit, Template


def _format_path(pattern: str, row: Mapping[str, Any], item: Mapping[str, Any] | None) -> str:
    """Fill a path pattern from the row, falling back to the raw pattern.

    A path is documentation of provenance, not control flow: if a value is
    missing the citation should still name its traversal rather than raise
    and lose the evidence entirely.
    """
    values = dict(row)
    if item:
        values.update(item)
    try:
        return pattern.format(**values)
    except (KeyError, IndexError):
        return pattern


def _from_emit(emit: Emit, template: Template, row: Mapping[str, Any]) -> list[Evidence]:
    entries: list[Mapping[str, Any]]
    if emit.collection:
        raw = row.get(emit.collection) or []
        entries = [entry for entry in raw if isinstance(entry, Mapping)]
    else:
        entries = [row]

    found = []
    for entry in entries:
        key = entry.get(emit.key)
        if key in (None, ""):
            # The empty collect() of a missed OPTIONAL MATCH, or a null
            # property. Either way there is nothing to cite.
            continue
        found.append(
            Evidence(
                kind=emit.kind,
                key=str(key),
                text=str(entry.get(emit.text) or ""),
                template=template.name,
                path=_format_path(emit.path, row, entry if emit.collection else None),
                distance=emit.distance,
            )
        )
    return found


def to_evidence(template: Template, rows: Iterable[Mapping[str, Any]]) -> list[Evidence]:
    """Convert a traversal's rows into evidence, in declaration order.

    Args:
        template: The traversal that produced ``rows``; its ``emits`` are
            the mapping.
        rows: Result rows, each a mapping of column name to value.

    Returns:
        Evidence in the order the mappings are declared, which puts the
        nearest node first and lets the subgraph's budget keep it.
    """
    found: list[Evidence] = []
    for row in rows:
        for emit in template.emits:
            found.extend(_from_emit(emit, template, row))
    return found
