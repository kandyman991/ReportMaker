"""Compare two independent, non-release Windows V2 packaging provenance artifacts.

No network, installer execution, publishing or repository mutation. Requires two
distinct manifest files, not merely two copies of one job's summary. A PASS means
recorded binaries match byte hashes on the observed runs; it is *not* proof of
hermetic builds or a code-signing/attestation claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "reportmaker.windows-v2-build-provenance.v1"
HEX_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
HEX_SHA1 = re.compile(r"[a-f0-9]{40}\Z")
EXACT_FIELDS = (
    "schema", "source_commit", "reviewed_branch_head_commit",
    "configuration_commit", "configuration_file", "platform", "architecture",
    "python", "github_runner_image", "lock_sha256", "qt_runtime",
)


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not HEX_SHA256.fullmatch(value):
        raise ValueError(f"Invalid SHA-256 digest: {label}")
    return value


def read_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError(f"Invalid Windows V2 provenance schema: {path.name}")
    for key in EXACT_FIELDS:
        if key not in data:
            raise ValueError(f"Missing provenance field: {key}")
    for key in ("source_commit", "reviewed_branch_head_commit", "configuration_commit"):
        value = data[key]
        if not isinstance(value, str) or not HEX_SHA1.fullmatch(value):
            raise ValueError(f"Invalid Git commit: {key}")
    cfg = data["configuration_file"]
    if not isinstance(cfg, dict) or not isinstance(cfg.get("path"), str):
        raise ValueError("Invalid configuration file record")
    _hash(cfg.get("sha256"), "configuration_file")
    _hash(data["lock_sha256"], "lock")
    if not isinstance(data.get("installer"), dict):
        raise ValueError("Missing installer metadata")
    if not isinstance(data["installer"].get("filename"), str):
        raise ValueError("Invalid installer filename")
    _hash(data["installer"].get("sha256"), "installer")
    if not isinstance(data.get("wheels"), list) or not data["wheels"]:
        raise ValueError("Missing wheel metadata")
    if not isinstance(data.get("frozen_payload"), list) or not data["frozen_payload"]:
        raise ValueError("Missing frozen payload")
    for list_name, field in (("wheels", "name"), ("frozen_payload", "path")):
        names = set()
        for entry in data[list_name]:
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid {list_name} entry")
            identity = entry.get(field)
            if not isinstance(identity, str) or not identity or identity in names:
                raise ValueError(f"Missing or duplicate {list_name} identity")
            names.add(identity)
            _hash(entry.get("sha256"), f"{list_name}:{identity}")
            if list_name == "wheels":
                if not isinstance(entry.get("version"), str) or not isinstance(entry.get("wheel"), str):
                    raise ValueError(f"Incomplete wheel metadata: {identity}")
    return data


def compare(left: dict, right: dict) -> dict:
    differences = []
    # Forward-compatible: new compiler/toolchain metadata must not be silently
    # ignored. The generation timestamp is the *only* intentionally volatile
    # top-level field excluded from reproducibility comparisons.
    ignored = {"generated_utc", "installer", "wheels", "frozen_payload"}
    for field in sorted((left.keys() | right.keys()) - ignored):
        if left.get(field) != right.get(field):
            differences.append({"kind": "environment_or_source", "field": field})
    if left["installer"] != right["installer"]:
        differences.append({"kind": "installer", "field": "installer"})
    for category, key in (("wheels", "name"), ("frozen_payload", "path")):
        a = {x[key]: x for x in left[category]}
        b = {x[key]: x for x in right[category]}
        added = sorted(b.keys() - a.keys())
        removed = sorted(a.keys() - b.keys())
        modified = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
        if added or removed or modified:
            differences.append({
                "kind": category,
                "added_count": len(added),
                "removed_count": len(removed),
                "changed_count": len(modified),
                "sample": (added + removed + modified)[:20],
            })
    matching = not differences
    return {
        "status": "matching_byte_hashes" if matching else "differences_found",
        "full_installer_sha256_matches": left["installer"]["sha256"] == right["installer"]["sha256"],
        "frozen_payload_sha256_matches": not any(x["kind"] == "frozen_payload" for x in differences),
        "wheel_sha256_matches": not any(x["kind"] == "wheels" for x in differences),
        "first_payload_file_count": len(left["frozen_payload"]),
        "second_payload_file_count": len(right["frozen_payload"]),
        "differences": differences,
        "limitation": (
            "Equal recorded hashes on two separate runs are evidence of byte-identical "
            "observed artifacts, not proof of hermetic inputs, independent builder "
            "trust, valid signatures or a generally reproducible release."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path, help="First independent build's provenance JSON")
    parser.add_argument("second", type=Path, help="Second independent build's provenance JSON")
    parser.add_argument("--json-out", type=Path, help="Optional local comparison report")
    args = parser.parse_args()
    if args.first.resolve() == args.second.resolve():
        parser.error("Two distinct provenance files from independent build runs are required")
    try:
        first = read_manifest(args.first)
        second = read_manifest(args.second)
        result = compare(first, second)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID comparison input: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "matching_byte_hashes" else 1


if __name__ == "__main__":
    raise SystemExit(main())
