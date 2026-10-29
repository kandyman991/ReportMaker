"""M6 report information form with a single canonical, undoable commit.

No database identity is invented: database-backed snapshots keep their IDs;
manually entered snapshots remain detached, portable and project-local.
"""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox,
)

from ..reference import manual_snapshot
from .commands import CommandIntent

_TYPES = (
    ("supervision", "Supervision"),
    ("ordinary_maintenance", "Ordinary maintenance"),
    ("extraordinary_maintenance", "Extraordinary maintenance"),
    ("other", "Other"),
)


class ReportInfoDialog(QDialog):
    def __init__(self, session, gateway, parent=None, *, database_path: Path | None = None):
        super().__init__(parent)
        self.setObjectName("v2ReportInfo")
        self.setWindowTitle("Report information")
        self.session, self.gateway = session, gateway
        self.database_path = database_path
        report = session.report_snapshot()
        self._revision, self._generation = session.revision, session.generation
        self._snapshot = report.customer_snapshot
        layout = QVBoxLayout(self)
        info = QLabel(
            "Report information is shared by Modules, Editor and exports. "
            "Apply commits one undoable canonical change.")
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        self.fields = {}
        for key, label, value in (
            ("title", "Report title", report.title.original),
            ("customer_name", "Customer", self._snapshot.customer_name if self._snapshot else ""),
            ("site_name", "Site", self._snapshot.site_name if self._snapshot else ""),
            ("machine_name", "Machine", self._snapshot.machine_name if self._snapshot else ""),
            ("machine_serial", "Serial number", self._snapshot.machine_serial if self._snapshot else ""),
            ("ticket", "Reference ticket", report.ticket),
            ("technicians", "Personnel (comma-separated)", ", ".join(report.technicians)),
            ("other_intervention_detail", "Other intervention detail", report.other_intervention_detail),
            ("primary_language", "Source language tag", report.primary_language),
            ("output_languages", "Export language tags (comma-separated)",
             ", ".join(report.output_languages)),
        ):
            control = QLineEdit(str(value), self)
            control.setObjectName("v2Info_" + key)
            form.addRow(label, control)
            self.fields[key] = control

        for key, label, value in (
            ("created_date", "Creation date", report.created_date),
            ("start_date", "Intervention start", report.start_date),
            ("end_date", "Intervention end", report.end_date),
        ):
            control = QDateEdit(self)
            control.setObjectName("v2Info_" + key)
            control.setDisplayFormat("yyyy-MM-dd")
            control.setCalendarPopup(True)
            control.setDate(QDate(value.year, value.month, value.day))
            form.addRow(label, control)
            self.fields[key] = control

        self.types = {}
        for key, label in _TYPES:
            control = QCheckBox(label, self)
            control.setObjectName("v2InfoType_" + key)
            control.setChecked(key in report.intervention_types)
            form.addRow("Intervention type", control)
            self.types[key] = control
        layout.addLayout(form)
        reference_buttons = QHBoxLayout()
        choose_db = QPushButton("Choose from local database…", self)
        choose_db.setObjectName("v2ChooseCustomerDatabase")
        choose_db.clicked.connect(self.choose_database)
        reference_buttons.addWidget(choose_db)
        choose_manual = QPushButton("Use one-off manual details", self)
        choose_manual.setObjectName("v2ChooseManualCustomer")
        choose_manual.clicked.connect(self.use_manual)
        reference_buttons.addWidget(choose_manual)
        layout.addLayout(reference_buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.apply_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_database(self):
        """Stage a frozen reference; only Apply changes the report project."""
        from ..storage import CustomerStore
        from .reference_picker import CustomerReferencePicker
        try:
            with CustomerStore(self.database_path) as store:
                picker = CustomerReferencePicker(store, self)
                if picker.exec() != QDialog.DialogCode.Accepted or picker.snapshot is None:
                    return False
                selected = picker.snapshot
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            self.status.setText("Local customer database unavailable: " + str(exc))
            return False
        self._snapshot = selected
        for key in ("customer_name", "site_name", "machine_name", "machine_serial"):
            self.fields[key].setText(getattr(selected, key))
        self.status.setText("Detached database snapshot staged. Apply to save it in this report.")
        return True

    def use_manual(self):
        # Remove master linkage but retain all existing snapshot-only address,
        # contact and machine fields, including those not visible in this form.
        # No master record is edited or silently discarded.
        if self._snapshot is not None:
            from dataclasses import fields
            from ..reference import CustomerSnapshot
            details = {
                item.name: getattr(self._snapshot, item.name)
                for item in fields(CustomerSnapshot)
                if item.name not in {
                    "customer_name", "customer_id", "site_id", "machine_id",
                    "captured_at", "schema_version"
                }
            }
            self._snapshot = manual_snapshot(self._snapshot.customer_name, **details)
        self.status.setText(
            "Manual customer mode staged. Existing snapshot details are retained "
            "without database IDs only after Apply.")
        return True

    def _build_args(self):
        get = lambda key: self.fields[key].text().strip()
        if self._snapshot is None:
            snapshot = manual_snapshot(
                get("customer_name"), site_name=get("site_name"),
                machine_name=get("machine_name"), machine_serial=get("machine_serial"))
        else:
            # Frozen database IDs remain untouched; never adopt a new master
            # or rewrite its current customer/site/machine details.
            snapshot = replace(
                self._snapshot, customer_name=get("customer_name"),
                site_name=get("site_name"), machine_name=get("machine_name"),
                machine_serial=get("machine_serial"))
        return {
            "title": get("title"),
            "created_date": self.fields["created_date"].date().toPython(),
            "start_date": self.fields["start_date"].date().toPython(),
            "end_date": self.fields["end_date"].date().toPython(),
            "ticket": get("ticket"),
            "technicians": [value.strip() for value in get("technicians").split(",")
                            if value.strip()],
            "intervention_types": [key for key, control in self.types.items()
                                   if control.isChecked()],
            "other_intervention_detail": get("other_intervention_detail"),
            "customer_snapshot": snapshot,
            "customer_id": snapshot.customer_id,
            "primary_language": get("primary_language"),
            "output_languages": [value.strip() for value in get("output_languages").split(",")
                                 if value.strip()],
        }

    def apply_changes(self):
        try:
            args = self._build_args()
            source = self.session.report_snapshot().primary_language
            target = args["primary_language"]
            if source.casefold() != target.casefold():
                answer = QMessageBox.question(
                    self, "Confirm original-language relabel",
                    "The report already contains original text labeled as " + source +
                    ". Changing the primary source to " + target +
                    " does NOT translate any words. It relabels all original "
                    "fields as " + target + " and marks existing translations stale. "
                    "Continue only if the existing original text is already "
                    "written in the new language. Translations targeting that "
                    "language will block this operation to prevent data loss.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    self.status.setText("Source-language change cancelled; original content unchanged.")
                    return False
                args["relabel_source_language"] = True
            self.gateway.execute(CommandIntent(
                "set_report_metadata", None, args, self._revision, self._generation))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.status.setText("Report information not applied: " + str(exc))
            return False
        self.accept()
        return True
