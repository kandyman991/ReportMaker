"""Regression gates for independent final PR #5 review findings.

Synthetic data only; never touches the user's local customer database.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from reportmaker.model import LocalizedText, Module, Report
from reportmaker.reference import CustomerSnapshot, manual_snapshot
from reportmaker.storage import CustomerStore


def _report(customer_id, snapshot=None):
    return Report(
        customer_id=customer_id, customer_snapshot=snapshot,
        start_date=date(2026, 10, 26), end_date=date(2026, 10, 26),
        primary_language="it", output_languages=["it", "fr-CA"],
        conclusion=Module(LocalizedText("it", "Conclusioni")),
    )


class FinalReviewCorrections(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = CustomerStore(Path(self.folder.name) / "synthetic.sqlite3")
        self.addCleanup(self.store.close)

    def test_optional_customer_key_none_and_blank_are_supported_with_snapshot(self):
        manual = manual_snapshot("Temporary buyer", site_name="One-off site")
        self.assertIsNone(_report(None, manual).customer_id)
        self.assertEqual(_report("", manual).customer_id, "")
        with self.assertRaises(ValueError):
            _report(None)
        with self.assertRaises(ValueError):
            _report("")
        with self.assertRaises(ValueError):
            _report(" ")
        with self.assertRaises(ValueError):
            _report(42, manual)
        with self.assertRaises(ValueError):
            _report("registered-id", manual)

        registered = CustomerSnapshot(customer_name="Linked", customer_id="linked-id")
        self.assertEqual(_report("linked-id", registered).customer_id, "linked-id")
        with self.assertRaises(ValueError):
            _report(None, registered)
        with self.assertRaises(ValueError):
            _report("other-id", registered)

    def test_snapshot_preserves_complete_postal_address_after_master_edit(self):
        customer = self.store.create_customer(
            "Synthetic Cust", postal_code="12345", address="Initial Street", city="Example City",
        )
        site = self.store.create_site(
            customer, "Test Plant", postal_code="67890", address="Test Avenue",
        )
        machine = self.store.create_machine(site, "Synthetic Machine")
        snapshot = self.store.capture_snapshot(customer, site_id=site, machine_id=machine)
        self.assertEqual(snapshot.customer_postal_code, "12345")
        self.assertEqual(snapshot.site_postal_code, "67890")
        self.store.save_report_reference("synthetic-report-id", snapshot)
        self.store.update("customers", customer, postal_code="00000")
        self.store.update("sites", site, postal_code="99999")
        loaded = self.store.load_report_reference("synthetic-report-id")
        self.assertEqual(loaded.customer_postal_code, "12345")
        self.assertEqual(loaded.site_postal_code, "67890")
        self.assertEqual(loaded.to_dict()["customer_postal_code"], "12345")

        # New snapshot attributes are backward-compatible with M1 v1 JSON.
        legacy = snapshot.to_dict()
        legacy.pop("customer_postal_code")
        legacy.pop("site_postal_code")
        self.assertEqual(CustomerSnapshot.from_dict(legacy).site_postal_code, "")

    def test_one_off_reference_accepts_all_detached_address_fields(self):
        snapshot = manual_snapshot(
            "  One-off customer  ", customer_code="M-1", customer_postal_code="12345",
            customer_contact="Synthetic Operator", customer_email="nobody@example.invalid",
            site_name="Demo Site", site_postal_code="67890",
            site_country="Exampleland", machine_name="Demo machine",
            machine_manufacturer="Demo Co", machine_serial="DEMO-001",
            machine_asset_tag="LOCAL",
        )
        self.assertEqual(snapshot.customer_name, "One-off customer")
        self.assertEqual(snapshot.site_postal_code, "67890")
        self.assertIsNone(snapshot.customer_id)
        self.assertIsNone(snapshot.machine_id)
        self.assertEqual(self.store.list_customers(), [])
        with self.assertRaises(ValueError):
            manual_snapshot("One-off", customer_id="must-not-link")
        with self.assertRaises(ValueError):
            manual_snapshot("One-off", unexpected="field")
        with self.assertRaises(ValueError):
            manual_snapshot("One-off", site_postal_code=42)

    def test_hierarchy_grouping_and_constant_query_count(self):
        # More than one site/customer: a N+1 query implementation violates
        # the bounded-query assertion below.
        for i in range(14):
            c = self.store.create_customer(f"Synthetic Customer {i:02d}")
            s = self.store.create_site(c, f"Site {i:02d}")
            self.store.create_machine(s, f"Machine {i:02d}", serial_number=f"SERIAL-{i:02d}")
        traces = []
        self.store.connection.set_trace_callback(traces.append)
        try:
            customers, sites, machines = self.store.list_hierarchy("")
        finally:
            self.store.connection.set_trace_callback(None)
        self.assertEqual(len(customers), 14)
        self.assertEqual(sum(map(len, sites.values())), 14)
        self.assertEqual(sum(map(len, machines.values())), 14)
        selects = [s for s in traces if s.strip().upper().startswith("SELECT")]
        self.assertEqual(len(selects), 3)
        # The customers query also contains a correlated "FROM sites";
        # count only the concrete grouped child SELECT statements.
        self.assertEqual(sum(q.lstrip().startswith("SELECT * FROM sites ") for q in selects), 1)
        self.assertEqual(sum(q.lstrip().startswith("SELECT * FROM machines ") for q in selects), 1)
        selected, child_sites, child_machines = self.store.list_hierarchy("SERIAL-09")
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(child_sites[selected[0]["id"]]), 1)
        self.assertEqual(len(child_machines), 1)
        self.assertEqual(self.store.list_hierarchy("not-found"), ([], {}, {}))

    def test_historical_m0_release_is_archived_manual_only_and_source_pinned(self):
        workflow = (Path(__file__).resolve().parents[1]
                    / ".github" / "workflows" / "windows-installer.yml").read_text(
                        encoding="utf-8",
                    )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotRegex(workflow, r"(?m)^  push:")
        self.assertIn("if: ${{ false }}", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertIn("M0_SOURCE_SHA: 1981d802194bb2619e689533ac35dabde0f706da", workflow)
        self.assertIn("ref: ${{ env.M0_SOURCE_SHA }}", workflow)
        self.assertIn('sha=$env:M0_SOURCE_SHA', workflow)
        self.assertIn('--target $env:M0_SOURCE_SHA', workflow)
        self.assertNotIn('sha=$env:GITHUB_SHA', workflow)
        self.assertNotIn('--target $env:GITHUB_SHA', workflow)


if __name__ == "__main__":
    unittest.main()
