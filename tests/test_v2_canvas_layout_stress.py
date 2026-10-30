"""Regression tests for Branch Editor layout stress and cross-surface interference.

Synthetic content only. These are offscreen Qt geometry checks: they are NOT
Windows DPI / font-rendering acceptance. Display scaling (devicePixelRatio) made
no difference when probed offscreen, so it is not parametrised here; text size
is, by scaling the application font.

Two kinds of test live here:

* strict tests describe behaviour that holds today and must keep holding;
* ``KnownDefect*`` tests assert the behaviour we WANT for problems found in the
  2026-10-29 review. They are marked ``expectedFailure`` so CI stays green, and
  they turn into an "unexpected success" (a failure) the day someone fixes the
  problem, which is the signal to delete the marker and keep the test as a
  strict one. See ``docs/v2/CANVAS_LAYOUT_STRESS.md``.
"""
from __future__ import annotations

import os
import unittest
from datetime import date
from io import BytesIO
from itertools import pairwise

from reportmaker.model import (
    HeadingBlock,
    LocalizedText,
    Module,
    NestedModuleBlock,
    PageBreakBlock,
    ParagraphBlock,
    PhotoBlock,
    Report,
    TableBlock,
)
from reportmaker.project_io import ReportProject
from reportmaker.reference import manual_snapshot
from reportmaker.v2.projections import NodeAddress


def L(text: str) -> LocalizedText:
    return LocalizedText("en", text)


SENTENCE = "Grease replaced on both drive-end bearings; corrosion noted on the coupling guard. "
LONG = "Both drive-end bearings were within tolerance and the grease was replaced according to the plan. " * 14
CJK = "駆動側ベアリングは許容範囲内でした。グリース交換済み。🔧🛠️ " * 30


def _png(width: int, height: int, color) -> bytes:
    from PIL import Image
    out = BytesIO()
    Image.new("RGB", (width, height), color).save(out, "PNG")
    return out.getvalue()


ASSETS = {"p_big": _png(4000, 3000, (80, 110, 150)), "p_tiny": _png(12, 12, (150, 80, 80)),
          "p_pano": _png(3000, 260, (60, 140, 90)), "p_tall": _png(500, 3600, (140, 120, 60))}


def _table(columns: int, long_cells: bool = False) -> TableBlock:
    def cell(row, column):
        text = f"r{row}c{column}"
        if long_cells:
            text = ("W" * 60 if column == 1 else text) + " lorem ipsum dolor" * 3
        return L(text)
    return TableBlock([[cell(r, c) for c in range(columns)] for r in range(4)])


def _module(title, blocks):
    return Module(L(title), blocks=blocks)


def _deep(levels: int) -> Module:
    inner = _module(f"Level {levels}", [ParagraphBlock(L("Deepest paragraph. " + LONG[:300]))])
    for level in range(levels - 1, 0, -1):
        inner = _module(f"Level {level} " + "title " * 6,
                        [ParagraphBlock(L(f"Paragraph at level {level}")), NestedModuleBlock(inner)])
    return inner


SCENARIOS = {
    "long text": lambda: [_module("Text", [ParagraphBlock(L(LONG)), ParagraphBlock(L(CJK)),
                                           HeadingBlock(L("Heading " + LONG[:150]), level=2)])],
    "wide table": lambda: [_module("Tables", [_table(8, True), _table(3), _table(12)])],
    "photos": lambda: [_module("Photos", [PhotoBlock(key, caption=L("Caption " + LONG[:200])) for key in ASSETS])],
    "deep nesting": lambda: [_deep(10)],
    "everything": lambda: [_module("Mix " + LONG[:90], [
        ParagraphBlock(L(LONG)), PhotoBlock("p_big", caption=L("c")), _table(6, True), PageBreakBlock(),
        NestedModuleBlock(_deep(6)), HeadingBlock(L("H"), level=1)])],
}


def _project(modules) -> ReportProject:
    report = Report(customer_id=None, customer_snapshot=manual_snapshot("Example customer"),
                    start_date=date(2026, 10, 27), end_date=date(2026, 10, 28), primary_language="en",
                    output_languages=["en"], title=L("Stress"), modules=modules,
                    conclusion=_module("Conclusions", [ParagraphBlock(L("Done."))]))
    project = ReportProject(report)
    project.assets.update(ASSETS)
    return project


def measure(window) -> list[tuple[str, str]]:
    """Return (kind, detail) for every layout problem visible right now."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTableWidget

    from reportmaker.v2.branch.canvas import DropRow
    canvas = window.branch
    host = canvas._host
    problems: list[tuple[str, str]] = []
    rows = sorted(((r.mapTo(host, QPoint(0, 0)).y(), r) for r in host.findChildren(DropRow) if r.isVisible()),
                  key=lambda pair: pair[0])
    for (top0, row0), (top1, row1) in pairwise(rows):
        if top1 < top0 + row0.height() - 1:
            problems.append(("sibling-overlap", (f"{row0.property('nodeKind')} and {row1.property('nodeKind')} "
                             f"overlap by {top0 + row0.height() - top1}px")))
    for top, row in rows:
        needed = row.minimumSizeHint().height()
        if row.height() + 1 < needed:
            problems.append(("row-shorter-than-content", f"{row.property('nodeKind')} {row.height()}px < {needed}px"))
        if row.mapTo(host, QPoint(row.width(), 0)).x() > host.width() + 1:
            problems.append(("row-outside-host", row.property("nodeKind")))
    for editor in host.findChildren(QPlainTextEdit):
        if editor.isVisible() and editor.document().size().height() > editor.viewport().height() + 4:
            problems.append(("text-clipped", (f"{editor.document().size().height():.0f}px > "
                             f"{editor.viewport().height()}px")))
    for field in host.findChildren(QLineEdit):
        if field.isVisible() and field.fontMetrics().horizontalAdvance(field.text()) + 12 > field.width():
            problems.append(("title-truncated", f"{len(field.text())} characters do not fit {field.width()}px"))
    for table in host.findChildren(QTableWidget):
        if table.isVisible() and (table.horizontalScrollBar().maximum() > 0 or table.verticalScrollBar().maximum() > 0):
            problems.append(("table-internal-scroll", table.objectName()))
        if table.isVisible() and sum(table.columnWidth(c) for c in range(table.columnCount())) > table.viewport().width() + 2:
            problems.append(("table-wider-than-card", table.objectName()))
    if canvas.horizontalScrollBar().maximum() > 0:
        problems.append(("canvas-horizontal-overflow", f"{canvas.horizontalScrollBar().maximum()}px"))
    return problems


STRICT_KINDS = {"sibling-overlap", "row-shorter-than-content", "text-clipped", "table-internal-scroll", "row-outside-host"}


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "Qt offscreen CI")
class _QtCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def pump(self, rounds=8):
        for _ in range(rounds):
            self.app.processEvents()

    def make_window(self, project, width=1100, height=800):
        from reportmaker.v2.app import V2MainWindow
        window = V2MainWindow(project=project, load_website=False, ephemeral_browser=True)
        window.resize(width, height)
        window.show()
        self.pump()
        self.addCleanup(self.close_window, window)
        return window

    def close_window(self, window):
        window._confirm_transition = lambda: False
        window.close()
        self.pump()


class CanvasLayoutStressTests(_QtCase):
    def test_no_overlap_or_clipping_across_scenarios_widths_and_zoom(self):
        for name, modules in SCENARIOS.items():
            window = self.make_window(_project(modules()))
            for width in (660, 1100, 1920):
                window.resize(width, 900)
                self.pump()
                for zoom in (55, 100, 160):
                    with self.subTest(scenario=name, width=width, zoom=zoom):
                        self.assertTrue(window.branch.set_zoom(zoom))
                        self.pump()
                        found = [p for p in measure(window) if p[0] in STRICT_KINDS]
                        self.assertEqual(found, [])

    def test_larger_system_text_does_not_cause_overlap_or_clipping(self):
        original = self.app.font()
        scaled = self.app.font()
        scaled.setPointSizeF(original.pointSizeF() * 1.5)
        self.app.setFont(scaled)
        self.addCleanup(self.app.setFont, original)
        for name in ("deep nesting", "wide table", "everything"):
            window = self.make_window(_project(SCENARIOS[name]()))
            for width in (660, 1366):
                window.resize(width, 900)
                self.pump()
                with self.subTest(scenario=name, width=width, text="150%"):
                    found = [p for p in measure(window) if p[0] in STRICT_KINDS]
                    self.assertEqual(found, [])

    def test_typing_a_long_paragraph_settles_without_overlap_and_keeps_the_caret_visible(self):
        from PySide6.QtTest import QTest
        project = _project([_module("Inspection", [ParagraphBlock(L("Intro")), NestedModuleBlock(
            _module("Mechanical checks", [ParagraphBlock(L(f"Paragraph {i}. " + SENTENCE)) for i in range(4)])),
            ParagraphBlock(L("Outro"))])])
        window = self.make_window(project)
        report = window.session.report_snapshot()
        inner = report.modules[0].blocks[1].module
        address = NodeAddress(report.id, inner.id, inner.blocks[1].id, "text")
        editor = window.branch.editor_for(address)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        for step in range(40):
            QTest.keyClicks(editor, SENTENCE[:30])
            self.pump(30)  # a row may lag one frame behind a keystroke; it must settle
            found = [p for p in measure(window) if p[0] in STRICT_KINDS]
            self.assertEqual(found, [], f"after {step + 1} insertions")
        viewport = window.branch.viewport()
        caret_y = editor.mapTo(viewport, editor.cursorRect().topLeft()).y()
        self.assertTrue(0 <= caret_y <= viewport.height(), f"caret at {caret_y}px of {viewport.height()}px")

    def test_resizing_with_an_open_draft_never_overlaps(self):
        from PySide6.QtTest import QTest
        window = self.make_window(_project(SCENARIOS["long text"]()))
        report = window.session.report_snapshot()
        module = report.modules[0]
        address = NodeAddress(report.id, module.id, module.blocks[0].id, "text")
        editor = window.branch.editor_for(address)
        editor.setFocus()
        QTest.keyClicks(editor, " draft")
        self.pump()
        for width in (700, 1500, 660, 1100):
            window.resize(width, 800)
            self.pump()
            with self.subTest(width=width):
                self.assertEqual([p for p in measure(window) if p[0] in STRICT_KINDS], [])

    def test_collapsing_and_expanding_repeatedly_keeps_the_layout_clean(self):
        window = self.make_window(_project(SCENARIOS["everything"]()))
        module_id = window.session.report_snapshot().modules[0].id
        for step in range(6):
            window.branch.toggle_branch(module_id)
            self.pump(4)
            with self.subTest(step=step):
                self.assertEqual([p for p in measure(window) if p[0] in STRICT_KINDS], [])


class SurfaceInterferenceTests(_QtCase):
    def setUp(self):
        project = _project([_module("Inspection", [ParagraphBlock(L("Intro")), NestedModuleBlock(
            _module("Mechanical checks", [ParagraphBlock(L("Original text. " + SENTENCE))]))])])
        self.window = self.make_window(project)
        report = self.window.session.report_snapshot()
        inner = report.modules[0].blocks[1].module
        self.address = NodeAddress(report.id, inner.id, inner.blocks[0].id, "text")

    def stage_in_modules(self, text=" BRANCH-EDIT"):
        from PySide6.QtTest import QTest
        editor = self.window.branch.editor_for(self.address)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, text)
        self.pump()

    def test_preview_never_shows_unapplied_text(self):
        from PySide6.QtWidgets import QLabel
        self.stage_in_modules()
        self.window.tabs.setCurrentWidget(self.window.preview_tab)
        self.pump()
        # Preview uses QLabel, not editable text controls. Assert that the
        # actual rendered report contains the approved source first: an empty
        # widget collection must not let this regression test pass vacuously.
        labels = self.window.preview_tab.findChildren(QLabel)
        shown = "\n".join(label.text() for label in labels if label.isVisible())
        self.assertTrue(labels, "Preview rendered no report labels")
        self.assertIn("Original text.", shown)
        self.assertNotIn("BRANCH-EDIT", shown)

    def test_a_field_has_exactly_one_draft_owner(self):
        from reportmaker.v2.session import PendingDraftError
        report_before = self.window.session.report_snapshot()
        self.stage_in_modules()
        drafts = self.window.branch.drafts
        self.assertEqual(drafts.draft_owner(self.address), "branch")
        staged = drafts.text(self.address)
        # A second editor must not steal ownership or replace the text.
        with self.assertRaises(PendingDraftError):
            drafts.update(self.address, "ANOTHER OWNER", owner="page-editor")
        self.assertEqual(drafts.draft_owner(self.address), "branch")
        self.assertEqual(drafts.text(self.address), staged)
        self.assertEqual(self.window.session.report_snapshot(), report_before)

    def test_the_editor_tab_cannot_change_a_draft_owned_by_modules(self):
        from PySide6.QtTest import QTest
        self.stage_in_modules()
        before = self.window.branch.drafts.text(self.address)
        self.window.tabs.setCurrentWidget(self.window.editor_tab)
        self.pump()
        page_editor = self.window.editor_tab._editors[self.address]
        page_editor.setFocus()
        page_editor.moveCursor(page_editor.textCursor().MoveOperation.End)
        QTest.keyClicks(page_editor, " PAGE-EDIT")
        self.pump()
        self.assertEqual(self.window.branch.drafts.text(self.address), before)
        self.assertEqual(self.window.branch.drafts.draft_owner(self.address), "branch")


class KnownDefectLayoutTests(_QtCase):
    """Behaviour we WANT, currently failing. Remove ``expectedFailure`` when fixed."""

    @unittest.expectedFailure
    def test_known_defect_deep_nesting_fits_a_660px_window(self):
        # 2026-10-29: 10 levels already overflow by 34px at 660px; 14 makes it unmistakable.
        window = self.make_window(_project([_deep(14)]), width=660)
        self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0,
                         "indentation should shrink instead of pushing the canvas past the window")

    @unittest.expectedFailure
    def test_known_defect_long_module_titles_are_fully_visible(self):
        # Titles are single-line fields, so a long one is silently cut off.
        title = "Gearbox lubrication and bearing inspection " * 12
        window = self.make_window(_project([_module(title, [ParagraphBlock(L("x"))])]), width=1100)
        self.assertEqual([p for p in measure(window) if p[0] == "title-truncated"], [],
                         "a long title should wrap, not be cut off")

    @unittest.expectedFailure
    def test_known_defect_drop_indicator_never_covers_card_controls(self):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtWidgets import QToolButton

        from reportmaker.v2.branch.canvas import DropRow
        window = self.make_window(_project(SCENARIOS["everything"]()))
        covered = []
        for row in window.branch._host.findChildren(DropRow):
            if not row.isVisible():
                continue
            buttons = [b for b in row.findChildren(QToolButton) if b.isVisible()]
            for position in ("before", "after", "inside"):
                try:
                    row.show_indicator(position, True)
                except KeyError:
                    continue
                self.pump(1)
                marker = QRect(row.marker.mapTo(row, QPoint(0, 0)), row.marker.size())
                for button in buttons:
                    if row.marker.isVisible() and marker.intersects(QRect(button.mapTo(row, QPoint(0, 0)), button.size())):
                        covered.append(f"{row.property('nodeKind')}/{position} covers {button.objectName()}")
                row.marker.hide()
        self.assertEqual(sorted(set(covered)), [])

    @unittest.expectedFailure
    def test_known_defect_editor_tab_does_not_accept_typing_into_a_field_edited_in_modules(self):
        from PySide6.QtTest import QTest
        project = _project([_module("Inspection", [ParagraphBlock(L("Original text. " + SENTENCE))])])
        window = self.make_window(project)
        report = window.session.report_snapshot()
        address = NodeAddress(report.id, report.modules[0].id, report.modules[0].blocks[0].id, "text")
        editor = window.branch.editor_for(address)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, " BRANCH-EDIT")
        self.pump()
        window.tabs.setCurrentWidget(window.editor_tab)
        self.pump()
        page_editor = window.editor_tab._editors[address]
        page_editor.setFocus()
        page_editor.moveCursor(page_editor.textCursor().MoveOperation.End)
        QTest.keyClicks(page_editor, " PAGE-EDIT")
        self.pump()
        # Wanted: the page editor shows the Modules draft, is read-only, and never
        # keeps characters the model rejected.
        self.assertTrue(page_editor.isReadOnly(), "should be read-only while Modules owns the draft")
        self.assertIn("BRANCH-EDIT", page_editor.toPlainText(), "should show the draft being edited in Modules")
        self.assertNotIn("PAGE-EDIT", page_editor.toPlainText(), "must not keep text the model rejected")


if __name__ == "__main__":
    unittest.main()
