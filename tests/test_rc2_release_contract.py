"""Offline safeguards for the one-time RC2 Windows release workflow."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-rc2.yml"
INSTALLER = ROOT / "packaging" / "windows" / "ReportMaker-RC2.iss"
LEGACY = ROOT / "packaging" / "windows" / "ReportMaker.iss"
SOURCE_SHA = "9865178a0ccdfe27e79fc16640c0c3eca50fe099"


class RC2BuildContractTests(unittest.TestCase):
    def test_pin_and_main_only_release_entry_point(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"RC2_SOURCE_SHA: {SOURCE_SHA}", workflow)
        self.assertRegex(workflow, r"(?m)^  push:\s*$")
        self.assertIn("branches: [main]", workflow)
        self.assertIn("- .github/workflows/windows-rc2.yml", workflow)
        self.assertIn("github.repository == 'kandyman991/ReportMaker'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("ref: ${{ env.RC2_SOURCE_SHA }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("merge-base --is-ancestor", workflow)
        self.assertIn("git -C release-config diff --name-only", workflow)

    def test_frozen_smoke_before_release_publication(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for mode in ("--self-test", "--layout-self-test", "--customer-self-test",
                     "--visual-editor-self-test", "--export-self-test"):
            self.assertIn(mode, workflow)
        self.assertIn("--collect-all pillow_heif", workflow)
        self.assertIn("SHA256SUMS.txt", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("gh release edit", workflow)
        self.assertIn("--draft=false --prerelease", workflow)
        self.assertLess(workflow.index("Smoke-test the actual frozen application"),
                        workflow.index("gh release create"))
        self.assertLess(workflow.index("gh release upload"),
                        workflow.index("gh release edit"))
        self.assertNotIn("reportmaker-windows-m0", workflow)

    def test_separate_versioned_setup_and_existing_upgrade_identity(self):
        iss = INSTALLER.read_text(encoding="utf-8")
        previous = LEGACY.read_text(encoding="utf-8")
        for token in ("AppId={{24EFAC39-A017-405C-BEE1-EA15E90F8CE0}",
                      "PrivilegesRequired=lowest"):
            self.assertIn(token, iss)
            self.assertIn(token, previous)
        self.assertIn("AppVersion={#MyAppVersion}", iss)
        self.assertIn('#define MyAppVersion "0.5.0-rc.2"', iss)
        self.assertIn("OutputBaseFilename=ReportMaker-0.5.0-rc.2-Setup", iss)
        self.assertIn('Source: "{#SourceRoot}\\dist\\ReportMaker\\*"', iss)
        self.assertNotIn("ReportMaker-M0-Setup", iss)


if __name__ == "__main__":
    unittest.main()
