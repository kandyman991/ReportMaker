"""Regression for RC2 issue #36: Apply updates visible labels immediately.

Synthetic in-memory reports only. No desktop installation or customer files.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reportmaker.project_io import load_project
from reportmaker.reference import manual_snapshot


class AppliedBlockLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 desktop dependencies absent")
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _controller(folder):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
        from reportmaker.visual_editor import VisualReportEditor

        owner = QMainWindow()
        owner.settings = QSettings(str(Path(folder) / "local.ini"), QSettings.Format.IniFormat)
        body = QWidget()
        owner.setCentralWidget(body)
        row = QHBoxLayout(body)
        left, center = QVBoxLayout(), QVBoxLayout()
        row.addLayout(left)
        row.addLayout(center)
        return owner, VisualReportEditor(owner, left, center)

    def test_paragraph_apply_updates_list_page_preview_and_saved_project(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPushButton

        with TemporaryDirectory() as folder:
            owner, editor = self._controller(folder)
            paragraph = editor.report.modules[0].blocks[0]
            module_id, block_id = editor.report.modules[0].id, paragraph.id
            key = (module_id, block_id, "text")
            before_count = editor.blocks.count()
            selected = editor.blocks.currentItem()
            self.assertEqual(selected.data(Qt.ItemDataRole.UserRole), block_id)
            self.assertEqual(paragraph.text.original, "")

            marker = "Paragraph refresh sentinel"
            editor.text_edit.setPlainText(marker)
            caret = editor.text_edit.textCursor()
            caret.setPosition(9)
            editor.text_edit.setTextCursor(caret)
            self.assertTrue(editor._block_pending)
            self.assertIn("Unapplied", editor.block_hint.text())
            self.assertNotIn(marker, selected.text())
            self.assertNotIn(marker, editor.preview.toPlainText())
            self.assertEqual(editor.report.modules[0].blocks[0].text.original, "")
            self.assertEqual(editor.page.fields[key].toPlainText(), "")

            selection_changes = []
            editor.blocks.currentItemChanged.connect(
                lambda current, previous: selection_changes.append((current, previous)))
            undo_before = len(editor.editor._undo)
            owner.findChild(QPushButton, "applyBlockAction").click()
            self.assertEqual(len(editor.editor._undo), undo_before + 1)
            self.assertEqual(editor.blocks.count(), before_count)
            self.assertIs(editor.blocks.currentItem(), selected)
            self.assertFalse(selection_changes)
            self.assertEqual(editor._edit_block_id, block_id)
            self.assertEqual(editor.text_edit.textCursor().position(), 9)
            self.assertEqual(editor.text_edit.toPlainText(), marker)
            self.assertFalse(editor._block_pending)
            self.assertIn("applied", editor.block_hint.text())
            self.assertIn(marker, selected.text())
            self.assertEqual(editor.report.modules[0].blocks[0].text.original, marker)
            self.assertIn(marker, editor.preview.toPlainText())
            self.assertEqual(editor.page.fields[key].toPlainText(), marker)
            self.assertFalse(editor.page.pending)
            self.assertTrue(editor.dirty)

            # Clicking Apply again is a no-op, never a duplicate Undo command.
            owner.findChild(QPushButton, "applyBlockAction").click()
            self.assertEqual(len(editor.editor._undo), undo_before + 1)
            editor.undo()
            self.assertEqual(editor.report.modules[0].blocks[0].text.original, "")
            self.assertNotIn(marker, editor.blocks.item(0).text())
            self.assertNotIn(marker, editor.preview.toPlainText())
            editor.redo()
            self.assertEqual(editor.report.modules[0].blocks[0].text.original, marker)
            self.assertIn(marker, editor.blocks.item(0).text())
            self.assertIn(marker, editor.page.fields[key].toPlainText())

            # An actual .rmproj save/reopen retains the canonical edit.
            editor.editor.apply(lambda report: setattr(
                report, "customer_snapshot", manual_snapshot("Synthetic customer")))
            target = Path(folder) / "issue-36.rmproj"
            self.assertTrue(editor.save_to_path(target))
            self.assertFalse(editor.dirty)
            self.assertEqual(load_project(target).report.modules[0].blocks[0].text.original, marker)
            self.assertTrue(editor.open_from_path(target))
            self.assertIn(marker, editor.blocks.item(0).text())
            self.assertEqual(editor.page.fields[key].toPlainText(), marker)
            owner.close()

    def test_heading_and_other_pending_page_edits_update_without_selection_reset(self):
        from PySide6.QtCore import Qt

        with TemporaryDirectory() as folder:
            owner, editor = self._controller(folder)
            editor.add_heading()  # prepare both block kinds BEFORE the regression assertion
            blocks = editor.report.modules[0].blocks
            paragraph_id, heading_id = blocks[0].id, blocks[1].id
            module_id = editor.report.modules[0].id
            key = (module_id, paragraph_id, "text")
            self.assertEqual(editor.blocks.currentItem().data(Qt.ItemDataRole.UserRole),
                             heading_id)

            # Another nonconflicting page draft must be committed, not lost.
            page_marker = "Page text committed before heading"
            editor.page.fields[key].setPlainText(page_marker)
            self.assertIn(key, editor.page.pending)
            heading_marker = "Heading refresh sentinel"
            editor.text_edit.setPlainText(heading_marker)
            prior_count = editor.blocks.count()
            selected = editor.blocks.currentItem()
            self.assertNotIn(heading_marker, selected.text())
            self.assertNotIn(page_marker, editor.blocks.item(0).text())
            self.assertTrue(editor.apply_block())
            self.assertEqual(editor.blocks.count(), prior_count)
            self.assertIs(editor.blocks.currentItem(), selected)
            self.assertEqual(editor._edit_block_id, heading_id)
            self.assertIn(heading_marker, editor.blocks.item(1).text())
            self.assertIn(page_marker, editor.blocks.item(0).text())
            self.assertIn(heading_marker, editor.preview.toPlainText())
            self.assertIn(page_marker, editor.preview.toPlainText())
            self.assertEqual(editor.page.fields[key].toPlainText(), page_marker)
            self.assertFalse(editor.page.pending)
            owner.close()

    def test_cancelled_conflict_does_not_commit_or_refresh_label(self):
        from PySide6.QtWidgets import QMessageBox

        with TemporaryDirectory() as folder:
            owner, editor = self._controller(folder)
            module = editor.report.modules[0]
            key = (module.id, module.blocks[0].id, "text")
            editor.text_edit.setPlainText("New block draft")
            editor.page.fields[key].setPlainText("Different page draft")
            previous_label = editor.blocks.currentItem().text()
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Cancel):
                self.assertFalse(editor.apply_block())
            self.assertEqual(editor.blocks.currentItem().text(), previous_label)
            self.assertEqual(editor.report.modules[0].blocks[0].text.original, "")
            self.assertTrue(editor._block_pending)
            self.assertIn(key, editor.page.pending)
            self.assertEqual(editor.text_edit.toPlainText(), "New block draft")
            self.assertNotIn("New block draft", editor.preview.toPlainText())
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                self.assertTrue(editor.apply_block())
            self.assertIn("New block draft", editor.blocks.currentItem().text())
            self.assertFalse(editor.page.pending)
            self.assertEqual(editor.page.fields[key].toPlainText(), "New block draft")
            owner.close()


if __name__ == "__main__":
    unittest.main()
