"""Issue #105: isolated Windows supply-chain guardrails without publishing."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packaging/windows/requirements-win314-x64.lock"
W = ROOT / ".github/workflows/v2-m7-packaging.yml"


def import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supply = import_script("windows_supply_chain")


class WindowsSupplyChainTests(unittest.TestCase):
    def test_lock_covers_runtime_build_and_transitive_packages_with_hashes(self):
        entries = supply.parse_lock(LOCK)
        self.assertGreaterEqual(len(entries), 20)
        self.assertEqual(entries["pyside6"]["version"], "6.12.0")
        self.assertEqual(entries["pyinstaller"]["version"], "6.22.3")
        self.assertEqual(entries["pillow"]["version"], "13.0.0")
        self.assertEqual(entries["pyside6-webengine"]["version"], "6.12.0.140")
        self.assertTrue(all(e["hashes"] for e in entries.values()))

    def test_windows_python_migration_is_non_release_and_retains_rollback_lock(self):
        previous = ROOT / "packaging/windows/requirements-win312-x64.lock"
        self.assertTrue(previous.is_file(), "Keep the last successful Windows 3.12 build manifest")
        current = supply.parse_lock(LOCK)
        self.assertEqual(len(current), 22)
        self.assertEqual(len(supply.parse_lock(previous)), 22)
        workflow = W.read_text(encoding="utf-8")
        builder = (ROOT / "scripts/build_v2_m73_local.ps1").read_text(encoding="utf-8")
        self.assertIn('python-version: "3.14.10"', workflow)
        self.assertIn('sys.exit(0 if sys.version_info[:3] == (3, 14, 10)', workflow)
        self.assertIn('Assert security-patched Windows Python runtime', workflow)
        self.assertIn('& py -3.14 -m venv', builder)
        self.assertIn('(3,14,10) <= sys.version_info[:3] < (3,15,0)', builder)
        self.assertIn('sys.exit(0 if', builder)
        self.assertNotIn('assert sys.version_info', workflow)
        self.assertNotIn('assert platform.system()', builder)
        self.assertNotIn('requirements-win312-x64.lock', workflow)
        self.assertNotIn('requirements-win312-x64.lock', builder)
        for legacy in (".github/workflows/windows-rc2.yml",
                       ".github/workflows/windows-rc3.yml",
                       ".github/workflows/windows-installer.yml"):
            self.assertTrue((ROOT / legacy).is_file())
        self.assertIn("inputs.manual_qa_installer == true", workflow)
        self.assertNotIn("gh release create", workflow)

    def test_lock_rejects_url_unhashed_and_duplicate_dependencies(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "lock.txt"
            data = LOCK.read_text()
            for fragment in (
                "random-package>=1",
                "extra==1.0",
                "foo @ https://example.com/executable.whl",
                "pyside6==6.12.0",
            ):
                path.write_text(data + "\n" + fragment + "\n")
                with self.subTest(fragment=fragment):
                    with self.assertRaises(ValueError):
                        supply.parse_lock(path)

    def test_installed_mismatch_or_unknown_dependency_is_blocked(self):
        lock = supply.parse_lock(LOCK)
        actual = {name: e["version"] for name, e in lock.items()}
        actual.update({"pip": "26.0", "reportmaker": "0.0.1"})
        supply.verify_installed(lock, actual)
        actual["pillow"] = "12.0.0"
        with self.assertRaisesRegex(ValueError, "pillow"):
            supply.verify_installed(lock, actual)
        actual["pillow"] = lock["pillow"]["version"]
        actual["unknown-executable-dependency"] = "1.0"
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            supply.verify_installed(lock, actual)

    def test_pip_report_rejects_missing_or_tampered_wheel_hashes(self):
        lock = supply.parse_lock(LOCK)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pip.json"
            path.write_text(json.dumps({"install": []}))
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                supply.verified_wheels(path, lock)
            path.write_text(json.dumps({"install": [{
                "metadata": {"name": "pillow", "version": lock["pillow"]["version"]},
                "download_info": {
                    "url": "https://secret:token@example.com/pillow.whl",
                    "archive_info": {"hashes": {"sha256": "a" * 64}}
                }
            }]}))
            with self.assertRaisesRegex(ValueError, "Unverified"):
                supply.verified_wheels(path, lock)
            report = {"install": [
                {"metadata": {"name": name, "version": entry["version"]},
                 "download_info": {
                     "url": "https://example.invalid/" +
                            ("pillow%5Cevil.whl" if name == "pillow" else name + ".whl"),
                     "archive_info": {"hashes": {"sha256": entry["hashes"][0]}}}}
                for name, entry in lock.items()
            ]}
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "Unverified"):
                supply.verified_wheels(path, lock)

    def test_fake_provenance_outputs_only_public_wheel_names_and_hashes(self):
        lock = supply.parse_lock(LOCK)
        actual = {name: e["version"] for name, e in lock.items()}
        actual["pip"] = "26.2"
        actual["reportmaker"] = "0.0.1"
        report = {"install": [
            {"metadata": {"name": name, "version": e["version"]},
             "download_info": {
                 "url": f"https://user:secret@private-index.invalid/dist/{name}.whl",
                 "archive_info": {"hashes": {"sha256": e["hashes"][0]}}
             }}
            for name, e in lock.items()
        ]}
        with TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "pip.json").write_text(json.dumps(report))
            (base / "installer.exe").write_bytes(b"synthetic private test only")
            (base / "packaging.yml").write_text("synthetic reviewed configuration")
            (base / "frozen").mkdir()
            (base / "frozen" / "launcher.exe").write_bytes(b"synthetic")
            with (patch.object(supply, "installed_versions", return_value=actual),
                  patch.object(supply, "runtime_versions", return_value={
                      "qt": "6.12.0", "chromium": "test", "chromium_security_patch": "test"
                  })):
                provenance = supply.generate(
                    LOCK, base / "pip.json", base / "installer.exe",
                    "a" * 40, "b" * 40, base / "out", base / "frozen",
                    "c" * 40, base / "packaging.yml"
                )
            self.assertEqual(len(provenance["wheels"]), len(lock))
            self.assertEqual(provenance["source_commit"], "a" * 40)
            self.assertEqual(provenance["configuration_commit"], "b" * 40)
            self.assertEqual(provenance["reviewed_branch_head_commit"], "c" * 40)
            self.assertEqual(provenance["configuration_file"]["path"], "packaging.yml")
            self.assertEqual(provenance["configuration_file"]["sha256"],
                             supply.sha256_file(base / "packaging.yml"))
            with self.assertRaisesRegex(ValueError, "Frozen payload directory"):
                supply.generate(LOCK, base / "pip.json", base / "installer.exe",
                                "a" * 40, "b" * 40, base / "out", None,
                                "c" * 40, base / "packaging.yml")
            with self.assertRaisesRegex(ValueError, "configuration file"):
                supply.generate(LOCK, base / "pip.json", base / "installer.exe",
                                "a" * 40, "b" * 40, base / "out", base / "frozen",
                                "c" * 40, base / "does-not-exist.yml")
            self.assertEqual(len(provenance["frozen_payload"]), 1)
            self.assertEqual(provenance["installer"]["filename"], "installer.exe")
            generated = (base / "out" / "windows-v2-provenance.json").read_text()
            self.assertNotIn("secret", generated)
            self.assertNotIn("private-index", generated)
            bom = json.loads((base / "out" / "windows-v2-sbom.cdx.json").read_text())
            self.assertEqual(bom["bomFormat"], "CycloneDX")
            self.assertEqual(len(bom["components"]), len(lock))

    def test_windows_preview_uses_hash_lock_and_preserves_acceptance(self):
        workflow = W.read_text()
        local = (ROOT / "scripts/build_v2_m73_local.ps1").read_text()
        for text in (workflow, local):
            self.assertIn("requirements-win314-x64.lock", text)
            self.assertIn("--require-hashes --only-binary=:all:", text)
            self.assertIn("--no-build-isolation", text)
            self.assertIn("windows_supply_chain.py", text)
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertIn("Record source/config/wheel/Qt/Chromium/installer provenance", workflow)
        self.assertIn("Verify clean source before freezing", workflow)
        self.assertIn("--branch-head-sha", workflow)
        self.assertIn("--configuration-file", workflow)
        self.assertIn("--configuration-file", local)
        self.assertIn("retention-days: 7", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("inputs.manual_qa_installer == true", workflow)
        self.assertIn("Installed HTML V2 offline smoke failed", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/setup-python@v5", workflow)
        self.assertNotIn("actions/upload-artifact@v4", workflow)
        for old in ("windows-rc2.yml", "windows-rc3.yml", "windows-installer.yml"):
            self.assertTrue((ROOT / ".github/workflows" / old).is_file())

    def test_qt_security_monitor_is_read_only(self):
        monitor = (ROOT / ".github/workflows/qt-webengine-security-watch.yml").read_text()
        self.assertIn("  schedule:", monitor)
        self.assertIn("permissions:\n  contents: read", monitor)
        self.assertNotIn("gh release", monitor)
        self.assertNotIn("contents: write", monitor)


if __name__ == "__main__":
    unittest.main()
