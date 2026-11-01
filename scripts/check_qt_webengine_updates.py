"""Advisory-only checks for *both* independently released PySide6 and WebEngine wheels.

A newer PyPI version is a review signal, not proof of a fixed Chromium CVE.
No package install, lock refresh, branch write or publishing is performed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_LOCK = PROJECT_ROOT / "packaging/windows/requirements-win314-x64.lock"


def latest_release(package: str) -> str:
    """Only query fixed, known PyPI package names over TLS; cap response size."""
    if package not in ("PySide6", "PySide6-WebEngine"):
        raise ValueError("Unrecognized package query")
    with urlopen(f"https://pypi.org/pypi/{package}/json", timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Oversized PyPI metadata response")
    value = json.loads(raw)["info"]["version"]
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid PyPI version")
    return value


def current_versions(pyproject: Path, lock: Path) -> tuple[str, str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    pins = data["project"]["optional-dependencies"]["desktop"]
    pyside = [item.split("==", 1)[1] for item in pins
              if isinstance(item, str) and item.lower().startswith("pyside6==")]
    if len(pyside) != 1:
        raise ValueError("Desktop PySide6 pin missing or ambiguous")
    body = lock.read_text(encoding="utf-8")
    def locked(package: str) -> str:
        matches = re.findall(rf"(?im)^{re.escape(package)}==([^\s\\]+)", body)
        if len(matches) != 1:
            raise ValueError(f"{package} lock pin missing or ambiguous")
        return matches[0]
    if locked("pyside6") != pyside[0]:
        raise ValueError("Windows lock PySide6 differs from desktop pin")
    return pyside[0], locked("pyside6-webengine")


def compare_versions(pyproject: Path, lock: Path,
                     latest_pyside: str, latest_webengine: str) -> tuple[str, bool]:
    from packaging.version import Version
    pyside, webengine = current_versions(pyproject, lock)
    outdated = (Version(latest_pyside) > Version(pyside)
                or Version(latest_webengine) > Version(webengine))
    return (f"Windows locked PySide6 {pyside} (PyPI latest {latest_pyside}); "
            f"locked PySide6-WebEngine {webengine} (PyPI latest {latest_webengine}). "
            "Independently investigate Qt WebEngine/Chromium advisories, backports, "
            "and the exact running Windows wheel; these version checks do not clear CVEs.",
            outdated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=PROJECT_ROOT / "pyproject.toml")
    parser.add_argument("--lock", type=Path, default=WINDOWS_LOCK)
    parser.add_argument("--latest-pyside6", help="Test-only PyPI response override")
    parser.add_argument("--latest-webengine", help="Test-only PyPI response override")
    args = parser.parse_args()
    try:
        latest_pyside = args.latest_pyside6 or latest_release("PySide6")
        latest_engine = args.latest_webengine or latest_release("PySide6-WebEngine")
        message, outdated = compare_versions(
            args.pyproject, args.lock, latest_pyside, latest_engine)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print(f"Qt update watcher FAILED (not a clearance): {exc}", file=sys.stderr)
        return 2
    print(message)
    if outdated:
        print("::warning title=Qt/PySide6 WebEngine security update review due::" + message)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("### Independent Qt/WebEngine wheel update check\n\n" + message +
                         "\n\nOfficial Qt advisories: https://wiki.qt.io/Qt_Security_Advisories\n")
    return 1 if outdated else 0


if __name__ == "__main__":
    raise SystemExit(main())
