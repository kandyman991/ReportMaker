"""Synthetic offline smoke test of the actual Qt customer editor (Windows CI).

No ChatGPT navigation or browser profile. No customer data leaves the temp dir.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

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
        assert shell.browser.url().toString() != "https://chatgpt.com/"
        shell.close()
        shell.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return 0
