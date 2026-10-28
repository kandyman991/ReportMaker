"""M2.4 canonical outline/descendants and device-local Qt expansion state.

Only synthetic report data and temporary QSettings/archives are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from reportmaker.engine import module_outline
from reportmaker.model import PageBreakBlock
from reportmaker.project_io import load_project
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.presentation import PresentationStore
from reportmaker.v2.projections import DescendantCounts, NodeAddress, descendant_counts
from reportmaker.v2.session import ReportSession
from test_v2_structure import addr, fixture


class DerivedOutlineTests(unittest.TestCase):
    def setUp(self):
        self.session = ReportSession(fixture())
        self.gateway = CommandGateway(self.session)
        self.before = self.session.report_snapshot()
        self.a, self.b = self.before.modules
        self.child = self.a.blocks[1].module

    def execute(self, kind, target, **args):
        return self.gateway.execute(CommandIntent(kind, target, args,
            self.session.revision, self.session.generation))

    def test_counts_include_nested_mixed_and_are_visibility_independent(self):
        expected = descendant_counts(self.before)
        self.assertEqual(expected[self.a.id], DescendantCounts(1, 2, 1, 1, 0))
        self.assertEqual(expected[self.child.id], DescendantCounts(text=1))
        self.assertEqual(expected[self.b.id], DescendantCounts(text=1))
        self.assertEqual(expected[self.before.conclusion.id], DescendantCounts())
        self.assertEqual([x.number for x in module_outline(self.before)],
                         ["1", "1.1", "2", ""])
        self.assertEqual(self.session.report_snapshot(), self.before)

    def test_reparent_duplicate_delete_undo_recompute_one_outline(self):
        self.execute("move_node", addr(self.before, self.b.id),
                     anchor=addr(self.before, self.child.id), position="inside")
        nested = self.session.report_snapshot()
        self.assertEqual([x.number for x in module_outline(nested)],
                         ["1", "1.1", "1.1.1", ""])
        counts = descendant_counts(nested)
        self.assertEqual(counts[self.a.id], DescendantCounts(2, 3, 1, 1, 0))
        self.execute("duplicate_node", addr(nested, self.a.id))
        duplicated = self.session.report_snapshot()
        entries = module_outline(duplicated)
        self.assertEqual([x.number for x in entries],
                         ["1", "1.1", "1.1.1", "2", "2.1", "2.1.1", ""])
        self.assertEqual(entries[-1].module_id, self.before.conclusion.id)
        self.assertNotEqual(entries[0].module_id, entries[3].module_id)
        self.execute("delete_node", addr(duplicated, self.a.id))
        self.assertEqual([x.number for x in module_outline(self.session.report_snapshot())],
                         ["1", "1.1", "1.1.1", ""])
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(module_outline(self.session.report_snapshot()), entries)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), nested)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)

    def test_counts_recalculate_after_mixed_leaf_deletion(self):
        self.session._editor.add_block(self.a.id, PageBreakBlock())
        modified = self.session.report_snapshot()
        self.assertEqual(descendant_counts(modified)[self.a.id].page_breaks, 1)
        last = modified.modules[0].blocks[-1]
        self.execute("delete_node", addr(modified, self.a.id, last.id))
        self.assertEqual(descendant_counts(self.session.report_snapshot())[self.a.id],
                         DescendantCounts(1, 2, 1, 1, 0))


@unittest.skipUnless(os.getenv("QT_QPA_PLATFORM") == "offscreen", "Qt offscreen")
class OutlineQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from reportmaker.v2.app import V2MainWindow
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.settings = QSettings(str(self.folder / "view.ini"), QSettings.Format.IniFormat)
        self.store = PresentationStore(self.settings)
        self.win = V2MainWindow(project=fixture(), presentation=self.store)
        self.win.show()
        self.pump()
        self.windows = [self.win]

    def tearDown(self):
        for win in self.windows:
            win._confirm_transition = lambda: False
            win.close()
        self.pump()

    def pump(self):
        for _ in range(5):
            self.app.processEvents()

    def test_collapse_hides_descendants_only_and_shows_counts_and_numbering(self):
        from PySide6.QtWidgets import QLabel, QToolButton
        before = self.win.session.report_snapshot()
        a, b = before.modules
        visible = self.win.branch.visible_nodes
        was_dirty = self.win.session.dirty
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        self.pump()
        ids = [item[0] for item in self.win.branch.visible_nodes]
        self.assertEqual(ids, [before.id, a.id, b.id, b.blocks[0].id,
                               before.conclusion.id])
        self.assertEqual(self.win.session.report_snapshot(), before)
        self.assertEqual(self.store.load_view(self.win.session)[2], frozenset({a.id}))
        self.assertEqual(self.win.session.revision, 0)
        self.assertEqual(self.win.session.dirty, was_dirty)
        summaries = self.win.branch.findChildren(QLabel, "v2CollapsedSummary")
        self.assertEqual(len(summaries), 1)
        self.assertIn("1 submodules", summaries[0].text())
        self.assertIn("2 text", summaries[0].text())
        self.assertIn("1 photos", summaries[0].text())
        self.assertIn("1 tables", summaries[0].text())
        buttons = self.win.branch.findChildren(QToolButton, "v2ToggleBranch")
        self.assertTrue(any(btn.property("nodeId") == a.id and btn.text() == "▸"
                            for btn in buttons))
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        self.pump()
        self.assertEqual(self.win.branch.visible_nodes, visible)
        labels = [item.text() for item in self.win.branch.findChildren(QLabel)]
        for num in ("MODULE 1", "MODULE 1.1", "MODULE 2"):
            self.assertIn(num, labels)
        self.assertEqual(self.win.branch.verticalScrollBarPolicy().name,
                         "ScrollBarAlwaysOff")

    def test_independent_nested_collapse_survives_parent_toggle(self):
        before = self.win.session.report_snapshot()
        a = before.modules[0]
        child = a.blocks[1].module
        self.assertTrue(self.win.branch.toggle_branch(child.id))
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        self.pump()
        self.assertEqual(self.win.branch.collapsed_module_ids,
                         frozenset({a.id, child.id}))
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        self.pump()
        ids = [row[0] for row in self.win.branch.visible_nodes]
        self.assertIn(child.id, ids)
        self.assertNotIn(child.blocks[0].id, ids)
        self.assertEqual(self.store.load_view(self.win.session)[2],
                         frozenset({child.id}))
        self.assertTrue(self.win.branch.toggle_branch(child.id))
        self.pump()
        self.assertIn(child.blocks[0].id,
                      [row[0] for row in self.win.branch.visible_nodes])

    def test_pending_draft_blocks_collapse_and_reveal_preserving_editor(self):
        before = self.win.session.report_snapshot()
        a = before.modules[0]
        address = NodeAddress(before.id, a.id)
        editor = self.win.branch.editor_for(address)
        editor.setText("Not yet applied")
        editor.textEdited.emit(editor.text())
        self.assertTrue(self.win.branch.drafts.pending)
        self.assertFalse(self.win.branch.toggle_branch(a.id))
        self.assertIs(self.win.branch.editor_for(address), editor)
        self.assertEqual(editor.text(), "Not yet applied")
        self.assertEqual(self.win.branch.collapsed_module_ids, frozenset())
        self.assertTrue(self.win.branch.reveal_module(a.id))
        self.assertIs(self.win.branch.editor_for(address), editor)

    def test_hidden_draft_blocks_toc_reveal_without_losing_text(self):
        before = self.win.session.report_snapshot()
        a, b = before.modules
        child = a.blocks[1].module
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        address = NodeAddress(before.id, b.id)
        editor = self.win.branch.editor_for(address)
        editor.setText("Uncommitted but visible")
        editor.textEdited.emit(editor.text())
        self.assertFalse(self.win.branch.reveal_module(child.id))
        self.assertEqual(self.win.branch.collapsed_module_ids, frozenset({a.id}))
        self.assertEqual(editor.text(), "Uncommitted but visible")
        self.assertIs(self.win.branch.editor_for(address), editor)
        self.assertEqual(self.win.session.report_snapshot(), before)

    def test_large_paragraph_geometry_survives_collapse_expand(self):
        from PySide6.QtCore import Qt
        from reportmaker.v2.branch.canvas import DropRow
        before = self.win.session.report_snapshot()
        b = before.modules[1]
        paragraph = NodeAddress(before.id, b.id, b.blocks[0].id, "text")
        editor = self.win.branch.editor_for(paragraph)
        editor.setPlainText("Long multilingual natural-height text 🌍 日本語. " * 130)
        self.pump()
        self.assertTrue(self.win.branch.apply_draft(paragraph))
        self.pump()
        self.assertTrue(self.win.branch.toggle_branch(b.id))
        self.pump()
        self.assertIsNone(self.win.branch.editor_for(paragraph))
        self.assertTrue(self.win.branch.toggle_branch(b.id))
        self.pump()
        expanded = self.win.branch.editor_for(paragraph)
        self.assertGreater(expanded.height(), 230)
        self.assertEqual(expanded.verticalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(expanded.verticalScrollBar().maximum(), 0)
        rows = sorted(self.win.branch._host.findChildren(DropRow), key=lambda r: r.y())
        for previous, current in zip(rows, rows[1:]):
            self.assertLess(previous.geometry().bottom(), current.geometry().top())

    def test_toc_reveals_collapsed_ancestors_and_tracks_structure_changes(self):
        before = self.win.session.report_snapshot()
        a, b = before.modules
        child = a.blocks[1].module
        menu = self.win.build_contents_menu()
        self.assertEqual([x.text().strip() for x in menu.actions()],
                         ["1  A", "1.1  Child", "2  B", "Conclusions"])
        self.assertEqual([x.data() for x in menu.actions()][-1],
                         before.conclusion.id)
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        self.pump()
        self.assertFalse(any(i[0] == child.id for i in self.win.branch.visible_nodes))
        self.assertTrue(self.win.branch.reveal_module(child.id))
        self.pump()
        self.assertTrue(any(i[0] == child.id for i in self.win.branch.visible_nodes))
        self.assertEqual(self.win.branch._selected_module_id, child.id)
        self.win.gateway.execute(CommandIntent(
            "move_node", addr(before, b.id),
            {"anchor": addr(before, child.id), "position": "inside"},
            self.win.session.revision, self.win.session.generation))
        self.pump()
        refreshed = self.win.build_contents_menu()
        self.assertEqual([x.text().strip() for x in refreshed.actions()],
                         ["1  A", "1.1  Child", "1.1.1  B", "Conclusions"])
        self.assertEqual([x.module_id for x in module_outline(self.win.session.report_snapshot())],
                         [x.data() for x in refreshed.actions()])
        self.assertTrue(self.win.branch.undo())
        self.pump()
        self.assertEqual([x.text().strip() for x in self.win.build_contents_menu().actions()],
                         ["1  A", "1.1  Child", "2  B", "Conclusions"])

    def test_collapse_state_reopens_and_is_local_not_in_portable_archive(self):
        from reportmaker.v2.app import V2MainWindow
        before = self.win.session.report_snapshot()
        a, b = before.modules
        self.assertTrue(self.win.branch.toggle_branch(a.id))
        first = self.folder / "first.rmproj"
        second = self.folder / "second.rmproj"
        self.assertTrue(self.win.save_project(first))
        self.assertTrue(self.win.save_project_as(second))
        self.assertEqual(load_project(first).report, before)
        self.assertEqual(load_project(second).report, before)
        reopened = V2MainWindow(project=load_project(second), presentation=self.store)
        self.windows.append(reopened)
        self.assertEqual(reopened.branch.collapsed_module_ids, frozenset({a.id}))
        self.assertFalse(any(row[0] == a.blocks[1].module.id
                             for row in reopened.branch.visible_nodes))
        reopened.show()
        self.pump()
        self.assertTrue(reopened.branch.toggle_branch(a.id))
        self.assertTrue(reopened.save_project())
        self.assertIn(a.id, self.win.branch.collapsed_module_ids)
        old = V2MainWindow(project=load_project(first), presentation=self.store)
        self.windows.append(old)
        self.assertIn(a.id, old.branch.collapsed_module_ids)
        # Separate local settings: no collapse information is added to project v4.
        from zipfile import ZipFile
        with ZipFile(second) as archive:
            self.assertNotIn("collapsed", archive.read("manifest.json").decode("utf-8"))

    def test_stale_ids_legacy_settings_and_failed_save_as(self):
        from PySide6.QtWidgets import QMessageBox
        before = self.win.session.report_snapshot()
        a = before.modules[0].id
        key = self.store.key_for(self.win.session)
        self.settings.setValue(key, json.dumps({
            "selected": a, "scroll": 11, "collapsed": [a, "removed-node-id"]}))
        self.assertEqual(self.store.load_view(self.win.session),
                         (a, 11, frozenset({a})))
        self.settings.setValue(key, json.dumps({"selected": a, "scroll": 11}))
        self.assertEqual(self.store.load_view(self.win.session), (a, 11, frozenset()))
        self.settings.setValue(key, json.dumps({
            "selected": a, "scroll": 12, "collapsed": [False]}))
        self.assertEqual(self.store.load_view(self.win.session),
                         (None, 0, frozenset()))
        self.assertTrue(self.win.branch.toggle_branch(a))
        target = self.folder / "saved.rmproj"
        self.assertTrue(self.win.save_project(target))
        old_key = self.store.key_for(self.win.session)
        missing_parent = self.folder / "file-instead-of-dir"
        missing_parent.write_bytes(b"placeholder")
        invalid = missing_parent / "blocked.rmproj"
        with mock.patch.object(QMessageBox, "critical"):
            self.assertFalse(self.win.save_project_as(invalid))
        self.assertEqual(self.store.key_for(self.win.session), old_key)
        self.assertFalse(self.settings.contains(self.store.identity(before.id, invalid)))
        self.assertEqual(self.win.branch.collapsed_module_ids, frozenset({a}))


if __name__ == "__main__":
    unittest.main()
