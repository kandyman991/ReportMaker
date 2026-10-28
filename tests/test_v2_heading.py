"""M3.1 heading text/position commands and Qt branch-only editor regressions.

All inputs synthetic. Native installed-Windows DPI/keyboard acceptance is separate.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.model import HeadingBlock, LocalizedText, ParagraphBlock
from reportmaker.project_io import ReportProject, load_project
from reportmaker.rich_text import RichFormatting, TextRun
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from test_v2_inline import sample


class HeadingCommandTests(unittest.TestCase):
    def setUp(self):
        report, _, self.paragraph_address = sample()
        self.parent = report.modules[0].blocks[0].module.id
        self.session = ReportSession(ReportProject(report))
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)

    def execute(self, kind, target, **args):
        return self.gateway.execute(CommandIntent(kind, target, args,
            self.session.revision, self.session.generation))

    def test_insert_heading_at_exact_mixed_index_and_undo(self):
        report = self.session.report_snapshot()
        owner = NodeAddress(report.id, self.parent)
        change = self.execute("add_heading", owner, text="Safety", level=3, index=0)
        assert change is not None
        heading_id = next(iter(change.changed_ids))
        blocks = find_node(self.session.report_snapshot(), owner).blocks
        self.assertEqual([type(x) for x in blocks], [HeadingBlock, ParagraphBlock])
        self.assertEqual(blocks[0].id, heading_id)
        self.assertEqual(blocks[0].level, 3)
        self.assertEqual(blocks[0].text.original, "Safety")
        self.assertTrue(change.structure_changed)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual([type(x) for x in find_node(self.session.report_snapshot(), owner).blocks],
                         [ParagraphBlock])
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.assertEqual(find_node(self.session.report_snapshot(), owner).blocks[0].id, heading_id)

    def test_heading_draft_rebases_unicode_styles_and_stales_translations(self):
        report = self.session.report_snapshot()
        owner = report.modules[0].blocks[0].module
        heading = HeadingBlock(LocalizedText("en", "Café 👷 check"), level=4,
                               rich=RichFormatting(runs=[TextRun(0, 4, bold=True)]))
        heading.text.set_translation("it", "Controllo")
        report.modules[0].blocks[0].module.blocks.insert(0, heading)
        self.session.replace_project(ReportProject(report), discard_unsaved=True)
        address = NodeAddress(report.id, owner.id, heading.id, "text")
        self.drafts.update(address, "Café + 👷 check")
        self.assertEqual(find_node(self.session.report_snapshot(), address).text.original,
                         "Café 👷 check")
        self.assertTrue(self.drafts.commit(address))
        stored = find_node(self.session.report_snapshot(), address)
        self.assertEqual(stored.rich.runs, [TextRun(0, 4, bold=True)])
        self.assertEqual(stored.level, 4)
        self.assertEqual(stored.text.translations["it"], "Controllo")
        self.assertIn("it", stored.text.stale_languages)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        old = find_node(self.session.report_snapshot(), address)
        self.assertEqual(old.text.original, "Café 👷 check")
        self.assertFalse(old.text.stale_languages)

    def test_heading_validation_and_pending_draft_fail_closed(self):
        report = self.session.report_snapshot()
        owner = NodeAddress(report.id, self.parent)
        before = self.session.report_snapshot()
        for level in (True, 0, 7, "2"):
            with self.subTest(level=level), self.assertRaises(ValueError):
                self.execute("add_heading", owner, text="Invalid", level=level)
        with self.assertRaises(ValueError):
            self.execute("add_heading", owner, text="", level=2, index=25)
        with self.assertRaises(ValueError):
            self.execute("set_heading_rich", self.paragraph_address,
                         text="Wrong type", rich=RichFormatting())
        self.assertEqual(self.session.report_snapshot(), before)
        self.assertEqual(self.session.revision, 0)
        self.drafts.update(self.paragraph_address, "Unapplied")
        with self.assertRaises(PendingDraftError):
            self.execute("add_heading", owner, text="Blocked", level=2)
        self.assertTrue(self.drafts.is_dirty(self.paragraph_address))

    def test_heading_noop_retains_redo_and_rejects_stale_source(self):
        report = self.session.report_snapshot()
        owner = report.modules[0].blocks[0].module
        heading = HeadingBlock(LocalizedText("en", "Before"))
        owner.blocks.insert(0, heading)
        self.session.replace_project(ReportProject(report), discard_unsaved=True)
        address = NodeAddress(report.id, owner.id, heading.id, "text")
        self.drafts.update(address, "After")
        self.assertTrue(self.drafts.commit(address))
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertIsNone(self.execute("set_heading_rich", address,
                                       text="Before", rich=RichFormatting()))
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.drafts.update(address, "Uncommitted")
        self.drafts._committing = True
        try:
            self.execute("set_heading_rich", address, text="External",
                         rich=RichFormatting())
        finally:
            self.drafts._committing = False
        with self.assertRaisesRegex(StaleIntentError, "Source changed"):
            self.drafts.commit(address)
        self.assertEqual(self.drafts.text(address), "Uncommitted")


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class HeadingQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        report, _, self.paragraph = sample()
        self.win = V2MainWindow(report)
        self.win.show()
        self.app.processEvents()
        self.module = report.modules[0].blocks[0].module.id

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def test_heading_inline_apply_revert_and_natural_height(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPlainTextEdit
        self.win.branch._selected_module_id = self.module
        self.assertTrue(self.win.branch.add_heading())
        self.app.processEvents()
        report = self.win.session.report_snapshot()
        heading = report.modules[0].blocks[0].module.blocks[-1]
        address = NodeAddress(report.id, self.module, heading.id, "text")
        editor = self.win.branch.editor_for(address)
        self.assertIsInstance(editor, QPlainTextEdit)
        self.assertEqual(editor.objectName(), "v2InlineHeading")
        self.assertEqual(editor.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setPlainText("Heading — 日本語 " * 75)
        self.app.processEvents()
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertGreater(editor.sizeHint().height(), 100)
        self.assertTrue(self.win.branch.apply_draft(address))
        self.app.processEvents()
        self.assertTrue(find_node(self.win.session.report_snapshot(), address).text.original)
        self.assertTrue(self.win.branch.undo())
        self.assertEqual(find_node(self.win.session.report_snapshot(), address).text.original, "")

    def test_context_insertion_after_exact_leaf_and_collapsed_parent(self):
        report = self.win.session.report_snapshot()
        parent = self.module
        self.assertTrue(self.win.branch.insert_heading_after(self.paragraph))
        self.app.processEvents()
        blocks = self.win.session.report_snapshot().modules[0].blocks[0].module.blocks
        self.assertIsInstance(blocks[1], HeadingBlock)
        self.assertEqual([row.kind for row in project_branch(self.win.session.report_snapshot())
                          if row.parent_module_id == parent], ["paragraph", "heading"])
        self.assertTrue(self.win.branch.toggle_branch(parent))
        self.win.branch._selected_module_id = parent
        self.assertTrue(self.win.branch.add_heading(level=2))
        self.app.processEvents()
        self.assertNotIn(parent, self.win.branch.collapsed_module_ids)
        self.assertIsInstance(self.win.session.report_snapshot().modules[0].blocks[0].module.blocks[-1],
                              HeadingBlock)
        self.assertTrue(any(row[1] == "heading" for row in self.win.branch.visible_nodes))
        self.assertFalse(self.win.branch.insert_heading_after(
            NodeAddress(report.id, parent, "not-a-block", "text")))

    def test_apply_restores_utf16_caret_and_selection_after_queued_redraw(self):
        from PySide6.QtGui import QTextCursor
        self.win.branch._selected_module_id = self.module
        self.assertTrue(self.win.branch.add_heading())
        for _ in range(5):
            self.app.processEvents()
        report = self.win.session.report_snapshot()
        heading = report.modules[0].blocks[0].module.blocks[-1]
        address = NodeAddress(report.id, self.module, heading.id, "text")
        editor = self.win.branch.editor_for(address)
        editor.setPlainText("👷abc")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        self.assertEqual(cursor.position(), 5)  # UTF-16 code units
        self.assertTrue(self.win.branch.apply_draft(address))
        for _ in range(5):
            self.app.processEvents()
        refreshed = self.win.branch.editor_for(address)
        self.assertEqual(refreshed.toPlainText(), "👷abc")
        self.assertEqual(refreshed.textCursor().position(), 5)
        self.assertEqual(refreshed.textCursor().anchor(), 5)
        # Editing the next character must append, not overwrite/reposition.
        refreshed.insertPlainText("!")
        self.assertEqual(refreshed.toPlainText(), "👷abc!")
        cursor = refreshed.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
        refreshed.setTextCursor(cursor)
        self.assertEqual(refreshed.textCursor().selectedText(), "👷")
        self.assertTrue(self.win.branch.apply_draft(address))
        for _ in range(5):
            self.app.processEvents()
        preserved = self.win.branch.editor_for(address).textCursor()
        self.assertEqual((preserved.anchor(), preserved.position()), (0, 2))

    def test_heading_save_reopen_retains_text(self):
        self.win.branch._selected_module_id = self.module
        self.assertTrue(self.win.branch.add_heading(level=5))
        self.app.processEvents()
        report = self.win.session.report_snapshot()
        heading = report.modules[0].blocks[0].module.blocks[-1]
        address = NodeAddress(report.id, self.module, heading.id, "text")
        self.win.branch.editor_for(address).setPlainText("Reference heading")
        self.assertTrue(self.win.branch.apply_draft(address))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "heading.rmproj"
            self.assertTrue(self.win.save_project(path))
            reopened = load_project(path)
            stored = reopened.report.modules[0].blocks[0].module.blocks[-1]
            self.assertEqual((stored.id, stored.level, stored.text.original),
                             (heading.id, 5, "Reference heading"))


if __name__ == "__main__":
    unittest.main()
