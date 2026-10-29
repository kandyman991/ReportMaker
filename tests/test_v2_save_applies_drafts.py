"""Save/Open/New/Close apply pending inline edits (docs/adr/0009).

Synthetic data only. The Qt tests are offscreen behaviour checks, not native
Windows acceptance of issue #98.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import os
import unittest

from reportmaker.project_io import ReportProject, load_project
from reportmaker.v2.commands import CommandGateway
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError

from test_v2_inline import sample


class ApplyAllDraftTests(TestCase):
    def setUp(self):
        report, self.title, self.paragraph = sample()
        self.session = ReportSession(ReportProject(report))
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)

    def test_nothing_pending_is_a_noop(self):
        revision = self.session.revision
        self.assertIsNone(self.drafts.apply_all())
        self.assertEqual(self.session.revision, revision)

    def test_drafts_from_different_editors_apply_as_one_undo_step(self):
        before = self.session.report_snapshot()
        self.drafts.update(self.title, "Renamed by branch", owner="branch")
        self.drafts.update(self.paragraph, "Edited by page editor", owner="page-editor")
        revision = self.session.revision
        self.drafts.apply_all()
        self.assertFalse(self.drafts.pending)
        self.assertEqual(self.session.revision, revision + 1)
        report = self.session.report_snapshot()
        self.assertEqual(report.modules[0].title.original, "Renamed by branch")
        self.assertEqual(report.modules[0].blocks[0].module.blocks[0].text.original,
                         "Edited by page editor")
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), before)

    def test_unappliable_draft_keeps_every_draft_and_the_report(self):
        self.drafts.update(self.title, "Renamed", owner="branch")
        self.drafts.update(self.paragraph, "Edited", owner="page-editor")
        before = self.session.report_snapshot()
        revision = self.session.revision
        with mock.patch.object(self.gateway, "execute",
                               side_effect=StaleIntentError("stale")):
            with self.assertRaises(StaleIntentError):
                self.drafts.apply_all()
        self.assertTrue(self.drafts.pending)
        self.assertEqual(self.drafts.text(self.title), "Renamed")
        self.assertEqual(self.drafts.text(self.paragraph), "Edited")
        self.assertEqual(self.session.report_snapshot(), before)
        self.assertEqual(self.session.revision, revision)

    def test_named_batch_still_rejects_another_editors_fields(self):
        self.drafts.update(self.title, "Renamed", owner="branch")
        port = self.drafts.for_editor("page-editor")
        with self.assertRaises(PendingDraftError):
            port.apply_batch((self.title,))
        self.assertTrue(self.drafts.pending)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class SaveAppliesDraftsQtTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from reportmaker.v2.app import V2MainWindow, blank_report
        from reportmaker.v2.presentation import PresentationStore
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        settings = QSettings(str(self.folder / "view.ini"), QSettings.Format.IniFormat)
        self.win = V2MainWindow(
            blank_report("Save test customer", today=date(2026, 10, 29)),
            presentation=PresentationStore(settings), load_website=False,
            ephemeral_browser=True)
        self.win.show()
        self.pump()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.pump()

    def pump(self):
        for _ in range(4):
            self.app.processEvents()

    def test_save_applies_drafts_from_branch_and_page_editor_in_one_undo_step(self):
        self.win.branch.add_paragraph()
        self.pump()
        report = self.win.session.report_snapshot()
        module = report.modules[0]
        paragraph = module.blocks[-1]
        title_address = NodeAddress(report.id, module.id)
        text_address = NodeAddress(report.id, module.id, paragraph.id, "text")

        self.win.tabs.setCurrentWidget(self.win.editor_tab)
        self.pump()
        self.win.editor_tab._editors[text_address].setPlainText("Typed in the page editor")
        self.pump()
        self.win.tabs.setCurrentWidget(self.win.branch)
        self.pump()
        title_editor = self.win.branch.editor_for(title_address)
        title_editor.setText("Typed in the branch")
        title_editor.textEdited.emit(title_editor.text())
        owners = {self.win.branch.drafts.draft_owner(a) for a in (title_address, text_address)}
        self.assertEqual(owners, {"branch", "page-editor"})

        revision = self.win.session.revision
        target = self.folder / "two-editors.rmproj"
        with mock.patch("reportmaker.v2.app.QMessageBox.warning") as warn:
            self.assertTrue(self.win.save_project(target))
            warn.assert_not_called()
        self.assertFalse(self.win.branch.drafts.pending)
        saved = load_project(target).report
        self.assertEqual(saved.modules[0].title.original, "Typed in the branch")
        self.assertEqual(saved.modules[0].blocks[-1].text.original, "Typed in the page editor")
        self.assertEqual(self.win.session.revision, revision + 1)
        self.assertTrue(self.win.branch.undo())
        self.assertNotEqual(self.win.session.report_snapshot().modules[0].title.original,
                            "Typed in the branch")

    def test_apply_all_drafts_reports_the_reason_and_keeps_text(self):
        report = self.win.session.report_snapshot()
        address = NodeAddress(report.id, report.modules[0].id)
        editor = self.win.branch.editor_for(address)
        editor.setText("Draft that cannot apply")
        editor.textEdited.emit(editor.text())
        with mock.patch.object(self.win.branch.drafts, "apply_all",
                               side_effect=StaleIntentError("Source changed")):
            self.assertEqual(self.win.branch.apply_all_drafts(), "Source changed")
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertEqual(self.win.branch.drafts.text(address), "Draft that cannot apply")
        self.assertIsNone(self.win.branch.apply_all_drafts())  # the real apply works
        self.assertFalse(self.win.branch.drafts.pending)


if __name__ == "__main__":
    unittest.main()
