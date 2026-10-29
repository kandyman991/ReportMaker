"""M7.3 local-only physical Windows acceptance ledger.

No test is automatically accepted. The repository's canonical 33-case matrix is
never mutated. Evidence and machine observations remain outside the Git tree.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import sys

MATRIX = Path(__file__).resolve().parents[1] / "docs/v2/M7_ACCEPTANCE_MATRIX.json"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
DOSSIER_NAME = "m73-native-local.json"
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
GIT_SHA = re.compile(r"[a-fA-F0-9]{40}\Z")
CASE_ID = re.compile(r"BE-(?:L|E|S|U|I)[0-9]{2}\Z")
ISSUE_URL = re.compile(r"https://github[.]com/kandyman991/ReportMaker/issues/[1-9][0-9]*\Z")
STATUS = {"pending", "pass", "fail", "blocked"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _matrix() -> dict:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = matrix["requirements"]
    ids = [item["id"] for item in rows]
    if (len(ids) != 33 or len(set(ids)) != 33
            or any(CASE_ID.fullmatch(i) is None for i in ids)
            or any(item["status"] != "pending_native_acceptance"
                   or item["evidence_ref"] is not None for item in rows)):
        raise ValueError("Canonical native matrix was unexpectedly modified")
    return matrix


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _outside_repo(folder: Path) -> Path:
    folder = folder.resolve()
    if folder == SOURCE_ROOT or SOURCE_ROOT in folder.parents:
        raise ValueError("Private native evidence must be outside the repository")
    return folder


def _dossier_path(folder: Path) -> Path:
    return _outside_repo(folder) / DOSSIER_NAME


def _read(folder: Path) -> dict:
    path = _dossier_path(folder)
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = set(x["id"] for x in _matrix()["requirements"])
    if (data.get("schema_version") != 1 or data.get("platform") != "Windows-x64"
            or data.get("case_count") != 33 or set(data.get("cases", {})) != expected
            or data.get("matrix_sha256") != _digest(MATRIX)
            or not GIT_SHA.fullmatch(data.get("source_sha", ""))
            or not all(SHA256.fullmatch(data.get(k, "")) for k in
                       ("installer_sha256", "installed_exe_sha256"))):
        raise ValueError("Invalid or mismatched native acceptance dossier")
    for record in data["cases"].values():
        if record.get("result") not in STATUS:
            raise ValueError("Invalid acceptance result")
        if record.get("review_status") not in ("pending", "accepted", "rejected"):
            raise ValueError("Invalid native review state")
        if record["review_status"] == "accepted":
            if (record["result"] != "pass" or not record.get("evidence")
                or not record.get("reviewer_alias")
                or record.get("reviewer_alias") == data.get("tester_alias")):
                raise ValueError("Unreviewed case cannot be accepted")
            proof = record["evidence"]
            if (not isinstance(proof, dict) or not isinstance(proof.get("ref"), str)
                or not proof["ref"].startswith("evidence/")
                or _evidence(folder, proof["ref"][len("evidence/"):]) != proof):
                raise ValueError("Accepted screenshot evidence was modified")
    return data


def _write(folder: Path, data: dict) -> None:
    path = _dossier_path(folder)
    if path.is_symlink():
        raise ValueError("Refusing to write via symlink")
    tmp = path.with_suffix(".tmp")
    if tmp.is_symlink():
        raise ValueError("Refusing symlinked temporary dossier")
    try:
        with tmp.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _native_platform() -> tuple[str, str]:
    if sys.platform != "win32" or platform.machine().lower() not in (
        "amd64", "x86_64"
    ):
        raise ValueError("Physical x64 Windows required; hosted/Linux checks cannot qualify")
    caption, version, _, _ = platform.win32_ver()
    if not version:
        raise ValueError("Cannot determine Windows version")
    return caption, version


def prepare(args) -> None:
    edition, build = _native_platform()
    folder = _outside_repo(Path(args.output))
    if folder.exists() and (folder / DOSSIER_NAME).exists():
        raise ValueError("A native dossier already exists; never reset recorded evidence")
    if not GIT_SHA.fullmatch(args.source_sha):
        raise ValueError("Source SHA must be a complete 40-character commit SHA")
    if not args.display_scale.strip() or len(args.display_scale) > 80:
        raise ValueError("Record observed display scale(s), e.g. 100%, 150%")
    if not args.tester_alias.strip() or len(args.tester_alias) > 80:
        raise ValueError("Use a short pseudonymous tester alias")
    setup, exe = Path(args.installer), Path(args.installed_exe)
    if setup.name != "ReportMaker-V2-M7-Preview-Setup.exe" or exe.name != "ReportMakerV2.exe":
        raise ValueError("Use the isolated V2 preview setup and installed executable")
    if not setup.is_file() or not exe.is_file() or setup.is_symlink() or exe.is_symlink():
        raise ValueError("Installer and physically installed V2 executable are required")
    build_path = Path(args.build_manifest)
    if not build_path.is_file() or build_path.is_symlink():
        raise ValueError("A verified local V2 build manifest is required")
    build = json.loads(build_path.read_text(encoding="utf-8-sig"))
    if (build.get("source_sha") != args.source_sha.lower()
        or build.get("installer_sha256") != _digest(setup)
        or build.get("installed_exe_sha256") != _digest(exe)):
        raise ValueError("Source, installer and installed executable do not match the local build")
    matrix = _matrix()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "evidence").mkdir(exist_ok=True)
    data = {
        "schema_version": 1, "platform": "Windows-x64", "windows_edition": edition,
        "windows_build": build, "display_scale": args.display_scale.strip(),
        "tested_at_utc": _now(), "source_sha": args.source_sha.lower(),
        "installer_sha256": _digest(setup), "installed_exe_sha256": _digest(exe),
        "matrix_sha256": _digest(MATRIX), "case_count": 33,
        "tester_alias": args.tester_alias.strip(),
        "cases": {
            row["id"]: {
                "result": "pending", "steps": row["manual_acceptance"],
                "expected": row["manual_acceptance"], "observed": "",
                "evidence": None, "issue": None, "tested_at_utc": None,
                "review_status": "pending", "reviewer_alias": None,
                "reviewed_at_utc": None, "review_notes": "",
            }
            for row in matrix["requirements"]
        },
    }
    _write(folder, data)
    print("Local private dossier created (0/33 accepted):", folder)


def _evidence(folder: Path, name: str) -> dict:
    if not name or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", name) is None:
        raise ValueError("Evidence must be a sanitized filename inside dossier/evidence")
    if Path(name).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("Evidence must be a redacted PNG/JPEG screenshot")
    base = _outside_repo(folder) / "evidence"
    if base.is_symlink():
        raise ValueError("Evidence folder cannot be a symlink")
    path = base / name
    if path.is_symlink() or not path.is_file() or not 8 <= path.stat().st_size <= 20 * 1024 * 1024:
        raise ValueError("Missing, symlinked or oversized private screenshot")
    with path.open("rb") as stream:
        signature = stream.read(8)
    if (path.suffix.lower() == ".png" and signature != b"\x89PNG\r\n\x1a\n") or (
        path.suffix.lower() in (".jpg", ".jpeg") and not signature.startswith(b"\xff\xd8\xff")
    ):
        raise ValueError("Screenshot must have PNG/JPEG signature")
    return {"ref": "evidence/" + name, "sha256": _digest(path)}


def record(args) -> None:
    folder = Path(args.dossier)
    data = _read(folder)
    if args.case not in data["cases"]:
        raise ValueError("Unknown RM-BE acceptance case")
    if args.result not in ("pass", "fail", "blocked") or not args.observed.strip():
        raise ValueError("Record pass/fail/blocked and an actual observed result")
    if not args.steps.strip():
        raise ValueError("Executed synthetic test steps are required")
    if args.result == "pass" and not args.evidence:
        raise ValueError("Native pass requires a manually redacted screenshot")
    if args.result != "pass" and not args.issue:
        raise ValueError("Failed or blocked tests require a related tracking issue")
    if args.issue and ISSUE_URL.fullmatch(args.issue) is None:
        raise ValueError("Only a ReportMaker GitHub issue URL may identify a blocker")
    entry = data["cases"][args.case]
    entry.update(
        result=args.result, steps=args.steps.strip(),
        observed=args.observed.strip(), issue=args.issue,
        evidence=_evidence(folder, args.evidence) if args.evidence else None,
        tested_at_utc=_now(), review_status="pending",
        reviewer_alias=None, reviewed_at_utc=None, review_notes="",
    )
    _write(folder, data)
    print(args.case, "recorded; independent native review still pending")


def review(args) -> None:
    folder = Path(args.dossier)
    data = _read(folder)
    if args.case not in data["cases"]:
        raise ValueError("Unknown RM-BE acceptance case")
    entry = data["cases"][args.case]
    if entry["result"] != "pass" or not entry["evidence"]:
        raise ValueError("Only a recorded native pass with evidence can be reviewed")
    reviewer = args.reviewer_alias.strip()
    if not reviewer or reviewer == data["tester_alias"]:
        raise ValueError("Independent reviewer alias must differ from tester")
    if not args.notes.strip():
        raise ValueError("Independent review notes are required")
    if args.decision == "accept":
        info = entry["evidence"]
        if _evidence(folder, Path(info["ref"]).name) != info:
            raise ValueError("Screenshot changed since it was recorded")
    entry["review_status"] = "accepted" if args.decision == "accept" else "rejected"
    entry["reviewer_alias"] = reviewer
    entry["reviewed_at_utc"] = _now()
    entry["review_notes"] = args.notes.strip()
    _write(folder, data)
    print(args.case, entry["review_status"], "(local evidence only; repository register unchanged)")


def summary(args) -> None:
    data = _read(Path(args.dossier))
    result = {
        key: data[key] for key in (
            "schema_version", "platform", "windows_edition", "windows_build",
            "display_scale", "tested_at_utc", "source_sha",
            "installer_sha256", "installed_exe_sha256", "matrix_sha256",
            "case_count",
        )
    }
    result["cases"] = data["cases"]
    result["accepted_count"] = sum(
        row["review_status"] == "accepted" for row in data["cases"].values()
    )
    result["complete"] = result["accepted_count"] == 33
    # Read-only stdout: no raw screenshot, credentials, host/user name,
    # local absolute paths or automatic GitHub uploads.
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


def checklist(args) -> None:
    matrix = _matrix()
    records = _read(Path(args.dossier))["cases"] if args.dossier else {}
    for row in matrix["requirements"]:
        state = records.get(row["id"], {}).get("review_status", "pending")
        result = records.get(row["id"], {}).get("result", "pending")
        print(f'{row["id"]}: {result} / review {state} — {row["manual_acceptance"]}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("prepare", help="Only on a real installed Windows x64 PC")
    for name in ("installer", "installed-exe", "build-manifest", "source-sha",
                 "display-scale", "tester-alias", "output"):
        init.add_argument("--" + name, required=True)
    init.set_defaults(func=prepare)
    rec = sub.add_parser("record", help="Record a manually executed case")
    for name in ("dossier", "case", "result", "steps", "observed"):
        rec.add_argument("--" + name, required=True)
    rec.add_argument("--evidence", help="Sanitized screenshot basename in evidence/")
    rec.add_argument("--issue", help="GitHub tracking issue for failures/blocks")
    rec.set_defaults(func=record)
    rev = sub.add_parser("review", help="Separate human reviewer; no automatic passes")
    for name in ("dossier", "case", "reviewer-alias", "notes"):
        rev.add_argument("--" + name, required=True)
    rev.add_argument("--decision", required=True, choices=("accept", "reject"))
    rev.set_defaults(func=review)
    listing = sub.add_parser("list", help="Display the 33 manual scenarios and local review states")
    listing.add_argument("--dossier", help="Optional local dossier folder")
    listing.set_defaults(func=checklist)
    summ = sub.add_parser("summary", help="Print text-only metadata for manual redaction")
    summ.add_argument("--dossier", required=True)
    summ.set_defaults(func=summary)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Acceptance gate rejected: {exc}\n")


if __name__ == "__main__":
    main()
