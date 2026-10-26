"""Synthetic offline smoke test of the actual Qt customer editor (Windows CI).

No ChatGPT navigation or browser profile. No customer data leaves the temp dir.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDialog

from .customer_ui import CustomerManagerDialog
from .storage import CustomerStore
from .ui import MainWindow


def run() -> int:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="reportmaker-m1-smoke-") as folder:
        with CustomerStore(Path(folder) / "synthetic.sqlite3") as db:
            customer = db.create_customer("Synthetic Bakery", city="Test City")
            site = db.create_site(customer, "Sample Site")
            machine = db.create_machine(site, "Sample Line", serial_number="SN-TEST-123")
            dialog = CustomerManagerDialog(db)
            dialog.show()
            app.processEvents()
            assert dialog.tree.topLevelItemCount() == 1
            customer_item = dialog.tree.topLevelItem(0)
            assert customer_item.childCount() == 1
            assert customer_item.child(0).childCount() == 1
            machine_item = customer_item.child(0).child(0)
            dialog.tree.setCurrentItem(machine_item)
            app.processEvents()
            assert dialog.actions["Machine history"].isEnabled()
            assert dialog._ancestors() == (customer, site, machine)
            # A failed DB edit must show an error without pretending to refresh
            # successfully or discarding the currently selected record.
            with patch("reportmaker.customer_ui.RecordForm.exec",
                       return_value=QDialog.DialogCode.Accepted), \
                 patch("reportmaker.customer_ui.RecordForm.values",
                       return_value={"name": "New value"}), \
                 patch.object(db, "update",
                              side_effect=sqlite3.OperationalError("synthetic failure")), \
                 patch("reportmaker.customer_ui.QMessageBox.warning") as warning, \
                 patch.object(dialog, "refresh") as refresh:
                dialog.edit_selected()
                assert warning.called
                refresh.assert_not_called()
            dialog.search.setText("SN-TEST-123")
            app.processEvents()
            assert dialog.tree.topLevelItemCount() == 1
            dialog.search.setText("nonexistent fixture")
            app.processEvents()
            assert dialog.tree.topLevelItemCount() == 0
            dialog.close()
            dialog.deleteLater()
            app.processEvents()
        shell = MainWindow(
            load_website=False, ephemeral_browser=True,
            settings=QSettings(str(Path(folder) / "workspace.ini"),
                               QSettings.Format.IniFormat))
        shell.show()
        app.processEvents()
        assert shell.findChild(QAction, "customerManagerAction") is not None
        # Opening a malformed/locked local DB must not escape into the Qt loop.
        with patch("reportmaker.storage.CustomerStore",
                   side_effect=sqlite3.DatabaseError("synthetic corrupted database")), \
             patch("PySide6.QtWidgets.QMessageBox.critical") as critical:
            shell._open_customers()
            assert critical.called
        assert shell.browser.url().toString() != "https://chatgpt.com/"
        shell.close()
        shell.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return 0
