"""Fail-closed evidence checks for 33 physical Windows M7 acceptance cases.

Run this on a real installed Windows PC with --init, complete each case and
record synthetic-only evidence. Passing synthetic unit tests does not count as
physical GUI acceptance. No report/customer files are needed or uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/v2/M7_ACCEPTANCE_MATRIX.json"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
SHA1 = re.compile(r"[a-f0-9]{40}\Z")


def required_cases() -> dict[str, str]:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    cases = {entry["id"]: entry["manual_acceptance"] for entry in matrix["requirements"]}
    if len(cases) != 33 or len(cases) != len(matrix["requirements"]):
        raise ValueError("Expected 33 unique physical Windows acceptance requirements")
    return cases


def init(path: Path, source: str, installer_hash: str) -> None:
    if platform.system() != "Windows":
        raise ValueError("Acceptance manifest creation must run on an actual Windows host")
    if not SHA1.fullmatch(source) or not SHA256.fullmatch(installer_hash):
        raise ValueError("Source and installer cryptographic hashes required")
    if path.exists():
        raise ValueError("Never overwrite existing physical evidence")
    data = {
        "schema": "reportmaker.physical-windows-acceptance.v1",
        "environment": "physical_windows",
        "host_os": platform.platform(),
        "machine_model": "",
        "tester": "",
        "reviewed_source_commit": source,
        "installed_preview_sha256": installer_hash,
        "reviewed_at_utc": "",
        "cases": [{"id": key, "status": "pending", "notes": "", "evidence": []}
                  for key in required_cases()],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def verify(path: Path, provenance_path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("schema") != "reportmaker.physical-windows-acceptance.v1":
        errors.append("Wrong physical Windows evidence schema")
    if data.get("environment") != "physical_windows" or not str(data.get("host_os", "")).startswith("Windows"):
        errors.append("Physical Windows environment assertion missing")
    for field in ("machine_model", "tester", "reviewed_at_utc"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"Missing physical review field: {field}")
    if not SHA1.fullmatch(str(data.get("reviewed_source_commit", ""))):
        errors.append("Invalid Git commit")
    if not SHA256.fullmatch(str(data.get("installed_preview_sha256", ""))):
        errors.append("Invalid installer digest")
    if data.get("reviewed_source_commit") != provenance.get("reviewed_branch_head_commit"):
        errors.append("Reviewed source SHA differs from packaged provenance")
    if data.get("installed_preview_sha256") != provenance.get("installer", {}).get("sha256"):
        errors.append("Installer SHA differs from packaged provenance")
    expected = required_cases()
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        cases = []
        errors.append("Cases must be an array")
    found: set[str] = set()
    for row in cases:
        if not isinstance(row, dict):
            errors.append("Invalid case object")
            continue
        id_ = row.get("id")
        if id_ not in expected or id_ in found:
            errors.append(f"Unknown or duplicate case: {id_}")
            continue
        found.add(id_)
        if row.get("status") != "passed":
            errors.append(f"{id_} is not physically accepted")
        if not isinstance(row.get("notes"), str) or len(row["notes"].strip()) < 12:
            errors.append(f"{id_} needs specific observed test notes")
        items = row.get("evidence")
        if not isinstance(items, list) or not items:
            errors.append(f"{id_} missing screenshot or test evidence")
            continue
        for evidence in items:
            if not isinstance(evidence, dict):
                errors.append(f"{id_} invalid evidence record")
                continue
            rel = evidence.get("file")
            digest = evidence.get("sha256")
            if not isinstance(rel, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f"{id_} invalid evidence file or SHA-256")
                continue
            relpath = Path(rel)
            if relpath.is_absolute() or ".." in relpath.parts:
                errors.append(f"{id_} unsafe evidence path")
                continue
            target = (path.parent / relpath).resolve()
            if not target.is_relative_to(path.parent.resolve()) or not target.is_file():
                errors.append(f"{id_} evidence missing or outside acceptance directory")
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                errors.append(f"{id_} evidence hash mismatch")
    errors.extend(f"Case {id_} has no evidence record" for id_ in expected.keys() - found)
    return {"status": "pass" if not errors else "blocked",
            "total_cases": len(expected), "provided_cases": len(found),
            "errors": errors, "warning": "Offline manifest checks cannot independently certify real hardware or human observations."}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence", type=Path)
    p.add_argument("--init", action="store_true")
    p.add_argument("--source-sha", default="")
    p.add_argument("--installer-sha256", default="")
    p.add_argument("--provenance", type=Path)
    args = p.parse_args()
    try:
        if args.init:
            init(args.evidence, args.source_sha, args.installer_sha256)
            print(f"Created pending 33-case manifest: {args.evidence}")
            return 0
        if args.provenance is None:
            p.error("--provenance is mandatory for verification")
        result = verify(args.evidence, args.provenance)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
