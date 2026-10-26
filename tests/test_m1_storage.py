"""M1 uses only synthetic, non-identifying data."""
from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import date
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.model import LocalizedText, Module, Report
from reportmaker.reference import CustomerSnapshot, manual_snapshot
from reportmaker.storage import CustomerStore, SCHEMA_VERSION


class CustomerStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "customers.sqlite3"
        self.store = CustomerStore(self.path)
        self.addCleanup(self.store.close)
        self.customer_id = self.store.create_customer(
            "Synthetic Foods", code="TEST-01", city="Sample Town",
            contact_name="Example Operator")
        self.site_id = self.store.create_site(
            self.customer_id, "Synthetic Plant", address="123 Demo Avenue")
        self.machine_id = self.store.create_machine(
            self.site_id, "Synthetic Conveyor", serial_number="TEST-SN-001",
            manufacturer="Example Machines")

    def test_relationships_search_and_reopen(self):
        self.assertEqual(self.store.connection.execute("PRAGMA user_version").fetchone()[0],
                         SCHEMA_VERSION)
        self.assertEqual(self.store.list_customers("TEST-SN-001")[0]["id"], self.customer_id)
        self.assertEqual(self.store.list_sites(self.customer_id)[0]["id"], self.site_id)
        self.assertEqual(self.store.list_machines(self.site_id)[0]["id"], self.machine_id)
        with CustomerStore(self.path) as reopened:
            self.assertEqual(reopened.get("machines", self.machine_id)["serial_number"], "TEST-SN-001")
            self.assertEqual(reopened.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_validate_relationships_and_restrict_deletions(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_site("missing-customer", "Impossible")
        other = self.store.create_customer("Another Example Customer")
        with self.assertRaises(ValueError):
            self.store.capture_snapshot(other, site_id=self.site_id)
        with self.assertRaises(ValueError):
            self.store.capture_snapshot(self.customer_id, machine_id=self.machine_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.delete("customers", self.customer_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.delete("sites", self.site_id)

    def test_edits_are_local_and_report_snapshot_is_immutable(self):
        original = self.store.capture_snapshot(
            self.customer_id, site_id=self.site_id, machine_id=self.machine_id)
        self.store.save_report_reference("synthetic-report", original)
        self.store.update("customers", self.customer_id, name="New Display Name")
        self.store.update("machines", self.machine_id, serial_number="CHANGED")
        saved = self.store.load_report_reference("synthetic-report")
        self.assertEqual(saved.customer_name, "Synthetic Foods")
        self.assertEqual(saved.machine_serial, "TEST-SN-001")
        self.assertEqual(self.store.capture_snapshot(self.customer_id).customer_name,
                         "New Display Name")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_report_reference("synthetic-report", self.store.capture_snapshot(
                self.customer_id))
        with self.assertRaises(FrozenInstanceError):
            saved.customer_name = "Changed"
        self.assertEqual(CustomerSnapshot.from_dict(saved.to_dict()), saved)

    def test_manual_report_does_not_require_master_entry(self):
        snapshot = manual_snapshot("One-off Customer", machine_name="Portable line")
        report = Report(
            customer_id="", customer_snapshot=snapshot,
            start_date=date(2026, 10, 26), end_date=date(2026, 10, 26),
            primary_language="it", output_languages=["de", "fr-CA"],
            conclusion=Module(LocalizedText("it", "Conclusioni")))
        self.assertIs(report.customer_snapshot, snapshot)
        self.store.save_report_reference(report.id, snapshot)
        self.assertIsNone(self.store.load_report_reference(report.id).customer_id)

    def test_history_dates_and_foreign_keys(self):
        record = self.store.add_intervention(
            self.machine_id, "2026-10-10", end_date="2026-10-11",
            ticket="TEST-42", description="Synthetic adjustment")
        self.assertEqual(self.store.list_interventions(self.machine_id)[0]["id"], record)
        with self.assertRaises(ValueError):
            self.store.add_intervention(
                self.machine_id, "2026-10-12", end_date="2026-10-11")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.delete("machines", self.machine_id)

    def test_online_backup_and_integrity(self):
        self.store.add_intervention(self.machine_id, "2026-10-09")
        destination = Path(self.folder.name) / "backup.sqlite3"
        self.store.backup(destination)
        with CustomerStore(destination) as backup:
            self.assertEqual(len(backup.list_interventions(self.machine_id)), 1)
        with self.assertRaises(FileExistsError):
            self.store.backup(destination)

    def test_newer_schema_is_not_modified(self):
        future_path = Path(self.folder.name) / "future.sqlite3"
        with closing(sqlite3.connect(future_path)) as db:
            db.execute("PRAGMA user_version = 999")
        with self.assertRaises(RuntimeError):
            CustomerStore(future_path)
        # sqlite3's context manager commits but does NOT close on Windows.
        with closing(sqlite3.connect(future_path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 999)

    def test_invalid_names_updates_and_snapshot_shape(self):
        with self.assertRaises(ValueError):
            self.store.create_customer("  ")
        with self.assertRaises(ValueError):
            self.store.update("customers", self.customer_id, name="")
        with self.assertRaises(ValueError):
            self.store.update("customers", self.customer_id, id="changed")
        with self.assertRaises(ValueError):
            CustomerSnapshot.from_dict({"customer_name": "Example", "unexpected": 5})


if __name__ == "__main__":
    unittest.main()
