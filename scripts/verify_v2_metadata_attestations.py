"""Verify REAL GitHub attestations for two V2 JSONs; never attest an installer.

The command intentionally uses online GitHub attestation verification and a
pinned repository, signer workflow, main source ref and expected commit.
Untrusted precomputed gh JSON or local bundle alone is not acceptance evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = "kandyman991/ReportMaker"
SIGNER = "kandyman991/ReportMaker/.github/workflows/v2-m7-packaging.yml"
SOURCE_REF = "refs/heads/main"
SCHEMA = "reportmaker.windows-v2-build-provenance.v1"
FILES = ("windows-v2-provenance.json", "windows-v2-sbom.cdx.json")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PROVENANCE_TYPE = "https://slsa.dev/provenance/v1"


def validate_metadata(provenance: dict, bom: dict, expected_commit: str) -> dict:
    if not SHA1.fullmatch(expected_commit):
        raise ValueError("Specify the exact trusted main build commit (40 lowercase hex)")
    if provenance.get("schema") != SCHEMA:
        raise ValueError("Unexpected Windows build provenance schema")
    for k in ("source_commit", "reviewed_branch_head_commit", "configuration_commit"):
        if provenance.get(k) != expected_commit:
            raise ValueError(f"{k} does not match the trusted main build commit")
    if provenance.get("python") != "3.14.10":
        raise ValueError("Unexpected locked Windows Python")
    if not str(provenance.get("platform", "")).startswith("Windows-"):
        raise ValueError("Windows platform provenance missing")
    installer = provenance.get("installer", {})
    if installer.get("filename") != "ReportMaker-V2-M7-Preview-Setup.exe":
        raise ValueError("Unexpected unsigned V2 preview name")
    if not SHA256.fullmatch(str(installer.get("sha256", ""))):
        raise ValueError("Installer digest is not a SHA-256")
    if not SHA256.fullmatch(str(provenance.get("lock_sha256", ""))):
        raise ValueError("Locked dependency manifest digest missing")
    wheels = provenance.get("wheels", [])
    if not isinstance(wheels, list) or len(wheels) != 22:
        raise ValueError("Expected exactly 22 reviewed locked wheel records")
    if len({str(w.get("name", "")).lower() for w in wheels}) != len(wheels):
        raise ValueError("Duplicate wheel identities")
    for w in wheels:
        if not w.get("name") or not w.get("version") or not SHA256.fullmatch(str(w.get("sha256", ""))):
            raise ValueError("Incomplete wheel lock record")
    frozen = provenance.get("frozen_payload", [])
    if not isinstance(frozen, list) or len(frozen) < 3000:
        raise ValueError("Frozen payload is incomplete")
    if len(set(f.get("path") for f in frozen)) != len(frozen):
        raise ValueError("Duplicate frozen paths")
    if any(not f.get("path") or not SHA256.fullmatch(str(f.get("sha256", ""))) for f in frozen):
        raise ValueError("Invalid frozen payload hash")
    qt = provenance.get("qt_runtime", {})
    for k in ("qt", "qt_webengine", "chromium", "chromium_security_patch"):
        if not isinstance(qt.get(k), str) or not qt[k]:
            raise ValueError(f"Qt runtime field missing: {k}")
    if bom.get("bomFormat") != "CycloneDX":
        raise ValueError("CycloneDX SBOM required")
    parts = bom.get("components", [])
    if not isinstance(parts, list) or len(parts) != len(wheels):
        raise ValueError("SBOM and Windows dependency manifest component count differ")
    listed = {(str(c.get("name", "")).lower(), c.get("version")) for c in parts}
    locked = {(str(w["name"]).lower(), w["version"]) for w in wheels}
    if listed != locked:
        raise ValueError("SBOM and wheel name/version identities do not agree")
    return {"source_commit": expected_commit, "installer_sha256": installer["sha256"],
            "wheel_count": len(wheels), "frozen_file_count": len(frozen)}


def verify_one(path: Path, expected_commit: str, *, runner=subprocess.run) -> str:
    """Run trusted gh signature verification; on invalid output always fail closed."""
    if path.name not in FILES or not path.is_file() or path.is_symlink():
        raise ValueError("Missing, symlinked or unexpected JSON artifact")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    command = ["gh", "attestation", "verify", str(path),
               "--repo", REPO,
               "--signer-workflow", SIGNER,
               "--source-ref", SOURCE_REF,
               "--source-digest", expected_commit,
               "--deny-self-hosted-runners",
               "--format", "json"]
    result = runner(command, capture_output=True, text=True, check=False, timeout=100)
    if result.returncode != 0:
        raise ValueError(f"GitHub cryptographic attestation verification FAILED for {path.name}: "
                         + (result.stderr or "")[:300])
    try:
        attestations = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("gh returned malformed verification evidence") from exc
    if not isinstance(attestations, list) or not attestations:
        raise ValueError("gh returned no verified attestation")
    for attestation in attestations:
        verified = attestation.get("verificationResult", {})
        statement = verified.get("statement", {})
        if statement.get("predicateType") != PROVENANCE_TYPE:
            continue
        subjects = statement.get("subject", [])
        if any(s.get("name") == path.name and s.get("digest", {}).get("sha256") == digest
               for s in subjects):
            return digest
    raise ValueError(f"Verified attestation subjects do not contain {path.name} with exact SHA-256")


def verify_bundle(directory: Path, expected_commit: str, *, runner=subprocess.run) -> dict:
    if not directory.is_dir():
        raise ValueError("Metadata folder not found")
    found = sorted(p.name for p in directory.iterdir())
    if found != sorted(FILES):
        raise ValueError(f"Unexpected metadata folder contents: {found}")
    provenance = json.loads((directory / FILES[0]).read_text(encoding="utf-8"))
    sbom = json.loads((directory / FILES[1]).read_text(encoding="utf-8"))
    summary = validate_metadata(provenance, sbom, expected_commit)
    summary["verified_json_subjects"] = {
        name: verify_one(directory / name, expected_commit, runner=runner)
        for name in FILES
    }
    summary["status"] = "verified_metadata_only"
    summary["limitation"] = "No signature on the installer was verified; unsigned build SHA is not signed binary SHA."
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_directory", type=Path)
    parser.add_argument("--expected-main-commit", required=True,
                        help="Trusted Git SHA from the explicitly approved main workflow dispatch")
    args = parser.parse_args()
    try:
        result = verify_bundle(args.metadata_directory, args.expected_main_commit)
    except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
