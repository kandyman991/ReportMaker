"""Read-only chooser for a detached customer/site/machine report reference.

This dialog only browses the existing local SQLite master database. Selecting a
row snapshots its live parent chain once; the report is not mutated until its
Report Information dialog explicitly applies a validated canonical command.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from ..reference import CustomerSnapshot
from ..storage import CustomerStore


def chosen_ids(item: QTreeWidgetItem) -> tuple[str, str | None, str | None]:
    """Read the selected row's parent chain, never infer ownership by text."""
    if item is None:
        raise ValueError("Select a customer, site or machine")
    ids = {}
    cursor = item
    while cursor is not None:
        value = cursor.data(0, Qt.ItemDataRole.UserRole)
        if (not isinstance(value, tuple) or len(value) != 2
                or value[0] not in ("customers", "sites", "machines")
                or not isinstance(value[1], str)):
            raise ValueError("Invalid database reference")
        ids[value[0]] = value[1]
        cursor = cursor.parent()
    if not ids.get("customers"):
        raise ValueError("Selection has no customer")
    if ids.get("machines") and not ids.get("sites"):
        raise ValueError("Selection has no parent site")
    return ids["customers"], ids.get("sites"), ids.get("machines")


class CustomerReferencePicker(QDialog):
    def __init__(self, store: CustomerStore, parent=None):
        super().__init__(parent)
        self.setObjectName("v2CustomerReferencePicker")
        self.setWindowTitle("Select from local customer database")
        self.resize(770, 520)
        self.store = store
        self.snapshot: CustomerSnapshot | None = None
        layout = QVBoxLayout(self)
        info = QLabel("Select a customer, site or machine. A detached copy of its "
                      "current details is saved in this report only after Apply.")
        info.setWordWrap(True)
        layout.addWidget(info)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        self.search = QLineEdit(self)
        self.search.setObjectName("v2CustomerSearch")
        self.search.setPlaceholderText("Customer, site, model or machine serial")
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("v2CustomerResults")
        self.tree.setHeaderLabels(["Customer / Site / Machine", "Location / Model", "Code / Serial"])
        self.tree.setColumnCount(3)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, parent=self)
        self.buttons.accepted.connect(self.choose)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.refresh()

    def refresh(self, *_args):
        try:
            customers, sites, machines = self.store.list_hierarchy(self.search.text())
        except (OSError, RuntimeError, ValueError) as exc:
            # Keep the visible selection; never silently select another record.
            self.status.setText("Cannot read local database: " + str(exc))
            return False
        self.tree.clear()
        for customer in customers:
            root = self._item(None, "customers", customer,
                              customer["name"], customer["city"], customer["code"])
            for site in sites.get(customer["id"], ()):
                site_item = self._item(root, "sites", site,
                                       site["name"], site["city"], site["address"])
                for machine in machines.get(site["id"], ()):
                    self._item(site_item, "machines", machine,
                               machine["name"], machine["model"],
                               machine["serial_number"])
        self.tree.expandAll()
        self.status.setText(f"{len(customers)} matching customers · selection is local only")
        return True

    def _item(self, parent, kind, record, title, extra, detail):
        row = QTreeWidgetItem([title, extra, detail])
        row.setData(0, Qt.ItemDataRole.UserRole, (kind, record["id"]))
        if parent is None:
            self.tree.addTopLevelItem(row)
        else:
            parent.addChild(row)
        return row

    def choose(self):
        try:
            customer, site, machine = chosen_ids(self.tree.currentItem())
            snapshot = self.store.capture_snapshot(
                customer, site_id=site, machine_id=machine)
        except (OSError, RuntimeError, ValueError, LookupError) as exc:
            self.status.setText("Selection rejected: " + str(exc))
            return False
        self.snapshot = snapshot
        self.accept()
        return True
