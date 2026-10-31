"""Weekly PySide6/Qt WebEngine version signal; not a CVE clearance.

Official Qt security advisories still require human review:
https://wiki.qt.io/Qt_Security_Advisories
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.request import urlopen


def latest_pyside6() -> str:
    # A bounded, authenticated-by-TLS metadata query; no system commands or tokens.
    with urlopen("https://pypi.org/pypi/PySide6/json", timeout=15) as result:
        raw = result.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Oversized PyPI metadata response")
    data = json.loads(raw)
    return str(data["info"]["version"])


def monitored_versions(pyproject: Path, latest: str) -> tuple[str, bool]:
    import tomllib
    from packaging.version import Version
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    pins = data["project"]["optional-dependencies"]["desktop"]
    actual = [p.split("==", 1)[1] for p in pins if p.lower().startswith("pyside6==")]
    if len(actual) != 1:
        raise ValueError("Desktop Qt/PySide6 pin missing or ambiguous")
    return actual[0], Version(latest) > Version(actual[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--latest", help="Test-only override: no network")
    args = parser.parse_args()
    latest = args.latest or latest_pyside6()
    current, outdated = monitored_versions(args.pyproject, latest)
    message = (
        f"Pinned PySide6 {current}; latest available PySide6 {latest}. "
        "Review Qt WebEngine/Chromium security advisories, Qt patch notes, "
        "and rebuilt Windows payload before approving a release."
    )
    print(message)
    if outdated:
        print("::warning title=Qt WebEngine security update review due::" + message)
    summary = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("### Qt/PySide6 security review\n\n" + message +
                         "\n\nOfficial Qt advisories: https://wiki.qt.io/Qt_Security_Advisories\n")
    # A new version signals a mandatory review, not automatic upgrades or publishing.
    if outdated:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
