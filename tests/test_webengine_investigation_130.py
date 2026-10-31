"""PR #130: independent wheel version alerts and fail-closed Qt/Chromium triage."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updates = load("webengine_updates_130", "scripts/check_qt_webengine_updates.py")
risk = load("webengine_gate_130", "scripts/check_webengine_release_risk.py")


class IndependentWheelWatcherTests(unittest.TestCase):
    def test_reads_pyside_pin_and_separate_webengine_windows_lock(self):
        self.assertEqual(
            updates.current_versions(ROOT / "pyproject.toml", updates.WINDOWS_LOCK),
            ("6.12.0", "6.12.0.140"),
        )

    def test_new_webengine_alone_requires_review_even_without_pyside_upgrade(self):
        message, outdated = updates.compare_versions(
            ROOT / "pyproject.toml", updates.WINDOWS_LOCK, "6.12.0", "6.12.0.141")
        self.assertTrue(outdated)
        self.assertIn("PySide6-WebEngine 6.12.0.140", message)
        self.assertFalse(updates.compare_versions(
            ROOT / "pyproject.toml", updates.WINDOWS_LOCK, "6.12.0", "6.12.0.140")[1])
        self.assertTrue(updates.compare_versions(
            ROOT / "pyproject.toml", updates.WINDOWS_LOCK, "6.12.1", "6.12.0.140")[1])

    def test_fails_closed_if_lock_missing_duplicate_or_core_pin_drifted(self):
        contents = updates.WINDOWS_LOCK.read_text()
        with TemporaryDirectory() as temp:
            lock = Path(temp) / "lock.txt"
            for altered in (
                contents.replace("pyside6-webengine==6.12.0.140", "# missing webengine"),
                contents + "\npyside6-webengine==9.9.9\n",
                contents.replace("pyside6==6.12.0", "pyside6==6.12.1"),
            ):
                lock.write_text(altered)
                with self.assertRaises(ValueError):
                    updates.current_versions(ROOT / "pyproject.toml", lock)

    def test_qt_security_changes_trigger_nonrelease_windows_preflight(self):
        workflow = (ROOT / ".github/workflows/v2-m7-packaging.yml").read_text()
        for path in ("scripts/check_qt_webengine_updates.py",
                     "scripts/check_webengine_release_risk.py",
                     "security/webengine_release_review.json",
                     ".github/workflows/qt-webengine-security-watch.yml",
                     "tests/test_webengine_*.py"):
            self.assertIn(f'- "{path}"', workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("contents: read", workflow)

    def test_live_pypi_lookup_has_fixed_package_allowlist(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized package"):
            updates.latest_release("not-pyside6")


class ReleaseWebEngineGateTests(unittest.TestCase):
    @staticmethod
    def reviewed_policy() -> dict:
        policy = json.loads((ROOT / "security/webengine_release_review.json").read_text())
        policy["release_decision"] = "approved"
        policy["vendor_patch_backport_evidence"] = "https://code.qt.io/cgit/qt/qtwebengine.git/"
        for record in policy["known_advisories"]:
            record["status"] = "verified_fixed"
            record["resolution_evidence"] = "https://code.qt.io/cgit/qt/qtwebengine.git/"
        return policy

    @staticmethod
    def matching_provenance() -> dict:
        return {"qt_runtime": {
            "qt": "6.12.0", "qt_webengine": "6.140.0",
            "chromium": "140.0.7339.225",
            "chromium_security_patch": "152.0.7977.83",
        }}

    def test_strict_requires_actual_runtime_even_for_reviewed_policy(self):
        policy = self.reviewed_policy()
        outcome = risk.check(policy, require_provenance=True)
        self.assertEqual(outcome["status"], "hold")
        self.assertIn("No exact Windows installed-build Qt runtime provenance",
                      outcome["release_blockers"])

    def test_exact_qt_webengine_runtime_and_patch_are_checked(self):
        policy = self.reviewed_policy()
        valid = self.matching_provenance()
        # This is only an input-validation test, NOT a real independent review.
        self.assertEqual(risk.check(policy, valid, require_provenance=True)["status"], "approved")
        for field in ("qt", "qt_webengine", "chromium", "chromium_security_patch"):
            changed = self.matching_provenance()
            changed["qt_runtime"][field] = "different"
            with self.subTest(field=field):
                self.assertEqual(risk.check(policy, changed,
                                            require_provenance=True)["status"], "hold")
            del changed["qt_runtime"][field]
            self.assertEqual(risk.check(policy, changed,
                                        require_provenance=True)["status"], "hold")

    def test_malformed_cves_and_removed_critical_candidates_fail_closed(self):
        policy = self.reviewed_policy()
        policy["known_advisories"] = [None, {"id": "CVE-2026-76024",
                                            "status": "verified_fixed",
                                            "resolution_evidence": "https://code.qt.io/cgit/qt/qtwebengine.git/"}]
        result = risk.check(policy, self.matching_provenance(), require_provenance=True)
        self.assertEqual(result["status"], "hold")
        self.assertTrue(any("candidate removed" in f for f in result["release_blockers"]))

    def test_current_real_review_remains_hold_even_without_windows_provenance(self):
        actual = json.loads((ROOT / "security/webengine_release_review.json").read_text())
        self.assertEqual(risk.check(actual, require_provenance=True)["status"], "hold")
        command = [sys.executable, str(ROOT / "scripts/check_webengine_release_risk.py"), "--strict"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("No exact Windows installed-build Qt runtime provenance", result.stdout)


if __name__ == "__main__":
    unittest.main()
