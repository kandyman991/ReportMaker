"""Two-pane workspace: every pane has its own tabs and each tab shows a tool.

The tools (Modules, Editor, Photos, Assistant, Preview) are single widgets
owned by the window. A tool is open in at most one tab at a time, so there is
exactly one set of drafts, one report session and one browser view no matter how
the workspace is arranged. Choosing a tool that is open somewhere else moves it
there instead of opening a copy.

This module only arranges existing widgets. It knows nothing about the report,
drafts or commands; the window tells it which widget is which tool and reacts
to ``toolShown`` / ``currentChanged`` / ``layoutChanged``.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import icon
from .theme import LIGHT

PAGE_TOOL = "workspaceTool"  # dynamic property on a page: its tool id, "" for a picker
SPLIT_MIN_WIDTH = 960        # two readable panes plus the rail
SINGLE_MIN_WIDTH = 660


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    legacy_label: str  # the name the tab had before the workspace existed
    icon: str
    tooltip: str
    blurb: str


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("modules", "Modules", "Modules", "layers",
             "Modules — build the report structure", "Build the report structure"),
    ToolSpec("editor", "Editor", "Editor", "file",
             "Editor — edit as a document page", "Edit it as a document page"),
    ToolSpec("photos", "Photos", "Photo Gallery", "image",
             "Photos — the project picture gallery", "Browse and insert pictures"),
    ToolSpec("assistant", "Assistant", "ChatGPT", "chat",
             "Assistant — an AI website, copy and paste only",
             "An AI website next to your report"),
    ToolSpec("preview", "Preview", "Preview", "eye",
             "Preview — check and export the report", "Check and export the report"),
)
SPEC = {spec.id: spec for spec in TOOLS}


def default_state(*, split: bool) -> dict:
    """Modules on the left; with the split on, Preview beside it."""
    return {"split": split, "left": ["modules"], "left_current": 0,
            "right": ["preview"] if split else [], "right_current": 0,
            "sizes": [1, 1], "active": "left"}


_SETTINGS_KEY = "v2/workspace"


def restore_state(settings: QSettings | None = None) -> dict | None:
    """The layout saved by ``store_state``, or None when there is none or it is unreadable."""
    raw = (settings or QSettings()).value(_SETTINGS_KEY)
    try:
        state = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return state if isinstance(state, dict) else None


def store_state(state: dict, settings: QSettings | None = None) -> None:
    """Remember the layout (tool ids and sizes only; never report content)."""
    (settings or QSettings()).setValue(_SETTINGS_KEY, json.dumps(state))


def _tab_icon(spec: ToolSpec):
    return icon(spec.icon, normal=LIGHT["text2"], checked=LIGHT["accent-soft-ink"],
                disabled=LIGHT["text3"], size=16)


class ToolTile(QToolButton):
    """A big button for one tool: icon, name and a line saying what it is (or where it is)."""

    def __init__(self, spec: ToolSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.setObjectName("v2ToolTile")
        self.setProperty("toolId", spec.id)
        self.setAccessibleName(spec.label)
        self.setToolTip(spec.tooltip)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumSize(170, 118)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(4)
        glyph = QLabel(self)
        glyph.setPixmap(icon(spec.icon, normal=LIGHT["accent-soft-ink"], checked=LIGHT["accent-soft-ink"],
                             disabled=LIGHT["text3"], size=28).pixmap(QSize(28, 28)))
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name = QLabel(spec.label, self)
        self.name.setObjectName("v2TileName")
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note = QLabel(spec.blurb, self)
        self.note.setObjectName("v2TileNote")
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setWordWrap(True)
        for label in (glyph, self.name, self.note):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(label)

    def set_note(self, text: str) -> None:
        self.note.setText(text)


class ToolPicker(QWidget):
    """What an empty tab shows: one tile per tool."""

    def __init__(self, workspace: Workspace) -> None:
        super().__init__()
        self.workspace = workspace
        self.setObjectName("v2ToolPicker")
        self.setProperty(PAGE_TOOL, "")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.addStretch(1)
        title = QLabel("Open a tool in this tab", self)
        title.setObjectName("v2PickerTitle")
        hint = QLabel("A tool can be open in one tab at a time. Picking one that is open "
                      "elsewhere moves it here.", self)
        hint.setObjectName("v2PickerHint")
        hint.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(hint)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tiles: dict[str, ToolTile] = {}
        for position, spec in enumerate(TOOLS):
            tile = ToolTile(spec, self)
            tile.clicked.connect(lambda checked=False, tool=spec.id: self._choose(tool))
            grid.addWidget(tile, position // 2, position % 2)
            self.tiles[spec.id] = tile
        outer.addLayout(grid)
        outer.addStretch(2)
        self.refresh()

    def _choose(self, tool_id: str) -> None:
        pane = self.workspace.pane_of(self)
        if pane is not None:
            self.workspace.assign(pane, pane.indexOf(self), tool_id)

    def refresh(self) -> None:
        for spec in TOOLS:
            where = self.workspace.describe_location(spec.id)
            self.tiles[spec.id].set_note(spec.blurb if where is None else where + " · click to move it here")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()


class WorkspacePane(QTabWidget):
    """One side of the workspace: a row of tabs over the selected tool."""

    def __init__(self, workspace: Workspace, side: str) -> None:
        super().__init__(workspace)
        self.workspace, self.side = workspace, side
        self.setObjectName("v2WorkspacePane")
        self.setProperty("side", side)
        self.setProperty("active", False)
        self.setDocumentMode(True)
        self.setMovable(True)
        self.setTabsClosable(False)
        bar = self.tabBar()
        bar.setExpanding(False)
        bar.setDrawBase(False)
        bar.setElideMode(Qt.TextElideMode.ElideRight)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._context_menu)
        bar.tabMoved.connect(lambda *_: workspace.layoutChanged.emit())
        bar.installEventFilter(self)
        plus = QToolButton(self)
        plus.setObjectName("v2NewTab")
        plus.setText("+")
        plus.setToolTip("New tab — then pick a tool for it")
        plus.setAccessibleName("New tab")
        plus.clicked.connect(lambda: workspace.new_tab(self))
        self.setCornerWidget(plus, Qt.Corner.TopRightCorner)
        self.currentChanged.connect(lambda index: workspace._pane_current_changed(self, index))

    # -- reading ---------------------------------------------------------
    def tool_at(self, index: int) -> str:
        page = self.widget(index)
        return (page.property(PAGE_TOOL) or "") if page is not None else ""

    def tools(self) -> list[str]:
        return [t for t in (self.tool_at(i) for i in range(self.count())) if t]

    def current_tool(self) -> str:
        return self.tool_at(self.currentIndex())

    def index_of_tool(self, tool_id: str) -> int:
        for index in range(self.count()):
            if self.tool_at(index) == tool_id:
                return index
        return -1

    # -- tab menu --------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        if watched is self.tabBar() and event.type() == QEvent.Type.MouseButtonPress:
            self.workspace.set_active(self)
        return super().eventFilter(watched, event)

    def decorate(self, page: QWidget) -> None:
        """Give a tab the little menu button that picks its tool."""
        button = QToolButton(self.tabBar())
        button.setObjectName("v2TabMenu")
        button.setText("▾")
        button.setAutoRaise(True)
        button.setToolTip("Choose the tool this tab shows")
        button.setAccessibleName("Tab tool menu")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.setObjectName("v2TabMenuActions")
        menu.aboutToShow.connect(lambda: self.fill_menu(menu, page))
        button.setMenu(menu)
        self.tabBar().setTabButton(self.indexOf(page), QTabBar.ButtonPosition.RightSide, button)

    def fill_menu(self, menu: QMenu, page: QWidget) -> QMenu:
        menu.clear()
        current = page.property(PAGE_TOOL) or ""
        for spec in TOOLS:
            where = self.workspace.describe_location(spec.id)
            text = spec.label if where is None or spec.id == current else f"{spec.label} — {where}"
            action = QAction(text, menu)
            action.setObjectName("tabTool_" + spec.id)
            action.setCheckable(True)
            action.setChecked(spec.id == current)
            action.triggered.connect(
                lambda checked=False, tool=spec.id, p=page: self.workspace.assign(
                    self, self.indexOf(p), tool))
            menu.addAction(action)
        menu.addSeparator()
        other = QAction("Move to the other pane", menu)
        other.setObjectName("tabMoveToOther")
        other.triggered.connect(lambda: self.workspace.move_to_other(self, page))
        menu.addAction(other)
        close = QAction("Close tab", menu)
        close.setObjectName("tabClose")
        close.setEnabled(not (self.count() == 1 and not current))
        close.triggered.connect(lambda: self.workspace.close_tab(self, page))
        menu.addAction(close)
        return menu

    def _context_menu(self, point) -> None:
        index = self.tabBar().tabAt(point)
        if index < 0:
            return
        menu = QMenu(self)
        self.fill_menu(menu, self.widget(index))
        menu.exec(self.tabBar().mapToGlobal(point))


class Workspace(QWidget):
    """Left pane, right pane, and the rules for moving tools between them."""

    toolShown = Signal(str)     # a tool became visible in a pane
    currentChanged = Signal(int)  # active pane's tool, as an index into TOOLS (-1: empty tab)
    layoutChanged = Signal()    # split toggled, tool moved/opened/closed, splitter dragged

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("v2WorkspaceTabs")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("v2WorkspaceSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(7)
        outer.addWidget(self._splitter)
        # Tools that are not on screen live here, hidden but still in the window's tree.
        self._parking = QWidget(self)
        self._parking.setObjectName("v2ToolParking")
        self._parking.hide()
        self.left = WorkspacePane(self, "left")
        self.right = WorkspacePane(self, "right")
        for pane in (self.left, self.right):
            pane.setMinimumWidth(300)
            self._splitter.addWidget(pane)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        self.right.hide()
        self._tools: dict[str, QWidget] = {}
        self._split = False
        self._active = self.left
        self._batch = 0
        self._announce_panes: set[WorkspacePane] = set()
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.setInterval(300)
        self._saved_timer.timeout.connect(self.layoutChanged.emit)
        self._splitter.splitterMoved.connect(lambda *_: self._saved_timer.start())
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._focus_changed)

    # -- tools -----------------------------------------------------------
    def register_tools(self, widgets: Mapping[str, QWidget]) -> None:
        unknown = set(widgets) - set(SPEC)
        if unknown:
            raise KeyError(sorted(unknown))
        for tool_id, widget in widgets.items():
            widget.setProperty(PAGE_TOOL, tool_id)
            widget.setParent(self._parking)
            self._tools[tool_id] = widget

    def tool_widget(self, tool_id: str) -> QWidget:
        return self._tools[tool_id]

    def panes(self) -> tuple[WorkspacePane, ...]:
        return (self.left, self.right) if self._split else (self.left,)

    def pane_of(self, page: QWidget) -> WorkspacePane | None:
        for pane in (self.left, self.right):
            if pane.indexOf(page) >= 0:
                return pane
        return None

    def locate(self, tool_id: str) -> tuple[WorkspacePane, int] | None:
        for pane in (self.left, self.right):
            index = pane.index_of_tool(tool_id)
            if index >= 0:
                return pane, index
        return None

    def describe_location(self, tool_id: str) -> str | None:
        """"Open in the right pane", or None when the tool is not open anywhere."""
        found = self.locate(tool_id)
        if found is None:
            return None
        pane, _ = found
        if not self._split:
            return "Open in another tab"
        return f"Open in the {pane.side} pane"

    def visible_tools(self) -> list[str]:
        """The tool each visible pane is showing right now."""
        return [t for t in (pane.current_tool() for pane in self.panes()) if t]

    def current_tool(self) -> str:
        return self._active.current_tool()

    @property
    def active_pane(self) -> WorkspacePane:
        return self._active

    @property
    def is_split(self) -> bool:
        return self._split

    # -- opening, assigning, closing --------------------------------------
    class _Batch:
        """Group several tab changes so Qt's intermediate selections stay silent."""

        def __init__(self, workspace: Workspace) -> None:
            self.workspace = workspace

        def __enter__(self):
            self.workspace._batch += 1

        def __exit__(self, *exc):
            workspace = self.workspace
            workspace._batch -= 1
            if workspace._batch == 0:
                workspace._normalize()
                workspace._flush()
            return False

    def _take(self, pane: WorkspacePane, index: int) -> None:
        """Remove a tab; a tool is parked, an empty tab is discarded."""
        page = pane.widget(index)
        pane.removeTab(index)
        if page is None:
            return
        if page.property(PAGE_TOOL):
            page.setParent(self._parking)
        else:
            page.deleteLater()

    def _put_tool(self, pane: WorkspacePane, tool_id: str, index: int | None = None) -> int:
        widget = self._tools[tool_id]
        spec = SPEC[tool_id]
        position = pane.count() if index is None else index
        position = pane.insertTab(position, widget, _tab_icon(spec), spec.label)
        pane.setTabToolTip(position, spec.tooltip)
        pane.decorate(widget)
        return position

    def _put_picker(self, pane: WorkspacePane, index: int | None = None) -> int:
        picker = ToolPicker(self)
        position = pane.count() if index is None else index
        position = pane.insertTab(position, picker, "New tab")
        pane.decorate(picker)
        return position

    def _normalize(self) -> None:
        for pane in self.panes():
            if pane.count() == 0:
                self._put_picker(pane)
                pane.setCurrentIndex(0)

    def _flush(self) -> None:
        panes = list(self._announce_panes)
        self._announce_panes.clear()
        for pane in panes:
            self._announce(pane)
        self.currentChanged.emit(self._current_index())
        self.layoutChanged.emit()

    def _mark(self, pane: WorkspacePane) -> None:
        self._announce_panes.add(pane)

    def _announce(self, pane: WorkspacePane) -> None:
        tool_id = pane.current_tool()
        if tool_id and (pane is self.left or self._split):
            self.toolShown.emit(tool_id)

    def new_tab(self, pane: WorkspacePane | None = None) -> QWidget:
        """An empty tab that offers every tool."""
        pane = pane or self._active
        with self._Batch(self):
            index = self._put_picker(pane)
            pane.setCurrentIndex(index)
            self._set_active(pane)
            self._mark(pane)
        return pane.widget(index)

    def assign(self, pane: WorkspacePane, index: int, tool_id: str) -> None:
        """Make the tab at ``index`` show ``tool_id``, taking it from wherever it was."""
        if tool_id not in self._tools:
            raise KeyError(tool_id)
        with self._Batch(self):
            if pane.widget(index) is self._tools[tool_id]:
                pane.setCurrentIndex(index)
            else:
                source = self.locate(tool_id)
                if source is not None:
                    source_pane, source_index = source
                    if source_pane.count() == 1:
                        self._take(source_pane, source_index)
                        self._put_picker(source_pane)
                    else:
                        self._take(source_pane, source_index)
                        if source_pane is pane and source_index < index:
                            index -= 1
                    self._mark(source_pane)
                self._take(pane, index)
                position = self._put_tool(pane, tool_id, index)
                pane.setCurrentIndex(position)
            self._set_active(pane)
            self._mark(pane)

    def show_tool(self, tool_id: str) -> None:
        """Bring a tool on screen: select its tab, or open it in the active pane."""
        if tool_id not in self._tools:
            raise KeyError(tool_id)
        found = self.locate(tool_id)
        with self._Batch(self):
            if found is not None:
                pane, index = found
                pane.setCurrentIndex(index)
            else:
                pane = self._active if self._active in self.panes() else self.left
                if pane.current_tool() == "" and pane.count():
                    # An empty tab is waiting for exactly this choice.
                    self.assign(pane, pane.currentIndex(), tool_id)
                else:
                    position = self._put_tool(pane, tool_id)
                    pane.setCurrentIndex(position)
            self._set_active(pane)
            self._mark(pane)

    def close_tab(self, pane: WorkspacePane, page: QWidget) -> None:
        index = pane.indexOf(page)
        if index < 0:
            return
        with self._Batch(self):
            if pane.count() == 1:
                if not page.property(PAGE_TOOL):
                    return  # the last tab is already empty
                self._take(pane, index)
                self._put_picker(pane)
            else:
                self._take(pane, index)
            pane.setCurrentIndex(max(0, min(pane.currentIndex(), pane.count() - 1)))
            self._mark(pane)

    def move_to_other(self, pane: WorkspacePane, page: QWidget) -> None:
        other = self.right if pane is self.left else self.left
        tool_id = page.property(PAGE_TOOL) or ""
        index = pane.indexOf(page)
        if index < 0:
            return
        with self._Batch(self):
            if not self._split:
                self.set_split(True)
            if pane.count() == 1:
                self._take(pane, index)
                self._put_picker(pane)
            else:
                self._take(pane, index)
            if tool_id:
                position = self._put_tool(other, tool_id)
            else:
                position = self._put_picker(other)
            other.setCurrentIndex(position)
            self._set_active(other)
            self._mark(pane)
            self._mark(other)

    # -- split ------------------------------------------------------------
    def set_split(self, on: bool) -> None:
        on = bool(on)
        if on == self._split:
            return
        with self._Batch(self):
            if on:
                self._split = True
                if self.right.count() == 0:
                    if self.locate("preview") is None:
                        self._put_tool(self.right, "preview")
                    else:
                        self._put_picker(self.right)
                    self.right.setCurrentIndex(0)
                self.right.show()
                self._splitter.setSizes([1, 1])
            else:
                carried = self.right.tools()
                while self.right.count():
                    self._take(self.right, 0)
                self._split = False
                self.right.hide()
                for tool_id in carried:
                    self._put_tool(self.left, tool_id)
                self._set_active(self.left)
            self._mark(self.left)
            self._mark(self.right)

    # -- activity ---------------------------------------------------------
    def set_active(self, pane: WorkspacePane) -> None:
        self._set_active(pane)

    def _set_active(self, pane: WorkspacePane) -> None:
        if pane not in self.panes():
            pane = self.left
        changed = pane is not self._active
        self._active = pane
        for each in (self.left, self.right):
            each.setProperty("active", each is pane)
            each.style().unpolish(each)
            each.style().polish(each)
        if changed and not self._batch:
            self.currentChanged.emit(self._current_index())

    def _focus_changed(self, _old, new) -> None:
        try:
            widget = new
            while widget is not None:
                if isinstance(widget, WorkspacePane):
                    if widget in self.panes():
                        self._set_active(widget)
                    return
                widget = widget.parentWidget()
        except RuntimeError:
            return  # the window is being torn down

    def _pane_current_changed(self, pane: WorkspacePane, index: int) -> None:
        if self._batch:
            return
        self._announce(pane)
        if pane is self._active:
            self.currentChanged.emit(self._current_index())
        self.layoutChanged.emit()

    def _current_index(self) -> int:
        tool_id = self._active.current_tool()
        return next((i for i, spec in enumerate(TOOLS) if spec.id == tool_id), -1)

    # -- the QTabWidget-style API the rest of V2 (and its tests) already use --
    def count(self) -> int:
        return len(TOOLS)

    def widget(self, index: int) -> QWidget:
        return self._tools[TOOLS[index].id]

    def indexOf(self, widget: QWidget) -> int:
        return next((i for i, spec in enumerate(TOOLS) if self._tools.get(spec.id) is widget), -1)

    def tabText(self, index: int) -> str:
        return TOOLS[index].legacy_label

    def currentIndex(self) -> int:
        return self._current_index()

    def currentWidget(self) -> QWidget | None:
        tool_id = self._active.current_tool()
        return self._tools[tool_id] if tool_id else self._active.currentWidget()

    def setCurrentWidget(self, widget: QWidget) -> None:
        index = self.indexOf(widget)
        if index < 0:
            raise ValueError("Not a workspace tool")
        self.show_tool(TOOLS[index].id)

    def setCurrentIndex(self, index: int) -> None:
        self.show_tool(TOOLS[index].id)

    # -- saved arrangement --------------------------------------------------
    def state(self) -> dict:
        sizes = self._splitter.sizes()
        return {
            "split": self._split,
            "left": self.left.tools(), "left_current": max(0, self.left.currentIndex()),
            "right": self.right.tools(), "right_current": max(0, self.right.currentIndex()),
            "sizes": sizes if len(sizes) == 2 and all(s > 0 for s in sizes) else [1, 1],
            "active": "right" if self._active is self.right else "left",
        }

    def apply_state(self, state: Mapping | None) -> None:
        """Rebuild the arrangement from ``state``; anything unusable falls back to defaults."""
        state = state if isinstance(state, Mapping) else {}
        wants_split = state.get("split") is True
        used: set[str] = set()

        def tools_for(side: str) -> list[str]:
            raw = state.get(side)
            ids = []
            for tool_id in raw if isinstance(raw, list) else []:
                if isinstance(tool_id, str) and tool_id in self._tools and tool_id not in used:
                    used.add(tool_id)
                    ids.append(tool_id)
            return ids

        with self._Batch(self):
            for pane in (self.left, self.right):
                while pane.count():
                    self._take(pane, 0)
            self._split = wants_split
            left_ids, right_ids = tools_for("left"), tools_for("right")
            if not wants_split:
                left_ids, right_ids = left_ids + right_ids, []
            if not left_ids and "modules" not in used and "modules" in self._tools:
                left_ids = ["modules"]
                used.add("modules")
            for tool_id in left_ids:
                self._put_tool(self.left, tool_id)
            for tool_id in right_ids:
                self._put_tool(self.right, tool_id)
            self.right.setVisible(wants_split)
            for pane, key in ((self.left, "left_current"), (self.right, "right_current")):
                raw = state.get(key)
                wanted = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
                if pane.count():
                    pane.setCurrentIndex(max(0, min(wanted, pane.count() - 1)))
            sizes = state.get("sizes")
            if (isinstance(sizes, list) and len(sizes) == 2
                    and all(isinstance(s, int) and not isinstance(s, bool) and s > 0 for s in sizes)):
                self._splitter.setSizes(sizes)
            else:
                self._splitter.setSizes([1, 1])
            self._set_active(self.right if wants_split and state.get("active") == "right"
                             else self.left)
            self._mark(self.left)
            self._mark(self.right)
