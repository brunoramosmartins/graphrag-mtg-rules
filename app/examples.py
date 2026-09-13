"""Resolving the text of a golden question, where the licence allows it.

The golden set does not store every question the same way, and that is a
compliance decision rather than an inconsistency. Authored and generated rows
carry their text inline. **RulesGuru rows carry `question: null`** — the repo
versions their ids and a gitignored fetch retrieves the text — so on a clean
clone eight of the twenty development questions have no text at all.

A picker that reads `row["question"]` gets `None` for those and raises
`TypeError` on the first slice. The harness's own `question_and_key` raises
`SystemExit` instead, which is right for a batch script and fatal for an app:
it would take the whole page down over a question nobody selected.

So this module resolves what it can, reports what it cannot, and never raises.

Kept out of `demo.py` because that imports streamlit at module scope, and a
test that needs the app extra installed to check a fallback is a test that
gets skipped.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

#: Where the text of a licensed question lives, if it lives anywhere locally.
#: Two pools store it differently and both are consulted rather than one being
#: assumed — assuming the E-007 layout is what silently empties half a batch.
CACHES = (Path("data/interim/e007_cache"), Path("data/interim/golden_cache"))


def question_text(row: dict, root: Path, caches: Sequence[Path] = CACHES) -> str:
    """This question's text, or empty when the checkout does not have it."""
    for cache in caches:
        path = root / cache / f"{row['id']}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = payload.get("questionSimple") or payload.get("question") or ""
            if text:
                return text
    return row.get("question") or ""


def resolve(rows: Sequence[dict], root: Path,
            caches: Sequence[Path] = CACHES) -> tuple[list[dict], int]:
    """Rows whose text is available, and how many were withheld.

    Returns:
        ``(resolved, withheld)``. The count is returned rather than dropped so
        the page can say why the list is short instead of quietly being short.
    """
    filled = [dict(row, question=question_text(row, root, caches)) for row in rows]
    resolved = [row for row in filled if row["question"]]
    return resolved, len(filled) - len(resolved)
