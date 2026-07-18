"""Hashed, idempotent downloads of the Phase 1 source corpus.

Downloads the raw sources into ``data/raw/`` (gitignored — **never** committed)
and records a SHA-256 manifest so re-runs are incremental: a source whose
upstream version is unchanged is skipped without re-downloading. Nothing here
calls an LLM.

Sources:
    * Scryfall bulk ``oracle_cards`` and ``rulings`` (JSON) — the structured
      backbone and the rulings corpus. Change detection uses Scryfall's
      ``updated_at`` so a 100+ MB bulk is not re-fetched when unchanged.
    * WotC Comprehensive Rules (TXT), resolved from the rules landing page
      (the dated TXT link changes each release). Override with ``CR_TXT_URL``.
    * WotC MTR / IPG (PDF) — optional (CR + rulings carry the project). Their
      URLs are not reliably auto-resolvable; supply ``MTR_PDF_URL`` /
      ``IPG_PDF_URL`` (env) or ``--mtr-url`` / ``--ipg-url`` to fetch them.

Compliance: bulk data and rules text are downloaded on demand and never
committed (see docs/data-sources.md). Requests carry a descriptive User-Agent
and Scryfall is rate-limited politely.

Usage:
    python -m graphrag_mtg.etl.download                  # all resolvable sources
    python -m graphrag_mtg.etl.download --source scryfall
    python -m graphrag_mtg.etl.download --dry-run        # resolve + report only
    python -m graphrag_mtg.etl.download --force          # ignore manifest, re-fetch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

RAW_DIR = Path("data/raw")
MANIFEST_PATH = RAW_DIR / "manifest.json"

USER_AGENT = "graphrag-mtg-rules/0.1 (non-commercial fan project; +github.com/brunoramosmartins)"
TIMEOUT = 60.0
CHUNK = 1 << 16  # 64 KiB streaming chunks

SCRYFALL_BULK_INDEX = "https://api.scryfall.com/bulk-data"
SCRYFALL_WANTED = ("oracle_cards", "rulings")
CR_LANDING = "https://magic.wizards.com/en/rules"

# Top-level source groups selectable via --source.
SOURCE_GROUPS = ("scryfall", "comprehensive-rules", "mtr", "ipg")


@dataclass(frozen=True)
class ResolvedSource:
    """A concrete download target resolved from a source group.

    Attributes:
        name: Stable manifest key (e.g. ``scryfall_oracle_cards``).
        url: The URL to download.
        version: A cheap upstream-version token for change detection
            (Scryfall ``updated_at``; for static files, the URL itself).
        filename: Destination file name under ``data/raw/``.
    """

    name: str
    url: str
    version: str
    filename: str


def _client() -> httpx.Client:
    """Return an httpx client with the project User-Agent and redirects on."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in streaming chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict]:
    """Load the download manifest, or an empty dict if none exists."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, dict], path: Path = MANIFEST_PATH) -> None:
    """Write the manifest as pretty JSON, keys sorted for stable diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_current(manifest: dict[str, dict], source: ResolvedSource, raw_dir: Path = RAW_DIR) -> bool:
    """Return True if the manifest version matches and the file is present.

    Pure change-detection predicate (no I/O beyond an existence check), so a
    re-run skips a source whose upstream ``version`` is unchanged.
    """
    entry = manifest.get(source.name)
    if entry is None or entry.get("version") != source.version:
        return False
    return (raw_dir / source.filename).exists()


def stream_download(client: httpx.Client, url: str, dest: Path) -> tuple[str, int]:
    """Stream ``url`` to ``dest``, returning ``(sha256_hex, byte_count)``.

    Writes to a ``.part`` sidecar and renames on success so an interrupted
    download never leaves a truncated file in place.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()
    total = 0
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes(CHUNK):
                fh.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
    tmp.replace(dest)
    return hasher.hexdigest(), total


def resolve_scryfall(client: httpx.Client) -> list[ResolvedSource]:
    """Resolve the wanted Scryfall bulk artifacts from the bulk index."""
    index = client.get(SCRYFALL_BULK_INDEX).raise_for_status().json()
    by_type = {item["type"]: item for item in index.get("data", [])}
    resolved: list[ResolvedSource] = []
    for bulk_type in SCRYFALL_WANTED:
        item = by_type.get(bulk_type)
        if item is None:
            print(f"[scryfall] WARNING: bulk type {bulk_type!r} not in index; skipping")
            continue
        resolved.append(
            ResolvedSource(
                name=f"scryfall_{bulk_type}",
                url=item["download_uri"],
                version=item.get("updated_at", item["download_uri"]),
                filename=f"scryfall_{bulk_type}.json",
            )
        )
    return resolved


def resolve_comprehensive_rules(client: httpx.Client) -> list[ResolvedSource]:
    """Resolve the current Comprehensive Rules TXT link.

    Prefers the ``CR_TXT_URL`` env override; otherwise scrapes the first
    ``.txt`` link from the rules landing page. Returns an empty list (with a
    message) if neither resolves, so a run does not crash on WotC page changes.
    """
    override = os.getenv("CR_TXT_URL")
    if override:
        url = override
    else:
        html = client.get(CR_LANDING, headers={"Accept": "text/html"}).raise_for_status().text
        matches = re.findall(r'https?://[^"\'\s]+?\.txt', html)
        # Prefer a link that looks like the comprehensive rules file.
        preferred = [m for m in matches if re.search(r"(comp|rule)", m, re.IGNORECASE)]
        candidates = preferred or matches
        if not candidates:
            print(
                "[comprehensive-rules] could not find a .txt link on the landing "
                "page (it is JS-rendered). Set CR_TXT_URL to the current rules "
                "TXT and re-run — it lives at "
                "media.wizards.com/<year>/downloads/MagicCompRules%20<YYYYMMDD>.txt "
                "(linked from magic.wizards.com/en/rules)."
            )
            return []
        url = candidates[0]
    return [
        ResolvedSource(
            name="comprehensive_rules",
            url=url,
            version=url,  # the dated URL is the version token for a static file
            filename="comprehensive_rules.txt",
        )
    ]


def resolve_optional_pdf(name: str, env_var: str, cli_url: str | None) -> list[ResolvedSource]:
    """Resolve an optional PDF (MTR/IPG) from a CLI arg or env var, if given."""
    url = cli_url or os.getenv(env_var)
    if not url:
        print(f"[{name}] no URL provided (optional); set {env_var} or --{name}-url to fetch")
        return []
    return [ResolvedSource(name=name, url=url, version=url, filename=f"{name}.pdf")]


def process(
    source: ResolvedSource,
    manifest: dict[str, dict],
    client: httpx.Client,
    *,
    dry_run: bool,
    force: bool,
    raw_dir: Path = RAW_DIR,
) -> str:
    """Download one resolved source if needed; update the manifest in place.

    Returns a short human-readable status: ``unchanged``, ``downloaded``, or
    ``dry-run``.
    """
    if not force and is_current(manifest, source, raw_dir):
        print(f"[{source.name}] unchanged (version {source.version}); skipping")
        return "unchanged"
    if dry_run:
        print(f"[{source.name}] would download {source.url}")
        return "dry-run"

    dest = raw_dir / source.filename
    sha256, size = stream_download(client, source.url, dest)
    manifest[source.name] = {
        "url": source.url,
        "version": source.version,
        "sha256": sha256,
        "bytes": size,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"[{source.name}] downloaded {size:,} bytes -> {dest} (sha256 {sha256[:12]}...)")
    return "downloaded"


def resolve_all(client: httpx.Client, groups: list[str], args: argparse.Namespace) -> list[ResolvedSource]:
    """Resolve every selected source group to concrete targets."""
    resolved: list[ResolvedSource] = []
    for group in groups:
        if group == "scryfall":
            resolved += resolve_scryfall(client)
        elif group == "comprehensive-rules":
            resolved += resolve_comprehensive_rules(client)
        elif group == "mtr":
            resolved += resolve_optional_pdf("mtr", "MTR_PDF_URL", args.mtr_url)
        elif group == "ipg":
            resolved += resolve_optional_pdf("ipg", "IPG_PDF_URL", args.ipg_url)
    return resolved


def main() -> int:
    load_dotenv()  # pick up CR_TXT_URL / MTR_PDF_URL / IPG_PDF_URL from .env
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=SOURCE_GROUPS, help="download only one source group")
    parser.add_argument("--dry-run", action="store_true", help="resolve and report; write nothing")
    parser.add_argument("--force", action="store_true", help="ignore the manifest and re-download")
    parser.add_argument("--mtr-url", help="URL of the current MTR PDF (optional)")
    parser.add_argument("--ipg-url", help="URL of the current IPG PDF (optional)")
    args = parser.parse_args()

    groups = [args.source] if args.source else list(SOURCE_GROUPS)
    manifest = load_manifest()
    with _client() as client:
        sources = resolve_all(client, groups, args)
        if not sources:
            print("No sources resolved. Nothing to do.")
            return 0
        for source in sources:
            process(source, manifest, client, dry_run=args.dry_run, force=args.force)

    if not args.dry_run:
        save_manifest(manifest)
        print(f"\nManifest written to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
