"""Windows-first local master-data editor. No website, cloud or CAD access.

Customers, sites, machines and intervention history live in a local SQLite
database, separate from any report project. Reports only ever receive a frozen
snapshot of a record (see ``reference.CustomerSnapshot``), so editing master
data never changes an existing report.

This module was ported from the V1 shell; ``reportmaker.customer_ui`` remains
as a thin compatibility import until V1 is removed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..reference import manual_snapshot
from ..storage import CustomerStore, FIELDS


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


class ManualReferenceForm(QDialog):
    """Full local one-off customer/site/machine entry, without a DB record."""

    GROUPS = (
        ("Customer", (
            ("customer_name", "Name *"), ("customer_code", "Code"),
            ("customer_address", "Address"), ("customer_postal_code", "Postal code"),
            ("customer_city", "City"), ("customer_country", "Country"),
            ("customer_contact", "Contact"), ("customer_email", "Email"),
            ("customer_phone", "Phone"),
        )),
        ("Site", (
            ("site_name", "Name"), ("site_address", "Address"),
            ("site_postal_code", "Postal code"), ("site_city", "City"),
            ("site_country", "Country"), ("site_contact", "Contact"),
            ("site_email", "Email"), ("site_phone", "Phone"),
        )),
        ("Machine", (
            ("machine_name", "Name"), ("machine_manufacturer", "Manufacturer"),
            ("machine_model", "Model"), ("machine_serial", "Serial number"),
            ("machine_asset_tag", "Asset tag"),
        )),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual customer/site/machine reference — no master record")
        self.resize(620, 590)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("This is an unsaved reference preview, not a report."))
        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        content = QWidget()
        section_layout = QVBoxLayout(content)
        self.controls: dict[str, QLineEdit] = {}
        for section, items in self.GROUPS:
            group = QGroupBox(section)
            form = QFormLayout(group)
            for key, label in items:
                editor = QLineEdit(group)
                editor.setMaxLength(10000)
                form.addRow(label, editor)
                self.controls[key] = editor
            section_layout.addWidget(group)
        scroller.setWidget(content)
        layout.addWidget(scroller, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self):
        if not self.controls["customer_name"].text().strip():
            QMessageBox.warning(self, "Required value", "Enter a customer name.")
            return
        self.accept()

    def snapshot(self):
        values = {key: editor.text() for key, editor in self.controls.items()}
        return manual_snapshot(values.pop("customer_name"), **values)


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
        try:
            rows = self.store.list_interventions(self.machine_id)
        except (LookupError, ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Could not load machine history", str(error))
            return
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
    """Search/edit the hierarchy; master data never enters the AI browser panel."""

    def __init__(self, store: CustomerStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Customers, sites and machines")
        self.resize(970, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Local records only. No data is uploaded. Reports keep a frozen copy of the "
            "record they use, so editing it here never changes an existing report."))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search customers, sites, machine names, models or serial numbers")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        top.addWidget(QLabel("Search"))
        top.addWidget(self.search, 1)
        layout.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Customer / Site / Machine", "Location / Model", "Code / Serial"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)
        buttons = QGridLayout()
        self.actions = {}
        for position, (label, callback) in enumerate((
            ("Add customer", self.add_customer), ("Add site", self.add_site),
            ("Add machine", self.add_machine), ("Edit selected", self.edit_selected),
            ("Delete selected", self.delete_selected), ("Machine history", self.history),
            ("Preview reference", self.preview_reference),
            ("Manual reference", self.manual_reference), ("Backup database", self.backup),
        )):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button, position // 3, position % 3)
            self.actions[label] = button
        layout.addLayout(buttons)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self, *_args, selected: tuple[str, str] | None = None):
        # Read *before* clearing current contents: on SQLite failure, preserve
        # the existing tree, selection and user context.
        hierarchy = self._safe(lambda: self.store.list_hierarchy(self.search.text()))
        if hierarchy is None:
            return
        customers, sites, machines = hierarchy
        self.tree.clear()
        selected_item = None
        for customer in customers:
            customer_item = self._item(None, "customers", customer,
                                       customer["name"], customer["city"],
                                       customer["code"])
            if selected == ("customers", customer["id"]):
                selected_item = customer_item
            for site in sites.get(customer["id"], ()):
                site_item = self._item(customer_item, "sites", site,
                                       site["name"], site["city"], site["address"])
                if selected == ("sites", site["id"]):
                    selected_item = site_item
                for machine in machines.get(site["id"], ()):
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

    def _safe(self, action, *, success_marker=False):
        try:
            result = action()
            # update/delete return None on success, which otherwise looks like
            # the failure sentinel used by this error-reporting wrapper.
            return True if success_marker else result
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
            self._search_timer.stop()
            self.refresh(selected=("customers", identifier))

    def add_site(self):
        if self._selected() is None:
            return
        ancestors = self._safe(self._ancestors)
        if ancestors is None:
            return
        customer, _, _ = ancestors
        dialog = RecordForm("sites", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = self._safe(lambda: self.store.create_site(customer, **dialog.values()))
        if identifier:
            self.search.clear()
            self._search_timer.stop()
            self.refresh(selected=("sites", identifier))

    def add_machine(self):
        if self._selected() is None or self._selected()[0] == "customers":
            return
        ancestors = self._safe(self._ancestors)
        if ancestors is None:
            return
        _, site, _ = ancestors
        dialog = RecordForm("machines", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        identifier = self._safe(lambda: self.store.create_machine(site, **dialog.values()))
        if identifier:
            self.search.clear()
            self._search_timer.stop()
            self.refresh(selected=("machines", identifier))

    def edit_selected(self):
        selected = self._selected()
        if selected is None:
            return
        table, identifier = selected
        record = self._safe(lambda: self.store.get(table, identifier))
        if record is None:
            return
        dialog = RecordForm(table, values=record, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._safe(lambda: self.store.update(table, identifier, **dialog.values()),
                      success_marker=True):
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
        if self._safe(lambda: self.store.delete(table, identifier), success_marker=True):
            self.refresh()

    def history(self):
        selected = self._selected()
        if selected is None or selected[0] != "machines":
            return
        HistoryDialog(self.store, selected[1], self).exec()

    def preview_reference(self):
        if self._selected() is None:
            return
        ancestors = self._safe(self._ancestors)
        if ancestors is None:
            return
        customer, site, machine = ancestors
        snapshot = self._safe(lambda: self.store.capture_snapshot(
            customer, site_id=site, machine_id=machine))
        if snapshot is None:
            return
        self._show_snapshot(snapshot)

    def manual_reference(self):
        """One-off details are previewed without creating master records."""
        form = ManualReferenceForm(self)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        snapshot = self._safe(form.snapshot)
        if snapshot is not None:
            self._show_snapshot(snapshot)

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
