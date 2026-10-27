"""Regression checks for safe workflow-level GitHub Actions concurrency.

Only validation workflows cancel older runs. Publication and state writers use
their existing serialization rules and manual test dispatches stay independent.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/m1-customer-ui.yml",
    ".github/workflows/continuity-contract.yml",
)
GROUP = (
    "  group: ${{ github.workflow }}-${{ github.event_name }}-"
    "${{ github.event_name == 'workflow_dispatch' && github.run_id || "
    "github.event.pull_request.number || github.ref }}"
)
CANCEL = "  cancel-in-progress: ${{ github.event_name != 'workflow_dispatch' }}"


class WorkflowConcurrencyContractTests(unittest.TestCase):
    def test_validators_only_cancel_superseded_event_and_ref(self):
        for path in WORKFLOWS:
            with self.subTest(workflow=path):
                body = (ROOT / path).read_text(encoding="utf-8")
                # The policy is workflow-level, not restricted to a single job.
                self.assertEqual(len(re.findall(r"^concurrency:$", body, re.M)), 1)
                section = body.split("\nconcurrency:\n", 1)[1].split("\n\n", 1)[0]
                self.assertIn(GROUP, section.splitlines())
                self.assertIn(CANCEL, section.splitlines())
                self.assertEqual(section.count("  group: "), 1)
                self.assertEqual(section.count("  cancel-in-progress: "), 1)
                self.assertIn("\n  pull_request:", body)
                self.assertIn("\n  push:", body)
                self.assertIn("\njobs:\n", body)

    def test_publishers_and_shared_state_writers_remain_serialized(self):
        release = (ROOT / ".github/workflows/windows-installer.yml").read_text(
            encoding="utf-8"
        )
        state = (ROOT / ".github/workflows/update-chat-handoff-state.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("group: reportmaker-windows-rolling-release", release)
        self.assertIn("group: reportmaker-chat-handoff-state", state)
        for workflow in (release, state):
            self.assertIn("cancel-in-progress: true", workflow)

    def test_manual_triggers_keep_unique_run_id_in_the_group(self):
        for path in WORKFLOWS[1:]:
            with self.subTest(workflow=path):
                body = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn("\n  workflow_dispatch:\n", body)
                self.assertIn("workflow_dispatch' && github.run_id", body)
                self.assertIn(CANCEL, body)


if __name__ == "__main__":
    unittest.main()
