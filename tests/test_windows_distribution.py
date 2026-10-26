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

    def test_packaged_webengine_has_offline_self_test_and_artifact(self):
        workflow = (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("--onedir", workflow)
        self.assertIn("--self-test", workflow)
        self.assertIn("upload-artifact@v4", workflow)
        self.assertIn("Inno Setup", workflow)
        code = (ROOT / "src/reportmaker/__main__.py").read_text(encoding="utf-8")
        self.assertIn('QUrl("about:blank")', code)
        self.assertIn('if "--self-test" in sys.argv:', code)
        self.assertNotIn("https://chatgpt.com", code)


if __name__ == "__main__":
    unittest.main()
