"""M2.3 structural actions: synthetic canonical, project and offscreen Qt checks."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import os

from reportmaker.model import NestedModuleBlock, PageBreakBlock
from reportmaker.project_io import load_project
from reportmaker.v2.adapters.persistence import ProjectPersistence
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.projections import NodeAddress, project_branch
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from reportmaker.v2.structure import plan_indent, plan_outdent, structural_node

from test_v2_structure import addr, fixture


def all_identifiers(report):
    return {r.stable_id for r in project_branch(report)} | {
        r.wrapper_id for r in project_branch(report) if r.wrapper_id
    }


class StructuralActionTests(TestCase):
    def setUp(self):
        self.session = ReportSession(fixture())
        self.gateway = CommandGateway(self.session)
        self.before = self.session.report_snapshot()
        self.a, self.b = self.before.modules
        self.child = self.a.blocks[1].module

    def run_command(self, kind, address, **args):
        return self.gateway.execute(CommandIntent(
            kind, address, args, self.session.revision, self.session.generation))

    def move(self, source, where):
        anchor, position = where
        return self.run_command("move_node", source, anchor=anchor, position=position)

    def test_indent_and_outdent_from_root_preserve_content_and_undo(self):
        source = addr(self.before, self.b.id)
        self.assertEqual(plan_indent(self.before, source),
                         (addr(self.before, self.a.id), "inside"))
        self.move(source, plan_indent(self.before, source))
        nested = self.session.report_snapshot()
        self.assertEqual(len(nested.modules), 1)
        self.assertEqual(nested.modules[0].blocks[-1].module.id, self.b.id)
        self.assertEqual(nested.modules[0].blocks[-1].module.blocks[0],
                         self.b.blocks[0])
        wrapper = nested.modules[0].blocks[-1].id
        self.move(source, plan_outdent(nested, source))
        promoted = self.session.report_snapshot()
        self.assertEqual([m.id for m in promoted.modules], [self.a.id, self.b.id])
        self.assertEqual(promoted.modules[1].blocks, self.b.blocks)
        self.assertNotIn(wrapper, all_identifiers(promoted))
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), nested)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), nested)

    def test_outdent_one_level_in_mixed_parent(self):
        # Child is nested under A; its preceding Heading blocks indentation.
        source = addr(self.before, self.child.id)
        with self.assertRaises(ValueError):
            plan_indent(self.before, source)
        self.move(source, plan_outdent(self.before, source))
        after = self.session.report_snapshot()
        self.assertEqual([m.id for m in after.modules],
                         [self.a.id, self.child.id, self.b.id])
        self.assertEqual(after.modules[1].blocks, self.child.blocks)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)

    def test_nested_indent_keeps_wrapper_identity(self):
        # Add a second nested sibling immediately following the first.
        child2 = deepcopy(self.child)
        child2.id = "child2_unique"
        for block in child2.blocks:
            block.id += "_clone"
        self.session._editor.add_module(child2, parent_id=self.a.id, index=2)
        source_report = self.session.report_snapshot()
        nested2 = source_report.modules[0].blocks[2]
        source = addr(source_report, nested2.module.id)
        self.move(source, plan_indent(source_report, source))
        after = self.session.report_snapshot()
        self.assertEqual(after.modules[0].blocks[1].module.blocks[-1].id, nested2.id)
        self.assertEqual(after.modules[0].blocks[1].module.blocks[-1].module.id,
                         nested2.module.id)
        self.move(source, plan_outdent(after, source))
        self.assertEqual(self.session.report_snapshot(), source_report)

    def test_duplicate_deep_subtree_renews_all_object_ids_not_media(self):
        clone = self.run_command("duplicate_node", addr(self.before, self.a.id))
        duplicate_id = next(iter(clone.changed_ids))
        after = self.session.report_snapshot()
        self.assertEqual(after.modules[1].id, duplicate_id)
        self.assertEqual(after.modules[1].title, self.a.title)
        self.assertEqual(after.modules[1].blocks[1].module.blocks[0].text,
                         self.child.blocks[0].text)
        self.assertEqual(after.modules[1].blocks[2].asset_id,
                         self.a.blocks[2].asset_id)
        self.assertEqual(after.modules[1].blocks[2].visual,
                         self.a.blocks[2].visual)
        original_ids = all_identifiers(self.before)
        cloned_ids = all_identifiers(after) - original_ids
        self.assertEqual(len(cloned_ids), len(all_identifiers(after)) - len(original_ids))
        self.assertEqual(len(cloned_ids), 7)  # module, 4 blocks, nested module, child paragraph
        self.assertEqual(len(all_identifiers(after)), len(original_ids) + 7)
        self.assertEqual(self.session.assets["synthetic_photo"], b"synthetic-photo-bytes")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "duplicate.rmproj"
            ProjectPersistence().save(self.session, path)
            restored = load_project(path)
            self.assertEqual(restored.report, after)
            self.assertEqual(restored.assets["synthetic_photo"], b"synthetic-photo-bytes")
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), after)

    def test_duplicate_each_leaf_type_and_delete_undo_redo(self):
        # Include a page break and paragraph with translations in the same mixed list.
        self.session._editor.add_block(self.a.id, PageBreakBlock())
        with_break = self.session.report_snapshot()
        leafs = [b for b in with_break.modules[0].blocks if not isinstance(b, NestedModuleBlock)]
        for block in leafs:
            with self.subTest(kind=type(block).__name__):
                old = self.session.report_snapshot()
                owner = old.modules[0]
                original = next(b for b in owner.blocks if b.id == block.id)
                at = owner.blocks.index(original)
                result = self.run_command("duplicate_node", addr(old, self.a.id, block.id))
                new_id = next(iter(result.changed_ids))
                latest = self.session.report_snapshot()
                self.assertEqual(latest.modules[0].blocks[at + 1].id, new_id)
                clone = deepcopy(original)
                clone.id = new_id
                self.assertEqual(latest.modules[0].blocks[at + 1], clone)
                self.assertNotEqual(new_id, block.id)
                self.assertEqual(self.session.assets["synthetic_photo"], b"synthetic-photo-bytes")
                self.run_command("delete_node", addr(latest, self.a.id, new_id))
                self.assertEqual(self.session.report_snapshot(), old)
                self.gateway.undo(self.session.generation, self.session.revision)
                self.assertEqual(self.session.report_snapshot(), latest)
                self.gateway.redo(self.session.generation, self.session.revision)
                self.assertEqual(self.session.report_snapshot(), old)

    def test_delete_subtree_preserves_undo_and_conclusions(self):
        self.run_command("delete_node", addr(self.before, self.a.id))
        after = self.session.report_snapshot()
        self.assertEqual([m.id for m in after.modules], [self.b.id])
        self.assertEqual(after.conclusion, self.before.conclusion)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)
        self.gateway.redo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), after)

    def test_invalid_and_stale_actions_do_not_alter_history(self):
        valid = addr(self.before, self.a.id, self.a.blocks[2].id)
        self.run_command("duplicate_node", valid)
        changed = self.session.report_snapshot()
        revision = self.session.revision
        invalid = [
            addr(self.before, self.before.id),
            addr(self.before, self.before.conclusion.id),
            addr(self.before, self.b.id, self.a.blocks[2].id),
            addr(self.before, self.a.id, self.a.blocks[1].id),  # wrapper ID
            NodeAddress(self.before.id, self.a.id, self.a.blocks[0].id),
            NodeAddress(self.before.id, self.a.id, None, "text"),
            NodeAddress(self.before.id, self.a.id, row=0),
            NodeAddress("other_report", self.a.id),
        ]
        for kind in ("delete_node", "duplicate_node"):
            for address in invalid:
                with self.subTest(kind=kind, address=address):
                    with self.assertRaises((ValueError, LookupError)):
                        self.run_command(kind, address)
                    self.assertEqual(self.session.report_snapshot(), changed)
                    self.assertEqual(self.session.revision, revision)
        with self.assertRaises(ValueError):
            self.run_command("duplicate_node", addr(self.before, self.a.id), index=0)
        with self.assertRaises(StaleIntentError):
            self.gateway.execute(CommandIntent(
                "delete_node", addr(self.before, self.a.id), {}, 0, self.session.generation))
        self.session.set_draft_guard(lambda: False)
        with self.assertRaises(PendingDraftError):
            self.run_command("delete_node", addr(self.before, self.a.id))
        self.assertEqual(self.session.report_snapshot(), changed)
        self.session.set_draft_guard(lambda: True)
        self.gateway.undo(self.session.generation, self.session.revision)
        self.assertEqual(self.session.report_snapshot(), self.before)


from unittest import skipUnless


@skipUnless(os.getenv("QT_QPA_PLATFORM") == "offscreen", "offscreen Qt")
class StructuralActionQtTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        self.window = V2MainWindow(project=fixture())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._confirm_transition = lambda: False
        self.window.close()
        self.app.processEvents()

    def test_actions_context_buttons_and_nested_move(self):
        from PySide6.QtGui import QAction
        win = self.window
        original = win.session.report_snapshot()
        win.branch._selected_module_id = original.modules[1].id
        win.branch._refresh()
        self.assertTrue(win.findChild(QAction, "v2Indent").isEnabled())
        self.assertFalse(win.findChild(QAction, "v2Outdent").isEnabled())
        self.assertTrue(win.findChild(QAction, "v2Duplicate").isEnabled())
        self.assertTrue(win.findChild(QAction, "v2Delete").isEnabled())
        self.assertTrue(win.branch.indent_selected())
        self.app.processEvents()
        self.assertFalse(win.findChild(QAction, "v2Indent").isEnabled())
        self.assertTrue(win.findChild(QAction, "v2Outdent").isEnabled())
        self.assertTrue(win.branch.outdent_selected())
        self.assertEqual(win.session.report_snapshot(), original)
        self.assertTrue(win.branch.duplicate_selected())
        after = win.session.report_snapshot()
        self.assertEqual(len(after.modules), 3)
        self.assertTrue(win.branch.undo())
        self.assertEqual(win.session.report_snapshot(), original)
        self.assertGreaterEqual(len(win.branch.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QToolButton"]).QToolButton,
            "v2NodeActions")), 6)

    def test_delete_confirmation_and_pending_drafts(self):
        from PySide6.QtWidgets import QMessageBox
        win = self.window
        original = win.session.report_snapshot()
        win.branch._selected_module_id = original.modules[0].id
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.No):
            self.assertFalse(win.branch.delete_selected())
        self.assertEqual(win.session.report_snapshot(), original)
        a = addr(original, original.modules[0].id)
        win.branch.drafts.update(a, "Pending edit")
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question") as question:
            self.assertFalse(win.branch.delete_selected())
            question.assert_not_called()
        win.branch.drafts.discard(a)
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question",
                        return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(win.branch.delete_selected())
        self.assertEqual(len(win.session.report_snapshot().modules), 1)
        self.assertTrue(win.branch.undo())
        self.assertEqual(win.session.report_snapshot(), original)

    def test_confirmed_delete_rejects_modal_stale_generation(self):
        from PySide6.QtWidgets import QMessageBox
        win = self.window
        original = win.session.report_snapshot()
        win.branch._selected_module_id = original.modules[0].id
        next_project = fixture()
        next_report = deepcopy(next_project.report)
        def replaced(*unused, **kwargs):
            win.session.replace_project(next_project, discard_unsaved=True)
            return QMessageBox.StandardButton.Yes
        with mock.patch("reportmaker.v2.branch.canvas.QMessageBox.question",
                        side_effect=replaced):
            self.assertFalse(win.branch.delete_selected())
        self.assertEqual(win.session.report_snapshot(), next_report)
        self.assertEqual(win.session.revision, 0)

