#!/usr/bin/env python
"""E-001 pin 10 — the legality answer key decays, so re-verify it before a run.

Fifteen of the 57 evaluation questions are `legality_1hop`: *"Is X legal in
Modern?"*. Their answer is not a fact about Magic's rules, it is a fact about a
ban list, and ban lists move. The golden row froze the answer as

    snapshot_sha256 = sha256("{oracle_id}|{format}|{status}")

at curation time (`evaluation/generators.py`), and ingestion is a **daily**
Scryfall bulk. So between the draw and the run the key can silently stop being
the key, and the arm that gets it right scores wrong.

E-001 amendment 2026-08-15b pin 10 registered the procedure: if a newer bulk is
used, the legality answers are re-verified against it **before** the run, and
any changed answer is marked `key_stale` and excluded with the exclusion
stated. This script is that check. It is deterministic, free, and reads the
same bulk the run will read.

It answers one question and refuses to answer it vaguely: **exit 0 when every
key still holds, exit 1 when any of them drifted.** A check that reports
"mostly fine" is a check nobody acts on.

Usage:
    python scripts/verify_legality_keys.py
    python scripts/verify_legality_keys.py --json data/interim/legality_drift.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from graphrag_mtg.etl.bulk import ORACLE_CARDS_STEM, bulk_path, iter_bulk
from graphrag_mtg.evaluation.golden import content_sha256

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE = "-" * 78
GOLDEN = Path("data/golden")

#: `scry-leg-<oracle_id>-<format>`; the oracle id is a UUID and the format is
#: the trailing segment. Split from the right, because a UUID contains hyphens
#: and splitting from the left would hand back a fragment of the id.
QUESTION_ID = re.compile(r"^scry-leg-(?P<oracle_id>[0-9a-f-]{36})-(?P<fmt>[a-z]+)$")


def legality_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(GOLDEN.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("stratum") == "legality_1hop":
                    rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", type=Path, default=None,
                        help="write the per-question verdict here as well")
    args = parser.parse_args()

    rows = legality_rows()
    if not rows:
        raise SystemExit("No legality_1hop rows found under data/golden/.")

    wanted: dict[str, list[dict]] = {}
    for row in rows:
        match = QUESTION_ID.match(row["id"])
        if not match:
            raise SystemExit(f"Unparseable legality question id: {row['id']}")
        wanted.setdefault(match["oracle_id"], []).append(
            {"row": row, "fmt": match["fmt"]}
        )

    path = bulk_path(ORACLE_CARDS_STEM)
    if not path.exists():
        raise SystemExit(f"No Scryfall bulk at {path}. Run etl/download.py first.")

    # One pass over the bulk, not one lookup per question: the file is ~150MB
    # gzipped and 20 passes over it to answer 20 questions is 20x the I/O for
    # the same answer.
    current: dict[str, dict] = {}
    for card in iter_bulk(path):
        oracle_id = card.get("oracle_id")
        if oracle_id in wanted:
            current[oracle_id] = card

    print(f"E-001 pin 10 — legality answer keys against {path}")
    print(f"{len(rows)} legality_1hop question(s) over {len(wanted)} card(s)")
    print(RULE)

    verdicts: list[dict] = []
    drifted: list[dict] = []
    missing: list[dict] = []
    for oracle_id, entries in sorted(wanted.items()):
        card = current.get(oracle_id)
        for entry in entries:
            row, fmt = entry["row"], entry["fmt"]
            if card is None:
                missing.append(row)
                verdicts.append({"id": row["id"], "verdict": "card_absent"})
                continue
            status = (card.get("legalities") or {}).get(fmt)
            if status is None:
                missing.append(row)
                verdicts.append({"id": row["id"], "verdict": "format_absent"})
                continue
            now = content_sha256(f"{oracle_id}|{fmt}|{status}")
            ok = now == row.get("snapshot_sha256")
            verdicts.append(
                {
                    "id": row["id"],
                    "verdict": "holds" if ok else "key_stale",
                    "format": fmt,
                    "status_now": status,
                    "card": card.get("name"),
                }
            )
            if not ok:
                drifted.append(verdicts[-1])

    holds = sum(1 for v in verdicts if v["verdict"] == "holds")
    print(f"  holds     {holds}/{len(verdicts)}")
    print(f"  key_stale {len(drifted)}")
    print(f"  missing   {len(missing)}")
    for entry in drifted:
        print(f"    ** {entry['id']}")
        print(f"       {entry['card']} — Scryfall now says {entry['format']}: "
              f"{entry['status_now']}, which is not what the key was frozen on")
    for row in missing:
        print(f"    ** {row['id']} — no current record for this card/format")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"bulk": str(path), "verdicts": verdicts}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n  wrote {args.json}")

    print(RULE)
    if drifted or missing:
        print("PIN 10: the evaluation run does NOT open until each question above is")
        print("either re-verified against the new bulk or marked key_stale and")
        print("excluded, with the exclusion stated in the registry.")
        return 1
    print("PIN 10 SATISFIED: every legality key still holds against the current bulk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
