"""Deterministic, offline Windows GUI layout probe used in source and frozen CI.

This intentionally does not navigate to chatgpt.com or access user accounts.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import QCoreApplication, QEvent

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .ui import MainWindow, PANEL_NAMES


def run() -> int:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="reportmaker-layout-") as directory:
        settings_path = str(Path(directory) / "workspace.ini")
        w = MainWindow(
            load_website=False,
            settings=QSettings(settings_path, QSettings.Format.IniFormat),
            ephemeral_browser=True,
        )
        w.show()
        app.processEvents()
        chat_panel = w._panels["chat"]
        # Detect the screenshot regression: WebEngine occupies only a narrow band.
        assert chat_panel.height() > 300, "Chat panel did not receive usable height"
        assert w.browser.height() >= int(chat_panel.height() * 0.70), (
            f"Browser only {w.browser.height()}px high in {chat_panel.height()}px panel"
        )
        w.set_panel_visible("modules", False)
        app.processEvents()
        assert not w._panels["modules"].isVisible()
        assert w._panels["editor"].isVisible()
        w.set_panel_visible("modules", True)
        app.processEvents()
        assert w._panels["modules"].isVisible()
        w.toggle_maximize("chat")
        app.processEvents()
        assert w._panels["chat"].isVisible()
        assert not w._panels["editor"].isVisible()
        assert not w._panels["modules"].isVisible()
        w.toggle_maximize("chat")
        app.processEvents()
        assert all(w._panels[name].isVisible() for name in PANEL_NAMES)
        w.set_panel_visible("editor", False)
        w.close()
        w.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        reopened = MainWindow(
            load_website=False,
            settings=QSettings(settings_path, QSettings.Format.IniFormat),
            ephemeral_browser=True,
        )
        reopened.show()
        app.processEvents()
        assert not reopened._panels["editor"].isVisible(), "Visibility did not persist"
        reopened.reset_layout()
        app.processEvents()
        assert all(reopened._panels[name].isVisible() for name in PANEL_NAMES)
        reopened.close()
        app.processEvents()
    return 0
