#!/usr/bin/env python
"""Can you ask an arm *why* an item is in the context? E-029's instrument.

No API, no graph, no model: arithmetic and rendering over E-001's retrieval
dumps.

**This is a capability demonstration, not a test.** There is no hypothesis, no
decision rule and no p-value, and there will not be one: "the answer cites the
edge it walked" is not a quantity with a sampling distribution. E-026 measured
that this evaluation cannot see correctness differences below 0.20, and the
response is not to invent a statistic for something structural.

**The quantity that looked equal, and the question that separates it.** Every
evidence item in every arm carries a `path` field, and it is populated **100%
of the time in all three arms**. Standing rule 9: of the items that carry a
path, how many? All of them. What *else* would make that come back 100%?

    A vector   2215 items   1 distinct path     1 shape
    B graph     710 items   275 distinct paths  4 shapes

The vector arm's provenance is **one constant string**. It records that the
index returned the item, which is true of every item the index returns. The
graph arm's records which edge was walked, from which node, at what depth — a
claim about *why this item bears on this question* that a reader can check
against the corpus.

That difference does not show up in any correctness figure, and it is the thing
a person auditing a rules answer actually needs.

Usage:
    python scripts/provenance_demo.py
    python scripts/provenance_demo.py --qid rg-1591
    python scripts/provenance_demo.py --qid rg-1591 --full
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e001_inspect import artefacts, load_jsonl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "=" * 78
THIN = "-" * 78

ARMS = (("A vector", "A-hybrid"), ("B graph", "B"), ("C hybrid", "C-vector-hybrid-routed"))
SPLIT = "eval"

#: The literal the vector arm writes into every item's `path`. Named here so
#: the report can say "this is a constant" rather than leaving a reader to
#: notice it, and so a future change to that string fails loudly.
VECTOR_CONSTANT = "hybrid retrieval over the shared corpus"

#: Characters that survive when a path is reduced to its shape. Two paths with
#: the same shape walked the same kind of edge from a different node.
SHAPE_CHARS = "()[]-><*:"


def shape(path: str) -> str:
    """A path stripped to its structure, so distinct nodes collapse.

    Node contents go first. `-` is a shape character *and* appears in card
    names, so reducing the raw string leaves "Snow-Covered Forest" contributing
    a hyphen and splitting one shape into two. The first version of this
    function did exactly that and reported six shapes where there are four.
    """
    stripped = re.sub(r"\{[^}]*\}", "", path)
    return "".join(character for character in stripped if character in SHAPE_CHARS)


def survey(split: str) -> int:
    """How much provenance each arm records, across the whole split."""
    print(f"{RULE}\nPROVENANCE ACROSS THE SPLIT\n{RULE}\n")
    print(f"{'arm':<12}{'items':>8}{'with a path':>14}{'distinct':>11}{'shapes':>9}")
    for label, slug in ARMS:
        path, _, _ = artefacts(slug, split)
        items = [item for row in load_jsonl(path, what=slug) for item in row.get("evidence", ())]
        populated = [item for item in items if (item.get("path") or "").strip()]
        paths = Counter(item["path"] for item in populated)
        shapes = Counter(shape(item["path"]) for item in populated)
        print(
            f"{label:<12}{len(items):>8}{f'{len(populated) / len(items):.0%}':>14}"
            f"{len(paths):>11}{len(shapes):>9}"
        )

    print(
        f"\n  **All three arms populate the field on every item.** The count is not\n"
        "  the measurement; the number of *distinct* values is. The vector arm\n"
        f"  writes one string, {VECTOR_CONSTANT!r},\n"
        "  which is true of everything an index returns and therefore says\n"
        "  nothing about any particular item."
    )

    print(f"\n{THIN}\nWHAT THE GRAPH ARM RECORDS INSTEAD\n{THIN}")
    path, _, _ = artefacts("B", split)
    items = [item for row in load_jsonl(path, what="B") for item in row.get("evidence", ())]
    depths = Counter(item.get("distance") for item in items)
    print(f"  traversal depth: {dict(sorted(depths.items(), key=lambda kv: kv[0]))}")
    print("  the distinct shapes, with an example and a count for each:\n")
    seen: dict[str, str] = {}
    for item in items:
        seen.setdefault(shape(item["path"]), item["path"])
    for _, example in sorted(seen.items(), key=lambda kv: len(kv[0])):
        count = sum(1 for item in items if shape(item["path"]) == shape(example))
        print(f"    {count:>4}x  {example}")
    return 0


def one_question(qid: str, split: str, full: bool) -> int:
    """The same question's evidence, side by side, with its provenance.

    Raises:
        SystemExit: when an arm did not run this question, rather than printing
            a one-sided comparison that looks like a two-sided one.
    """
    print(f"{RULE}\n{qid} — WHY IS EACH ITEM HERE?\n{RULE}")
    for label, slug in ARMS[:2]:
        path, _, _ = artefacts(slug, split)
        rows = {row["question_id"]: row for row in load_jsonl(path, what=slug)}
        if qid not in rows:
            raise SystemExit(f"{qid} is not in arm {label}'s {split} dump.")
        items = rows[qid].get("evidence", ())
        print(f"\n{THIN}\n{label} — {len(items)} item(s)\n{THIN}")
        for item in items if full else items[:12]:
            key = str(item.get("key", ""))[:36]
            print(f"  [{item.get('kind','?'):<9}] {key:<38} d={item.get('distance')}")
            print(f"      via {item.get('template','?')}: {item.get('path','')}")
        if not full and len(items) > 12:
            print(f"  ... {len(items) - 12} more; pass --full")
    print(
        f"\n{THIN}\n  Read the `via` lines. In one arm each is a claim about this item\n"
        "  that a reader can check against the corpus; in the other every line\n"
        f"  is the same sentence, repeated once per item.\n{THIN}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default=SPLIT)
    parser.add_argument("--qid", default=None, help="render one question side by side")
    parser.add_argument("--full", action="store_true", help="every item, not the first twelve")
    args = parser.parse_args()
    if args.qid:
        return one_question(args.qid, args.split, args.full)
    return survey(args.split)


if __name__ == "__main__":
    raise SystemExit(main())
