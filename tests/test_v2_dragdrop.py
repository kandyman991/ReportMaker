"""M2.2 native Qt Branch Editor drop feedback and transactional drag regressions.

All fixtures use fabricated report data. No real Windows Explorer, private media,
embedded browser, or external file MIME is used by these internal-only moves.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.project_io import load_project
from reportmaker.v2.adapters.persistence import ProjectPersistence
from reportmaker.v2.projections import NodeAddress
from reportmaker.v2.session import PendingDraftError

from test_v2_structure import fixture


@unittest.skipUnless(os.getenv("QT_QPA_PLATFORM") == "offscreen",
                     "Requires real PySide6 offscreen interaction")
class DragDropQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        self.window = V2MainWindow(project=fixture())
        self.window.show()
        self.app.processEvents()
        self.canvas = self.window.branch
        self.original = self.window.session.report_snapshot()
        self.a, self.b = self.original.modules
        self.child = self.a.blocks[1].module
        self.photo = self.a.blocks[2]

    def tearDown(self):
        self.canvas._drag_context = None
        self.canvas._clear_drop_preview()
        self.window._confirm_transition = lambda: False
        self.window.close()
        self.app.processEvents()

    def addr(self, node_id, parent=None):
        return NodeAddress(self.original.id, parent or node_id,
                           node_id if parent else None,
                           "text" if parent else "title")

    def row(self, node_id):
        from reportmaker.v2.branch.canvas import DropRow
        rows = [r for r in self.canvas.findChildren(DropRow)
                if r.property("nodeId") == node_id]
        self.assertEqual(len(rows), 1, "Every visible node must have exactly one drop target")
        return rows[0]

    def native_event(self, row, mime, position, kind):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
        y = (2 if position == "before" else
             row.height() - 2 if position == "after" else row.height() // 2)
        if kind == "enter":
            event = QDragEnterEvent(
                QPoint(8, y), Qt.DropAction.MoveAction, mime,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(row, event)
        elif kind == "move":
            event = QDragMoveEvent(
                QPoint(8, y), Qt.DropAction.MoveAction, mime,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(row, event)
        else:
            event = QDropEvent(
                QPointF(8, y), Qt.DropAction.MoveAction, mime,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(row, event)
        return event

    def start(self, address):
        mime = self.canvas._arm_drag(address)
        self.assertIsNotNone(mime)
        return mime

    def drop(self, source, target_id, position):
        mime = self.start(source)
        target = self.row(target_id)
        preview = self.native_event(target, mime, position, "enter")
        self.assertTrue(preview.isAccepted(), f"Expected {position} target to be accepted")
        self.assertEqual(target._position, position)
        self.assertTrue(target._valid)
        self.assertFalse(target.marker.isHidden())
        self.assertIn(position.upper(), target.marker.text())
        result = self.native_event(target, mime, position, "drop")
        self.assertTrue(result.isAccepted())
        self.canvas._drag_context = None
        self.app.processEvents()
        return result

    def test_drag_handles_are_separate_from_inline_editors_and_positions_visible(self):
        from reportmaker.v2.branch.canvas import DragHandle
        handles = self.canvas.findChildren(DragHandle)
        self.assertEqual(len(handles), len(self.canvas.visible_nodes) - 2)
        self.assertTrue(all(h.accessibleName() == "Drag branch node" for h in handles))
        self.assertTrue(self.canvas.editor_for(self.addr(self.a.id)) is not None)
        self.assertTrue(self.canvas.editor_for(self.addr(self.child.id)) is not None)
        self.assertEqual(self.row(self.a.id).position_at(1), "before")
        self.assertEqual(self.row(self.a.id).position_at(self.row(self.a.id).height() // 2), "inside")
        self.assertEqual(self.row(self.a.id).position_at(self.row(self.a.id).height() - 1), "after")
        self.assertEqual(self.row(self.photo.id).position_at(self.row(self.photo.id).height() // 2),
                         "after")  # leaf content never exposes an implicit Inside target
        self.assertEqual(self.row(self.original.id).position_at(1), "inside")

    def test_native_drop_reorders_roots_and_one_undo_reverts(self):
        self.drop(self.addr(self.a.id), self.b.id, "after")
        moved = self.window.session.report_snapshot()
        self.assertEqual([m.id for m in moved.modules], [self.b.id, self.a.id])
        self.assertEqual(moved.modules[1].blocks, self.a.blocks)
        self.assertEqual(moved.conclusion.id, self.original.conclusion.id)
        self.assertEqual(self.window.session.revision, 1)
        self.assertTrue(self.canvas.undo())
        self.assertEqual(self.window.session.report_snapshot(), self.original)
        self.assertEqual(self.window.session.revision, 2)

    def test_native_photo_drop_inside_cross_parent_preserves_bytes_and_save(self):
        self.drop(self.addr(self.photo.id, self.a.id), self.b.id, "inside")
        moved = self.window.session.report_snapshot()
        self.assertEqual(moved.modules[1].blocks[-1], self.photo)
        self.assertEqual(self.window.session.assets["synthetic_photo"], b"synthetic-photo-bytes")
        self.assertEqual(moved.modules[0].blocks[1].module.blocks[0].text.translations["de"],
                         "Drehmoment geprüft")
        with TemporaryDirectory() as root:
            path = Path(root) / "moved.rmproj"
            ProjectPersistence().save(self.window.session, path)
            stored = load_project(path)
            self.assertEqual(stored.report, moved)
            self.assertEqual(stored.assets["synthetic_photo"], b"synthetic-photo-bytes")

    def test_nested_move_before_leaf_preserves_wrapper_identity(self):
        wrapper_id = self.a.blocks[1].id
        self.drop(self.addr(self.child.id), self.photo.id, "after")
        blocks = self.window.session.report_snapshot().modules[0].blocks
        self.assertEqual([b.id for b in blocks],
                         [self.a.blocks[0].id, self.photo.id, wrapper_id, self.a.blocks[3].id])

    def test_cycle_and_conclusions_invalid_preview_is_nonmutating(self):
        mime = self.start(self.addr(self.a.id))
        target = self.row(self.child.id)
        preview = self.native_event(target, mime, "inside", "enter")
        self.assertFalse(preview.isAccepted())
        self.assertEqual(target.marker.text(), "INVALID INSIDE")
        self.assertIn("subtree", target.marker.toolTip())
        blocked = self.native_event(target, mime, "inside", "drop")
        self.assertFalse(blocked.isAccepted())
        self.assertEqual(self.window.session.report_snapshot(), self.original)
        self.assertEqual(self.window.session.revision, 0)
        self.assertFalse(self.window.session._editor.can_undo)

        mime = self.start(self.addr(self.photo.id, self.a.id))
        conclusion = self.row(self.original.conclusion.id)
        preview = self.native_event(conclusion, mime, "inside", "enter")
        self.assertFalse(preview.isAccepted())
        self.assertIn("INVALID", conclusion.marker.text())
        self.assertEqual(self.window.session.report_snapshot(), self.original)

    def test_before_conclusions_and_inside_root_are_explicit(self):
        self.drop(self.addr(self.a.id), self.original.conclusion.id, "before")
        self.assertEqual([m.id for m in self.window.session.report_snapshot().modules],
                         [self.b.id, self.a.id])
        self.assertEqual(self.window.session.report_snapshot().ordered_sections()[-1].id,
                         self.original.conclusion.id)
        self.assertTrue(self.canvas.undo())
        self.canvas._drag_context = None
        self.app.processEvents()
        self.drop(self.addr(self.a.id), self.original.id, "inside")
        self.assertEqual([m.id for m in self.window.session.report_snapshot().modules],
                         [self.b.id, self.a.id])

    def test_foreign_mime_and_token_forgery_rejected(self):
        from PySide6.QtCore import QMimeData
        from reportmaker.v2.branch.canvas import _INTERNAL_MOVE_MIME
        good = self.start(self.addr(self.a.id))
        target = self.row(self.b.id)
        foreign = QMimeData()
        foreign.setUrls([])  # no external files or HTML can mutate the report
        ev = self.native_event(target, foreign, "before", "enter")
        self.assertFalse(ev.isAccepted())
        forged = QMimeData()
        forged.setData(_INTERNAL_MOVE_MIME, b"not-the-live-in-process-token")
        ev = self.native_event(target, forged, "before", "enter")
        self.assertFalse(ev.isAccepted())
        self.assertEqual(self.window.session.report_snapshot(), self.original)
        self.assertTrue(good.hasFormat(_INTERNAL_MOVE_MIME))

    def test_noop_and_stale_drag_preserve_history(self):
        # B is already after A; a redundant drop must not clear redo/history.
        self.canvas._selected_module_id = self.b.id
        self.assertTrue(self.canvas.move_selected_up())
        self.assertTrue(self.canvas.undo())
        redo_exists = self.window.session._editor.can_redo
        revision = self.window.session.revision
        mime = self.start(self.addr(self.b.id))
        target = self.row(self.a.id)
        ev = self.native_event(target, mime, "after", "enter")
        self.assertFalse(ev.isAccepted())
        self.assertIn("Already", target.marker.toolTip())
        self.assertEqual(self.window.session.revision, revision)
        self.assertEqual(self.window.session._editor.can_redo, redo_exists)

        # A distinct accepted drag becomes stale when an unrelated command changes revision.
        mime = self.start(self.addr(self.a.id))
        self.assertTrue(self.canvas.add_module())
        self.app.processEvents()
        target = self.row(self.b.id)
        ev = self.native_event(target, mime, "after", "enter")
        self.assertFalse(ev.isAccepted())
        self.assertIn("changed", target.marker.toolTip())

    def test_pending_draft_rejects_drag_and_preserves_text(self):
        addr = self.addr(self.a.id)
        editor = self.canvas.editor_for(addr)
        self.canvas.drafts.update(addr, "Unapplied title")
        editor.setText("Unapplied title")
        self.assertTrue(self.canvas.drafts.pending)
        self.assertIsNone(self.canvas._arm_drag(self.addr(self.b.id)))
        self.assertEqual(self.window.session.report_snapshot(), self.original)
        self.assertEqual(editor.text(), "Unapplied title")
        self.assertEqual(self.window.session.revision, 0)
        self.canvas.revert_draft(addr)
        self.assertFalse(self.canvas.drafts.pending)


if __name__ == "__main__":
    unittest.main()
