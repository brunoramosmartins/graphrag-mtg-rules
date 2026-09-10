"""``--help`` has to be printable on the console that will print it.

On 2026-09-10 `python -m graphrag_mtg.extraction.pipeline --help` died with
`UnicodeEncodeError` on Windows. argparse prints the module docstring as the
description, that docstring drew its cascade with box-drawing characters, and
a Windows console is cp1252, where those characters raise rather than print.

The failure is small and the shape is not: it turns the one command a
newcomer runs to find out what a tool does into a traceback, on the platform
this project is developed on, and no test could see it because the pipeline's
own tests never render its help.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The encoding a Windows console uses by default. Not the encoding anyone
# wants — the encoding help text has to survive.
CONSOLE_ENCODING = "cp1252"


def cli_modules() -> list[Path]:
    """Every module that hands its docstring to argparse."""
    found: list[Path] = []
    for directory in ("src", "scripts"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "description=__doc__" in text or "ArgumentParser(__doc__" in text:
                found.append(path)
    return found


def test_the_scan_finds_something() -> None:
    # A guard that silently matches nothing passes forever. `pipeline.py` is
    # the module the defect was found in, so it is the one that must be here.
    modules = cli_modules()
    assert modules
    assert any(p.name == "pipeline.py" for p in modules)


@pytest.mark.parametrize("path", cli_modules(), ids=lambda p: p.name)
def test_a_help_description_is_printable_on_a_windows_console(path: Path) -> None:
    docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    assert docstring, f"{path} passes __doc__ to argparse but has no docstring"

    unprintable = sorted(
        {c for c in docstring if c.encode(CONSOLE_ENCODING, "ignore") == b""}
    )
    assert not unprintable, (
        f"{path.relative_to(ROOT)} cannot print --help on a {CONSOLE_ENCODING} "
        f"console: {unprintable!r}. Draw diagrams in ASCII."
    )
