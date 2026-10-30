"""ReportMaker V2 M1.4: one Branch Editor with safe project lifecycle.

V1 UI/browser remain untouched. All content edits go through the existing
canonical session, command gateway and atomic .rmproj persistence adapter.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QToolBar, QToolButton, QWidget,
)

from ..engine import module_outline
from ..model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from ..project_io import ReportProject, VERSION, default_projects_directory
from ..reference import manual_snapshot
from .adapters.persistence import ProjectPersistence, _same_path
from .branch.canvas import BranchCanvas
from .commands import CommandGateway
from .presentation import PresentationStore
from .theme import LIGHT, stylesheet
from .session import PendingDraftError, ReportSession
from .workspace import SINGLE_MIN_WIDTH, SPLIT_MIN_WIDTH, TOOLS, Workspace, default_state


def example_report() -> Report:
    """Synthetic M1.1 preview; user-created reports never inherit its customer."""
    lang = "en"
    nested = Module(
        LocalizedText(lang, "Mechanical checks"),
        blocks=[
            ParagraphBlock(LocalizedText(
                lang, "Example inspection note. Edit me directly in the branch."
            )),
        ],
    )
    parent = Module(
        LocalizedText(lang, "Inspection"),
        blocks=[NestedModuleBlock(nested)],
    )
    return Report(
        customer_id=None,
        customer_snapshot=manual_snapshot("Example customer"),
        start_date=date(2026, 10, 28),
        end_date=date(2026, 10, 28),
        primary_language=lang,
        output_languages=[lang],
        title=LocalizedText(lang, "Technical intervention (example)"),
        modules=[parent],
        conclusion=Module(LocalizedText(lang, "Conclusions")),
    )


def blank_report(customer_name: str, *, today: date | None = None) -> Report:
    """New report with explicit real/manual customer name and fresh stable IDs."""
    when = today if today is not None else date.today()
    return Report(
        customer_id=None,
        customer_snapshot=manual_snapshot(customer_name),
        start_date=when, end_date=when, primary_language="en",
        output_languages=["en"],
        title=LocalizedText("en", "Technical intervention"),
        modules=[Module(LocalizedText("en", "Module 1"))],
        conclusion=Module(LocalizedText("en", "Conclusions")),
    )


class V2MainWindow(QMainWindow):
    """One canonical session shared by Branch Editor and file actions."""

    def __init__(self, report: Report | None = None, *,
                 project: ReportProject | None = None,
                 presentation: PresentationStore | None = None,
                 load_website: bool = True,
                 browser_profile_root: Path | None = None,
                 ephemeral_browser: bool = False,
                 customer_database_path: Path | None = None,
                 workspace_state: dict | None = None,
                 workspace_saver: Callable[[dict], None] | None = None) -> None:
        super().__init__()
        if report is not None and project is not None:
            raise ValueError("Pass either a Report or an existing project")
        self.setObjectName("reportmakerV2Window")
        self.customer_database_path = customer_database_path
        self.resize(1280, 820)
        self.setMinimumSize(660, 460)
        self._synthetic_preview = report is None and project is None
        initial = project if project is not None else ReportProject(
            example_report() if report is None else report
        )
        self.session = ReportSession(initial)
        self.gateway = CommandGateway(self.session)
        self.persistence = ProjectPersistence()
        self.presentation = presentation or PresentationStore()
        self.branch = BranchCanvas(self)
        self.branch.bind_session(self.session, self.gateway)
        self.branch.feedback.connect(self.statusBar().showMessage)
        # Distinct workspaces share the *same* canonical report session.
        # No V1 three-pane shell or second data tree is imported.
        from .editor_tab import DocumentEditorTab
        from .gallery_tab import GalleryTab
        from .chat_tab import ChatTab
        from .preview_tab import PreviewTab
        # The tools are single widgets; the workspace decides which pane and tab
        # shows each one (see workspace.py). ``tabs`` keeps its old name so the
        # rest of V2 and its tests can still say ``tabs.setCurrentWidget(tool)``.
        self.tabs = Workspace(self)
        self.editor_tab = DocumentEditorTab(self.session, self.branch, self.tabs)
        self.gallery_tab = GalleryTab(self.session, self.gateway, self.branch, self.tabs)
        self.chat_tab = ChatTab(
            load_website=load_website, browser_profile_root=browser_profile_root,
            ephemeral_browser=ephemeral_browser, parent=self.tabs)
        self.preview_tab = PreviewTab(self.session, self.tabs)
        self._tool_widgets = {
            "modules": self.branch, "editor": self.editor_tab, "photos": self.gallery_tab,
            "assistant": self.chat_tab, "preview": self.preview_tab,
        }
        self.tabs.register_tools(self._tool_widgets)
        self.gallery_tab.on_inserted = lambda: self.tabs.show_tool("modules")
        self.workspace_saver = workspace_saver
        self.setCentralWidget(self.tabs)
        self._refresh_queued = False
        self.tabs.toolShown.connect(self._tool_shown)
        self.tabs.layoutChanged.connect(self._workspace_layout_changed)
        self.tabs.apply_state(workspace_state if workspace_state is not None
                              else default_state(split=False))
        self._build_rail()
        self.tabs.currentChanged.connect(self._sync_rail)
        self.setStyleSheet(stylesheet(LIGHT))
        self._sync_rail()
        self._workspace_layout_changed()
        self.session.subscribe(self._workspace_changed)
        self.session.subscribe(lambda _: self._update_caption())
        # Staging a draft does not publish a canonical revision; separately
        # reflect unapplied changes in the window's unsaved marker immediately.
        self.branch.drafts.subscribe_pending(lambda _pending: self._update_caption())
        self.branch.drafts.subscribe_pending(lambda _pending: self._queue_visible_refresh())

        # Keep the primary commands visible at minimum window width. The
        # previous 27-action single toolbar overflowed even at 1600 px;
        # Qt silently hid critical insert and editing commands behind chevrons.
        toolbar = self.addToolBar("Project")
        toolbar.setObjectName("v2BranchActions")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        actions: dict[str, QAction] = {}
        for name, label, method, shortcut in (
            ("v2NewProject", "New", self.new_project, "Ctrl+N"),
            ("v2OpenProject", "Open", self.open_project, "Ctrl+O"),
            ("v2SaveProject", "Save", self.save_project, "Ctrl+S"),
            ("v2SaveProjectAs", "Save As", self.save_project_as, "Ctrl+Shift+S"),
            ("v2ReportInfo", "Report info", self.edit_report_info, "Ctrl+Shift+R"),
            ("v2CustomerManager", "Customers, sites and machines…",
             self.open_customer_manager, ""),
            ("v2Translations", "Translations…", self.edit_translations, ""),
            ("v2MetadataTranslations", "Metadata languages…", self.edit_metadata_translations, ""),
            ("v2FooterTranslation", "Footer languages…", self.edit_branding_footer, ""),
            ("v2ImportTemplate", "Layout template…", self.import_layout_template, ""),
            ("v2AddModule", "+ Module", self.branch.add_module, ""),
            ("v2AddSubmodule", "+ Submodule", self.branch.add_nested_module, ""),
            ("v2AddParagraph", "+ Paragraph", self.branch.add_paragraph, ""),
            ("v2AddHeading", "+ Heading", self.branch.add_heading, ""),
            ("v2AddTable", "+ Table", self.branch.add_table, ""),
            ("v2AddPageBreak", "+ Page break", self.branch.add_page_break, ""),
            ("v2AddExistingPhoto", "+ Existing photo", self.branch.add_photo, ""),
            ("v2ImportPhoto", "+ Import photo", self.branch.import_photo_dialog, "Ctrl+Shift+I"),
            # Ctrl+Shift+V is "paste as plain text" in browsers and Office and is how
            # text from an AI assistant is pasted. Never bind it to an action.
            ("v2PastePhoto", "Paste image", self.branch.paste_photo, "Ctrl+Alt+V"),
            ("v2MoveUp", "↑ Move", self.branch.move_selected_up, "Alt+Up"),
            ("v2MoveDown", "↓ Move", self.branch.move_selected_down, "Alt+Down"),
            ("v2Indent", "→ Indent", self.branch.indent_selected, "Alt+Shift+Right"),
            ("v2Outdent", "← Outdent", self.branch.outdent_selected, "Alt+Shift+Left"),
            ("v2Duplicate", "Duplicate", self.branch.duplicate_selected, "Alt+Shift+D"),
            ("v2Delete", "Delete…", self.branch.delete_selected, "Ctrl+Shift+Delete"),
            ("v2Contents", "Contents", self.show_contents, "Ctrl+Shift+T"),
            ("v2UndoChange", "Undo change", self.branch.undo, "Ctrl+Alt+Z"),
            ("v2RedoChange", "Redo change", self.branch.redo, "Ctrl+Alt+Shift+Z"),
        ):
            action = QAction(label, self)
            action.setObjectName(name)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(lambda checked=False, callback=method: callback())
            # A menu-only QAction must still belong to the main window so
            # its existing shortcut works even while that menu is closed.
            self.addAction(action)
            actions[name] = action

        def menu_button(bar, title: str, object_name: str,
                        keys: tuple[str, ...]) -> QToolButton:
            button = QToolButton(bar)
            button.setObjectName(object_name)
            button.setAccessibleName(title + " commands")
            button.setText(title)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(title, button)
            menu.setObjectName(object_name + "Actions")
            menu.setToolTipsVisible(True)
            for key in keys:
                menu.addAction(actions[key])
            button.setMenu(menu)
            bar.addWidget(button)
            return button

        for key in ("v2NewProject", "v2OpenProject", "v2SaveProject",
                    "v2ReportInfo"):
            toolbar.addAction(actions[key])
        menu_button(toolbar, "Project ▾", "v2ProjectMenu", (
            "v2SaveProjectAs", "v2CustomerManager", "v2ImportTemplate", "v2Contents"))
        menu_button(toolbar, "Languages ▾", "v2LanguagesMenu", (
            "v2Translations", "v2MetadataTranslations",
            "v2FooterTranslation"))

        self.addToolBarBreak()
        editing = self.addToolBar("Module editing")
        editing.setObjectName("v2BranchEditing")
        editing.setMovable(False)
        editing.setFloatable(False)
        editing.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for key in ("v2AddModule", "v2AddSubmodule", "v2AddParagraph"):
            editing.addAction(actions[key])
        menu_button(editing, "Insert ▾", "v2InsertMenu", (
            "v2AddHeading", "v2AddTable", "v2AddPageBreak",
            "v2AddExistingPhoto", "v2ImportPhoto", "v2PastePhoto"))
        menu_button(editing, "Arrange ▾", "v2ArrangeMenu", (
            "v2MoveUp", "v2MoveDown", "v2Indent", "v2Outdent",
            "v2Duplicate", "v2Delete"))
        for key in ("v2UndoChange", "v2RedoChange"):
            # Short button labels; full descriptions remain in tooltips.
            actions[key].setToolTip(actions[key].text())
            actions[key].setText("Undo" if key == "v2UndoChange" else "Redo")
            editing.addAction(actions[key])

        self.addToolBarBreak()
        navigation = self.addToolBar("Branch navigation")
        navigation.setObjectName("v2BranchNavigation")
        navigation.setMovable(False)
        navigation.setFloatable(False)
        navigation.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        nav_actions: dict[str, QAction] = {}
        for name, label, method, shortcut in (
            ("v2Search", "Find", self.search_branches, "Ctrl+F"),
            ("v2NextMatch", "Next match", self.branch.next_match, "F3"),
            ("v2Focus", "Focus", self.branch.focus_module, "Ctrl+Shift+F"),
            # Ctrl+Shift+Esc is reserved by Windows for Task Manager and never reaches
            # the application, so Exit focus uses Alt+Shift+F.
            ("v2ExitFocus", "Exit focus", self.branch.exit_focus, "Alt+Shift+F"),
            ("v2ZoomOut", "Zoom −", lambda: self.branch.zoom_by(-10), "Ctrl+-"),
            ("v2ZoomIn", "Zoom +", lambda: self.branch.zoom_by(10), "Ctrl++"),
            ("v2ZoomReset", "100%", lambda: self.branch.set_zoom(100), "Ctrl+0"),
            ("v2Fit", "Fit width", self.branch.fit_to_screen, "Ctrl+Shift+0"),
            ("v2PrevWindow", "Previous", lambda: self.branch.change_page(-1), "Ctrl+PgUp"),
            ("v2NextWindow", "Next", lambda: self.branch.change_page(1), "Ctrl+PgDown"),
            ("v2SelectPrevious", "Select above", lambda: self.branch.select_adjacent_module(-1), "Ctrl+Alt+Up"),
            ("v2SelectNext", "Select below", lambda: self.branch.select_adjacent_module(1), "Ctrl+Alt+Down"),
            ("v2PanLeft", "Pan ←", lambda: self.branch.pan_by(-160), "Ctrl+Alt+Left"),
            ("v2PanRight", "Pan →", lambda: self.branch.pan_by(160), "Ctrl+Alt+Right"),
        ):
            action = QAction(label, self)
            action.setObjectName(name)
            if shortcut:
                action.setShortcut(shortcut)
                action.setToolTip(f"{label} ({shortcut})")
            action.triggered.connect(lambda checked=False, callback=method: callback())
            self.addAction(action)
            nav_actions[name] = action
        # Reuse the same menu helper with the navigation action registry.
        actions.update(nav_actions)
        for key in ("v2Search", "v2NextMatch", "v2ZoomOut",
                    "v2ZoomIn", "v2ZoomReset"):
            navigation.addAction(actions[key])
        menu_button(navigation, "Navigate ▾", "v2NavigateMenu", (
            "v2Focus", "v2ExitFocus", "v2PrevWindow", "v2NextWindow",
            "v2SelectPrevious", "v2SelectNext",
            "v2PanLeft", "v2PanRight"))
        menu_button(navigation, "View ▾", "v2ViewMenu", ("v2Fit",))
        self.branch.selectionChanged.connect(self._update_move_actions)
        self.branch.visibilityChanged.connect(self._persist_live_view)
        self.branch.visibilityChanged.connect(self._update_move_actions)
        self._update_move_actions()
        self._restore_presentation()
        self._update_caption()
        self.statusBar().showMessage(
            "Edit inline; Save asks how to handle unapplied edits. "
            "Ctrl+Enter applies one edit, Esc reverts it; files use .rmproj."
        )

    def open_customer_manager(self) -> bool:
        """Manage local customers, sites and machines.

        Reports only ever keep a frozen copy of a record, so editing master
        data here never changes an existing report.
        """
        import sqlite3
        from ..storage import CustomerStore
        from .customer_manager import CustomerManagerDialog
        try:
            with CustomerStore(self.customer_database_path) as store:
                CustomerManagerDialog(store, self).exec()
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Customer database unavailable", str(error))
            return False
        return True

    def _build_rail(self) -> None:
        """Left rail: one action per tool, plus the split toggle at the bottom.

        A tool that is open in a tab is selected; one that is not opens in a new
        tab of the active pane. Each tab's own menu picks its tool in place.
        """
        from .icons import icon

        def rail_icon(name: str):
            return icon(name, normal=LIGHT["text2"], checked=LIGHT["accent-soft-ink"],
                        disabled=LIGHT["text3"])

        rail = QToolBar("Workspaces", self)
        rail.setObjectName("workspaceRail")
        rail.setOrientation(Qt.Orientation.Vertical)
        rail.setMovable(False)
        rail.setFloatable(False)
        rail.setIconSize(QSize(22, 22))
        rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        group = QActionGroup(self)
        group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self._rail_actions: dict[str, QAction] = {}
        for spec in TOOLS:
            action = QAction(rail_icon(spec.icon), spec.label, self)
            action.setObjectName("rail_" + spec.id)
            action.setCheckable(True)
            action.setToolTip(spec.tooltip)
            action.triggered.connect(lambda checked=False, tool=spec.id: self.tabs.show_tool(tool))
            group.addAction(action)
            rail.addAction(action)
            self._rail_actions[spec.id] = action
        spacer = QWidget(rail)
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rail.addWidget(spacer)
        split = QAction(rail_icon("columns"), "Split", self)
        split.setObjectName("rail_split")
        split.setCheckable(True)
        split.setShortcut("Ctrl+\\")
        split.setToolTip("Split view — two panes side by side, each with its own tabs (Ctrl+\\)")
        split.toggled.connect(self.tabs.set_split)
        rail.addAction(split)
        self.split_action = split
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail)
        self.rail = rail

    def _sync_rail(self, _index: int = -1) -> None:
        current = self.tabs.current_tool()
        for tool_id, action in self._rail_actions.items():
            if action.isChecked() != (tool_id == current):
                action.setChecked(tool_id == current)
        if self.split_action.isChecked() != self.tabs.is_split:
            self.split_action.blockSignals(True)
            self.split_action.setChecked(self.tabs.is_split)
            self.split_action.blockSignals(False)

    def _workspace_layout_changed(self) -> None:
        self.setMinimumWidth(SPLIT_MIN_WIDTH if self.tabs.is_split else SINGLE_MIN_WIDTH)
        if hasattr(self, "split_action"):
            self._sync_rail()
        if self.workspace_saver is not None:
            self.workspace_saver(self.tabs.state())

    def _workspace_changed(self, change) -> None:
        # Lazily rebuild inactive document/preview panes. Draft-owning widgets
        # are never thrown away during a native Qt text-change callback.
        self.preview_tab.invalidate()
        self._queue_visible_refresh()

    def _queue_visible_refresh(self) -> None:
        """Bring the tools that are on screen up to date, once, after the current event."""
        if self._refresh_queued:
            return
        self._refresh_queued = True
        QTimer.singleShot(0, self._refresh_visible_tools)

    def _refresh_visible_tools(self) -> None:
        self._refresh_queued = False
        for tool_id in self.tabs.visible_tools():
            self._activate_tool(tool_id)

    def _activate_tool(self, tool_id: str) -> None:
        if tool_id == "editor":
            self.editor_tab.activate()
        elif tool_id == "photos":
            self.gallery_tab.refresh()
        elif tool_id == "assistant":
            self.chat_tab.activate()
        elif tool_id == "preview":
            self.preview_tab.refresh()

    def _tool_shown(self, tool_id: str) -> None:
        self._activate_tool(tool_id)

    def _update_move_actions(self) -> None:
        """Disable unavailable moves, including their keyboard shortcuts."""
        up = self.findChild(QAction, "v2MoveUp")
        down = self.findChild(QAction, "v2MoveDown")
        if up is not None:
            up.setEnabled(self.branch.can_move_selected(-1))
        if down is not None:
            down.setEnabled(self.branch.can_move_selected(1))
        for name, enabled in (
            ("v2Focus", self.branch._selected_module_id is not None),
            ("v2ExitFocus", self.branch.focus_module_id is not None),
            ("v2PrevWindow", self.branch._page > 0),
            ("v2NextWindow", self.branch._page < self.branch.page_count - 1),
            ("v2Indent", self.branch.can_indent_selected()),
            ("v2Outdent", self.branch.can_outdent_selected()),
            ("v2Duplicate", self.branch.can_duplicate_selected()),
            ("v2Delete", self.branch.can_delete_selected()),
        ):
            action = self.findChild(QAction, name)
            if action is not None:
                action.setEnabled(enabled)

    def build_contents_menu(self) -> QMenu:
        """Ephemeral derived TOC; never a separately editable hierarchy."""
        menu = QMenu("Report contents", self)
        menu.setObjectName("v2ContentsMenu")
        generation = self.session.generation
        for entry in module_outline(self.session.report_snapshot()):
            prefix = ("  " * entry.depth) + (entry.number + "  " if entry.number else "")
            # Qt menus use ampersands as mnemonic markers; show user titles literally.
            action = menu.addAction(prefix + entry.title.replace("&", "&&"))
            action.setData(entry.module_id)
            action.triggered.connect(
                lambda checked=False, mid=entry.module_id, gen=generation:
                self.branch.reveal_node(mid) if gen == self.session.generation else None
            )
        return menu

    def show_contents(self) -> None:
        # Menu is rebuilt from the live canonical outline on every opening.
        self._contents_menu = self.build_contents_menu()
        self._contents_menu.popup(self.mapToGlobal(self.rect().topRight()))

    def search_branches(self) -> None:
        """User-initiated canonical search, including hidden captions and titles."""
        text, accepted = QInputDialog.getText(
            self, "Find in report", "Title, text, table or photo caption:")
        if not accepted:
            return
        hits = self.branch.search(text)
        if not hits:
            self.statusBar().showMessage("No matches in report")
        elif self.branch._search_index < 0:
            self.statusBar().showMessage("Apply or Revert pending edits before revealing a match")
        else:
            self.statusBar().showMessage(f"Found {len(hits)} matching report blocks — F3 for next")

    def import_layout_template(self, path: str | Path | None = None) -> bool:
        """Import a local, bounded Word layout profile without changing report."""
        from .layout_template import style_from_template
        from ..template_import import import_word_template, load_template
        try:
            self.session.require_clean_drafts()
        except PendingDraftError as exc:
            self.statusBar().showMessage(str(exc))
            return False
        if path is None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select a local Word layout",
                "", "Word and ReportMaker templates (*.docx *.dotx *.rmtemplate)")
            if not filename:
                return False
            path = filename
        try:
            local = Path(path)
            warnings = ()
            if local.suffix.lower() == ".rmtemplate":
                template = load_template(local)
            else:
                imported = import_word_template(local)
                template, warnings = imported.template, imported.warnings
            style = style_from_template(template)
            # Apply only after complete import/validation; never persist this
            # presentation profile into report facts or project media.
            self.editor_tab.set_style(style)
            self.preview_tab.set_style(style)
            self.statusBar().showMessage(
                "Local template selected; " +
                ("Some Word elements were not imported: " + "; ".join(warnings[:2])
                 if warnings else "export page geometry and branding updated"))
        except (OSError, ValueError, RuntimeError) as exc:
            self.statusBar().showMessage("Template import rejected: " + str(exc))
            return False
        return True

    def _reset_project_layout(self) -> None:
        """Never reuse another project's transient logo/header/footer.

        Until template profiles become explicit per-project data, a project
        switch returns the page Editor and both preview/export surfaces to
        safe defaults rather than leaking the prior customer's branding.
        """
        from ..export import ExportStyle
        self.editor_tab.set_style(ExportStyle())
        self.preview_tab.set_style(ExportStyle())

    def edit_translations(self) -> bool:
        """Edit explicit localized fields without changing the source writing."""
        from .translation_dialog import TranslationDialog
        try:
            self.session.require_clean_drafts()
        except PendingDraftError as exc:
            self.statusBar().showMessage(str(exc))
            return False
        TranslationDialog(self.session, self.gateway, self).exec()
        self.preview_tab.invalidate()
        return True

    def edit_metadata_translations(self) -> bool:
        """Approve semantic metadata/label translations in canonical history."""
        from .metadata_translation_dialog import MetadataTranslationDialog
        try:
            self.session.require_clean_drafts()
        except PendingDraftError as exc:
            self.statusBar().showMessage(str(exc))
            return False
        MetadataTranslationDialog(self.session, self.gateway, self).exec()
        self.preview_tab.invalidate()
        return True

    def edit_branding_footer(self) -> bool:
        """Approve transient Word-template footer prose, never project data."""
        from dataclasses import replace
        from ..model import validate_language_tag
        from .metadata_locale import MetadataLocale
        try:
            self.session.require_clean_drafts()
            style = self.preview_tab.style
            if not style.footer_note:
                self.statusBar().showMessage("Choose a template containing footer text first.")
                return False
            language, ok = QInputDialog.getText(
                self, "Template footer source language",
                "Explicit source language (e.g. en, it, fr-CA):",
                text=style.footer_source_language or "")
            if not ok:
                return False
            validate_language_tag(language)
            if language != style.footer_source_language:
                style = replace(style, footer_source_language=language,
                                footer_locale_approvals=())
            tags = [tag for tag in self.session.report_snapshot().output_languages
                    if tag.casefold() != language.casefold()]
            if tags:
                chosen, ok = QInputDialog.getItem(
                    self, "Footer translation language",
                    "Approve a target now, or only declare the source language:",
                    ["Source language only — translate later", *tags], 0, False)
                if not ok:
                    return False
                if chosen in tags:
                    existing = next((record for record in style.footer_locale_approvals
                                     if record.language.casefold() == chosen.casefold()), None)
                    target, ok = QInputDialog.getMultiLineText(
                        self, "Approve footer translation",
                        "Manual translation of template footer (no automatic translation):",
                        existing.text if existing is not None else "")
                    if not ok:
                        return False
                    approved = MetadataLocale(
                        self.session.report_snapshot(), [],
                        footer_note=style.footer_note,
                        footer_source_language=language).approve(
                            "branding.footer_note", chosen, target)
                    kept = tuple(record for record in style.footer_locale_approvals
                                 if record.language.casefold() != chosen.casefold())
                    style = replace(style, footer_locale_approvals=kept + (approved,))
            self.editor_tab.set_style(style)
            self.preview_tab.set_style(style)
            self.statusBar().showMessage("Transient footer language recorded for this layout only.")
            return True
        except (ValueError, RuntimeError) as exc:
            self.statusBar().showMessage("Footer localization rejected: " + str(exc))
            return False

    def edit_report_info(self) -> bool:
        """Apply metadata through the same guarded canonical command history."""
        from .report_info import ReportInfoDialog
        try:
            self.session.require_clean_drafts()
        except PendingDraftError as exc:
            self.statusBar().showMessage(str(exc))
            return False
        result = ReportInfoDialog(self.session, self.gateway, self,
                                  database_path=self.customer_database_path).exec()
        return bool(result)

    def _update_caption(self) -> None:
        name = self.session.path.name if self.session.path else "Untitled"
        marker = " *" if self.session.dirty or self.branch.drafts.pending else ""
        self.setWindowTitle(f"ReportMaker V2 — {name}{marker}")

    def _view(self) -> tuple[str, str | None, int, frozenset[str]]:
        return (self.presentation.key_for(self.session),
                self.branch._selected_module_id,
                self.branch.verticalScrollBar().value(),
                self.branch.collapsed_module_ids)

    def _restore_presentation(self) -> None:
        selected, scroll, collapsed = self.presentation.load_view(self.session)
        # Changing project generation invalidates old cursor/selection targets.
        self.branch._selected_module_id = selected
        self.branch._restore = None
        self.branch.restore_collapsed(collapsed)
        QTimer.singleShot(0, lambda value=scroll:
                          self.branch.verticalScrollBar().setValue(value))

    def _persist_live_view(self) -> None:
        """A collapse/TOC reveal is device-local state, not a report edit."""
        self._persist_previous_view(self._view())

    def _persist_previous_view(
            self, view: tuple[str, str | None, int, frozenset[str]]) -> None:
        key, selected, scroll, collapsed = view
        self.presentation.write(key, selected, scroll, collapsed=collapsed)

    def _prompt_pending_edits(self, *, saving: bool) -> str:
        """Ask before applying OR discarding any staged edits; Cancel is safest."""
        count = len(self.branch.drafts.pending_addresses())
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Unapplied edits")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            f"{count} unapplied edit(s) in Modules or Editor. "
            "Choose what to do with your typed changes.")
        dialog.setInformativeText(
            ("Apply and save: keep every edit as one undoable change, then save. "
             "Discard edits: remove unapplied changes and save only previously "
             "applied content. Cancel: change nothing."
             if saving else
             "Apply edits: keep every edit as one undoable change, then continue "
             "to the normal unsaved-report confirmation. Discard edits: remove "
             "only unapplied changes, then continue. Cancel: change nothing."))
        apply_button = dialog.addButton(
            "Apply and save" if saving else "Apply edits",
            QMessageBox.ButtonRole.AcceptRole)
        discard_button = dialog.addButton(
            "Discard edits", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(
            "Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is apply_button:
            return "apply"
        if dialog.clickedButton() is discard_button:
            return "discard"
        return "cancel"

    def _drafts_clean(self, *, saving: bool = False) -> bool:
        """Resolve pending drafts only after a separately confirmed decision.

        No file, report, project identity or undo state changes on Cancel.
        Applying all editors' drafts remains atomic, fail-closed and undoable.
        """
        if not self.branch.drafts.pending:
            return True
        choice = self._prompt_pending_edits(saving=saving)
        if choice not in {"apply", "discard"}:
            return False
        if choice == "discard":
            self.branch.discard_all_drafts()
            return True
        problem = self.branch.apply_all_drafts()
        if problem is None:
            return True
        if self.branch.drafts.pending_addresses(owner="branch"):
            self.tabs.setCurrentWidget(self.branch)
            self.branch.verticalScrollBar().setValue(0)
            where = ("Use the yellow UNAPPLIED EDITS panel at the top of Modules "
                     "to correct, apply or discard them.")
        else:
            where = "Return to Editor to correct, apply or revert them."
        QMessageBox.warning(
            self, "Unapplied edits",
            "Your pending edits could not be applied, so nothing was saved or "
            "closed:\n\n" + problem + "\n\n" + where)
        return False

    def _confirm_transition(self) -> bool | None:
        """Return whether to discard committed changes, or None to cancel.

        A successful Save makes discard unnecessary. A cancelled/failed Save
        preserves the current report, view identity, history and draft state.
        """
        if not self._drafts_clean():
            return None
        if not self.session.dirty or (
            self._synthetic_preview and self.session.revision == 0
        ):
            return False
        choice = QMessageBox.question(
            self, "Unsaved report",
            "Save changes to the current report before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        if choice == QMessageBox.StandardButton.Discard:
            return True
        if choice == QMessageBox.StandardButton.Save and self.save_project():
            return False
        return None

    def new_project(self, customer_name: str | None = None) -> bool:
        if customer_name is None:
            customer_name, accepted = QInputDialog.getText(
                self, "New report", "Customer name (one-off/manual):"
            )
            if not accepted:
                return False
        if not isinstance(customer_name, str) or not customer_name.strip():
            QMessageBox.warning(self, "Customer required",
                                "Enter a customer name to create a report.")
            return False
        decision = self._confirm_transition()
        if decision is None:
            return False
        view = self._view()
        try:
            self.session.replace_project(
                ReportProject(blank_report(customer_name)),
                discard_unsaved=decision,
            )
        except (ValueError, LookupError, RuntimeError) as exc:
            QMessageBox.critical(self, "Cannot create report", str(exc))
            return False
        self._persist_previous_view(view)
        self._reset_project_layout()
        self._synthetic_preview = False
        self._restore_presentation()
        self._update_caption()
        self.statusBar().showMessage("New report created (not saved)")
        return True

    def open_project(self, path: str | Path | None = None) -> bool:
        if path is None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Open ReportMaker project",
                str(default_projects_directory()), "ReportMaker (*.rmproj)"
            )
            if not filename:
                return False
            path = filename
        decision = self._confirm_transition()
        if decision is None:
            return False
        view = self._view()
        try:
            # A corrupt or future-version file never replaces the active report.
            self.persistence.open_into(
                self.session, Path(path), discard_unsaved=decision,
            )
        except (OSError, ValueError, LookupError, RuntimeError) as exc:
            QMessageBox.critical(self, "Cannot open project", str(exc))
            return False
        self._persist_previous_view(view)
        self._reset_project_layout()
        self._synthetic_preview = False
        self._restore_presentation()
        self._update_caption()
        self.statusBar().showMessage(f"Opened {self.session.path.name}")
        return True

    def _choose_save_path(self, *, as_copy: bool) -> Path | None:
        suggested = (self.session.path if self.session.path is not None else
                     default_projects_directory() / "report.rmproj")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save ReportMaker project as" if as_copy else "Save ReportMaker project",
            str(suggested), "ReportMaker (*.rmproj)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not filename:
            return None
        target = Path(filename)
        if target.suffix.lower() != ".rmproj":
            target = target.with_suffix(".rmproj")
        return target

    def _save_to(self, target: Path | None, *, as_copy: bool) -> bool:
        if target is None:
            target = self._choose_save_path(as_copy=as_copy)
            if target is None:
                return False
        target = Path(target)
        if as_copy and self.session.path is not None and _same_path(target, self.session.path):
            QMessageBox.warning(self, "Choose another destination",
                                "Save As must use a different path from the current project.")
            return False
        # A first Save may legitimately select an existing file through the
        # picker, but never overwrite without a separate explicit confirmation.
        existing = target.exists()
        overwrite = False
        if existing and (as_copy or self.session.path is None):
            answer = QMessageBox.question(
                self, "Overwrite project?",
                f"Replace existing project file {target.name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            overwrite = True
        # Do not apply or discard drafts if the user cancelled the destination
        # picker / overwrite warning. No implicit edits before confirmation.
        if not self._drafts_clean(saving=True):
            return False
        view = self._view()
        try:
            if as_copy or overwrite:
                self.persistence.save_as(self.session, target, overwrite=overwrite)
            else:
                self.persistence.save(self.session, target)
        except (OSError, ValueError, LookupError, RuntimeError) as exc:
            QMessageBox.critical(self, "Cannot save project", str(exc))
            return False
        # Persist both old and new identities *only* after archive success.
        self._persist_previous_view(view)
        self.presentation.write(self.presentation.key_for(self.session),
                                view[1], view[2], collapsed=view[3])
        self._synthetic_preview = False
        self._update_caption()
        self.statusBar().showMessage(
            f"Saved {self.session.path.name} as V2 project schema v{VERSION}. "
            "Older/V1 ReportMaker versions cannot reopen this file; "
            "keep any original legacy project as a separate backup.")
        return True

    def save_project(self, path: str | Path | None = None) -> bool:
        if self.session.path is not None and self.session.loaded_version != VERSION:
            # v1–v4 source is immutable. Route Save to a different Save As path.
            if path is not None:
                QMessageBox.warning(
                    self, "Legacy project", "Use Save As to a new project path."
                )
                return False
            return self.save_project_as()
        return self._save_to(
            Path(path) if path is not None else self.session.path,
            as_copy=False,
        )

    def save_project_as(self, path: str | Path | None = None) -> bool:
        return self._save_to(Path(path) if path is not None else None,
                             as_copy=True)

    def closeEvent(self, event) -> None:
        if self._confirm_transition() is None:
            event.ignore()
            return
        self._persist_previous_view(self._view())
        event.accept()
