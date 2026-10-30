"""M7.1: static independent V2 packaging and 33-feature evidence contracts."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "docs/v2/BRANCH_EDITOR_REQUIREMENTS.md"
MATRIX = ROOT / "docs/v2/M7_ACCEPTANCE_MATRIX.json"


class M7PackageContractTests(unittest.TestCase):
    def test_33_feature_matrix_is_exact_and_has_no_undocumented_passes(self):
        source = REQUIREMENTS.read_text(encoding="utf-8")
        expected = re.findall(r"\*\*(BE-[LESUI]\d{2}) — ", source)
        self.assertEqual(len(expected), 33)
        self.assertEqual(len(set(expected)), 33)
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(matrix["schema_version"], 1)
        rows = matrix["requirements"]
        self.assertEqual([r["id"] for r in rows], expected)
        self.assertTrue(all(r["manual_acceptance"].strip() for r in rows))
        # New M7.1 cases start pending. Later M7.3 native acceptance
        # may change statuses, but only with auditable physical evidence.
        allowed = {"pending_native_acceptance", "failed_native_acceptance",
                   "passed_native_acceptance"}
        for row in rows:
            with self.subTest(id=row["id"]):
                self.assertIn(row["status"], allowed)
                if row["status"] == "pending_native_acceptance":
                    self.assertIsNone(row["evidence_ref"])
                else:
                    self.assertIsInstance(row["evidence_ref"], str)
                    self.assertTrue(row["evidence_ref"].strip())
                if row["status"] == "passed_native_acceptance":
                    for field in ("reviewed_by", "tested_on", "windows_build",
                                  "display_scale", "installer_sha256"):
                        self.assertIsInstance(row.get(field), str)
                        self.assertTrue(row[field].strip())
                    self.assertRegex(row["installer_sha256"], r"^[0-9a-fA-F]{64}$")

    def test_preflight_rebuilds_for_shared_runtime_changes_and_checks_all_files(self):
        workflow = (ROOT / ".github/workflows/v2-m7-packaging.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('      - "src/reportmaker/**"', workflow)
        self.assertIn('      - "tests/test_v2_*.py"', workflow)
        self.assertIn('      - "packaging/windows/**"', workflow)
        self.assertNotIn('      - "src/reportmaker/v2/**"', workflow)
        self.assertIn("Get-ChildItem -LiteralPath $originalDir -Recurse -File", workflow)
        self.assertIn("Join-Path $installDir $relativePath", workflow)
        self.assertIn("Get-FileHash -LiteralPath $payload.FullName", workflow)
        self.assertIn("Get-FileHash -LiteralPath $installedPayload", workflow)
        self.assertIn("Installed frozen payload file is missing:", workflow)
        self.assertIn("Installed frozen payload file does not match:", workflow)

    def test_roadmap_cannot_revert_completed_m6_to_draft(self):
        roadmap = (ROOT / "docs/v2/ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("M6.7 — End-to-end Checkpoint C:** Independently reviewed and merged", roadmap)
        self.assertNotIn("M6.7 is a separate integration/checkpoint draft", roadmap)
        self.assertIn("M7.1 is isolated in draft PR #92", roadmap)

    def test_launcher_uses_v2_not_legacy_gui(self):
        v2 = (ROOT / "packaging/windows/v2_launcher.py").read_text(encoding="utf-8")
        self.assertIn("from reportmaker.v2.__main__ import main", v2)
        self.assertNotIn("from reportmaker.__main__ import main", v2)

    def test_preview_installer_is_isolated_and_local_per_user(self):
        v2 = (ROOT / "packaging/windows/ReportMaker-V2-M7.iss").read_text(encoding="utf-8")
        legacy = (ROOT / "packaging/windows/ReportMaker.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", v2)
        self.assertIn("ReportMakerV2.exe", v2)
        self.assertIn("ReportMaker V2 Preview", v2)
        self.assertIn("MinVersion=10.0.17763", v2)
        self.assertIn("#ifndef SourceRoot", v2)
        self.assertIn("#ifndef OutputRoot", v2)
        self.assertNotIn("Source: \"..\\..\\dist\\ReportMaker\\", v2)
        app_id = re.search(r"AppId=(\S+)", v2).group(1)
        legacy_id = re.search(r"AppId=(\S+)", legacy).group(1)
        self.assertNotEqual(app_id, legacy_id)
        self.assertNotIn("DefaultDirName={localappdata}\\Programs\\ReportMaker\n", v2)

    def test_hosted_ci_builds_and_installs_without_publishing(self):
        workflow = (ROOT / ".github/workflows/v2-m7-packaging.yml").read_text(encoding="utf-8")
        for marker in (
            "windows-latest", "architecture: x64", "contents: read",
            "--onedir", "--name ReportMakerV2", "--offline-self-test",
            "ReportMaker-V2-M7.iss", "Start-Process", "/VERYSILENT",
            "Get-FileHash", "unins000.exe", "persist-credentials: false",
            "test_v2_m73_native_draft_recovery.py",
            "test_v2_m73_photo_contrast.py",
        ):
            self.assertIn(marker, workflow)
        for forbidden in (
            "gh release create", "gh release upload", "gh release edit",
            "actions/cache@",
            "contents: write", "packaging/windows/launcher.py\n",
        ):
            self.assertNotIn(forbidden, workflow)
        # PR/push runs still MUST NOT upload. The user-requested M7.3
        # preview is a separate, explicitly opted-in manual QA artifact,
        # short-lived, unsigned, and never a GitHub Release.
        self.assertIn("default: false", workflow)
        self.assertIn("manual_qa_installer:", workflow)
        self.assertEqual(workflow.count("actions/upload-artifact@v4"), 1)
        manual_gate = "if: ${{ github.event_name == 'workflow_dispatch' && inputs.manual_qa_installer == true }}"
        self.assertEqual(workflow.count(manual_gate), 2)
        self.assertIn("retention-days: 1", workflow)
        self.assertLess(workflow.index(manual_gate), workflow.index("actions/upload-artifact@v4"))
        self.assertLess(workflow.index("Silent install, compare binary, smoke and uninstall"),
                        workflow.index("actions/upload-artifact@v4"))
        self.assertLess(workflow.index("Freeze actual V2 executable"),
                        workflow.index("Build local-only distinct per-user V2 installer"))
        self.assertLess(workflow.index("Build local-only distinct per-user V2 installer"),
                        workflow.index("Silent install, compare binary, smoke and uninstall"))
        # A successful installed-app gate must prove cleanup, not quietly skip
        # removal if the preview installer omitted its uninstaller.
        self.assertIn('if (!(Test-Path $uninstaller))', workflow)
        self.assertIn('throw "V2 binaries remain after the silent uninstall"', workflow)


if __name__ == "__main__":
    unittest.main()
