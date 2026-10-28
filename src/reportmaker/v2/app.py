"""Fresh V2 native application shell; V1's three-panel UI is not imported.

M1.1 displays an explicitly synthetic, read-only canonical hierarchy.
The project session/commands arrive in M1.2 and direct branch editing in M1.3.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QMainWindow

from ..model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from ..reference import manual_snapshot
from .branch.canvas import BranchCanvas


def example_report() -> Report:
    """Synthetic in-memory example only: no customer file or saved project."""
    lang = "en"
    nested = Module(
        LocalizedText(lang, "Mechanical checks"),
        blocks=[
            ParagraphBlock(LocalizedText(
                lang, "Example inspection note. Inline editing follows in M1.3."
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
    """Single primary Branch Editor workspace; no detached V1 editor/tree."""

    def __init__(self, report: Report | None = None) -> None:
        super().__init__()
        self.setObjectName("reportmakerV2Window")
        self.setWindowTitle("ReportMaker V2 — Branch Editor (M1.1)")
        self.resize(1280, 820)
        self.setMinimumSize(660, 460)
        self.branch = BranchCanvas(self)
        self.setCentralWidget(self.branch)
        self.branch.set_report(example_report() if report is None else report)
        self.statusBar().showMessage(
            "M1.1 architecture preview — read-only canonical branch. "
            "Inline editing and Save/Open follow in M1.2–M1.4."
        )
