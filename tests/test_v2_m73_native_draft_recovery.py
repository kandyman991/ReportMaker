"""M7.3 issue #98: visible draft recovery on installed-Windows-like Qt UI.

Offscreen tests verify behavior only, never certify physical Windows acceptance.
"""
from __future__ import annotations

import os
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from reportmaker.project_io import load_project
from reportmaker.v2.app import V2MainWindow, blank_report
from reportmaker.v2.projections import NodeAddress


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offscreen Qt")
class PendingDraftRecoveryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = V2MainWindow(blank_report("SYNTHETIC M7.3 QA"), load_website=False)
        self.window.show()
        self.app.processEvents()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def tearDown(self):
        self.window._confirm_transition = lambda: False
        self.window.close()
        self.app.processEvents()

    def _addresses(self):
        report = self.window.session.report_snapshot()
        module = report.modules[0]
        return NodeAddress(report.id, module.id), module

    def _stage_title(self, value="Mechanical Inspection"):
        address, _ = self._addresses()
        editor = self.window.branch.editor_for(address)
        editor.setText(value)
        editor.textEdited.emit(value)
        self.app.processEvents()
        return address

    def _panel(self):
        from PySide6.QtWidgets import QFrame
        return self.window.branch.findChild(QFrame, "v2PendingDraftPanel")

    def test_toolbar_block_then_explicit_apply_all_restores_structure_and_save(self):
        from PySide6.QtWidgets import QPushButton
        win = self.window
        branch = win.branch
        before = win.session.report_snapshot()
        address = self._stage_title()
        self.assertTrue(branch.drafts.pending)
        panel = self._panel()
        self.assertTrue(panel.isVisible())
        self.assertIn("UNAPPLIED EDITS", panel.findChild(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel,
            "v2PendingDraftMessage").text())
        primary = panel.findChild(QPushButton, "v2ApplyAllBranchDrafts")
        self.assertTrue(primary.isEnabled())
        self.assertIn("background: #1d4ed8", primary.styleSheet())
        self.assertFalse(branch.add_module())
        self.assertEqual(before.modules, win.session.report_snapshot().modules)
        # The toolbar cannot commit the user's text silently.
        self.assertTrue(branch.drafts.pending)
        self.assertTrue(branch.apply_all_branch_drafts())
        self.app.processEvents()
        self.assertFalse(branch.drafts.pending)
        self.assertFalse(self._panel().isVisible())
        self.assertEqual(win.session.report_snapshot().modules[0].title.original,
                         "Mechanical Inspection")
        self.assertTrue(branch.add_module())
        self.assertTrue(branch.add_nested_module())
        self.assertTrue(branch.add_paragraph())
        self.app.processEvents()
        self.assertEqual(len(win.session.report_snapshot().modules), 2)
        target = __import__("pathlib", fromlist=["Path"]).Path(self.temp.name) / "m73-test.rmproj"
        self.assertTrue(win.save_project(target))
        reopened = load_project(target).report
        self.assertEqual(reopened.modules[0].title.original, "Mechanical Inspection")
        self.assertEqual(len(reopened.modules), 2)
        self.assertEqual(len(reopened.modules[-1].blocks[-1].module.blocks), 1)

    def test_two_edit_drafts_apply_atomically_and_undo_together(self):
        win = self.window
        branch = win.branch
        self.assertTrue(branch.add_paragraph())
        initial = win.session.report_snapshot()
        module = initial.modules[0]
        paragraph = module.blocks[-1]
        paragraph_addr = NodeAddress(initial.id, module.id, paragraph.id, "text")
        field = branch.editor_for(paragraph_addr)
        field.setPlainText("A reviewed synthetic paragraph")
        self._stage_title()
        self.assertFalse(branch.add_paragraph())
        self.assertFalse(branch.drafts.pending_addresses(owner="editor"))
        self.assertEqual(len(branch.drafts.pending_addresses(owner="branch")), 2)
        before_revision = win.session.revision
        self.assertTrue(branch.apply_all_branch_drafts())
        self.assertEqual(win.session.revision, before_revision + 1)
        result = win.session.report_snapshot()
        self.assertEqual(result.modules[0].title.original, "Mechanical Inspection")
        self.assertEqual(result.modules[0].blocks[0].text.original, "A reviewed synthetic paragraph")
        self.assertTrue(branch.undo())
        restored = win.session.report_snapshot()
        self.assertEqual(restored.modules[0].title.original, module.title.original)
        self.assertEqual(restored.modules[0].blocks[0].text.original, paragraph.text.original)

    def test_invalid_batch_fails_atomically_without_draft_loss(self):
        win = self.window
        branch = win.branch
        self.assertTrue(branch.add_paragraph())
        report = win.session.report_snapshot()
        module = report.modules[0]
        paragraph = module.blocks[0]
        para_addr = NodeAddress(report.id, module.id, paragraph.id, "text")
        branch.editor_for(para_addr).setPlainText("keep this valid staged paragraph")
        title_addr = self._stage_title("Pending title")
        self.assertEqual(len(branch.drafts.pending_addresses(owner="branch")), 2)
        before = win.session.report_snapshot()
        revision = win.session.revision
        with mock.patch.object(branch.drafts.gateway, "execute",
                               side_effect=ValueError("Synthetic validation rejection")):
            self.assertFalse(branch.apply_all_branch_drafts())
        self.assertEqual(win.session.report_snapshot(), before)
        self.assertEqual(win.session.revision, revision)
        self.assertEqual(len(branch.drafts.pending_addresses(owner="branch")), 2)
        self.assertEqual(branch.drafts.text(para_addr),
                         "keep this valid staged paragraph")
        branch.drafts.update(title_addr, "Valid title")
        self.assertTrue(branch.apply_all_branch_drafts())
        self.assertEqual(win.session.report_snapshot().modules[0].title.original,
                         "Valid title")
        self.assertEqual(win.session.report_snapshot().modules[0].blocks[0].text.original,
                         "keep this valid staged paragraph")

    def test_toolbar_action_and_save_warning_reveal_recovery_banner(self):
        from PySide6.QtGui import QAction
        win = self.window
        self._stage_title()
        initial_count = len(win.session.report_snapshot().modules)
        win.findChild(QAction, "v2AddModule").trigger()
        self.assertEqual(len(win.session.report_snapshot().modules), initial_count)
        self.assertTrue(self._panel().isVisible())
        # Save is an explicit user action: it applies the pending edit as one
        # undoable change and saves (docs/adr/0009-save-applies-pending-edits.md).
        from pathlib import Path
        target = Path(self.temp.name) / "saved-with-pending-edit.rmproj"
        with mock.patch("reportmaker.v2.app.QMessageBox.warning") as warning:
            self.assertTrue(win.save_project(target))
            warning.assert_not_called()
        self.assertFalse(win.branch.drafts.pending)
        self.assertFalse(self._panel().isVisible())
        self.assertEqual(load_project(target).report.modules[0].title.original,
                         "Mechanical Inspection")
        win.findChild(QAction, "v2AddModule").trigger()
        self.assertEqual(len(win.session.report_snapshot().modules), initial_count + 1)

    def test_save_that_cannot_apply_keeps_edits_and_points_at_the_panel(self):
        from pathlib import Path
        from PySide6.QtWidgets import QPushButton
        from reportmaker.v2.session import StaleIntentError
        win = self.window
        address = self._stage_title()
        target = Path(self.temp.name) / "must-not-exist.rmproj"
        failure = StaleIntentError("Source changed since editing began; draft preserved")
        with mock.patch.object(win.branch.drafts, "apply_all", side_effect=failure), \
                mock.patch("reportmaker.v2.app.QMessageBox.warning") as warning:
            self.assertFalse(win.save_project(target))
            warning.assert_called_once()
            self.assertIn("Source changed", warning.call_args.args[2])
            self.assertIn("UNAPPLIED EDITS", warning.call_args.args[2])
        self.assertFalse(target.exists())
        self.assertTrue(win.branch.drafts.pending)
        self.assertEqual(win.branch.drafts.text(address), "Mechanical Inspection")
        self.assertTrue(self._panel().isVisible())
        # The explicit panel button still works exactly as before.
        win.branch.findChild(QPushButton, "v2ApplyAllBranchDrafts").click()
        self.app.processEvents()
        self.assertFalse(win.branch.drafts.pending)

    def test_drag_and_photo_import_reveal_recovery_without_os_dialog(self):
        win = self.window
        addr = self._stage_title()
        original = win.session.report_snapshot()
        with mock.patch("reportmaker.v2.branch.canvas.QFileDialog.getOpenFileNames") as chooser:
            self.assertFalse(win.branch.import_photo_dialog())
            chooser.assert_not_called()
        self.assertFalse(win.branch.paste_photo())
        self.assertIsNone(win.branch._arm_drag(addr))
        self.assertEqual(win.session.report_snapshot(), original)
        self.assertTrue(self._panel().isVisible())
        self.assertTrue(win.branch.drafts.pending)

    def test_discard_confirmation_never_silently_loses_words(self):
        from PySide6.QtWidgets import QMessageBox
        win = self.window
        addr = self._stage_title()
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.No):
            self.assertFalse(win.branch.discard_all_branch_drafts())
        self.assertEqual(win.branch.drafts.text(addr), "Mechanical Inspection")
        self.assertTrue(win.branch.drafts.pending)
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(win.branch.discard_all_branch_drafts())
        self.assertFalse(win.branch.drafts.pending)
        self.assertNotEqual(win.session.report_snapshot().modules[0].title.original,
                            "Mechanical Inspection")

    def test_external_owner_is_not_committed_by_modules_banner(self):
        win = self.window
        addr, module = self._addresses()
        external = win.branch.drafts.for_editor("editor")
        external.stage_text(addr, "Editor-only draft")
        self.app.processEvents()
        panel = self._panel()
        self.assertTrue(panel.isVisible())
        self.assertFalse(panel.findChild(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton,
            "v2ApplyAllBranchDrafts").isEnabled())
        self.assertFalse(win.branch.apply_all_branch_drafts())
        self.assertEqual(module.title.original,
                         win.session.report_snapshot().modules[0].title.original)
        self.assertTrue(win.branch.drafts.pending)
        external.revert(addr)
        self.app.processEvents()
        self.assertFalse(self._panel().isVisible())

    def test_per_card_apply_and_revert_are_contrast_safe(self):
        from PySide6.QtWidgets import QPushButton
        branch = self.window.branch
        self._stage_title()
        apply = branch.findChild(QPushButton, "v2ApplyDraft")
        revert = branch.findChild(QPushButton, "v2RevertDraft")
        self.assertIn("color: #ffffff", apply.styleSheet())
        self.assertIn("color: #192d40", revert.styleSheet())
        self.assertTrue(apply.isEnabled())
        self.assertTrue(revert.isEnabled())


if __name__ == "__main__":
    unittest.main()
