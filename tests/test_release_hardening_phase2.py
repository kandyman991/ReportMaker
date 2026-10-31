"""Security regression gates: disabled legacy release, OIDC split and physical QA."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("physical", ROOT / "scripts/validate_windows_physical_acceptance.py")
physical = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(physical)
SPEC = importlib.util.spec_from_file_location("webengine", ROOT / "scripts/check_webengine_release_risk.py")
webengine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(webengine)


class LegacyReleaseRetirementTests(unittest.TestCase):
    def test_all_legacy_publisher_jobs_dead_and_write_scopes_removed(self):
        for f in ("windows-installer.yml", "windows-rc2.yml", "windows-rc3.yml"):
            with self.subTest(workflow=f):
                s = (ROOT / ".github/workflows" / f).read_text(encoding="utf-8")
                self.assertIn("on:\n  workflow_dispatch:", s)
                self.assertNotIn("\n  push:", s)
                self.assertNotIn("contents: write", s)
                self.assertNotIn("actions: write", s)
                self.assertIn("if: ${{ false }}", s)
                self.assertIn("gh release", s)  # archived historical script, no execution
        m0 = (ROOT / ".github/workflows/windows-installer.yml").read_text()
        self.assertIn("purge-legacy-storage:\n    if: ${{ false }}", m0)
        self.assertIn("reportmaker-windows-m0", m0)
        rc3 = (ROOT / ".github/workflows/windows-rc3.yml").read_text()
        self.assertIn("RC3_TAG: reportmaker-v0.5.0-rc.3", rc3)

    def test_readonly_pr_and_trusted_main_attestation_are_separate(self):
        s = (ROOT / ".github/workflows/v2-m7-packaging.yml").read_text()
        self.assertIn("default: false\n", s)
        self.assertIn("attest_nonrelease_metadata:", s)
        self.assertIn("github.event_name == 'workflow_dispatch'", s)
        self.assertIn("github.ref == 'refs/heads/main'", s)
        self.assertIn("inputs.attest_nonrelease_metadata == true", s)
        self.assertIn("attest-nonrelease-metadata:", s)
        block = s.split("\n  attest-nonrelease-metadata:", 1)[1]
        self.assertIn("id-token: write", block)
        self.assertIn("attestations: write", block)
        self.assertIn("artifact-metadata: write", block)
        self.assertIn("contents: read", block)
        self.assertIn("needs: [locked-windows-dependency-audit, windows-v2-frozen-installed-smoke]", block)
        self.assertIn("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6", block)
        self.assertIn("attestable-v2-metadata/*.json", block)
        self.assertNotIn("gh release ", block)
        self.assertNotIn("Setup.exe", block)
        # PR jobs are not permitted to mint OIDC identity or write attestations.
        self.assertNotIn("id-token: write", s.split("jobs:", 1)[1].split("\n  attest-nonrelease-metadata:", 1)[0])


class ReleaseSecurityEvidenceTests(unittest.TestCase):
    def test_webengine_risk_holds_unreviewed_critical_cves(self):
        policy = json.loads((ROOT / "security/webengine_release_review.json").read_text())
        outcome = webengine.check(policy)
        self.assertEqual(outcome["status"], "hold")
        self.assertGreaterEqual(outcome["cve_count"], 5)
        self.assertTrue(any("vendor" in x.lower() for x in outcome["release_blockers"]))
        trusted = json.loads(json.dumps(policy))
        trusted["release_decision"] = "approved"
        # Policy cannot be approved just by flipping a single boolean.
        self.assertEqual(webengine.check(trusted)["status"], "hold")
        trusted["known_advisories"].clear()
        self.assertTrue(any("removed" in x for x in webengine.check(trusted)["release_blockers"]))

    def test_physical_acceptance_requires_all_33_real_evidence(self):
        cases = physical.required_cases()
        self.assertEqual(len(cases), 33)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            p = root / "evidence.json"
            prov = root / "provenance.json"
            prov.write_text(json.dumps({"reviewed_branch_head_commit": "a" * 40,
                                        "installer": {"sha256": "b" * 64}}))
            data = {
                "schema": "reportmaker.physical-windows-acceptance.v1",
                "environment": "physical_windows",
                "host_os": "Windows-11",
                "machine_model": "synthetic test host (NOT physical acceptance)",
                "tester": "synthetic test only",
                "reviewed_at_utc": "2026-10-31T15:00:00Z",
                "reviewed_source_commit": "a" * 40,
                "installed_preview_sha256": "b" * 64,
                "cases": [{"id": k, "status": "pending", "notes": "", "evidence": []}
                          for k in cases],
            }
            p.write_text(json.dumps(data))
            result = physical.verify(p, prov)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["total_cases"], 33)
            self.assertGreaterEqual(len(result["errors"]), 33)
            data["cases"][0]["id"] = "UNRECOGNIZED"
            p.write_text(json.dumps(data))
            self.assertEqual(physical.verify(p, prov)["status"], "blocked")
            self.assertEqual(physical.verify(p, prov)["provided_cases"], 32)


if __name__ == "__main__":
    unittest.main()
