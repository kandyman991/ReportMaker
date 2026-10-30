"""Fail-closed audit of the *actual* PyInstaller V2 executable archive.

Windows CI runs this on ReportMakerV2.exe after freeze, before setup creation.
It deliberately inspects archive contents, not just loaded sys.modules or
the source-level import graph. Requires the build's pinned PyInstaller install.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

# V1-only GUI, default launcher, and test probes. Shared pre-V2 modules
# (photo_editor, photo_gallery, storage, project_io, export, etc.) are NOT V1.
LEGACY_MODULES = frozenset({
    "reportmaker.__main__",
    "reportmaker.ui",
    "reportmaker.visual_editor",
    "reportmaker.page_editor",
    "reportmaker.rich_editor",
    "reportmaker.template_dialog",
    "reportmaker.customer_ui",
    "reportmaker.customer_probe",
    "reportmaker.editor_probe",
    "reportmaker.export_probe",
    "reportmaker.layout_probe",
})

# Required dynamic/UI and shared behavior. A missing module is just as
# serious as an unexpected V1 module: the app may start but break later.
REQUIRED_MODULES = frozenset({
    "reportmaker.v2.app",
    "reportmaker.v2.chat_tab",
    "reportmaker.v2.gallery_tab",
    "reportmaker.v2.editor_tab",
    "reportmaker.v2.branch.canvas",
    "reportmaker.v2.branch.photo_tools",
    "reportmaker.v2.customer_manager",
    "reportmaker.engine",
    "reportmaker.export",
    "reportmaker.media_import",
    "reportmaker.model",
    "reportmaker.photo_editor",
    "reportmaker.photo_gallery",
    "reportmaker.project_io",
    "reportmaker.reference",
    "reportmaker.rich_text",
    "reportmaker.storage",
    "reportmaker.template_import",
})

# PyInstaller's recursive archive listing includes PYZ Python module names.
# Treat only dotted module identifiers, not diagnostic prose or paths.
_NAME = re.compile(
    r"(?<![a-zA-Z0-9_.])(?P<name>reportmaker(?:\.[a-zA-Z_][a-zA-Z_0-9]*)+)"
    r"(?![a-zA-Z_0-9])"
)


def verify_listing(listing: str) -> tuple[set[str], set[str], set[str]]:
    """Return modules, prohibited modules, and missing required modules."""
    if not isinstance(listing, str) or not listing.strip():
        raise ValueError("Empty frozen archive listing (fail closed)")
    names = set(_NAME.findall(listing))
    # Only exact module names; a dotted package descendant is also prohibited.
    unexpected = {
        name for name in names
        if any(name == old or name.startswith(old + ".") for old in LEGACY_MODULES)
    }
    missing = REQUIRED_MODULES - names
    return names, unexpected, missing


def inspect_archive(executable: Path) -> tuple[set[str], set[str], set[str]]:
    """List the EXE (and embedded PYZ) through PyInstaller's archive viewer."""
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        raise ValueError("Provide an existing frozen V2 .exe, not source or .spec")
    if executable.name != "ReportMakerV2.exe":
        raise ValueError("Only the isolated ReportMakerV2.exe may be validated")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller.utils.cliutils.archive_viewer",
         "-l", "-r", str(executable)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Frozen archive viewer failed ({result.returncode}): "
            + result.stderr[-1200:]
        )
    names, unexpected, missing = verify_listing(result.stdout)
    # Check loose app-package files too: no legacy source/data should leak into
    # the onedir payload even if it is outside the embedded executable archive.
    for item in executable.parent.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(executable.parent).as_posix()
        rel = rel.removeprefix("_internal/")
        candidate = rel.replace("/", ".")
        if candidate.endswith((".py", ".pyc", ".pyd")):
            module = candidate.rsplit(".", 1)[0]
            if any(module == old or module.startswith(old + ".")
                   for old in LEGACY_MODULES):
                unexpected.add(module)
    return names, unexpected, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args(argv)
    try:
        names, unexpected, missing = inspect_archive(args.executable)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"V2 frozen module inventory FAILED: {exc}", file=sys.stderr)
        return 1
    if unexpected or missing:
        print(f"V2 frozen module inventory FAILED ({len(names)} ReportMaker modules)",
              file=sys.stderr)
        if unexpected:
            print("Forbidden V1 modules: " + ", ".join(sorted(unexpected)), file=sys.stderr)
        if missing:
            print("Missing essential V2/shared modules: " + ", ".join(sorted(missing)),
                  file=sys.stderr)
        return 1
    print(f"V2 frozen archive boundary PASS: {len(names)} ReportMaker modules, "
          "0 legacy modules, all required V2/shared modules present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
