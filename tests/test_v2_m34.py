"""M3.4 final typed insertions and cross-editor shared drafts (synthetic only)."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from reportmaker.model import LocalizedText, PageBreakBlock, PhotoBlock, TableBlock
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from test_v2_inline import sample


def fixture():
    report, title, para = sample()
    raw = BytesIO()
    Image.new("RGB", (4, 3), (25, 80, 125)).save(raw, "PNG")
    photo_id = "m34-synthetic"
    project = ReportProject(report, {photo_id: raw.getvalue()},
                            {photo_id: "Synthetic inspection snapshot"})
    return project, title, para, photo_id


class M34PureTests(unittest.TestCase):
    def setUp(self):
        project, self.title, self.para, self.photo_id = fixture()
        self.session = ReportSession(project)
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)
        self.report = self.session.report_snapshot()
        self.owner = NodeAddress(self.report.id, self.para.module_id)

    def intent(self, kind, target=None, *, rev=None, gen=None, **args):
        return self.gateway.execute(CommandIntent(
            kind, target, args, self.session.revision if rev is None else rev,
            self.session.generation if gen is None else gen))

    def test_typed_media_and_page_break_insertions_keep_mixed_order_and_undo(self):
        before = self.session.report_snapshot()
        new_page = self.intent("add_page_break", self.owner, index=0)
        new_photo = self.intent("add_photo", self.owner, index=1, asset_id=self.photo_id)
        module = find_node(self.session.report_snapshot(), self.owner)
        self.assertIsInstance(module.blocks[0], PageBreakBlock)
        self.assertIsInstance(module.blocks[1], PhotoBlock)
        self.assertEqual(module.blocks[1].asset_id, self.photo_id)
        self.assertEqual(module.blocks[1].caption.original_language, "en")
        self.assertEqual([b.id for b in module.blocks][:2],
                         [next(iter(new_page.changed_ids)), next(iter(new_photo.changed_ids))])
        self.assertEqual([r.kind for r in project_branch(self.session.report_snapshot())
                          if r.parent_module_id == self.para.module_id],
                         ["page-break", "photo", "paragraph"])
        with TemporaryDirectory() as folder:
            path = Path(folder) / "m34.rmproj"
            save_project(self.session.project_snapshot(), path)
            loaded = load_project(path)
            self.assertEqual(loaded.report, self.session.report_snapshot())
            self.assertEqual(loaded.assets[self.photo_id], self.session.assets[self.photo_id])
            self.assertEqual(loaded.media_library[self.photo_id],
                             "Synthetic inspection snapshot")
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), before)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))

    def test_asset_validation_is_fail_closed_and_revision_stable(self):
        before = self.session.report_snapshot()
        for asset_id in ("unknown", "../bad", "", 11):
            with self.subTest(asset=asset_id), self.assertRaises(ValueError):
                self.intent("add_photo", self.owner, asset_id=asset_id)
        for kind, args in (("add_page_break", {"asset_id": self.photo_id}),
                           ("add_photo", {"asset_id": self.photo_id, "index": -1})):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.intent(kind, self.owner, **args)
        with self.assertRaises(ValueError):
            self.intent("add_photo", self.para, asset_id=self.photo_id)
        with self.assertRaises(ValueError):
            self.intent("add_page_break", self.owner, index=99)
        self.assertEqual(before, self.session.report_snapshot())
        self.assertEqual(self.session.revision, 0)
        revision, generation = self.session.revision, self.session.generation
        self.intent("add_page_break", self.owner)
        with self.assertRaises(StaleIntentError):
            self.intent("add_photo", self.owner, rev=revision, gen=generation,
                        asset_id=self.photo_id)
        self.assertEqual(self.session.revision, 1)

    def test_editor_port_same_field_conflict_and_guarded_save(self):
        editor = self.drafts.for_editor("page-editor")
        with self.assertRaises(ValueError):
            self.drafts.for_editor("branch")
        editor.stage_text(self.para, "From page editor 🛠️")
        self.assertTrue(editor.owns(self.para))
        self.assertEqual(self.drafts.draft_owner(self.para), "page-editor")
        with self.assertRaises(PendingDraftError):
            self.drafts.update(self.para, "Branch conflict")
        with self.assertRaises(PendingDraftError):
            self.drafts.commit(self.para)
        with self.assertRaises(PendingDraftError):
            self.drafts.discard(self.para)
        with self.assertRaises(PendingDraftError):
            self.session.require_clean_drafts()
        with self.assertRaises(PendingDraftError):
            self.intent("add_page_break", self.owner)
        baseline = self.session.report_snapshot()
        self.assertEqual(find_node(baseline, self.para).text.original, "Inspection note")
        self.assertIsNotNone(editor.apply(self.para))
        self.assertFalse(editor.owns(self.para))
        changed = find_node(self.session.report_snapshot(), self.para).text
        self.assertEqual(changed.original, "From page editor 🛠️")
        self.assertEqual(changed.stale_languages, {"it"})
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), baseline)

    def test_external_table_and_branch_drafts_share_atomic_history(self):
        table_change = self.intent("add_table", self.owner, index=0)
        table_addr = NodeAddress(self.report.id, self.owner.module_id,
                                 next(iter(table_change.changed_ids)), "table")
        page = self.drafts.for_editor("page-editor")
        page.stage_cell(table_addr, 0, 0, "From page")
        page.stage_grid(table_addr, "insert_row", 1)
        with self.assertRaises(PendingDraftError):
            self.drafts.update_cell(table_addr, 0, 1, "Branch collision")
        self.drafts.update(self.title, "Branch title")
        with self.assertRaises(PendingDraftError):
            self.session.require_clean_drafts()
        self.assertIsNotNone(page.apply(table_addr))
        self.assertTrue(self.drafts.pending)
        self.assertEqual(len(find_node(self.session.report_snapshot(), table_addr).rows), 3)
        self.drafts.commit(self.title)
        self.assertFalse(self.drafts.pending)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(len(find_node(self.session.report_snapshot(), table_addr).rows), 2)

    def test_multiple_external_ports_do_not_steal_or_discard_each_other(self):
        first = self.drafts.for_editor("page-editor")
        second = self.drafts.for_editor("photo-editor")
        first.stage_text(self.para, "One")
        with self.assertRaises(PendingDraftError):
            second.stage_text(self.para, "Two")
        with self.assertRaises(PendingDraftError):
            second.revert(self.para)
        first.revert(self.para)
        self.assertFalse(self.drafts.pending)
        second.stage_text(self.para, "Two")
        self.assertIsNotNone(second.apply(self.para))
        self.assertEqual(find_node(self.session.report_snapshot(), self.para).text.original,
                         "Two")

    def test_pending_external_edit_stale_generation_rejected_and_kept(self):
        page = self.drafts.for_editor("page-editor")
        page.stage_text(self.para, "Pending")
        self.drafts._committing = True
        try:
            self.intent("set_paragraph", self.para, text="Canonical change")
        finally:
            self.drafts._committing = False
        with self.assertRaises(StaleIntentError):
            page.apply(self.para)
        self.assertTrue(page.owns(self.para))
        page.revert(self.para)
        self.assertEqual(find_node(self.session.report_snapshot(), self.para).text.original,
                         "Canonical change")


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class M34QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        project, self.title, self.para, self.photo_id = fixture()
        self.win = V2MainWindow(project=project)
        self.win.show()
        for _ in range(5):
            self.app.processEvents()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def test_contextual_mixed_insertion_uses_exact_position_and_guards_pending(self):
        report = self.win.session.report_snapshot()
        owner = next(b.module for b in report.modules[0].blocks if hasattr(b, "module"))
        original = len(owner.blocks)
        self.assertTrue(self.win.branch.insert_content_after(self.para, "page_break"))
        self.assertTrue(self.win.branch.insert_content_after(self.para, "photo",
                                                             asset_id=self.photo_id))
        self.assertEqual([type(b).__name__ for b in
                          find_node(self.win.session.report_snapshot(),
                                    NodeAddress(report.id, owner.id)).blocks],
                         ["ParagraphBlock", "PhotoBlock", "PageBreakBlock"])
        self.assertEqual(original + 2, 3)
        self.assertFalse(self.win.branch.insert_content_after(self.para, "photo",
                                                              asset_id="other"))
        baseline = self.win.session.report_snapshot()
        editor = self.win.branch.editor_for(self.para)
        editor.setPlainText("Unapplied")
        self.app.processEvents()
        self.assertFalse(self.win.branch.insert_content_after(self.para, "table"))
        self.assertEqual(self.win.session.report_snapshot(), baseline)
        self.win.branch.revert_draft(self.para)

    def test_held_contextual_revision_rejects_stale_and_preserves_tree(self):
        revision = self.win.session.revision
        generation = self.win.session.generation
        self.assertTrue(self.win.branch.insert_content_after(self.para, "heading"))
        before = self.win.session.report_snapshot()
        self.assertFalse(self.win.branch.insert_content_after(
            self.para, "page_break", expected_revision=revision,
            expected_generation=generation))
        self.assertEqual(self.win.session.report_snapshot(), before)

    def test_external_edit_disables_branch_controls_and_keeps_natural_heights(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPushButton, QLabel
        page = self.win.branch.drafts.for_editor("page-editor")
        page.stage_text(self.para, "Pending text from page editor")
        self.win.branch._refresh()
        editor = self.win.branch.editor_for(self.para)
        self.assertTrue(editor.isReadOnly())
        self.assertEqual(editor.toPlainText(), "Pending text from page editor")
        self.assertIsNotNone(self.win.branch.findChild(
            QLabel, "v2ExternalDraftNotice"))
        self.assertIsNone(self.win.branch.findChild(
            QLabel, "v2StaleTextDraftWarning"))
        self.assertEqual(editor.verticalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertFalse(editor.parent().findChild(
            QPushButton, "v2ApplyDraft").isEnabled())
        with self.assertRaises(PendingDraftError):
            self.win.session.require_clean_drafts()
        page.revert(self.para)
        self.win.branch._refresh()
        self.assertFalse(self.win.branch.editor_for(self.para).isReadOnly())

    def test_stale_text_preview_remains_visible_and_revertible(self):
        from PySide6.QtWidgets import QPushButton, QLabel
        branch = self.win.branch
        editor = branch.editor_for(self.para)
        editor.setPlainText("Pending draft")
        rows = self.win.session.report_snapshot()
        changed = find_node(rows, self.para).text
        self.assertEqual(changed.original, "Inspection note")
        branch.drafts._committing = True
        try:
            self.win.gateway.execute(CommandIntent(
                "set_paragraph", self.para, {"text": "Modified elsewhere"},
                self.win.session.revision, self.win.session.generation))
        finally:
            branch.drafts._committing = False
        branch._refresh()
        staged = branch.editor_for(self.para)
        self.assertTrue(staged.isReadOnly())
        self.assertEqual(staged.toPlainText(), "Pending draft")
        self.assertIsNotNone(branch.findChild(QLabel, "v2StaleTextDraftWarning"))
        # A stale branch-owned draft must not tell users to find another editor.
        self.assertIsNone(branch.findChild(QLabel, "v2ExternalDraftNotice"))
        self.assertFalse(staged.parent().findChild(
            QPushButton, "v2ApplyDraft").isEnabled())
        branch.revert_draft(self.para)
        self.assertEqual(branch.editor_for(self.para).toPlainText(),
                         "Modified elsewhere")
        self.assertFalse(branch.drafts.pending)

    def test_external_table_draft_is_locked_in_branch_until_port_resolves(self):
        from PySide6.QtWidgets import QPushButton
        new_table = self.win.gateway.execute(CommandIntent(
            "add_table", NodeAddress(self.para.report_id, self.para.module_id),
            {"index": 0}, self.win.session.revision, self.win.session.generation))
        address = NodeAddress(self.para.report_id, self.para.module_id,
                              next(iter(new_table.changed_ids)), "table")
        port = self.win.branch.drafts.for_editor("page-editor")
        port.stage_cell(address, 0, 0, "Held in other tab")
        self.win.branch._refresh()
        cell = self.win.branch.table_editor_for(address, 0, 0)
        self.assertTrue(cell.isReadOnly())
        self.assertEqual(cell.toPlainText(), "Held in other tab")
        self.assertFalse(self.win.branch.findChild(
            QPushButton, "v2ApplyTableDraft").isEnabled())
        port.revert(address)
        self.win.branch._refresh()
        self.assertFalse(self.win.branch.table_editor_for(address, 0, 0).isReadOnly())

    def test_existing_photo_is_explicit_asset_and_page_break_is_visible(self):
        self.assertTrue(self.win.branch.add_photo(module_id=self.para.module_id,
                                                   asset_id=self.photo_id))
        self.assertTrue(self.win.branch.add_page_break(module_id=self.para.module_id))
        report = self.win.session.report_snapshot()
        blocks = find_node(report, NodeAddress(report.id, self.para.module_id)).blocks
        self.assertIsInstance(blocks[-2], PhotoBlock)
        self.assertIsInstance(blocks[-1], PageBreakBlock)
        self.assertEqual(blocks[-2].asset_id, self.photo_id)
        self.assertTrue(self.win.branch.undo())
        self.assertTrue(self.win.branch.redo())


if __name__ == "__main__":
    unittest.main()
