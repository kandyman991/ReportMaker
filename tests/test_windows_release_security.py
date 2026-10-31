"""Static fail-closed checks for historical Windows publishers and build comparison."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
RC3_WORKFLOW_SHA256 = "1d62d6bd581318bfab6a83884848e367e29d6518fccbfb7b185206610df81005"
RC3_INSTALLER_SHA256 = "45f62b16b8ef254a4e144c402af6a45f49314cd66de42d8242be5ecd463a514f"

spec = importlib.util.spec_from_file_location(
    "compare_windows_build_provenance", ROOT / "scripts/compare_windows_build_provenance.py"
)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


def minimal_provenance() -> dict:
    return {
        "schema": compare.SCHEMA,
        "generated_utc": "2026-10-31T12:00:00Z",
        "source_commit": "a" * 40,
        "reviewed_branch_head_commit": "b" * 40,
        "configuration_commit": "a" * 40,
        "configuration_file": {"path": "v2-m7-packaging.yml", "sha256": "c" * 64},
        "platform": "Windows-2022", "architecture": "AMD64", "python": "3.14.10",
        "github_runner_image": {"name": "win22", "version": "20261026"},
        "lock_sha256": "d" * 64,
        "qt_runtime": {"qt": "6.12.0", "chromium": "140.0.7339.225"},
        "wheels": [{"name": "pyside6", "version": "6.12.0",
                    "wheel": "PySide6-6.12.0-win_amd64.whl", "sha256": "e" * 64}],
        "frozen_payload": [{"path": "ReportMakerV2.exe", "sha256": "f" * 64}],
        "installer": {"filename": "ReportMaker-V2-M7-Preview-Setup.exe", "sha256": "0" * 64},
    }


class HistoricalWindowsReleaseSafetyTests(unittest.TestCase):
    def test_manual_legacy_publishers_use_reviewed_action_shas(self):
        for filename, checkout_count in (("windows-installer.yml", 1),
                                          ("windows-rc2.yml", 2)):
            with self.subTest(filename=filename):
                workflow = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertIn("on:\n  workflow_dispatch:", workflow)
                self.assertNotIn("\n  push:\n", workflow)
                self.assertEqual(workflow.count(CHECKOUT), checkout_count)
                self.assertEqual(workflow.count(PYTHON), 1)
                self.assertNotIn("actions/checkout@v4", workflow)
                self.assertNotIn("actions/setup-python@v5", workflow)
                self.assertEqual(workflow.count("persist-credentials: false"), checkout_count)
                self.assertIn("contents: read", workflow)
                self.assertIn("contents: write", workflow)
                self.assertIn("gh release", workflow)
        self.assertIn("M0_SOURCE_SHA: 1981d802194bb2619e689533ac35dabde0f706da",
                      (WORKFLOWS / "windows-installer.yml").read_text())
        self.assertIn("RC2_SOURCE_SHA: 9865178a0ccdfe27e79fc16640c0c3eca50fe099",
                      (WORKFLOWS / "windows-rc2.yml").read_text())

    def test_deterministic_pyinstaller_environment_is_source_pinned(self):
        workflow = (WORKFLOWS / "v2-m7-packaging.yml").read_text(encoding="utf-8")
        builder = (ROOT / "scripts/build_v2_m73_local.ps1").read_text(encoding="utf-8")
        self.assertIn("git show -s --format=%ct HEAD", workflow)
        self.assertIn("git show -s --format=%ct $sourceSha", builder)
        for item in (workflow, builder):
            self.assertIn('PYTHONHASHSEED = "1"', item)
            self.assertIn("SOURCE_DATE_EPOCH =", item)
            self.assertIn("Unable to establish deterministic source commit epoch", item)
        self.assertLess(workflow.index('PYTHONHASHSEED = "1"'),
                        workflow.index('python -m PyInstaller --noconfirm'))
        self.assertLess(builder.index('PYTHONHASHSEED = "1"'),
                        builder.index('& $python -m PyInstaller --noconfirm'))

    def test_rc3_release_publisher_is_unmodified_and_remains_separately_gated(self):
        rc3 = WORKFLOWS / "windows-rc3.yml"
        iss = ROOT / "packaging/windows/ReportMaker-RC3.iss"
        self.assertEqual(hashlib.sha256(rc3.read_bytes().replace(b"\r\n", b"\n")).hexdigest(), RC3_WORKFLOW_SHA256)
        self.assertEqual(hashlib.sha256(iss.read_bytes().replace(b"\r\n", b"\n")).hexdigest(), RC3_INSTALLER_SHA256)
        data = rc3.read_text(encoding="utf-8")
        self.assertIn("on:\n  push:", data)
        self.assertIn("- .github/workflows/windows-rc3.yml", data)
        self.assertIn("github.ref == 'refs/heads/main'", data)
        self.assertIn("gh release create", data)
        self.assertIn("RC3_SOURCE_SHA: 5da9f06e72303f1370783f5efdae17fb8fcd5f40", data)


class ReproducibilityComparisonTests(unittest.TestCase):
    def test_ignores_timestamp_but_requires_same_installer_and_payload(self):
        first = minimal_provenance()
        second = minimal_provenance()
        second["generated_utc"] = "2026-10-31T13:00:00Z"
        result = compare.compare(first, second)
        self.assertEqual(result["status"], "matching_byte_hashes")
        self.assertTrue(result["full_installer_sha256_matches"])
        self.assertTrue(result["frozen_payload_sha256_matches"])
        self.assertIn("not proof", result["limitation"])

    def test_changed_installer_payload_wheel_or_environment_blocks_match(self):
        for label, mutation in (
            ("installer", lambda x: x["installer"].update(sha256="1" * 64)),
            ("payload", lambda x: x["frozen_payload"][0].update(sha256="1" * 64)),
            ("wheel", lambda x: x["wheels"][0].update(sha256="1" * 64)),
            ("python", lambda x: x.update(python="3.14.9")),
            ("source", lambda x: x.update(source_commit="1" * 40)),
            ("runner", lambda x: x["github_runner_image"].update(version="changed")),
            ("new_toolchain_field", lambda x: x.update(inno_setup_sha256="1" * 64)),
        ):
            with self.subTest(label=label):
                first = minimal_provenance()
                second = minimal_provenance()
                mutation(second)
                self.assertEqual(compare.compare(first, second)["status"], "differences_found")

    def test_invalid_hash_duplicate_paths_and_missing_data_are_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "build.json"
            for mutation in (
                lambda x: x["wheels"][0].update(sha256="not-a-hash"),
                lambda x: x["frozen_payload"].append(x["frozen_payload"][0].copy()),
                lambda x: x.pop("installer"),
                lambda x: x.update(source_commit="not-a-git-sha"),
            ):
                data = minimal_provenance()
                mutation(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    compare.read_manifest(path)

    def test_two_distinct_artifacts_and_a_machine_readable_result(self):
        with TemporaryDirectory() as folder:
            first = Path(folder) / "run_a.json"
            second = Path(folder) / "run_b.json"
            first.write_text(json.dumps(minimal_provenance()))
            second.write_text(json.dumps(minimal_provenance()))
            a, b = compare.read_manifest(first), compare.read_manifest(second)
            self.assertEqual(compare.compare(a, b)["status"], "matching_byte_hashes")
            a["frozen_payload"][0]["sha256"] = "a" * 64
            self.assertEqual(compare.compare(a, b)["differences"][0]["kind"], "frozen_payload")


if __name__ == "__main__":
    unittest.main()
