"""Contract tests for M7.3 evidence tooling; NOT physical Windows acceptance."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main, mock
import json
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/m73_native_acceptance.py"
spec = spec_from_file_location("m73_native_acceptance", SCRIPT)
gate = module_from_spec(spec)
spec.loader.exec_module(gate)


class NativeAcceptanceToolTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "private-evidence"
        self.setup = self.root / "ReportMaker-V2-M7-Preview-Setup.exe"
        self.exe = self.root / "ReportMakerV2.exe"
        self.setup.write_bytes(b"synthetic-setup-not-a-windows-binary")
        self.exe.write_bytes(b"synthetic-exe-not-a-windows-binary")
        self.build_manifest = self.root / "m73-local-build.json"
        self.build_manifest.write_text(json.dumps({
            "source_sha": "a" * 40,
            "installer_sha256": sha256(self.setup.read_bytes()).hexdigest(),
            "installed_exe_sha256": sha256(self.exe.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        self.args = SimpleNamespace(
            installer=str(self.setup), installed_exe=str(self.exe),
            build_manifest=str(self.build_manifest),
            source_sha="a" * 40, display_scale="100%; 150% secondary monitor",
            tester_alias="Tester-1", output=str(self.output),
        )

    def _prepare(self):
        # Mock is used ONLY by unit tests to exercise schema behavior on Linux;
        # no fixture result is native acceptance or a CI-pass equivalent.
        with mock.patch.object(gate, "_native_platform", return_value=("Windows", "10.0.22631")):
            with redirect_stdout(StringIO()):
                gate.prepare(self.args)

    def _pass(self, case="BE-L01"):
        screenshot = self.output / "evidence" / (case + ".png")
        screenshot.write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC_NOT_VALID_SCREENSHOT")
        args = SimpleNamespace(
            dossier=str(self.output), case=case, result="pass",
            steps="Manually generated synthetic modules", observed="Hierarchy visible",
            evidence=screenshot.name, issue=None,
        )
        with redirect_stdout(StringIO()):
            gate.record(args)
        return screenshot

    def test_exact_33_pending_and_no_repo_mutation(self):
        before = gate.MATRIX.read_bytes()
        self.assertEqual(len(gate._matrix()["requirements"]), 33)
        self._prepare()
        record = gate._read(self.output)
        self.assertEqual(record["case_count"], 33)
        self.assertTrue(all(row["result"] == "pending" for row in record["cases"].values()))
        self.assertTrue(all(row["review_status"] == "pending" for row in record["cases"].values()))
        self.assertEqual(before, gate.MATRIX.read_bytes())
        self.assertEqual(record["installer_sha256"], sha256(self.setup.read_bytes()).hexdigest())
        self.assertNotIn("hostname", record)
        self.assertNotIn("username", record)

    def test_cli_on_linux_cannot_claim_physical_windows(self):
        if sys.platform != "win32":
            with self.assertRaisesRegex(ValueError, "physical|Physical"):
                gate._native_platform()

    def test_pass_requires_evidence_and_separate_reviewer(self):
        self._prepare()
        no_image = SimpleNamespace(
            dossier=str(self.output), case="BE-L01", result="pass",
            observed="Tested synthetic modules", steps="Open and edit modules",
            evidence=None, issue=None,
        )
        with self.assertRaisesRegex(ValueError, "screenshot"):
            gate.record(no_image)
        self._pass()
        initial = gate._read(self.output)["cases"]["BE-L01"]
        self.assertEqual(initial["review_status"], "pending")
        reviewer = SimpleNamespace(
            dossier=str(self.output), case="BE-L01",
            reviewer_alias="Tester-1", decision="accept",
            notes="Independent synthetic-only test review",
        )
        with self.assertRaisesRegex(ValueError, "differ"):
            gate.review(reviewer)
        reviewer.reviewer_alias = "Reviewer-2"
        with redirect_stdout(StringIO()):
            gate.review(reviewer)
        result = gate._read(self.output)["cases"]["BE-L01"]
        self.assertEqual(result["review_status"], "accepted")
        with redirect_stdout(StringIO()) as stream:
            gate.summary(SimpleNamespace(dossier=str(self.output)))
        summary = json.loads(stream.getvalue())
        self.assertEqual(summary["accepted_count"], 1)
        self.assertFalse(summary["complete"])
        self.assertNotIn(str(self.output), stream.getvalue())
        self.assertEqual(gate._matrix()["requirements"][0]["status"], "pending_native_acceptance")

    def test_fail_or_blocked_requires_issue_not_acceptance(self):
        self._prepare()
        entry = SimpleNamespace(
            dossier=str(self.output), case="BE-U07", result="fail",
            observed="Clipboard insertion failed", steps="Synthetic bitmap paste",
            evidence=None, issue=None,
        )
        with self.assertRaisesRegex(ValueError, "tracking issue"):
            gate.record(entry)
        entry.issue = "https://github.com/kandyman991/ReportMaker/issues/1234"
        with redirect_stdout(StringIO()):
            gate.record(entry)
        record = gate._read(self.output)["cases"]["BE-U07"]
        self.assertEqual(record["result"], "fail")
        self.assertEqual(record["review_status"], "pending")
        with self.assertRaisesRegex(ValueError, "Only a recorded native pass"):
            gate.review(SimpleNamespace(
                dossier=str(self.output), case="BE-U07",
                reviewer_alias="Reviewer-2", decision="accept", notes="not allowed"))

    def test_reject_bad_paths_and_changed_evidence(self):
        self._prepare()
        for unsafe in ("../private.png", "/tmp/test.png", "C:\\Users\\Private.png"):
            with self.assertRaises(ValueError):
                gate._evidence(self.output, unsafe)
        image = self._pass()
        image.write_bytes(b"\x89PNG\r\n\x1a\nALTERED_SYNTHETIC")
        with self.assertRaisesRegex(ValueError, "Screenshot changed"):
            gate.review(SimpleNamespace(
                dossier=str(self.output), case="BE-L01",
                reviewer_alias="Reviewer-2", decision="accept",
                notes="Different contents are not approved"))

    def test_build_provenance_mismatch_is_rejected(self):
        manifest = json.loads(self.build_manifest.read_text(encoding="utf-8"))
        manifest["installer_sha256"] = "0" * 64
        self.build_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(gate, "_native_platform", return_value=("Windows", "10.0.22631")):
            with self.assertRaisesRegex(ValueError, "do not match"):
                gate.prepare(self.args)
        self.assertFalse((self.output / gate.DOSSIER_NAME).exists())

    def test_no_overwrite_or_repo_evidence(self):
        self._prepare()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self._prepare()
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            gate._outside_repo(gate.SOURCE_ROOT / "private-evidence")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            gate.record(SimpleNamespace(
                dossier=str(self.output), case="BE-INVALID", result="pass",
                steps="x", observed="x", evidence="x.png", issue=None))


if __name__ == "__main__":
    main()
