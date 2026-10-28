"""Fresh V2 native application shell with M1.3 inline branch editing.

V1\'s independent UI and browser remain untouched; the V2 workspace uses
one M1.2 canonical session and typed command gateway for every edit.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from ..model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from ..project_io import ReportProject
from ..reference import manual_snapshot
from .commands import CommandGateway
from .session import ReportSession
from .branch.canvas import BranchCanvas


def example_report() -> Report:
    """Synthetic in-memory example only: no customer file or saved project."""
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


class V2MainWindow(QMainWindow):
    """One primary branch; all inserts and edits use the V2 command gateway."""

    def __init__(self, report: Report | None = None) -> None:
        super().__init__()
        self.setObjectName("reportmakerV2Window")
        self.setWindowTitle("ReportMaker V2 — Branch Editor (M1.3)")
        self.resize(1280, 820)
        self.setMinimumSize(660, 460)
        self.session = ReportSession(ReportProject(example_report() if report is None else report))
        self.gateway = CommandGateway(self.session)
        self.branch = BranchCanvas(self)
        self.setCentralWidget(self.branch)
        self.branch.bind_session(self.session, self.gateway)
        self.branch.feedback.connect(self.statusBar().showMessage)
        snapshot = self.session.report_snapshot()
        if snapshot.modules:
            self.branch._selected_module_id = snapshot.modules[0].id
        toolbar = self.addToolBar("Branch actions")
        toolbar.setObjectName("v2BranchActions")
        for label, method, shortcut in (
            ("+ Module", self.branch.add_module, ""),
            ("+ Submodule", self.branch.add_nested_module, ""),
            ("+ Paragraph", self.branch.add_paragraph, ""),
            ("Undo change", self.branch.undo, "Ctrl+Alt+Z"),
            ("Redo change", self.branch.redo, "Ctrl+Alt+Shift+Z"),
        ):
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(lambda checked=False, callback=method: callback())
            toolbar.addAction(action)
        self.statusBar().showMessage(
            "Edit titles and paragraphs in place. Enter/Ctrl+Enter applies, Escape reverts; "
            "unapplied drafts block structural edits and Undo/Redo. Save/Open follows in M1.4."
        )
