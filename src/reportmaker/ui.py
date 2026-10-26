"""M0 shell to assess Windows UI and browser compatibility.

WARNING: no report project save/export or customer database at this stage.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView


CHAT_URL = QUrl("https://chatgpt.com/")


class MainWindow(QMainWindow):
    """Resizable prototype only: scratchpad notes are not persisted."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ReportMaker — M0 Browser Compatibility Prototype")
        self.resize(1450, 850)
        self._notes: dict[str, str] = {}
        self._build_interface()

    def _new_item(self, title: str) -> QListWidgetItem:
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, uuid4().hex)
        self._notes[item.data(Qt.ItemDataRole.UserRole)] = ""
        return item

    def _build_interface(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(splitter)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("MODULES — IN-MEMORY DEMO"))
        self.modules = QListWidget(left)
        self.modules.addItem(self._new_item("Intervention module"))
        self.modules.addItem(self._new_item("Conclusions (always last)"))
        left_layout.addWidget(self.modules)
        add = QPushButton("Add intervention module", left)
        add.clicked.connect(self._add_module)
        left_layout.addWidget(add)
        splitter.addWidget(left)

        center = QWidget(self)
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(QLabel("MODULE SCRATCHPAD — NOT SAVED TO DISK"))
        self.editor = QPlainTextEdit(center)
        self.editor.setPlaceholderText("Write technical notes or paste text manually from the browser.")
        center_layout.addWidget(self.editor)
        paste = QPushButton("Paste clipboard text into selected module", center)
        paste.clicked.connect(self._paste_clipboard)
        center_layout.addWidget(paste)
        splitter.addWidget(center)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("CHATGPT WEBSITE — MANUAL LOGIN AND COPY/PASTE"))
        open_external = QPushButton("Open ChatGPT in default browser", right)
        open_external.clicked.connect(lambda: QDesktopServices.openUrl(CHAT_URL))
        right_layout.addWidget(open_external)
        self.browser = QWebEngineView(right)
        self.profile = QWebEngineProfile("reportmaker-chatgpt", self)
        root = Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        ))
        profile_root = root / "browser"
        profile_root.mkdir(parents=True, exist_ok=True)
        self.profile.setPersistentStoragePath(str(profile_root / "storage"))
        self.profile.setCachePath(str(profile_root / "cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        self.browser_page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.browser_page)
        right_layout.addWidget(self.browser)
        self.browser_origin = QLabel("Website origin: loading...")
        right_layout.addWidget(self.browser_origin)
        self.browser_status = QLabel("Browser compatibility and website login are not yet verified.")
        right_layout.addWidget(self.browser_status)
        # Construct labels before setting the initial URL: urlChanged may emit synchronously.
        self.browser.loadFinished.connect(self._web_loaded)
        self.browser.urlChanged.connect(self._show_browser_origin)
        self.browser.setUrl(CHAT_URL)
        splitter.addWidget(right)
        splitter.setSizes([235, 530, 685])
        splitter.setChildrenCollapsible(False)

        self.modules.currentItemChanged.connect(self._on_module_change)
        self.modules.setCurrentRow(0)
        self._active_item = self.modules.currentItem()
        self.statusBar().showMessage(
            "M0 shell: no database, DOCX export, credential capture or AI API."
        )

    def _show_browser_origin(self, url: QUrl) -> None:
        # Show a trustworthy origin indicator without exposing URL query secrets.
        origin = f"{url.scheme()}://{url.host()}" if url.host() else "(unknown)"
        if url.scheme() != "https":
            origin = f"WARNING — non-HTTPS website: {origin}"
        self.browser_origin.setText(f"Website origin: {origin}")

    def _web_loaded(self, succeeded: bool) -> None:
        if succeeded:
            self.browser_status.setText(
                "Page loaded. Login functionality requires a manual Windows test."
            )
        else:
            self.browser_status.setText(
                "Web page failed to load. Try the default-browser button."
            )

    def _on_module_change(self, current: QListWidgetItem | None,
                          previous: QListWidgetItem | None) -> None:
        if previous is not None:
            old_id = previous.data(Qt.ItemDataRole.UserRole)
            self._notes[old_id] = self.editor.toPlainText()
        self._active_item = current
        self.editor.setPlainText(
            self._notes.get(current.data(Qt.ItemDataRole.UserRole), "")
            if current is not None else ""
        )

    def _add_module(self) -> None:
        title, ok = QInputDialog.getText(self, "New module", "Module title:")
        if not ok or not title.strip():
            return
        item = self._new_item(title.strip())
        before_conclusion = max(0, self.modules.count() - 1)
        self.modules.insertItem(before_conclusion, item)
        self.modules.setCurrentItem(item)

    def _paste_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if text:
            # Always insert as plain text. No HTML, scripts or automatic scraping.
            self.editor.insertPlainText(text)

    def closeEvent(self, event) -> None:
        # Disconnect page before profile teardown so Chromium can flush profile.
        self.browser.setPage(QWebEnginePage(self.browser))
        self.browser_page.deleteLater()
        super().closeEvent(event)
