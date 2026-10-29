"""ReportMaker V2 M1.4: one Branch Editor with safe project lifecycle.

V1 UI/browser remain untouched. All content edits go through the existing
canonical session, command gateway and atomic .rmproj persistence adapter.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QMainWindow, QMenu, QMessageBox,
)

from ..engine import module_outline
from ..model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from ..project_io import ReportProject, VERSION, default_projects_directory
from ..reference import manual_snapshot
from .adapters.persistence import ProjectPersistence, _same_path
from .branch.canvas import BranchCanvas
from .commands import CommandGateway
from .presentation import PresentationStore
from .session import PendingDraftError, ReportSession


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
                 presentation: PresentationStore | None = None) -> None:
        super().__init__()
        if report is not None and project is not None:
            raise ValueError("Pass either a Report or an existing project")
        self.setObjectName("reportmakerV2Window")
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
        self.setCentralWidget(self.branch)
        self.branch.bind_session(self.session, self.gateway)
        self.branch.feedback.connect(self.statusBar().showMessage)
        self.session.subscribe(lambda _: self._update_caption())

        toolbar = self.addToolBar("Project and branch actions")
        toolbar.setObjectName("v2BranchActions")
        for name, label, method, shortcut in (
            ("v2NewProject", "New", self.new_project, "Ctrl+N"),
            ("v2OpenProject", "Open", self.open_project, "Ctrl+O"),
            ("v2SaveProject", "Save", self.save_project, "Ctrl+S"),
            ("v2SaveProjectAs", "Save As", self.save_project_as, "Ctrl+Shift+S"),
            ("v2AddModule", "+ Module", self.branch.add_module, ""),
            ("v2AddSubmodule", "+ Submodule", self.branch.add_nested_module, ""),
            ("v2AddParagraph", "+ Paragraph", self.branch.add_paragraph, ""),
            ("v2AddHeading", "+ Heading", self.branch.add_heading, ""),
            ("v2AddTable", "+ Table", self.branch.add_table, ""),
            ("v2AddPageBreak", "+ Page break", self.branch.add_page_break, ""),
            ("v2AddExistingPhoto", "+ Existing photo", self.branch.add_photo, ""),
            ("v2ImportPhoto", "+ Import photo", self.branch.import_photo_dialog, "Ctrl+Shift+I"),
            ("v2PastePhoto", "Paste image", self.branch.paste_photo, "Ctrl+Shift+V"),
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
            toolbar.addAction(action)
        # M5 navigation is separate so its controls are not buried behind
        # all the editing actions on a normal Windows laptop screen.
        self.addToolBarBreak()
        navigation = self.addToolBar("Branch navigation")
        navigation.setObjectName("v2BranchNavigation")
        for name, label, method, shortcut in (
            ("v2Search", "Find", self.search_branches, "Ctrl+F"),
            ("v2NextMatch", "Next match", self.branch.next_match, "F3"),
            ("v2Focus", "Focus", self.branch.focus_module, "Ctrl+Shift+F"),
            ("v2ExitFocus", "Exit focus", self.branch.exit_focus, "Ctrl+Shift+Escape"),
            ("v2ZoomOut", "Zoom −", lambda: self.branch.zoom_by(-10), "Ctrl+-"),
            ("v2ZoomIn", "Zoom +", lambda: self.branch.zoom_by(10), "Ctrl++"),
            ("v2ZoomReset", "100%", lambda: self.branch.set_zoom(100), "Ctrl+0"),
            ("v2Fit", "Fit width", self.branch.fit_to_screen, "Ctrl+Shift+0"),
            ("v2PrevWindow", "Previous", lambda: self.branch.change_page(-1), "Ctrl+PageUp"),
            ("v2NextWindow", "Next", lambda: self.branch.change_page(1), "Ctrl+PageDown"),
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
            navigation.addAction(action)
        self.branch.selectionChanged.connect(self._update_move_actions)
        self.branch.visibilityChanged.connect(self._persist_live_view)
        self.branch.visibilityChanged.connect(self._update_move_actions)
        self._update_move_actions()
        self._restore_presentation()
        self._update_caption()
        self.statusBar().showMessage(
            "Edit inline, Apply or Revert drafts before Save/Open; "
            "New/Open/Save/Save As use portable .rmproj files."
        )

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

    def _drafts_clean(self) -> bool:
        if self.branch.drafts.pending:
            QMessageBox.warning(
                self, "Unapplied edits",
                "Apply or Revert all inline drafts before saving or switching projects."
            )
            return False
        return True

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
        self._synthetic_preview = False
        self._restore_presentation()
        self._update_caption()
        self.statusBar().showMessage("New report created (not saved)")
        return True

    def open_project(self, path: str | Path | None = None) -> bool:
        if not self._drafts_clean():
            return False
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
        if not self._drafts_clean():
            return False
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
        self.statusBar().showMessage(f"Saved {self.session.path.name}")
        return True

    def save_project(self, path: str | Path | None = None) -> bool:
        if self.session.path is not None and self.session.loaded_version != VERSION:
            # v1–v3 source is immutable. Route Save to a different Save As path.
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
