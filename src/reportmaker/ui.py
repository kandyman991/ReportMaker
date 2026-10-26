"""ReportMaker M0 desktop shell.

The three panes are locally adjustable, collapsible and maximizable. Neither
website contents nor CAD/customer data are read by the layout manager.
The module scratchpad is a temporary demo and is not persisted to disk.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QPlainTextEdit, QPushButton, QSizePolicy,
    QSplitter, QToolBar, QVBoxLayout, QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView


CHAT_URL = QUrl("https://chatgpt.com/")
PANEL_NAMES = ("modules", "editor", "chat")
DEFAULT_WIDTHS = (245, 570, 635)


def _bool_setting(value: object) -> bool:
    """QSettings uses strings for some INI backends."""
    return value is True or str(value).strip().lower() in ("true", "1", "yes")


class MainWindow(QMainWindow):
    """Resizable Windows prototype with a regular website, not an AI API."""

    def __init__(
        self,
        *,
        load_website: bool = True,
        settings: QSettings | None = None,
        browser_profile_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("ReportMaker — M0 Browser Compatibility Prototype")
        self.resize(1450, 850)
        self.settings = settings if settings is not None else QSettings("ReportMaker", "ReportMaker")
        self._notes: dict[str, str] = {}
        self._panels: dict[str, QWidget] = {}
        self._visibility_actions: dict[str, QAction] = {}
        self._max_buttons: dict[str, QPushButton] = {}
        self._maximized_panel: str | None = None
        self._applying_layout = False
        self._widths = self._read_widths()
        self._visible = {
            name: _bool_setting(self.settings.value(f"workspace/{name}/visible", True))
            for name in PANEL_NAMES
        }
        self._build_interface(browser_profile_root)
        geometry = self.settings.value("workspace/window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        # QWidget sizes are not reliable until the window has been shown.
        QTimer.singleShot(0, self._apply_layout)
        if load_website:
            self.browser.setUrl(CHAT_URL)

    def _read_widths(self) -> list[int]:
        stored = self.settings.value("workspace/panel_widths", list(DEFAULT_WIDTHS))
        if not isinstance(stored, (list, tuple)) or len(stored) != 3:
            return list(DEFAULT_WIDTHS)
        try:
            widths = [int(value) for value in stored]
        except (TypeError, ValueError):
            return list(DEFAULT_WIDTHS)
        return widths if all(width > 0 for width in widths) else list(DEFAULT_WIDTHS)

    def _new_item(self, title: str) -> QListWidgetItem:
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, uuid4().hex)
        self._notes[item.data(Qt.ItemDataRole.UserRole)] = ""
        return item

    def _panel_header(self, name: str, title: str, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        label = QLabel(title)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(0)
        row.addWidget(label, 1)
        hide = QPushButton("Hide")
        hide.setToolTip(f"Collapse {name} panel; use the top toolbar to show it again")
        hide.clicked.connect(lambda checked=False, key=name: self.set_panel_visible(key, False))
        row.addWidget(hide)
        maximize = QPushButton("Maximize")
        maximize.setToolTip(f"Temporarily show only the {name} panel")
        maximize.clicked.connect(lambda checked=False, key=name: self.toggle_maximize(key))
        self._max_buttons[name] = maximize
        row.addWidget(maximize)
        layout.addLayout(row)

    def _make_panel(self, name: str, title: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget(self.splitter)
        panel.setObjectName(f"panel_{name}")
        panel.setMinimumSize(0, 0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self._panel_header(name, title, layout)
        self._panels[name] = panel
        self.splitter.addWidget(panel)
        self.splitter.setCollapsible(self.splitter.indexOf(panel), True)
        return panel, layout

    def _build_interface(self, browser_profile_root: Path | None) -> None:
        toolbar = QToolBar("Workspace", self)
        toolbar.setObjectName("workspaceToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for name, label in (("modules", "Modules"), ("editor", "Editor"), ("chat", "ChatGPT")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, key=name: self.set_panel_visible(key, checked))
            self._visibility_actions[name] = action
            toolbar.addAction(action)
        toolbar.addSeparator()
        reset = QAction("Reset layout", self)
        reset.triggered.connect(self.reset_layout)
        toolbar.addAction(reset)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.setChildrenCollapsible(True)
        self.splitter.setHandleWidth(7)
        self.setCentralWidget(self.splitter)

        _, left_layout = self._make_panel("modules", "MODULES — IN-MEMORY DEMO")
        self.modules = QListWidget()
        self.modules.addItem(self._new_item("Intervention module"))
        self.modules.addItem(self._new_item("Conclusions (always last)"))
        left_layout.addWidget(self.modules, 1)
        add = QPushButton("Add intervention module")
        add.clicked.connect(self._add_module)
        left_layout.addWidget(add)

        _, center_layout = self._make_panel("editor", "MODULE SCRATCHPAD — NOT SAVED")
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Write notes or paste approved text from ChatGPT manually.")
        center_layout.addWidget(self.editor, 1)
        paste = QPushButton("Paste clipboard text into selected module")
        paste.clicked.connect(self._paste_clipboard)
        center_layout.addWidget(paste)

        _, right_layout = self._make_panel("chat", "CHATGPT WEBSITE — MANUAL COPY/PASTE")
        external = QPushButton("Open ChatGPT in default browser")
        external.clicked.connect(lambda: QDesktopServices.openUrl(CHAT_URL))
        right_layout.addWidget(external)
        self.browser = QWebEngineView()
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.browser.setMinimumSize(0, 0)
        self.profile = QWebEngineProfile("reportmaker-chatgpt", self)
        root = browser_profile_root
        if root is None:
            root = Path(QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )) / "browser"
        root.mkdir(parents=True, exist_ok=True)
        self.profile.setPersistentStoragePath(str(root / "storage"))
        self.profile.setCachePath(str(root / "cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        self.browser_page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.browser_page)
        # Critical regression fix: the browser takes ALL spare vertical space.
        right_layout.addWidget(self.browser, 1)
        info = QHBoxLayout()
        self.browser_status = QLabel("Browser login not yet validated on Windows.")
        self.browser_origin = QLabel("Origin: loading...")
        for label in (self.browser_status, self.browser_origin):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            label.setMinimumWidth(0)
            label.setMaximumHeight(24)
            info.addWidget(label)
        right_layout.addLayout(info)
        self.browser.loadFinished.connect(self._web_loaded)
        self.browser.urlChanged.connect(self._show_browser_origin)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 4)
        self.splitter.splitterMoved.connect(self._capture_widths)
        self.modules.currentItemChanged.connect(self._on_module_change)
        self.modules.setCurrentRow(0)
        self.statusBar().showMessage(
            "M0 preview — no saved reports, DOCX export, AI API or website automation."
        )

    def _capture_widths(self, *_args) -> None:
        if self._applying_layout or self._maximized_panel is not None:
            return
        for index, (name, width) in enumerate(zip(PANEL_NAMES, self.splitter.sizes())):
            if self._visible[name] and width > 0:
                self._widths[index] = width

    def _apply_layout(self) -> None:
        if self._applying_layout:
            return
        self._applying_layout = True
        try:
            active = {
                name: self._visible[name] and (
                    self._maximized_panel is None or name == self._maximized_panel
                )
                for name in PANEL_NAMES
            }
            for name, panel in self._panels.items():
                panel.setVisible(active[name])
            self.splitter.setSizes([
                self._widths[index] if active[name] else 0
                for index, name in enumerate(PANEL_NAMES)
            ])
            for name, action in self._visibility_actions.items():
                old = action.blockSignals(True)
                action.setChecked(active[name])
                action.blockSignals(old)
            for name, button in self._max_buttons.items():
                button.setText("Restore" if self._maximized_panel == name else "Maximize")
        finally:
            self._applying_layout = False

    def set_panel_visible(self, name: str, visible: bool) -> None:
        if name not in PANEL_NAMES:
            raise ValueError(f"Unknown panel {name!r}")
        # Snapshot widths before leaving maximize; otherwise a full-width ChatGPT
        # pane could overwrite the user's three-pane divider preferences.
        self._capture_widths()
        self._maximized_panel = None
        self._visible[name] = bool(visible)
        self._apply_layout()

    def toggle_maximize(self, name: str) -> None:
        if name not in PANEL_NAMES:
            raise ValueError(f"Unknown panel {name!r}")
        if self._maximized_panel == name:
            self._maximized_panel = None
        else:
            self._capture_widths()
            self._visible[name] = True
            self._maximized_panel = name
        self._apply_layout()

    def reset_layout(self) -> None:
        self._maximized_panel = None
        self._visible = {name: True for name in PANEL_NAMES}
        self._widths = list(DEFAULT_WIDTHS)
        self._apply_layout()

    def _show_browser_origin(self, url: QUrl) -> None:
        origin = f"{url.scheme()}://{url.host()}" if url.host() else "(unknown)"
        if url.scheme() != "https":
            origin = f"WARNING — non-HTTPS origin: {origin}"
        self.browser_origin.setText(f"Origin: {origin}")

    def _web_loaded(self, succeeded: bool) -> None:
        self.browser_status.setText(
            "Page loaded (login unverified)." if succeeded
            else "Page failed — use external browser."
        )

    def _on_module_change(self, current: QListWidgetItem | None,
                          previous: QListWidgetItem | None) -> None:
        if previous is not None:
            old_id = previous.data(Qt.ItemDataRole.UserRole)
            self._notes[old_id] = self.editor.toPlainText()
        self.editor.setPlainText(
            self._notes.get(current.data(Qt.ItemDataRole.UserRole), "")
            if current is not None else ""
        )

    def _add_module(self) -> None:
        title, ok = QInputDialog.getText(self, "New module", "Module title:")
        if not ok or not title.strip():
            return
        item = self._new_item(title.strip())
        index = max(0, self.modules.count() - 1)
        self.modules.insertItem(index, item)
        self.modules.setCurrentItem(item)

    def _paste_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if text:
            self.editor.insertPlainText(text)  # Never HTML or website automation.

    def closeEvent(self, event) -> None:
        self._capture_widths()
        self.settings.setValue("workspace/window_geometry", self.saveGeometry())
        self.settings.setValue("workspace/panel_widths", self._widths)
        for name in PANEL_NAMES:
            self.settings.setValue(f"workspace/{name}/visible", self._visible[name])
        self.settings.sync()
        self.browser.setPage(QWebEnginePage(self.browser))
        self.browser_page.deleteLater()
        super().closeEvent(event)
