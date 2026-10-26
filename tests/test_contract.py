import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureContractTests(unittest.TestCase):
    def test_locked_invariants(self):
        contract = json.loads((ROOT / "docs/architecture_contract.json").read_text(
            encoding="utf-8"
        ))
        self.assertEqual(contract["platform"]["required"], "windows-x64")
        self.assertEqual(contract["report"]["modules"], "ordered-nested-heterogeneous")
        self.assertEqual(contract["report"]["block_order"], "unrestricted")
        self.assertEqual(contract["report"]["conclusion"], "dedicated-final")
        self.assertEqual(contract["report"]["languages"], "open-ended-bcp47-style")
        self.assertEqual(contract["report"]["word_export"], "editable-docx")
        self.assertEqual(contract["assistant"]["integration"], "user-browser-only")
        self.assertEqual(contract["assistant"]["transfer"], "explicit-manual-copy-paste")
        self.assertEqual(contract["assistant"]["fallback"], "external-browser")
        for forbidden in ("api_calls", "agents", "automation", "credential_capture"):
            self.assertIs(contract["assistant"][forbidden], False)


if __name__ == "__main__":
    unittest.main()
