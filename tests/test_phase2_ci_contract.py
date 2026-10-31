"""Phase 2 non-destructive CI and security scope contract."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / ".github/workflows/linux-application.yml"
DEPENDABOT = ROOT / ".github/dependabot.yml"


class Phase2CIGateTests(unittest.TestCase):
    def test_linux_application_ci_is_additive_to_windows_validation(self):
        text = LINUX.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n    branches: [main]", text)
        self.assertIn("  push:\n    branches: [main]", text)
        self.assertIn("  workflow_dispatch:", text)
        self.assertIn("runs-on: ubuntu-24.04", text)
        self.assertIn("python-version: ['3.12', '3.14']", text)
        for command in (
            "python -m compileall -q src",
            "python -m reportmaker.v2 --offline-self-test",
            "python -m reportmaker.v2 --html --offline-self-test",
            "python -m coverage run --source=reportmaker -m unittest discover -s tests -v",
        ):
            self.assertIn(command, text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("gh release", text)
        self.assertNotIn("upload-artifact", text)
        self.assertTrue((ROOT / ".github/workflows/ci.yml").is_file())
        self.assertTrue((ROOT / ".github/workflows/m1-customer-ui.yml").is_file())
        self.assertTrue((ROOT / ".github/workflows/v2-m7-packaging.yml").is_file())

    def test_action_revisions_pinned_in_new_workflow(self):
        text = LINUX.read_text(encoding="utf-8")
        actions = re.findall(r"uses:\s+(actions/(?:checkout|setup-python))@([^\s#]+)", text)
        self.assertEqual(len(actions), 4)
        for _, revision in actions:
            self.assertRegex(revision, r"\A[0-9a-f]{40}\Z")

    def test_advisory_audit_is_not_claimed_as_clean_release_gate(self):
        text = LINUX.read_text(encoding="utf-8")
        self.assertIn("ruff check --select E9,F63,F7,F82 src tests scripts", text)
        self.assertIn("pip_audit", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("NOT CLEAN (advisory only)", text)
        self.assertIn("issue #105", text)

    def test_dependabot_proposes_updates_without_auto_merge(self):
        text = DEPENDABOT.read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: pip", text)
        self.assertIn("package-ecosystem: github-actions", text)
        self.assertEqual(text.count("interval: weekly"), 2)
        self.assertNotIn("auto-merge", text)


if __name__ == "__main__":
    unittest.main()
