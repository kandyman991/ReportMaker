"""Auditable, read-only provenance for the Windows V2 frozen installer.

Run only after hash-verified wheel installation and completed installer smoke.
No network calls, user-data traversal, GitHub mutation, or release publication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import uuid
from urllib.parse import unquote, urlsplit

PIN = re.compile(r"^([A-Za-z][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)$")
HASH = re.compile(r"^--hash=sha256:([a-f0-9]{64})$")
SHA = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = {
    "pyside6", "pyside6-webengine", "pyside6-essentials", "shiboken6",
    "pillow", "pillow-heif", "pyinstaller", "reportlab", "python-docx",
    "pypdf", "setuptools", "wheel",
}


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> dict[str, dict]:
    """Reject loose constraints, direct URLs, un-hashed or duplicate packages."""
    items: dict[str, dict] = {}
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().rstrip(chr(92)).strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match:
            name = normalized(match.group(1))
            if name in items:
                raise ValueError(f"Duplicated lock distribution: {name}")
            items[name] = {"name": name, "version": match.group(2), "hashes": []}
            current = name
            continue
        match = HASH.fullmatch(line)
        if match and current is not None:
            items[current]["hashes"].append(match.group(1))
            continue
        raise ValueError(f"Unpinned or unrecognized lock line: {line[:80]}")
    if not REQUIRED <= items.keys():
        raise ValueError("Missing essential Windows build packages: " +
                         ", ".join(sorted(REQUIRED - items.keys())))
    for item in items.values():
        if not item["hashes"]:
            raise ValueError(f"Missing artifact hashes: {item['name']}")
        item["hashes"] = sorted(set(item["hashes"]))
    return items


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def installed_versions() -> dict[str, str]:
    return {normalized(d.metadata["Name"]): d.version
            for d in metadata.distributions() if d.metadata.get("Name")}


def verify_installed(lock: dict[str, dict], actual: dict[str, str]) -> None:
    for name, entry in lock.items():
        if actual.get(name) != entry["version"]:
            raise ValueError(
                f"Installed version drift: {name}: expected {entry['version']}, "
                f"found {actual.get(name, 'MISSING')}"
            )
    # pip bootstraps the virtualenv and the local editable app is the source.
    # Unreviewed extras could enter PyInstaller's dependency traversal.
    extras = set(actual) - set(lock) - {"pip", "reportmaker"}
    if extras:
        raise ValueError("Unexpected installed package(s): " + ", ".join(sorted(extras)))


def verified_wheels(report_path: Path, lock: dict[str, dict]) -> list[dict]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("install"), list):
        raise ValueError("Invalid pip --report JSON")
    wheels = []
    seen = set()
    for item in data["install"]:
        info = item.get("metadata", {})
        name = normalized(str(info.get("name", "")))
        version = str(info.get("version", ""))
        if name not in lock or version != lock[name]["version"] or name in seen:
            raise ValueError(f"Unknown, drifting or duplicate wheel: {name}")
        seen.add(name)
        download = item.get("download_info", {})
        digest = (download.get("archive_info") or {}).get("hashes", {}).get("sha256")
        url = download.get("url", "")
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        if (digest not in lock[name]["hashes"] or not filename.endswith(".whl")
                or "/" in filename or "\\\\" in filename):
            raise ValueError(f"Unverified wheel archive in pip report: {name}")
        # Keep only filenames and SHA hashes; no private indexes or tokens.
        wheels.append({"name": name, "version": version,
                       "wheel": filename, "sha256": digest})
    # A clean build environment must not silently reuse pre-existing wheels.
    if seen != set(lock):
        raise ValueError("Incomplete wheel download report: " +
                         ", ".join(sorted(set(lock) - seen)))
    return sorted(wheels, key=lambda item: item["name"])


def runtime_versions() -> dict:
    from PySide6.QtCore import qVersion
    from PySide6.QtWebEngineCore import (
        qWebEngineChromiumSecurityPatchVersion,
        qWebEngineChromiumVersion,
        qWebEngineVersion,
    )
    return {
        "qt": qVersion(),
        "qt_webengine": qWebEngineVersion(),
        "chromium": qWebEngineChromiumVersion(),
        "chromium_security_patch": qWebEngineChromiumSecurityPatchVersion(),
        "pyside6": metadata.version("PySide6"),
        "pyside6_webengine_wheel": metadata.version("PySide6-WebEngine"),
    }


def generate(lock_path: Path, pip_report: Path, installer: Path,
             source_sha: str, config_sha: str, output: Path,
             frozen_dir: Path | None = None) -> dict:
    if not SHA.fullmatch(source_sha) or not SHA.fullmatch(config_sha):
        raise ValueError("Both source/config SHA must be full Git commit IDs")
    lock = parse_lock(lock_path)
    versions = installed_versions()
    verify_installed(lock, versions)
    wheels = verified_wheels(pip_report, lock)
    if not installer.is_file():
        raise ValueError("Installer must exist before provenance is generated")
    image = os.environ.get("ImageOS", "")
    image_version = os.environ.get("ImageVersion", "")
    payload = []
    if frozen_dir is not None:
        if not frozen_dir.is_dir():
            raise ValueError("Frozen payload directory is missing")
        for path in sorted(frozen_dir.rglob("*")):
            if path.is_symlink():
                raise ValueError("Frozen payload contains symlink")
            if path.is_file():
                relative = path.relative_to(frozen_dir).as_posix()
                payload.append({"path": relative, "sha256": sha256_file(path)})
        if not payload:
            raise ValueError("Empty frozen application directory")
    now = datetime.now(timezone.utc).isoformat()
    details = {
        "schema": "reportmaker.windows-v2-build-provenance.v1",
        "generated_utc": now,
        "source_commit": source_sha,
        "configuration_commit": config_sha,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "github_runner_image": {"name": image, "version": image_version},
        "lock_sha256": sha256_file(lock_path),
        "installer": {"filename": installer.name, "sha256": sha256_file(installer)},
        "qt_runtime": runtime_versions(),
        "wheels": wheels,
        "frozen_payload": payload,
    }
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "serialNumber": "urn:uuid:" + str(uuid.uuid4()),
        "metadata": {"timestamp": now,
                     "component": {"type": "application", "name": "reportmaker",
                                   "version": versions.get("reportmaker", "0.0.1")}},
        "components": [
            {"type": "library", "name": entry["name"], "version": entry["version"],
             "purl": f"pkg:pypi/{entry['name']}@{entry['version']}"}
            for entry in sorted(lock.values(), key=lambda x: x["name"])
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "windows-v2-provenance.json").write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "windows-v2-sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--pip-report", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--frozen-dir", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--config-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    packages = parse_lock(args.lock)
    if args.verify_only:
        print(f"Validated {len(packages)} hash-locked Windows wheel distributions.")
        return
    if not all((args.pip_report, args.installer, args.source_sha,
                args.config_sha, args.output)):
        parser.error("Full provenance requires pip report, installer, source/config SHA and output")
    result = generate(args.lock, args.pip_report, args.installer,
                      args.source_sha, args.config_sha, args.output, args.frozen_dir)
    print(f"Installer SHA-256: {result['installer']['sha256']}")
    print(f"Lock SHA-256: {result['lock_sha256']}")
    print(f"Chromium: {result['qt_runtime']['chromium']} "
          f"(security patch {result['qt_runtime']['chromium_security_patch']})")


if __name__ == "__main__":
    main()
