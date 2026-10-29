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
        self.assertTrue(all(r["status"] == "pending_native_acceptance" for r in rows))
        self.assertTrue(all(r["evidence_ref"] is None for r in rows))
        self.assertTrue(all(r["manual_acceptance"].strip() for r in rows))

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
        ):
            self.assertIn(marker, workflow)
        for forbidden in (
            "actions/upload-artifact", "gh release create",
            "gh release upload", "gh release edit", "actions/cache@",
            "contents: write", "packaging/windows/launcher.py\n",
        ):
            self.assertNotIn(forbidden, workflow)
        self.assertLess(workflow.index("Freeze actual V2 executable"),
                        workflow.index("Build local-only distinct per-user V2 installer"))
        self.assertLess(workflow.index("Build local-only distinct per-user V2 installer"),
                        workflow.index("Silent install, compare binary, smoke and uninstall"))


if __name__ == "__main__":
    unittest.main()
