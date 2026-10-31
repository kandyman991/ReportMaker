"""Advisory-only Qt WebEngine/Chromium vulnerability triage and fail-closed release gate."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

POLICY = Path(__file__).resolve().parents[1] / "security/webengine_release_review.json"
CRITICAL_CVE_BASELINE = frozenset({"CVE-2026-76024", "CVE-2026-118306", "CVE-2026-118331", "CVE-2026-118348", "CVE-2026-118344"})


# A generic link or self-attested statement cannot establish that Qt has
# backported a particular Chromium fix into the shipped binary. Accept only
# audited Qt-maintained primary references, followed by human review.
QT_VENDOR_HOSTS = frozenset({
    "qt.io", "www.qt.io", "doc.qt.io", "code.qt.io",
    "bugreports.qt.io", "wiki.qt.io", "download.qt.io",
})


def is_vendor_evidence(link: object) -> bool:
    if not isinstance(link, str):
        return False
    parsed = urlsplit(link.strip())
    return (parsed.scheme == "https"
            and parsed.hostname in QT_VENDOR_HOSTS
            and not parsed.username and not parsed.password
            and bool(parsed.path) and parsed.path != "/")


def check(policy: dict, provenance: dict | None = None) -> dict:
    failures = []
    bundle = policy.get("bundle", {})
    if policy.get("schema") != "reportmaker.webengine-security-review.v1":
        failures.append("Invalid review policy schema")
    if policy.get("release_decision") != "approved":
        failures.append("Vendor WebEngine security decision is HOLD")
    if not is_vendor_evidence(policy.get("vendor_patch_backport_evidence")):
        failures.append("No verified Qt-maintained vendor patch/backport reference")
    advisories = policy.get("known_advisories", [])
    if not isinstance(advisories, list) or not advisories:
        failures.append("Missing critical Chromium advisory triage")
        advisories = []
    seen = [a.get("id") for a in advisories if isinstance(a, dict)]
    if len(seen) != len(set(seen)):
        failures.append("Duplicate Chromium CVE records")
    for missing in sorted(CRITICAL_CVE_BASELINE - set(seen)):
        failures.append(f"{missing}: critical review candidate removed")
    for advisory in advisories:
        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", str(advisory.get("id", ""))):
            failures.append("Invalid CVE identifier")
        if advisory.get("status") not in ("verified_fixed", "not_affected_with_evidence"):
            failures.append(f"{advisory.get('id')}: no verified Qt fix/non-applicability")
        if not is_vendor_evidence(advisory.get("resolution_evidence")):
            failures.append(f"{advisory.get('id')}: missing primary Qt vendor resolution evidence")
    if provenance:
        qt = provenance.get("qt_runtime", {})
        if qt.get("qt") != bundle.get("pyside6"):
            failures.append("Qt version in actual installer is not reviewed version")
        if qt.get("chromium") != bundle.get("chromium_baseline"):
            failures.append("Chromium binary baseline differs from reviewed version")
        if qt.get("chromium_security_patch") != bundle.get("qt_reported_chromium_patch"):
            failures.append("Qt chromium patch level differs from reviewed version")
    return {"status": "hold" if failures else "approved",
            "release_blockers": failures,
            "cve_count": len(advisories),
            "note": "Upstream Chrome CVEs are triage candidates, not proof of Qt WebEngine exposure."}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="Return nonzero if risk review blocks production release")
    ap.add_argument("--provenance", type=Path, help="Optional exact Windows build provenance")
    args = ap.parse_args()
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        prov = json.loads(args.provenance.read_text(encoding="utf-8")) if args.provenance else None
        result = check(policy, prov)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if args.strict and result["status"] != "approved" else 0


if __name__ == "__main__":
    raise SystemExit(main())
