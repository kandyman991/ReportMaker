"""M3.3 canonical inline table cell and structure drafts, synthetic only."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.model import LocalizedText, TableBlock
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.v2.adapters.tables import change_grid, edit_cell
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from test_v2_inline import sample


def fixture():
    report, title, paragraph = sample()
    table = TableBlock([
        [LocalizedText("en", "Motor"), LocalizedText("en", "Ready")],
        [LocalizedText("en", "Valve"), LocalizedText("en", "Open")],
    ])
    table.rows[0][1].set_translation("it", "Pronto")
    report.modules[0].blocks[0].module.blocks.insert(0, table)
    address = NodeAddress(report.id, paragraph.module_id, table.id, "table")
    return report, title, paragraph, address


class TableCommandTests(unittest.TestCase):
    def setUp(self):
        report, self.title, self.paragraph, self.address = fixture()
        self.session = ReportSession(ReportProject(report))
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)

    def table(self):
        return find_node(self.session.report_snapshot(), self.address)

    def execute(self, kind, target, **args):
        return self.gateway.execute(CommandIntent(
            kind, target, args, self.session.revision, self.session.generation))

    def test_cell_draft_is_atomic_undoable_and_marks_only_edited_translation_stale(self):
        baseline = self.session.report_snapshot()
        self.assertTrue(self.drafts.update_cell(self.address, 0, 1, "👷 稼働中"))
        self.assertTrue(self.drafts.pending)
        self.assertEqual(self.session.report_snapshot(), baseline)
        with self.assertRaises(PendingDraftError):
            self.session.require_clean_drafts()
        self.assertTrue(self.drafts.commit(self.address))
        changed = self.table()
        self.assertEqual(changed.rows[0][1].original, "👷 稼働中")
        self.assertEqual(changed.rows[0][1].translations, {"it": "Pronto"})
        self.assertEqual(changed.rows[0][1].stale_languages, {"it"})
        self.assertFalse(changed.rows[0][0].stale_languages)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.session.report_snapshot(), baseline)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.assertEqual(self.table(), changed)

    def test_reverting_source_keeps_translation_fresh_even_after_grid_shift(self):
        self.drafts.update_cell(self.address, 0, 1, "Temporary")
        self.assertEqual(self.drafts.table_rows(self.address)[0][1].stale_languages, {"it"})
        self.drafts.update_cell(self.address, 0, 1, "Ready")
        self.assertFalse(self.drafts.pending)
        self.assertEqual(self.session.revision, 0)
        self.drafts.modify_table(self.address, "insert_column", 1)
        self.drafts.modify_table(self.address, "insert_row", 0)
        # The original translated cell moved from (0,1) to (1,2).
        self.drafts.update_cell(self.address, 1, 2, "Temporarily edited")
        self.drafts.update_cell(self.address, 1, 2, "Ready")
        cell = self.drafts.table_rows(self.address)[1][2]
        self.assertEqual(cell.translations, {"it": "Pronto"})
        self.assertEqual(cell.stale_languages, set())
        self.drafts.commit(self.address)
        self.assertEqual(self.table().rows[1][2].stale_languages, set())

    def test_row_and_column_operations_preserve_unaffected_cells_and_undo_one_step(self):
        original = deepcopy(self.table())
        self.drafts.modify_table(self.address, "insert_row", 1)
        self.drafts.modify_table(self.address, "insert_column", 1)
        self.drafts.update_cell(self.address, 1, 1, "New 🛠")
        staged = self.drafts.table_rows(self.address)
        self.assertEqual([len(row) for row in staged], [3, 3, 3])
        self.assertEqual(staged[1][1].original, "New 🛠")
        self.assertEqual(staged[0][2], original.rows[0][1])
        self.assertEqual(staged[0][2].stale_languages, set())
        self.assertEqual(self.session.revision, 0)
        self.assertTrue(self.drafts.commit(self.address))
        self.assertEqual(self.session.revision, 1)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(self.table(), original)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.drafts.modify_table(self.address, "delete_row", 1)
        self.drafts.modify_table(self.address, "delete_column", 1)
        self.drafts.commit(self.address)
        self.assertEqual(self.table(), original)

    def test_invalid_commands_and_table_drafts_fail_closed(self):
        before = self.session.report_snapshot()
        for kind, args in (
            ("set_table_rows", {"rows": [["unsafe"]]}),
            ("set_table_rows", {"rows": {}}),
            ("set_table_rows", {"rows": self.table().rows, "oops": 1}),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.execute(kind, self.address, **args)
        with self.assertRaises(ValueError):
            self.execute("set_table_rows", self.paragraph, rows=[])
        with self.assertRaises(ValueError):
            self.drafts.update_cell(self.address, -1, 0, "Invalid")
        with self.assertRaises(ValueError):
            self.drafts.modify_table(self.address, "delete_column", 999)
        self.assertEqual(self.session.report_snapshot(), before)
        self.assertEqual(self.session.revision, 0)
        self.drafts.update_cell(self.address, 0, 0, "Pending")
        with self.assertRaises(PendingDraftError):
            self.execute("delete_node", NodeAddress(
                self.address.report_id, self.address.module_id, self.address.block_id, "text"))
        self.assertTrue(self.drafts.is_dirty(self.address))
        self.drafts.discard(self.address)
        self.assertFalse(self.drafts.pending)

    def test_stale_table_and_mixed_text_drafts_and_noop_redo(self):
        self.drafts.update_cell(self.address, 0, 0, "From table")
        self.drafts.update(self.title, "From title")
        self.drafts.commit(self.title)
        with self.assertRaises(PendingDraftError):
            self.gateway.undo(self.session.generation, self.session.revision)
        self.drafts._committing = True
        try:
            rows = deepcopy(self.table().rows)
            rows[0][0].update_original("Other editor")
            self.execute("set_table_rows", self.address, rows=rows)
        finally:
            self.drafts._committing = False
        with self.assertRaises(StaleIntentError):
            self.drafts.commit(self.address)
        self.assertEqual(self.drafts._drafts[self.address].rows[0][0].original, "From table")
        self.drafts.discard(self.address)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        # A no-op direct table commit must not erase a redo state.
        self.assertIsNone(self.execute("set_table_rows", self.address,
                                       rows=deepcopy(self.table().rows)))
        self.assertIsNotNone(self.gateway.redo(self.session.generation, self.session.revision))

    def test_table_mixed_order_add_and_roundtrip(self):
        report = self.session.report_snapshot()
        owner = NodeAddress(report.id, self.paragraph.module_id)
        change = self.execute("add_table", owner, index=1)
        self.assertTrue(change.structure_changed)
        inserted = next(iter(change.changed_ids))
        kinds = [row.kind for row in project_branch(self.session.report_snapshot())
                 if row.parent_module_id == owner.module_id]
        self.assertEqual(kinds, ["table", "table", "paragraph"])
        address = NodeAddress(report.id, owner.module_id, inserted, "table")
        self.drafts.update_cell(address, 0, 0, "Ω")
        self.drafts.commit(address)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "m33.rmproj"
            save_project(self.session.project_snapshot(), path)
            opened = load_project(path)
            self.assertEqual(find_node(opened.report, address).rows[0][0].original, "Ω")
            self.assertEqual(find_node(opened.report, self.address).rows[0][1].translations,
                             {"it": "Pronto"})
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(len(find_node(self.session.report_snapshot(), owner).blocks), 2)

    def test_zero_column_table_does_not_become_ragged_on_row_insert(self):
        existing = [[]]
        with self.assertRaisesRegex(ValueError, "zero-column"):
            change_grid(existing, "insert_row", 1, "en")
        self.assertEqual(existing, [[]])
        restored = change_grid(existing, "insert_column", 0, "en")
        self.assertEqual(len(restored[0]), 1)
        self.assertEqual([len(row) for row in change_grid(
            restored, "insert_row", 1, "en")], [1, 1])
        empty = change_grid([], "insert_row", 0, "en")
        self.assertEqual([len(row) for row in empty], [1])

    def test_ragged_table_operation_rejected_without_silent_normalization(self):
        rows = [[LocalizedText("en", "A")], [LocalizedText("en", "B"), LocalizedText("en", "C")]]
        before = deepcopy(rows)
        with self.assertRaisesRegex(ValueError, "ragged"):
            change_grid(rows, "insert_column", 1, "en")
        self.assertEqual(rows, before)
        new = edit_cell(rows, 1, 1, "X")
        self.assertEqual(new[0], before[0])
        self.assertEqual(new[1][1].original, "X")


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class InlineTableQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        report, self.title, self.paragraph, self.address = fixture()
        self.win = V2MainWindow(report)
        self.win.show()
        for _ in range(5):
            self.app.processEvents()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def editor(self, row=0, column=0):
        editor = self.win.branch.table_editor_for(self.address, row, column)
        self.assertIsNotNone(editor)
        editor.setFocus()
        for _ in range(3):
            self.app.processEvents()
        return editor

    def test_cells_render_inline_without_scrollbars_and_grow_naturally(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QScrollArea
        cell = self.editor(1, 0)
        self.assertEqual(cell.toPlainText(), "Valve")
        self.assertEqual(cell.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(cell.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        original = cell.sizeHint().height()
        cell.setPlainText("Valve\n" + "⛭ Diagnostic procedure " * 20)
        self.app.processEvents()
        self.assertGreater(cell.sizeHint().height(), original)
        self.assertFalse(self.win.branch.verticalScrollBar().isVisible())
        self.assertTrue(self.win.branch.drafts.pending)

    def test_cell_edit_apply_and_restore_focus_after_commit(self):
        cell = self.editor(0, 1)
        cell.setPlainText("Changed 🚀")
        self.app.processEvents()
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertEqual(find_node(self.win.session.report_snapshot(),
                                   self.address).rows[0][1].original, "Ready")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "table-guard.rmproj"
            with self.assertRaises(PendingDraftError):
                self.win.session.require_clean_drafts()
            self.assertFalse(path.exists())
        self.assertTrue(self.win.branch.apply_table_draft(self.address))
        for _ in range(4):
            self.app.processEvents()
        self.assertEqual(find_node(self.win.session.report_snapshot(),
                                   self.address).rows[0][1].original, "Changed 🚀")
        self.assertTrue(self.win.branch.table_editor_for(self.address, 0, 1).hasFocus())
        with TemporaryDirectory() as folder:
            path = Path(folder) / "table-ui.rmproj"
            self.assertTrue(self.win.save_project(path))
            reloaded = load_project(path)
            saved = find_node(reloaded.report, self.address).rows[0][1]
            self.assertEqual(saved.original, "Changed 🚀")
            self.assertEqual(saved.translations, {"it": "Pronto"})
            self.assertEqual(saved.stale_languages, {"it"})
        self.assertTrue(self.win.branch.undo())
        self.assertEqual(find_node(self.win.session.report_snapshot(),
                                   self.address).rows[0][1].original, "Ready")

    def test_row_column_actions_revert_and_commit_preserve_cells(self):
        from PySide6.QtWidgets import QToolButton
        self.editor(0, 1)
        plus = self.win.branch.findChild(QToolButton, "v2TableInsertColumn")
        self.assertIsNotNone(plus)
        plus.click()
        self.assertEqual(len(self.win.branch.drafts.table_rows(self.address)[0]), 3)
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertIsNotNone(self.win.branch.table_editor_for(self.address, 0, 2))
        self.win.branch.revert_table_draft(self.address)
        self.assertEqual(len(self.win.branch.drafts.table_rows(self.address)[0]), 2)
        self.editor(0, 0)
        add_row = self.win.branch.findChild(QToolButton, "v2TableInsertRow")
        add_row.click()
        self.assertEqual(len(self.win.branch.drafts.table_rows(self.address)), 3)
        self.assertTrue(self.win.branch.apply_table_draft(self.address))
        self.assertEqual(len(find_node(self.win.session.report_snapshot(),
                                       self.address).rows), 3)

    def test_stale_table_remains_visible_read_only_and_revertible(self):
        from PySide6.QtWidgets import QLabel, QPushButton, QToolButton

        cell = self.editor()
        cell.setPlainText("Pending staged wording")
        rows = deepcopy(find_node(self.win.session.report_snapshot(), self.address).rows)
        rows[0][0].update_original("Other editor's wording")
        # Exercise the same parallel-edit staleness simulated in the pure test.
        self.win.branch.drafts._committing = True
        try:
            self.win.gateway.execute(CommandIntent(
                "set_table_rows", self.address, {"rows": rows},
                self.win.session.revision, self.win.session.generation))
        finally:
            self.win.branch.drafts._committing = False
        with self.assertRaises(StaleIntentError):
            self.win.branch.drafts.table_rows(self.address)
        # Previously a queued refresh threw StaleIntentError and left the
        # entire branch partly rebuilt with no way to reach Revert.
        self.win.branch._refresh()
        staged = self.win.branch.table_editor_for(self.address, 0, 0)
        self.assertEqual(staged.toPlainText(), "Pending staged wording")
        self.assertTrue(staged.isReadOnly())
        self.assertIsNotNone(self.win.branch.findChild(
            QLabel, "v2StaleTableDraftWarning"))
        self.assertFalse(self.win.branch.findChild(
            QPushButton, "v2ApplyTableDraft").isEnabled())
        self.assertFalse(self.win.branch.findChild(
            QToolButton, "v2TableInsertRow").isEnabled())
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertFalse(self.win.branch.apply_table_draft(self.address))
        self.win.branch.revert_table_draft(self.address)
        self.assertEqual(self.win.branch.table_editor_for(
            self.address, 0, 0).toPlainText(), "Other editor's wording")
        self.assertFalse(self.win.branch.drafts.pending)

    def test_table_and_text_drafts_gate_undo_and_save(self):
        cell = self.editor()
        cell.setPlainText("Pending")
        with self.assertRaises(PendingDraftError):
            self.win.session.require_clean_drafts()
        self.win.branch.drafts.update(self.title, "Also pending")
        self.assertFalse(self.win.branch.undo())
        self.assertTrue(self.win.branch.apply_table_draft(self.address))
        self.assertTrue(self.win.branch.drafts.pending)
        with self.assertRaises(PendingDraftError):
            self.win.session.require_clean_drafts()
        self.win.branch.revert_draft(self.title)
        self.assertFalse(self.win.branch.drafts.pending)


if __name__ == "__main__":
    unittest.main()
