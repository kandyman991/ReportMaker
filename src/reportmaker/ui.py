"""ReportMaker desktop shell with the M3 visual editor.

The three panes are locally adjustable, collapsible and maximizable. Neither
website contents nor CAD/customer data are read by the layout manager.
The local report editor writes only user-selected .rmproj project files.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy,
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
        ephemeral_browser: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("ReportMaker — Visual Report Editor")
        self.resize(1450, 850)
        self.settings = settings if settings is not None else QSettings("ReportMaker", "ReportMaker")
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
        self._build_interface(browser_profile_root, ephemeral_browser)
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

    def _build_interface(self, browser_profile_root: Path | None, ephemeral_browser: bool) -> None:
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
        customers = QAction("Customers / Sites / Machines", self)
        customers.setObjectName("customerManagerAction")
        customers.triggered.connect(self._open_customers)
        toolbar.addAction(customers)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.setChildrenCollapsible(True)
        self.splitter.setHandleWidth(7)
        self.setCentralWidget(self.splitter)

        _, left_layout = self._make_panel("modules", "MODULE TREE & SUMMARY")
        _, center_layout = self._make_panel("editor", "VISUAL REPORT EDITOR")
        from .visual_editor import VisualReportEditor
        self.document = VisualReportEditor(self, left_layout, center_layout)
        self.modules = self.document.tree
        self.editor = self.document.text_edit
        toolbar.addSeparator()
        self.document.add_toolbar_actions(toolbar)

        _, right_layout = self._make_panel("chat", "CHATGPT WEBSITE — MANUAL COPY/PASTE")
        external = QPushButton("Open ChatGPT in default browser")
        external.clicked.connect(lambda: QDesktopServices.openUrl(CHAT_URL))
        right_layout.addWidget(external)
        self.browser = QWebEngineView()
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.browser.setMinimumSize(0, 0)
        if ephemeral_browser:
            # Automated offline tests must not create persistent Chromium files:
            # Windows holds LevelDB files open until the WebEngine process exits.
            self.profile = QWebEngineProfile(self)
        else:
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
        self.statusBar().showMessage(
            "M3 visual editor: local editable projects and preview. DOCX/PDF export is M4."
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

    def _paste_clipboard(self) -> None:
        self.document.paste_clipboard()

    def _open_customers(self) -> None:
        """Open local records on demand; do not mix them with browser storage."""
        import sqlite3
        from PySide6.QtWidgets import QMessageBox
        from .customer_ui import CustomerManagerDialog
        from .storage import CustomerStore
        try:
            with CustomerStore() as store:
                CustomerManagerDialog(store, self).exec()
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Customer database unavailable", str(error))

    def closeEvent(self, event) -> None:
        if not self.document.ok_to_close():
            event.ignore()
            return
        self._capture_widths()
        self.settings.setValue("workspace/window_geometry", self.saveGeometry())
        self.settings.setValue("workspace/panel_widths", self._widths)
        for name in PANEL_NAMES:
            self.settings.setValue(f"workspace/{name}/visible", self._visible[name])
        self.settings.sync()
        self.browser.setPage(QWebEnginePage(self.browser))
        self.browser_page.deleteLater()
        super().closeEvent(event)
