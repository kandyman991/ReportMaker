"""Windows-first local master-data editor. No website, cloud or CAD access.

Master records are separate from the M0 scratchpad and the future report editor.
The reference preview is NOT a saved report; M2 will bind it to projects.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from .reference import manual_snapshot
from .storage import CustomerStore, FIELDS


LABELS = {
    "name": "Name *", "code": "Customer code", "address": "Street address",
    "city": "City", "postal_code": "Postal code", "country": "Country",
    "contact_name": "Contact", "contact_email": "Email", "contact_phone": "Phone",
    "notes": "Notes", "manufacturer": "Manufacturer", "model": "Model",
    "serial_number": "Serial number", "asset_tag": "Asset tag",
}


class RecordForm(QDialog):
    def __init__(self, table: str, values: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {table[:-1]}")
        self.resize(460, 400)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.controls = {}
        for name in FIELDS[table]:
            widget = QPlainTextEdit() if name == "notes" else QLineEdit()
            old = (values or {}).get(name, "")
            if isinstance(widget, QPlainTextEdit):
                widget.setPlainText(old)
                widget.setMaximumHeight(85)
            else:
                widget.setText(old)
                widget.setMaxLength(10000)
            form.addRow(LABELS.get(name, name), widget)
            self.controls[name] = widget
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            key: (control.toPlainText() if isinstance(control, QPlainTextEdit)
                  else control.text()).strip()
            for key, control in self.controls.items()
        }

    def _validate(self):
        if not self.values()["name"]:
            QMessageBox.warning(self, "Required value", "Enter a name.")
            return
        self.accept()


class HistoryDialog(QDialog):
    def __init__(self, store: CustomerStore, machine_id: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.machine_id = machine_id
        self.setWindowTitle("Machine intervention history")
        self.resize(860, 480)
        layout = QVBoxLayout(self)
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(
            ["Start", "End", "Ticket", "Technician", "Description"])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history)
        add = QPushButton("Add intervention")
        add.clicked.connect(self._add_intervention)
        layout.addWidget(add)
        self._refresh()

    def _refresh(self):
        rows = self.store.list_interventions(self.machine_id)
        self.history.setRowCount(len(rows))
        for index, entry in enumerate(rows):
            for column, key in enumerate(
                    ("start_date", "end_date", "ticket", "technician", "description")):
                self.history.setItem(
                    index, column, QTableWidgetItem(entry.get(key) or ""))
        self.history.resizeColumnsToContents()

    def _add_intervention(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("New intervention — local record")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        start = QDateEdit(QDate.currentDate())
        start.setCalendarPopup(True)
        finish = QDateEdit(QDate.currentDate())
        finish.setCalendarPopup(True)
        include_end = QCheckBox("Record end date")
        finish.setEnabled(False)
        include_end.toggled.connect(finish.setEnabled)
        ticket = QLineEdit()
        technician = QLineEdit()
        description = QPlainTextEdit()
        description.setMaximumHeight(100)
        for label, widget in (
            ("Start date", start), ("", include_end), ("End date", finish),
            ("Ticket", ticket), ("Technician", technician), ("Notes", description),
        ):
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.store.add_intervention(
                self.machine_id, start.date().toString(Qt.DateFormat.ISODate),
                end_date=(finish.date().toString(Qt.DateFormat.ISODate)
                          if include_end.isChecked() else None),
                ticket=ticket.text(), technician=technician.text(),
                description=description.toPlainText())
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Could not add intervention", str(error))
            return
        self._refresh()


class CustomerManagerDialog(QDialog):
    """Search/edit the hierarchy; master data never enters the ChatGPT panel."""

    def __init__(self, store: CustomerStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("ReportMaker — Local customer database (M1)")
        self.resize(970, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Local records only. No data is uploaded. Report editing/export follows in M2–M4."))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search customers, sites, machine names, models or serial numbers")
        self.search.textChanged.connect(self.refresh)
        top.addWidget(QLabel("Search"))
        top.addWidget(self.search, 1)
        layout.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Customer / Site / Machine", "Location / Model", "Code / Serial"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)
        buttons = QHBoxLayout()
        self.actions = {}
        for label, callback in (
            ("Add customer", self.add_customer), ("Add site", self.add_site),
            ("Add machine", self.add_machine), ("Edit selected", self.edit_selected),
            ("Delete selected", self.delete_selected), ("Machine history", self.history),
            ("Preview reference", self.preview_reference),
            ("Manual reference", self.manual_reference), ("Backup database", self.backup),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
            self.actions[label] = button
        layout.addLayout(buttons)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self, *_args, selected: tuple[str, str] | None = None):
        self.tree.clear()
        selected_item = None
        customers = self.store.list_customers(self.search.text())
        for customer in customers:
            customer_item = self._item(None, "customers", customer,
                                       customer["name"], customer["city"],
                                       customer["code"])
            if selected == ("customers", customer["id"]):
                selected_item = customer_item
            for site in self.store.list_sites(customer["id"]):
                site_item = self._item(customer_item, "sites", site,
                                       site["name"], site["city"], site["address"])
                if selected == ("sites", site["id"]):
                    selected_item = site_item
                for machine in self.store.list_machines(site["id"]):
                    machine_item = self._item(site_item, "machines", machine,
                                              machine["name"], machine["model"],
                                              machine["serial_number"])
                    if selected == ("machines", machine["id"]):
                        selected_item = machine_item
        self.tree.expandAll()
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)
        self.tree.resizeColumnToContents(0)
        self.status.setText(f"{len(customers)} customer(s) matching search")
        self._selection_changed()

    def _item(self, parent, kind, record, name, extra, identifier):
        item = QTreeWidgetItem([name, extra, identifier])
        item.setData(0, Qt.ItemDataRole.UserRole, (kind, record["id"]))
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _selected(self) -> tuple[str, str] | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self):
        selected = self._selected()
        self.actions["Add site"].setEnabled(selected is not None)
        self.actions["Add machine"].setEnabled(
            selected is not None and selected[0] != "customers")
        for label in ("Edit selected", "Delete selected", "Preview reference"):
            self.actions[label].setEnabled(selected is not None)
        self.actions["Machine history"].setEnabled(
            selected is not None and selected[0] == "machines")

    def _ancestors(self):
        selected = self._selected()
        if selected is None:
            return None, None, None
        table, identifier = selected
        if table == "customers":
            return identifier, None, None
        if table == "sites":
            site = self.store.get("sites", identifier)
            return site["customer_id"], identifier, None
        machine = self.store.get("machines", identifier)
        site = self.store.get("sites", machine["site_id"])
        return site["customer_id"], site["id"], identifier

    def _safe(self, action):
        try:
            return action()
        except (LookupError, ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Local database operation failed", str(error))
            return None

    def add_customer(self):
        dialog = RecordForm("customers", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = self._safe(lambda: self.store.create_customer(**dialog.values()))
        if identifier:
            self.search.clear()
            self.refresh(selected=("customers", identifier))

    def add_site(self):
        if self._selected() is None:
            return
        customer, _, _ = self._ancestors()
        dialog = RecordForm("sites", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = self._safe(lambda: self.store.create_site(customer, **dialog.values()))
        if identifier:
            self.search.clear()
            self.refresh(selected=("sites", identifier))

    def add_machine(self):
        if self._selected() is None or self._selected()[0] == "customers":
            return
        _, site, _ = self._ancestors()
        dialog = RecordForm("machines", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = self._safe(lambda: self.store.create_machine(site, **dialog.values()))
        if identifier:
            self.search.clear()
            self.refresh(selected=("machines", identifier))

    def edit_selected(self):
        selected = self._selected()
        if selected is None:
            return
        table, identifier = selected
        record = self.store.get(table, identifier)
        dialog = RecordForm(table, values=record, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._safe(lambda: self.store.update(table, identifier, **dialog.values())) is None:
            # update() returns None on success; _safe reports errors separately.
            self.refresh(selected=selected)

    def delete_selected(self):
        selected = self._selected()
        if selected is None:
            return
        table, identifier = selected
        reply = QMessageBox.question(
            self, "Delete local record",
            "Delete this record? Records with linked sites, machines or history "
            "cannot be deleted. Saved report reference snapshots are retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._safe(lambda: self.store.delete(table, identifier))
        self.refresh()

    def history(self):
        selected = self._selected()
        if selected is None or selected[0] != "machines":
            return
        HistoryDialog(self.store, selected[1], self).exec()

    def preview_reference(self):
        if self._selected() is None:
            return
        customer, site, machine = self._ancestors()
        snapshot = self._safe(lambda: self.store.capture_snapshot(
            customer, site_id=site, machine_id=machine))
        if snapshot is None:
            return
        self._show_snapshot(snapshot)

    def manual_reference(self):
        """One-off customers are not silently inserted into the master database."""
        name, accepted = QInputDialog.getText(
            self, "Manual report reference", "Customer name (one-off):")
        if not accepted or not name.strip():
            return
        site, ok = QInputDialog.getText(self, "Manual reference", "Site (optional):")
        if not ok:
            return
        machine, ok = QInputDialog.getText(self, "Manual reference", "Machine (optional):")
        if not ok:
            return
        self._show_snapshot(manual_snapshot(name, site_name=site, machine_name=machine))

    def _show_snapshot(self, snapshot):
        message = QMessageBox(self)
        message.setWindowTitle("Immutable reference preview — M1")
        message.setText(
            "This is a detached reference preview. M2 will attach it to a saved report. "
            "It is NOT yet a saved report.")
        message.setDetailedText(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
        message.exec()

    def backup(self):
        target, _ = QFileDialog.getSaveFileName(
            self, "Create local SQLite backup", "reportmaker-backup.sqlite3",
            "SQLite databases (*.sqlite3)")
        if not target:
            return
        result = self._safe(lambda: self.store.backup(Path(target)))
        if result:
            QMessageBox.information(self, "Local backup complete",
                                    f"Backup created at:\n{result}")
