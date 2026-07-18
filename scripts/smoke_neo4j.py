#!/usr/bin/env python
"""Phase 0 smoke test: verify the Python driver can reach Neo4j.

Usage:
    docker compose up -d
    python scripts/smoke_neo4j.py

Exits 0 on success, 1 if Neo4j is unreachable.
"""

from __future__ import annotations

import sys

from graphrag_mtg.config import get_settings
from graphrag_mtg.graph.connection import verify_connectivity


def main() -> int:
    settings = get_settings()
    print(f"Connecting to {settings.neo4j_uri} as {settings.neo4j_user} ...")
    try:
        ok = verify_connectivity()
    except Exception as exc:  # smoke script prints, doesn't re-raise
        print(f"FAILED: {exc}")
        print("Is Neo4j up? Try: docker compose up -d && docker compose ps")
        return 1
    if ok:
        print("OK: Neo4j is healthy and answered `RETURN 1`.")
        return 0
    print("FAILED: connected but the trivial query did not return 1.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
