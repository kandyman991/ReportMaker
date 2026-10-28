"""M1.3 direct inline edits, safe drafts, rich text, and branch UI gates.

All fixtures are invented; Qt runs offscreen without a browser or customer data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import os
import unittest

from reportmaker.model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock, Report
from reportmaker.project_io import ReportProject
from reportmaker.reference import manual_snapshot
from reportmaker.rich_text import ParagraphStyle, RichFormatting, TextRun
from reportmaker.v2.adapters.rich_text import rebase_rich
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError


def sample():
    paragraph = ParagraphBlock(LocalizedText("en", "Inspection note"))
    paragraph.text.set_translation("it", "Nota di controllo")
    child = Module(LocalizedText("en", "Checks"), [paragraph])
    parent = Module(LocalizedText("en", "Inspection"), [NestedModuleBlock(child)])
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot("Synthetic customer M1.3"),
        start_date=date(2026, 10, 27), end_date=date(2026, 10, 28),
        primary_language="en", output_languages=["en", "it"],
        title=LocalizedText("en", "Synthetic report"), modules=[parent],
        conclusion=Module(LocalizedText("en", "Conclusions")),
    )
    return report, NodeAddress(report.id, parent.id), NodeAddress(
        report.id, child.id, paragraph.id, "text")


class DraftModelTests(unittest.TestCase):
    def setUp(self):
        report, self.title, self.paragraph = sample()
        self.session = ReportSession(ReportProject(report))
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)

    def test_draft_is_detached_and_blocks_undo_redo_and_structural_commands(self):
        before = self.session.report_snapshot()
        self.drafts.update(self.title, "Changed but not committed")
        self.assertEqual(self.session.report_snapshot(), before)
        self.assertTrue(self.drafts.pending)
        with self.assertRaises(PendingDraftError):
            self.gateway.undo(self.session.generation, self.session.revision)
        with self.assertRaises(PendingDraftError):
            self.gateway.redo(self.session.generation, self.session.revision)
        with self.assertRaises(PendingDraftError):
            self.gateway.execute(CommandIntent(
                "add_module", None, {"title": "Forbidden"},
                self.session.revision, self.session.generation))
        self.drafts.discard(self.title)
        self.assertFalse(self.drafts.pending)
        self.assertEqual(self.session.report_snapshot(), before)

    def test_multiple_independent_drafts_commit_one_at_a_time(self):
        self.drafts.update(self.title, "New title")
        self.drafts.update(self.paragraph, "Repair completed \u2014 東京 🛠️")
        self.assertEqual(self.session.revision, 0)
        self.drafts.commit(self.title)
        self.assertTrue(self.drafts.pending)
        with self.assertRaises(PendingDraftError):
            self.gateway.undo(self.session.generation, self.session.revision)
        self.drafts.commit(self.paragraph)
        self.assertFalse(self.drafts.pending)
        report = self.session.report_snapshot()
        self.assertEqual(find_node(report, self.title).title.original, "New title")
        edited = find_node(report, self.paragraph)
        self.assertIn("東京", edited.text.original)
        self.assertEqual(edited.text.translations, {"it": "Nota di controllo"})
        self.assertEqual(edited.text.stale_languages, {"it"})
        self.assertEqual(self.session.revision, 2)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(find_node(self.session.report_snapshot(), self.paragraph).text.original,
                         "Inspection note")
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertIn("東京", find_node(self.session.report_snapshot(), self.paragraph).text.original)

    def test_invalid_draft_commit_remains_editable_without_mutating_history(self):
        original, _, address = sample()
        para = find_node(original, address)
        para.text = LocalizedText("en", "A\\nB")
        para.rich.paragraphs = [ParagraphStyle(2, align="right")]
        self.session.replace_project(ReportProject(original), discard_unsaved=True)
        self.drafts.update(address, "A B")
        with self.assertRaises(ValueError):
            self.drafts.commit(address)
        self.assertTrue(self.drafts.pending)
        self.assertEqual(self.session.revision, 0)
        self.assertEqual(self.drafts.text(address), "A B")
        self.assertEqual(find_node(self.session.report_snapshot(), address).text.original, "A\\nB")

    def test_rich_edit_is_atomic_and_retains_surviving_styles(self):
        report, _, address = sample()
        para = find_node(report, address)
        para.rich.runs = [TextRun(0, 10, bold=True)]
        self.session.replace_project(ReportProject(report), discard_unsaved=True)
        self.drafts.update(address, "Inspection + note")
        self.drafts.commit(address)
        changed = find_node(self.session.report_snapshot(), address)
        self.assertEqual(changed.rich.runs, [TextRun(0, 10, bold=True)])
        self.gateway.undo(self.session.generation, self.session.revision)
        original = find_node(self.session.report_snapshot(), address)
        self.assertEqual(original.text.original, "Inspection note")
        self.assertEqual(original.rich.runs, [TextRun(0, 10, bold=True)])

    def test_stale_source_cannot_overwrite_pending_draft(self):
        self.drafts.update(self.title, "From branch")
        self.drafts._committing = True  # Simulate an external adapter violation.
        try:
            self.gateway.execute(CommandIntent(
                "rename_module", self.title, {"title": "Other editor"},
                self.session.revision, self.session.generation))
        finally:
            self.drafts._committing = False
        with self.assertRaises(StaleIntentError):
            self.drafts.commit(self.title)
        self.assertEqual(self.drafts.text(self.title), "From branch")
        self.assertEqual(find_node(self.session.report_snapshot(), self.title).title.original,
                         "Other editor")

    def test_noop_draft_does_not_destroy_redo(self):
        self.drafts.update(self.title, "First")
        self.drafts.commit(self.title)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.drafts.update(self.title, "temporary")
        self.drafts.update(self.title, "Inspection")
        self.assertFalse(self.drafts.pending)
        self.assertIsNotNone(self.gateway.redo(self.session.generation, self.session.revision))

    def test_rich_rebase_keeps_unmodified_unicode_ranges(self):
        rich = RichFormatting(runs=[TextRun(0, 7, bold=True),
                                    TextRun(8, 10, italic=True)],
                              paragraphs=[ParagraphStyle(0, align="center")])
        old = "Prefix 👷Z"
        self.assertEqual(len(old), 9)
        # Use an explicit valid range for the 9 Unicode codepoints.
        rich.runs = [TextRun(0, 6, bold=True), TextRun(7, 9, italic=True)]
        result = rebase_rich(old, "Prefix + 👷Z", rich)
        self.assertEqual([(r.start, r.end) for r in result.runs],
                         [(0, 6), (9, 11)])
        self.assertEqual(result.paragraphs[0].align, "center")
        self.assertEqual(rebase_rich(old, old, rich), rich)

    def test_styled_paragraph_boundary_change_fails_without_style_loss(self):
        rich = RichFormatting(paragraphs=[ParagraphStyle(2, align="right")])
        with self.assertRaises(ValueError):
            rebase_rich("A\nB", "A B", rich)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "Qt offscreen CI")
class BranchQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        report, self.title, self.paragraph = sample()
        self.win = V2MainWindow(report)
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win.close()
        self.app.processEvents()

    def test_text_edit_is_inline_and_undoable_without_second_tree(self):
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTreeWidget
        title = self.win.branch.editor_for(self.title)
        paragraph = self.win.branch.editor_for(self.paragraph)
        self.assertIsInstance(title, QLineEdit)
        self.assertIsInstance(paragraph, QPlainTextEdit)
        self.assertFalse(self.win.findChildren(QTreeWidget))
        paragraph.setPlainText("Edited in branch: café \n東京")
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertEqual(find_node(self.win.session.report_snapshot(), self.paragraph).text.original,
                         "Inspection note")
        self.assertFalse(self.win.branch.undo())
        self.assertTrue(self.win.branch.apply_draft(self.paragraph))
        self.app.processEvents()
        self.assertIn("東京", find_node(self.win.session.report_snapshot(), self.paragraph).text.original)
        self.assertTrue(self.win.branch.undo())
        self.assertEqual(find_node(self.win.session.report_snapshot(), self.paragraph).text.original,
                         "Inspection note")
        self.assertTrue(self.win.branch.redo())
        self.assertIn("東京", find_node(self.win.session.report_snapshot(), self.paragraph).text.original)

    def test_drafts_survive_rebuild_and_revert_from_original(self):
        title = self.win.branch.editor_for(self.title)
        title.setText("Uncommitted")
        title.textEdited.emit(title.text())
        self.assertTrue(self.win.branch.drafts.is_dirty(self.title))
        self.win.branch._refresh()
        self.app.processEvents()
        self.assertEqual(self.win.branch.editor_for(self.title).text(), "Uncommitted")
        self.win.branch.revert_draft(self.title)
        self.app.processEvents()
        self.assertFalse(self.win.branch.drafts.pending)
        self.assertEqual(self.win.branch.editor_for(self.title).text(), "Inspection")

    def test_add_nested_and_paragraph_from_toolbar_preserves_order(self):
        self.assertTrue(self.win.branch.add_module())
        self.app.processEvents()
        top = self.win.session.report_snapshot().modules[-1]
        self.assertTrue(
            self.win.branch.add_nested_module(),
            "insert rejected: " + self.win.statusBar().currentMessage()
            + "; selected=" + str(self.win.branch._selected_module_id)
            + "; expected=" + top.id,
        )
        self.app.processEvents()
        child = self.win.session.report_snapshot().modules[-1].blocks[-1].module
        self.assertTrue(self.win.branch.add_paragraph())
        self.app.processEvents()
        report = self.win.session.report_snapshot()
        self.assertEqual(report.modules[-1].id, top.id)
        self.assertEqual(report.modules[-1].blocks[-1].module.id, child.id)
        self.assertEqual(report.modules[-1].blocks[-1].module.blocks[-1].text.original, "")
        self.assertEqual(self.win.branch.visible_nodes[-1][0], report.conclusion.id)
        self.assertTrue(self.win.branch.undo())
        self.assertFalse(self.win.session.report_snapshot().modules[-1].blocks[-1].module.blocks)
        self.assertTrue(self.win.branch.redo())
        self.assertEqual(len(self.win.session.report_snapshot().modules[-1].blocks[-1].module.blocks), 1)

    def test_bound_canvas_rejects_a_second_report_projection(self):
        different = self.win.session.report_snapshot()
        different.modules[0].title.update_original("Different canonical content")
        before = self.win.branch.visible_nodes
        with self.assertRaises(ValueError):
            self.win.branch.set_report(different)
        self.assertEqual(self.win.branch.visible_nodes, before)

    def test_escape_on_inline_title_reverts_local_draft(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        field = self.win.branch.editor_for(self.title)
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "Edited")
        self.assertTrue(self.win.branch.drafts.pending)
        QTest.keyClick(field, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.win.branch.editor_for(self.title).text(), "Inspection")
        self.assertFalse(self.win.branch.drafts.pending)


if __name__ == "__main__":
    unittest.main()
