"""Advisory-only Qt WebEngine/Chromium CVE triage; strict release gate fails closed.

An upstream Chrome CVE is a candidate, not proof of exposure in the Qt wheel.
A Qt-maintained link is necessary, but never a substitute for independent review.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

POLICY = Path(__file__).resolve().parents[1] / "security/webengine_release_review.json"
CRITICAL_CVE_BASELINE = frozenset({
    "CVE-2026-76024", "CVE-2026-118306", "CVE-2026-118331",
    "CVE-2026-118348", "CVE-2026-118344",
})
QT_VENDOR_HOSTS = frozenset({
    "qt.io", "www.qt.io", "doc.qt.io", "code.qt.io",
    "bugreports.qt.io", "wiki.qt.io", "download.qt.io",
})


def is_vendor_evidence(link: object) -> bool:
    if not isinstance(link, str):
        return False
    parsed = urlsplit(link.strip())
    return (parsed.scheme == "https" and parsed.hostname in QT_VENDOR_HOSTS
            and not parsed.username and not parsed.password
            and bool(parsed.path) and parsed.path != "/")


def check(policy: dict, provenance: dict | None = None, *,
          require_provenance: bool = False) -> dict:
    failures = []
    if not isinstance(policy, dict):
        raise ValueError("Review policy must be a JSON object")
    bundle = policy.get("bundle")
    if not isinstance(bundle, dict):
        bundle = {}
        failures.append("Missing reviewed Qt/WebEngine version bundle")
    if policy.get("schema") != "reportmaker.webengine-security-review.v1":
        failures.append("Invalid review policy schema")
    if policy.get("release_decision") != "approved":
        failures.append("Vendor WebEngine security decision is HOLD")
    if not is_vendor_evidence(policy.get("vendor_patch_backport_evidence")):
        failures.append("No verified Qt-maintained vendor patch/backport reference")
    for required in ("pyside6", "qt_webengine", "chromium_baseline",
                     "qt_reported_chromium_patch"):
        if not isinstance(bundle.get(required), str) or not bundle[required].strip():
            failures.append(f"Missing reviewed runtime version: {required}")
    advisories = policy.get("known_advisories")
    if not isinstance(advisories, list) or not advisories:
        failures.append("Missing critical Chromium advisory triage")
        advisories = []
    seen = []
    for item in advisories:
        if not isinstance(item, dict):
            failures.append("Malformed Chromium CVE review record")
            continue
        cve = item.get("id")
        if not isinstance(cve, str) or not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve):
            failures.append("Invalid CVE identifier")
            continue
        if cve in seen:
            failures.append(f"{cve}: duplicate Chromium CVE record")
        seen.append(cve)
        if item.get("status") not in ("verified_fixed", "not_affected_with_evidence"):
            failures.append(f"{cve}: no verified Qt fix/non-applicability")
        if not is_vendor_evidence(item.get("resolution_evidence")):
            failures.append(f"{cve}: missing primary Qt vendor resolution evidence")
    for cve in sorted(CRITICAL_CVE_BASELINE - set(seen)):
        failures.append(f"{cve}: critical review candidate removed")
    if provenance is None:
        if require_provenance:
            failures.append("No exact Windows installed-build Qt runtime provenance")
    elif not isinstance(provenance, dict) or not isinstance(provenance.get("qt_runtime"), dict):
        failures.append("Invalid Windows installed-build Qt runtime provenance")
    else:
        qt = provenance["qt_runtime"]
        for observed, reviewed in (
            ("qt", "pyside6"),
            ("qt_webengine", "qt_webengine"),
            ("chromium", "chromium_baseline"),
            ("chromium_security_patch", "qt_reported_chromium_patch"),
        ):
            if not isinstance(qt.get(observed), str) or not qt[observed]:
                failures.append(f"Missing actual Windows Qt runtime: {observed}")
            elif qt[observed] != bundle.get(reviewed):
                failures.append(f"{observed}: actual Windows Qt runtime differs from reviewed version")
    return {
        "status": "hold" if failures else "approved",
        "release_blockers": failures,
        "cve_count": len(advisories),
        "note": "Chrome CVEs are triage candidates, not proof of Qt exposure; vendor links require manual verification.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="Require exact Windows provenance; nonzero on release HOLD")
    ap.add_argument("--provenance", type=Path, help="Exact Windows build provenance JSON")
    args = ap.parse_args()
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        prov = json.loads(args.provenance.read_text(encoding="utf-8")) if args.provenance else None
        result = check(policy, prov, require_provenance=args.strict)
    except (OSError, ValueError, TypeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if args.strict and result["status"] != "approved" else 0


if __name__ == "__main__":
    raise SystemExit(main())
