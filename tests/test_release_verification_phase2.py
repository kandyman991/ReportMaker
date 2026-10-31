"""Fail-closed contract tests for release readiness; no live attestations are forged."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


attest = load("verify_v2_metadata_attestations", "scripts/verify_v2_metadata_attestations.py")
risk = load("check_webengine_release_risk_129", "scripts/check_webengine_release_risk.py")
checklist = load("physical_windows_acceptance_checklist", "scripts/physical_windows_acceptance_checklist.py")
SHA = "a" * 40


def metadata() -> tuple[dict, dict]:
    wheels = [{"name": f"fake-wheel-{n:02}", "version": "1.0", "wheel": f"fake-wheel-{n:02}-1.0.whl",
               "sha256": "b" * 64} for n in range(22)]
    frozen = [{"path": f"file-{n:04}.dll", "sha256": "c" * 64} for n in range(3000)]
    return ({
        "schema": attest.SCHEMA,
        "source_commit": SHA,
        "reviewed_branch_head_commit": SHA,
        "configuration_commit": SHA,
        "platform": "Windows-2022",
        "python": "3.14.10",
        "installer": {"filename": "ReportMaker-V2-M7-Preview-Setup.exe", "sha256": "d" * 64},
        "lock_sha256": "e" * 64,
        "qt_runtime": {"qt": "6.12.0", "qt_webengine": "6.140.0",
                       "chromium": "140.0.7339.225", "chromium_security_patch": "152.0.7977.83"},
        "wheels": wheels,
        "frozen_payload": frozen,
    }, {"bomFormat": "CycloneDX",
        "components": [{"name": x["name"], "version": x["version"]} for x in wheels]})


class AttestationVerificationTests(unittest.TestCase):
    def test_build_provenance_and_sbom_matching(self):
        provenance, sbom = metadata()
        self.assertEqual(attest.validate_metadata(provenance, sbom, SHA)["wheel_count"], 22)
        sbom["components"][0]["version"] = "9.9"
        with self.assertRaisesRegex(ValueError, "name/version"):
            attest.validate_metadata(provenance, sbom, SHA)

    def test_fails_closed_on_unsigned_different_source_or_incomplete_payload(self):
        provenance, sbom = metadata()
        for field in ("source_commit", "configuration_commit", "reviewed_branch_head_commit"):
            copy = dict(provenance, **{field: "f" * 40})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                attest.validate_metadata(copy, sbom, SHA)
        copy = dict(provenance, frozen_payload=provenance["frozen_payload"][:100])
        with self.assertRaisesRegex(ValueError, "Frozen payload"):
            attest.validate_metadata(copy, sbom, SHA)

    def test_trusted_gh_signature_and_source_identity_required(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "windows-v2-provenance.json"
            p.write_text('{"synthetic":"not a real attestation"}')
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            calls = []

            def fake_gh(command, **kwargs):
                calls.append(command)
                signed = [{"verificationResult": {
                    "statement": {
                        "predicateType": attest.PROVENANCE_TYPE,
                        "subject": [{"name": p.name, "digest": {"sha256": digest}}],
                    }
                }}]
                return SimpleNamespace(returncode=0, stdout=json.dumps(signed), stderr="")

            self.assertEqual(attest.verify_one(p, SHA, runner=fake_gh), digest)
            command = calls[0]
            for required in ("--signer-workflow", attest.SIGNER, "--source-ref",
                             "refs/heads/main", "--source-digest", SHA,
                             "--repo", "kandyman991/ReportMaker",
                             "--deny-self-hosted-runners"):
                self.assertIn(required, command)
            self.assertNotIn("--bundle", command)
            def bad_gh(*args, **kwargs):
                return SimpleNamespace(returncode=1, stdout="", stderr="no signed attestation")
            with self.assertRaisesRegex(ValueError, "FAILED"):
                attest.verify_one(p, SHA, runner=bad_gh)
            def tampered_gh(command, **kwargs):
                return SimpleNamespace(returncode=0,
                                       stdout=json.dumps([{"verificationResult": {
                                           "statement": {"predicateType": attest.PROVENANCE_TYPE,
                                                         "subject": [{"name": p.name, "digest": {"sha256": "0" * 64}}]}
                                       }}]), stderr="")
            with self.assertRaisesRegex(ValueError, "exact SHA-256"):
                attest.verify_one(p, SHA, runner=tampered_gh)

    def test_reject_unexpected_files_before_contacting_gh(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p, s = metadata()
            (root / attest.FILES[0]).write_text(json.dumps(p))
            (root / attest.FILES[1]).write_text(json.dumps(s))
            (root / "ReportMaker-V2-M7-Preview-Setup.exe").write_bytes(b"unapproved")
            with self.assertRaisesRegex(ValueError, "Unexpected metadata folder"):
                attest.verify_bundle(root, SHA, runner=lambda *args, **kwargs: self.fail("gh called"))


class PhysicalAndSignerChecks(unittest.TestCase):
    def test_checklist_is_generated_from_all_exact_canonical_cases_without_claiming_pass(self):
        content = checklist.render()
        import json
        matrix = json.loads((ROOT / "docs/v2/M7_ACCEPTANCE_MATRIX.json").read_text())
        for entry in matrix["requirements"]:
            self.assertIn("## " + entry["id"] + " — " + entry["manual_acceptance"], content)
        self.assertEqual(content.count("## BE-"), 33)
        self.assertIn("PENDING", content)
        self.assertNotIn("accepted: true", content)

    def test_windows_signature_verifier_is_read_only_and_checks_real_trust(self):
        s = (ROOT / "scripts/verify_windows_installer_authenticode.ps1").read_text()
        for required in ("Get-AuthenticodeSignature", "Get-FileHash", "ApprovedSignerThumbprint",
                         "TimeStamperCertificate", "signtool.exe", "verify /pa /all /tw /v",
                         "Win32NT", "Get-Command"):
            self.assertIn(required, s)
        for unsafe in ("signtool sign", "gh release create", "ConvertFrom-SecureString"):
            self.assertNotIn(unsafe, s)

    def test_release_gate_requires_primary_qt_fix_evidence_and_five_candidates(self):
        self.assertFalse(risk.is_vendor_evidence(""))
        self.assertFalse(risk.is_vendor_evidence("http://qt.io/advisory"))
        self.assertFalse(risk.is_vendor_evidence("https://qt.io.attacker.example/review"))
        self.assertFalse(risk.is_vendor_evidence("https://qt.io@attacker.example/review"))
        self.assertFalse(risk.is_vendor_evidence("https://example.com/claims-fixed"))
        self.assertTrue(risk.is_vendor_evidence("https://code.qt.io/cgit/qt/qtwebengine.git/"))
        policy = json.loads((ROOT / "security/webengine_release_review.json").read_text())
        self.assertEqual(risk.check(policy)["status"], "hold")
        self.assertEqual(risk.check(policy)["cve_count"], 5)
        policy["release_decision"] = "approved"
        policy["known_advisories"] = []
        self.assertEqual(risk.check(policy)["status"], "hold")
        self.assertTrue(any("removed" in msg for msg in risk.check(policy)["release_blockers"]))


if __name__ == "__main__":
    unittest.main()
