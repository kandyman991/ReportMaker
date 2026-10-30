"""Regression tests for Branch Editor layout stress and cross-surface interference.

Synthetic content only. These are offscreen Qt geometry checks: they are NOT
Windows DPI / font-rendering acceptance. Display scaling (devicePixelRatio) made
no difference when probed offscreen, so it is not parametrised here; text size
is, by scaling the application font.

Found in the 2026-10-29 review and fixed since (see
``docs/v2/CANVAS_LAYOUT_STRESS.md``): deeply nested modules overflowing a narrow
window, long module titles cut off, the drop indicator covering a card's own
buttons, and the Editor tab accepting typing into a field being edited in Modules.
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

    def wait_until(self, condition, message="condition never became true", timeout_ms=8000):
        """Run the real event loop until ``condition()`` holds. Event-based, not a fixed sleep."""
        from PySide6.QtTest import QTest
        waited = 0
        while not condition():
            if waited >= timeout_ms:
                self.fail(message)
            QTest.qWait(10)
            waited += 10

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


class AdaptiveLayoutTests(_QtCase):
    def test_deep_nesting_fits_a_660px_window(self):
        window = self.make_window(_project([_deep(14)]), width=660)
        self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0,
                         "indentation should shrink instead of pushing the canvas past the window")
        self.assertEqual([p for p in measure(window) if p[0] in STRICT_KINDS], [])

    def test_indentation_only_shrinks_when_it_has_to(self):
        shallow = self.make_window(_project([_deep(3)]), width=1100)
        self.assertEqual(shallow.branch._gutters[-1].step, 25)  # the normal step
        deep = self.make_window(_project([_deep(14)]), width=660)
        steps = {gutter.step for gutter in deep.branch._gutters}
        self.assertEqual(len(steps), 1, "every row must use the same step so levels line up")
        self.assertLess(steps.pop(), 25)
        deep.resize(1500, 800)
        self.pump()
        self.assertEqual({g.step for g in deep.branch._gutters}, {25}, "wider window restores it")

    def test_connector_lines_stay_distinct_at_the_narrowest_step(self):
        # 20 levels at 660 px: still fits when a 90 px rail takes width from the canvas.
        window = self.make_window(_project([_deep(20)]), width=660)
        step = window.branch._gutters[-1].step
        self.assertGreaterEqual(step, 6)
        self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0)

    def _cards(self, window):
        from PySide6.QtWidgets import QFrame
        return window.branch._host.findChildren(QFrame, "v2BranchCard")

    def test_the_fit_follows_the_real_widths_not_a_cached_estimate(self):
        # A review run on another machine (different font metrics) saw the 20-level
        # case overflow by 3 px: the fit had used a card width cached at build time.
        window = self.make_window(_project([_deep(20)]), width=900)
        for card in self._cards(window):
            card.setMinimumWidth(card.minimumSizeHint().width() + 25)  # a wider font or style
        window.resize(660, 800)
        self.pump(10)
        self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(window.branch._gutters[-1].step, 6)

    def test_larger_application_fonts_still_fit_20_levels_at_660px(self):
        from PySide6.QtGui import QFont
        base = self.app.font()
        self.addCleanup(self.app.setFont, base)
        for points in (9, 12, 14):
            font = QFont(base)
            font.setPointSize(points)
            self.app.setFont(font)
            window = self.make_window(_project([_deep(20)]), width=660)
            self.pump(10)
            with self.subTest(points=points):
                self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0)
                self.assertGreaterEqual(window.branch._gutters[-1].step, 6)

    def test_the_side_margin_gives_room_back_only_when_the_step_is_already_at_its_floor(self):
        window = self.make_window(_project([_deep(20)]), width=660)
        canvas = window.branch
        self.assertEqual(canvas._body.contentsMargins().left(), 20, "plenty of room: margins untouched")
        for gutter in canvas._gutters:
            gutter.set_step(6)
        inner = canvas.viewport().width() - 40
        worst = max(row.minimumSizeHint().width() for row in canvas._rows)
        extra = inner - worst + 12  # make every row 12 px too wide even at the 6 px step
        for card in self._cards(window):
            card.setMinimumWidth(card.minimumSizeHint().width() + extra)
        canvas._apply_indent()
        self.assertEqual(canvas._gutters[-1].step, 6, "the step goes to its floor first")
        self.assertEqual(canvas._body.contentsMargins().left(), 14, "then each side gives up 6 px")
        self.assertEqual(canvas._body.contentsMargins().right(), 14)
        self.assertEqual(canvas.horizontalScrollBar().maximum(), 0)
        window.resize(1400, 800)
        self.pump(10)
        self.assertEqual(canvas._body.contentsMargins().left(), 20, "and they come back when there is room")

    def test_a_shallow_report_keeps_the_normal_step_and_margins(self):
        window = self.make_window(_project([_deep(3)]), width=660)
        self.assertEqual(window.branch._gutters[-1].step, 25)
        self.assertEqual(window.branch._body.contentsMargins().left(), 20)

    def test_a_long_title_wraps_instead_of_being_cut_off(self):
        title = "Gearbox lubrication and bearing inspection " * 12
        window = self.make_window(_project([_module(title, [ParagraphBlock(L("x"))])]), width=1100)
        report = window.session.report_snapshot()
        editor = window.branch.editor_for(NodeAddress(report.id, report.modules[0].id))
        self.assertEqual(editor.text(), title)
        line = editor.fontMetrics().lineSpacing()
        self.assertGreater(editor.height(), 2 * line, "a 500-character title needs several lines")
        self.assertLessEqual(editor.document().size().height(), editor.viewport().height() + 4)
        self.assertEqual([p for p in measure(window) if p[0] in STRICT_KINDS | {"title-truncated"}], [])

    def test_an_unbroken_title_also_wraps(self):
        window = self.make_window(_project([_module("W" * 400, [ParagraphBlock(L("x"))])]), width=660)
        self.assertEqual([p for p in measure(window) if p[0] in STRICT_KINDS], [])
        self.assertEqual(window.branch.horizontalScrollBar().maximum(), 0)

    def test_a_title_stays_one_logical_line(self):
        from PySide6.QtCore import QMimeData, Qt
        from PySide6.QtTest import QTest
        window = self.make_window(_project([_module("Plain", [ParagraphBlock(L("x"))])]))
        report = window.session.report_snapshot()
        address = NodeAddress(report.id, report.modules[0].id)
        title = window.branch.editor_for(address)
        emitted, returned = [], []
        title.textEdited.connect(emitted.append)
        title.returnPressed.connect(lambda: returned.append(True))
        title.setText("Set by code")
        self.assertEqual(emitted, [], "setText must not look like typing")
        title.setFocus()
        title.moveCursor(title.textCursor().MoveOperation.End)
        QTest.keyClicks(title, "!")
        self.assertEqual(emitted[-1], "Set by code!")
        QTest.keyClick(title, Qt.Key.Key_Return)
        self.assertEqual(returned, [True])
        self.assertNotIn("\n", title.text())
        data = QMimeData()
        data.setText("first\nsecond\r\nthird")
        title.insertFromMimeData(data)
        self.assertNotIn("\n", title.text())
        self.assertTrue(title.text().endswith("first second third"))

    def test_the_drop_indicator_never_covers_card_controls(self):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtWidgets import QAbstractButton

        from reportmaker.v2.branch.canvas import DropRow
        for width in (660, 1100):
            window = self.make_window(_project(SCENARIOS["everything"]()), width=width)
            covered = []
            for row in window.branch._host.findChildren(DropRow):
                if not row.isVisible():
                    continue
                buttons = [b for b in row.findChildren(QAbstractButton) if b.isVisible()]
                for position in ("before", "after", "inside"):
                    try:
                        row.show_indicator(position, True)
                    except KeyError:
                        continue
                    self.pump(1)
                    marker = QRect(row.marker.mapTo(row, QPoint(0, 0)), row.marker.size())
                    for button in buttons:
                        area = QRect(button.mapTo(row, QPoint(0, 0)), button.size())
                        if row.marker.isVisible() and marker.intersects(area):
                            covered.append(f"{row.property('nodeKind')}/{position} covers {button.text()!r}")
                    row.marker.hide()
            with self.subTest(width=width):
                self.assertEqual(sorted(set(covered)), [])


class LiveInterferenceTests(_QtCase):
    """Modules and Editor visible at the same time (the split workspace).

    Locking is asserted immediately after the keystroke, with no waiting: it happens
    inside the draft notification. Only the things that are allowed to be late (the
    redraw that adds notices, unlocking after the other editor lets go) use
    ``wait_until``, which runs the real event loop until the condition holds.
    """

    def setUp(self):
        project = _project([_module("Inspection", [ParagraphBlock(L("Original text. " + SENTENCE)),
                                                   _table(3)])])
        self.window = self.make_window(project, width=1280)
        report = self.window.session.report_snapshot()
        module = report.modules[0]
        self.text = NodeAddress(report.id, module.id, module.blocks[0].id, "text")
        self.table = NodeAddress(report.id, module.id, module.blocks[1].id, "table")
        self.window.tabs.setCurrentWidget(self.window.editor_tab)
        self.pump()

    def type_in_modules(self, text=" BRANCH-EDIT"):
        from PySide6.QtTest import QTest
        editor = self.window.branch.editor_for(self.text)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, text)

    def type_in_page(self, text=" PAGE-EDIT"):
        from PySide6.QtTest import QTest
        edit = self.page_editor()
        edit.setFocus()
        edit.moveCursor(edit.textCursor().MoveOperation.End)
        QTest.keyClicks(edit, text)

    def page_editor(self):
        return self.window.editor_tab._editors[self.text]

    def modules_field(self):
        return self.window.branch.editor_for(self.text)

    def assert_single_writer(self, address=None):
        """Whoever does not own the draft cannot write; if nobody owns it, both can."""
        address = address or self.text
        owner = self.window.branch.drafts.draft_owner(address)
        modules, page = self.modules_field(), self.page_editor()
        self.assertEqual(modules.isReadOnly(), owner == "page-editor",
                         f"Modules field read-only={modules.isReadOnly()} but owner={owner}")
        self.assertEqual(page.isReadOnly(), owner == "branch",
                         f"Editor field read-only={page.isReadOnly()} but owner={owner}")

    def test_the_editor_tab_locks_a_modules_draft_at_once_and_shows_it(self):
        self.type_in_modules()
        edit = self.page_editor()
        self.assertTrue(edit.isReadOnly(), "no waiting: the lock happens inside the notification")
        self.assertIn("BRANCH-EDIT", edit.toPlainText())
        before = self.window.branch.drafts.text(self.text)
        self.type_in_page()
        self.assertNotIn("PAGE-EDIT", edit.toPlainText())
        self.assertEqual(self.window.branch.drafts.text(self.text), before)
        self.assertEqual(self.window.branch.drafts.draft_owner(self.text), "branch")

    def test_modules_locks_an_editor_draft_at_once_and_shows_it(self):
        self.type_in_page()
        field = self.modules_field()
        self.assertEqual(self.window.branch.drafts.draft_owner(self.text), "page-editor")
        self.assertTrue(field.isReadOnly(), "no waiting, and Modules need not be on screen")
        self.assertIn("PAGE-EDIT", field.toPlainText())

    def test_the_lock_needs_neither_timers_nor_redraws(self):
        # Take away everything that is allowed to be late: the debounced redraw, the
        # deferred rebuild and the manual sync. The locks must still be there.
        window = self.window
        window.branch._refresh = lambda: None
        window.branch._foreign_timer.stop()
        window.branch._foreign_timer.start = lambda *a: None
        window.editor_tab._queue_sync = lambda: None
        self.type_in_modules()
        self.assert_single_writer()
        window.branch.revert_draft = lambda *a: None  # (no redraw either way)
        window.branch.drafts.discard(self.text)
        self.assertFalse(self.page_editor().isReadOnly(), "unlocking is immediate on this side")
        window.editor_tab.port.stage_text(self.text, "from the page editor")
        self.assertTrue(self.modules_field().isReadOnly())
        self.assertEqual(self.modules_field().toPlainText(), "from the page editor")

    def test_a_missed_notification_is_caught_by_the_first_rejected_keystroke(self):
        drafts = self.window.branch.drafts
        drafts._change_listeners.clear()  # nobody hears about the next draft
        self.window.editor_tab.port.stage_text(self.text, "owned by the page editor")
        self.assertFalse(self.modules_field().isReadOnly(), "this is the missed-notification case")
        self.type_in_modules("Q")
        self.wait_until(lambda: self.modules_field().isReadOnly(),
                        "a rejected keystroke must lock the field")
        self.wait_until(lambda: self.modules_field().toPlainText() == "owned by the page editor",
                        "and put the real draft text back")
        self.assertEqual(drafts.draft_owner(self.text), "page-editor")

    def test_the_field_becomes_editable_again_when_modules_reverts(self):
        self.type_in_modules()
        self.window.branch.revert_draft(self.text)
        self.assertFalse(self.window.branch.drafts.is_dirty(self.text))
        edit = self.page_editor()
        self.wait_until(lambda: not edit.isReadOnly(), "the Editor field never unlocked")
        self.assertNotIn("BRANCH-EDIT", edit.toPlainText())
        self.assertEqual(edit.toolTip(), "")

    def test_applying_in_modules_refreshes_the_editor_tab(self):
        self.type_in_modules()
        self.assertTrue(self.window.branch.apply_draft(self.text))
        self.wait_until(lambda: not self.page_editor().isReadOnly()
                        and "BRANCH-EDIT" in self.page_editor().toPlainText(),
                        "the Editor never showed the applied text")

    def test_modules_redraw_adds_the_notice_after_the_lock(self):
        from PySide6.QtWidgets import QLabel
        self.type_in_page()
        self.window.tabs.setCurrentWidget(self.window.branch)
        self.wait_until(lambda: any(label.objectName() == "v2ExternalDraftNotice"
                                    for label in self.window.branch.findChildren(QLabel)),
                        "the redraw never added the 'belongs to the other editor' notice")
        self.assertTrue(self.modules_field().isReadOnly())
        self.assertIn("PAGE-EDIT", self.modules_field().toPlainText())

    def test_a_table_draft_in_modules_locks_the_editor_tab_grid_at_once(self):
        from PySide6.QtWidgets import QAbstractItemView
        self.assertTrue(self.window.branch.drafts.update_cell(self.table, 0, 0, "edited"))
        grid = self.window.editor_tab._tables[self.table]
        self.assertEqual(grid.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assertEqual(grid.item(0, 0).text(), "edited")

    def test_ownership_and_locks_agree_after_every_step_of_a_long_back_and_forth(self):
        window = self.window
        for round_number in range(4):
            with self.subTest(round=round_number, step="modules edits"):
                self.type_in_modules(f" M{round_number}")
                self.assert_single_writer()
                self.type_in_page(" rejected")          # must change nothing
                self.assert_single_writer()
                self.assertNotIn("rejected", window.branch.drafts.text(self.text))
            with self.subTest(round=round_number, step="modules reverts"):
                window.branch.revert_draft(self.text)
                self.wait_until(lambda: not self.page_editor().isReadOnly(), "Editor never unlocked")
                self.assert_single_writer()
            with self.subTest(round=round_number, step="editor edits"):
                self.type_in_page(f" P{round_number}")
                self.assert_single_writer()
                self.type_in_modules(" rejected")       # must change nothing
                self.wait_until(lambda: self.modules_field().isReadOnly(), "Modules never locked")
                self.assertNotIn("rejected", window.branch.drafts.text(self.text))
            with self.subTest(round=round_number, step="editor reverts"):
                window.editor_tab.revert_changes()
                self.wait_until(lambda: not self.modules_field().isReadOnly(),
                                "Modules never unlocked")
                self.wait_until(lambda: self.page_editor().toPlainText().startswith("Original text."),
                                "the Editor page never showed the committed text")
                self.assert_single_writer()

    def test_draft_change_notifications_carry_no_text(self):
        events = []
        unsubscribe = self.window.branch.drafts.subscribe_changes(
            lambda address, owner, previous: events.append((address, owner, previous)))
        self.type_in_modules("!")
        self.window.branch.revert_draft(self.text)
        unsubscribe()
        self.assertEqual(events[0], (self.text, "branch", None))
        self.assertEqual(events[-1], (self.text, None, "branch"))
        self.assertTrue(all(isinstance(value, (type(None), str, NodeAddress))
                            for event in events for value in event))


if __name__ == "__main__":
    unittest.main()
