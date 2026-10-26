"""Static regression gates for the dependency-free Windows installer promise."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DistributionContractTests(unittest.TestCase):
    def test_per_user_gui_installer_and_no_developer_prerequisites(self):
        setup = (ROOT / "packaging/windows/ReportMaker.iss").read_text(encoding="utf-8")
        for requirement in (
            "PrivilegesRequired=lowest",
            "DefaultDirName={localappdata}",
            "ReportMaker.exe",
            "[Icons]",
            "[Files]",
            "[Run]",
        ):
            self.assertIn(requirement, setup)
        self.assertNotIn("ExecWait=pip", setup)
        self.assertNotIn("ExecWait=git", setup)

    def test_packaged_webengine_has_offline_self_test_and_rolling_release(self):
        workflow = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("--onedir", workflow)
        self.assertIn("--self-test", workflow)
        self.assertIn("Inno Setup", workflow)
        self.assertIn("reportmaker-windows-m0", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release edit", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("purge-legacy-storage:", workflow)
        self.assertIn("needs: installer", workflow)
        self.assertIn("SHA256SUMS.txt", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertNotIn("actions/cache@", workflow)
        code = (ROOT / "src/reportmaker/__main__.py").read_text(encoding="utf-8")
        self.assertIn('QUrl("about:blank")', code)
        self.assertIn('if "--self-test" in sys.argv:', code)
        self.assertNotIn("https://chatgpt.com", code)


if __name__ == "__main__":
    unittest.main()
