"""V2 Branch Editor natural-height cards and scrollbar-free presentation.

Qt offscreen geometry tests use synthetic report content only. Native Windows
DPI, physical wheel/touchpad and screen-reader acceptance remain separate.
"""
from __future__ import annotations

import os
import unittest

from reportmaker.v2.projections import NodeAddress
from tests.test_v2_inline import sample


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "Qt offscreen CI")
class NaturalCardLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        report, self.title, self.paragraph_address = sample()
        self.win = V2MainWindow(report)
        self.win.resize(1200, 760)
        self.win.show()
        self.pump()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.pump()

    def pump(self):
        for _ in range(6):
            self.app.processEvents()

    def paragraph(self):
        return self.win.branch.editor_for(self.paragraph_address)

    def assert_fits_content(self, editor):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtCore import Qt
        self.assertEqual(editor.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(editor.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(editor.verticalScrollBar().maximum(), 0, "Editor must never scroll internally")
        self.assertEqual(editor.horizontalScrollBar().maximum(), 0)
        cursor = QTextCursor(editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.assertLessEqual(
            editor.cursorRect(cursor).bottom(), editor.viewport().height(),
            "Last character must be visible inside the growing card",
        )

    def test_long_unicode_paragraph_grows_without_any_inner_scrollbar(self):
        from PySide6.QtCore import Qt
        from reportmaker.v2.branch.canvas import DropRow
        editor = self.paragraph()
        self.assertLess(editor.height(), 74)
        self.assert_fits_content(editor)
        long_text = "Inspection: 日本語 🧰 café — torque readings verified. " * 125
        editor.setPlainText(long_text)
        self.pump()
        self.assertGreater(editor.height(), 230)
        self.assertEqual(editor.height(), editor.sizeHint().height())
        self.assert_fits_content(editor)

        rows = self.win.branch._host.findChildren(DropRow)
        rows.sort(key=lambda row: row.y())
        for previous, current in zip(rows, rows[1:]):
            self.assertLess(previous.geometry().bottom(), current.geometry().top(),
                            "Qt-managed branch cards must never overlap")

        self.assertEqual(
            self.win.branch.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.assertEqual(
            self.win.branch.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.assertGreater(self.win.branch.verticalScrollBar().maximum(), 0,
                           "Long documents remain navigable despite a hidden scrollbar")

    def test_window_width_change_reflows_card_and_restores_height(self):
        editor = self.paragraph()
        editor.setPlainText("A long synthetic paragraph with Unicode 🌍 and words " * 115)
        self.pump()
        wide_height = editor.height()
        self.win.resize(650, 760)
        self.pump()
        narrow_height = editor.height()
        self.assertGreater(narrow_height, wide_height)
        self.assert_fits_content(editor)
        self.win.resize(1200, 760)
        self.pump()
        self.assertEqual(editor.height(), wide_height)
        self.assert_fits_content(editor)
        editor.setPlainText("Short")
        self.pump()
        self.assertLess(editor.height(), wide_height)
        self.assert_fits_content(editor)

    def test_hidden_workspace_scroll_works_over_editor_and_tracks_caret(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest
        editor = self.paragraph()
        editor.setPlainText("Synthetic paragraph 🌍 🔧 " * 330)
        self.pump()
        scrollbar = self.win.branch.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(0)
        event = QWheelEvent(
            QPointF(30, 80), QPointF(30, 80), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        # Event is delivered over the text editor, not the outer blank margin.
        self.app.sendEvent(editor.viewport(), event)
        self.pump()
        self.assertTrue(event.isAccepted())
        self.assertGreater(scrollbar.value(), 0)
        scrollbar.setValue(0)
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
        self.pump()
        self.assertGreater(scrollbar.value(), 0,
                           "Caret navigation should scroll the outer canvas")
        self.assertEqual(editor.verticalScrollBar().maximum(), 0)

    def test_canonical_commit_undo_redo_keeps_natural_height(self):
        editor = self.paragraph()
        long_text = ("Full technical finding with measured temperature " * 110)
        editor.setPlainText(long_text)
        self.pump()
        self.assertTrue(self.win.branch.apply_draft(self.paragraph_address))
        self.pump()
        editor = self.paragraph()
        self.assertEqual(editor.toPlainText(), long_text)
        self.assertGreater(editor.height(), 230)
        self.assert_fits_content(editor)
        self.assertTrue(self.win.branch.undo())
        self.pump()
        editor = self.paragraph()
        self.assertEqual(editor.toPlainText(), "Inspection note")
        self.assertLess(editor.height(), 74)
        self.assert_fits_content(editor)
        self.assertTrue(self.win.branch.redo())
        self.pump()
        editor = self.paragraph()
        self.assertEqual(editor.toPlainText(), long_text)
        self.assertGreater(editor.height(), 230)
        self.assert_fits_content(editor)


if __name__ == "__main__":
    unittest.main()
