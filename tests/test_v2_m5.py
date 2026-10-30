"""M5 navigation and bounded native Qt view, using only synthetic reports."""
from __future__ import annotations

from copy import deepcopy
import os
import unittest

from reportmaker.model import LocalizedText, Module, NestedModuleBlock, ParagraphBlock
from reportmaker.v2.navigation import search_report, subtree_range, window_for
from reportmaker.v2.projections import project_branch
from test_v2_structure import fixture


class NavigationCoreTests(unittest.TestCase):
    def setUp(self):
        self.project = fixture()
        self.report = self.project.report
        self.parent = self.report.modules[0]
        self.child = self.parent.blocks[1].module
        self.photo = self.parent.blocks[2]

    def test_searches_canonical_titles_text_photo_captions_and_hidden_children(self):
        self.assertEqual([hit.stable_id for hit in search_report(self.report, "CHILD")],
                         [self.child.id])
        self.assertEqual([hit.stable_id for hit in search_report(self.report, "torque")],
                         [self.child.blocks[0].id])
        self.assertEqual([hit.stable_id for hit in search_report(self.report, "fabricated photo")],
                         [self.photo.id])
        self.assertEqual(search_report(self.report, "unmatched"), ())
        self.assertEqual(search_report(self.report, "    "), ())
        self.assertEqual(search_report(self.report, "a", limit=1).__len__(), 1)

    def test_subtree_and_window_keep_full_document_unchanged(self):
        before = deepcopy(self.report)
        all_rows = project_branch(self.report)
        start, end = subtree_range(all_rows, self.parent.id)
        ids = [row.stable_id for row in all_rows[start:end]]
        self.assertIn(self.photo.id, ids)
        self.assertIn(self.child.id, ids)
        self.assertNotIn(self.report.conclusion.id, ids)
        first, count = window_for(all_rows, 0, size=3)
        self.assertEqual(len(first), 3)
        self.assertGreater(count, 1)
        last, _ = window_for(all_rows, 1000, size=3)
        self.assertTrue(last)
        self.assertEqual(self.report, before)

    def test_deep_iterative_search_and_focusing_are_safe(self):
        cursor = self.report.modules[0]
        for depth in range(28):
            nested = Module(LocalizedText("en", f"Nested {depth}"))
            cursor.blocks.append(NestedModuleBlock(nested))
            cursor = nested
        cursor.blocks.append(ParagraphBlock(LocalizedText("en", "Deep needle 🧭")))
        rows = project_branch(self.report)
        hits = search_report(self.report, "deep needle")
        self.assertEqual(hits[0].stable_id, cursor.blocks[-1].id)
        start, end = subtree_range(rows, cursor.id)
        self.assertEqual([r.stable_id for r in rows[start:end]],
                         [cursor.id, cursor.blocks[-1].id])


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class NavigationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        self.project = fixture()
        self.original = deepcopy(self.project.report)
        self.win = V2MainWindow(project=self.project)
        self.win.show()
        self.pump()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.pump()

    def pump(self):
        for _ in range(4):
            self.app.processEvents()

    def test_focus_nested_under_collapsed_parent_restores_previous_context(self):
        canvas = self.win.branch
        parent = self.original.modules[0]
        child = parent.blocks[1].module
        self.assertTrue(canvas.toggle_branch(parent.id))
        old_collapsed = canvas.collapsed_module_ids
        old_selected = canvas._selected_module_id
        self.assertTrue(canvas.focus_module(child.id))
        self.assertEqual(canvas.focus_module_id, child.id)
        self.assertEqual(canvas.visible_nodes[0][0], child.id)
        self.assertIn(child.blocks[0].id, [r[0] for r in canvas.visible_nodes])
        self.assertNotIn(self.original.conclusion.id, [r[0] for r in canvas.visible_nodes])
        self.assertTrue(canvas.exit_focus())
        self.assertEqual(canvas.focus_module_id, None)
        self.assertEqual(canvas.collapsed_module_ids, old_collapsed)
        self.assertEqual(canvas._selected_module_id, old_selected)
        self.assertEqual(self.win.session.report_snapshot(), self.original)

    def test_search_reveals_collapsed_photo_without_mutating_project(self):
        canvas = self.win.branch
        parent = self.original.modules[0]
        photo = parent.blocks[2]
        self.assertTrue(canvas.toggle_branch(parent.id))
        self.assertNotIn(photo.id, [r[0] for r in canvas.visible_nodes])
        matches = canvas.search("Fabricated photo")
        self.assertEqual(matches[0].stable_id, photo.id)
        self.pump()
        self.assertNotIn(parent.id, canvas.collapsed_module_ids)
        self.assertIn(photo.id, [r[0] for r in canvas.visible_nodes])
        self.assertEqual(canvas._selected_module_id, parent.id)
        self.assertEqual(self.win.session.report_snapshot(), self.original)

    def test_large_report_keeps_live_rows_bounded_and_search_reaches_last(self):
        from reportmaker.v2.app import V2MainWindow
        from reportmaker.v2.branch.canvas import DropRow
        project = fixture()
        module = project.report.modules[0]
        # Bulk synthetic generation only; never iterate a thousand UI commands.
        for i in range(300):
            module.blocks.append(ParagraphBlock(LocalizedText(
                "en", f"Test paragraph {i}" + (" unique-final-marker" if i == 299 else ""))))
        other = V2MainWindow(project=project)
        other.show()
        self.pump()
        try:
            canvas = other.branch
            self.assertGreater(canvas.page_count, 2)
            self.assertLessEqual(canvas.active_row_count, 120)
            self.assertLessEqual(len(canvas._host.findChildren(DropRow)), 120)
            self.assertEqual(canvas.verticalScrollBarPolicy(),
                             __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertTrue(canvas.change_page(1))
            self.pump()
            self.assertLessEqual(len(canvas._host.findChildren(DropRow)), 120)
            self.assertTrue(canvas.search("unique-final-marker"))
            self.pump()
            self.assertEqual(canvas._search_index, 0)
            self.assertIn("unique-final-marker", canvas._search_hits[0].excerpt)
            self.assertLessEqual(canvas.active_row_count, 120)
            self.assertLessEqual(len(canvas._host.findChildren(DropRow)), 120)
            last = module.blocks[-1]
            from reportmaker.v2.projections import NodeAddress
            editor = canvas.editor_for(NodeAddress(project.report.id, module.id, last.id, "text"))
            self.assertIsNotNone(editor)
            editor.setPlainText("Pending scalability test draft")
            self.pump()
            page = canvas._page
            self.assertFalse(canvas.change_page(-1))
            self.assertEqual(canvas._page, page)
            self.assertEqual(editor.toPlainText(), "Pending scalability test draft")
            self.assertEqual(other.session.report_snapshot(), project.report)
        finally:
            other._confirm_transition = lambda: False
            other.close()
            self.pump()

    def test_return_to_root_window_keeps_a_visible_module_selected(self):
        from reportmaker.v2.app import V2MainWindow
        project = fixture()
        module = project.report.modules[0]
        for i in range(160):
            module.blocks.append(ParagraphBlock(LocalizedText("en", f"Boundary paragraph {i}")))
        other = V2MainWindow(project=project)
        other.show()
        self.pump()
        try:
            canvas = other.branch
            self.assertGreater(canvas.page_count, 1)
            self.assertTrue(canvas.reveal_node(project.report.conclusion.id))
            self.assertGreater(canvas._page, 0)
            while canvas._page:
                self.assertTrue(canvas.change_page(-1))
            self.pump()
            self.assertEqual(canvas._page, 0)
            self.assertIn(module.id, [row[0] for row in canvas.visible_nodes])
            self.assertEqual(canvas._selected_module_id, module.id)
        finally:
            other._confirm_transition = lambda: False
            other.close()
            self.pump()

    def test_focus_restores_horizontal_pan_for_deep_workspace(self):
        from reportmaker.v2.app import V2MainWindow
        project = fixture()
        module = project.report.modules[0]
        cursor = module
        # Deep enough to overflow even after the canvas has used every fitting stage
        # (narrower indentation, margins, card padding, glyph-only drag handle).
        for i in range(64):
            nested = Module(LocalizedText("en", f"Deep level {i}"))
            cursor.blocks.append(NestedModuleBlock(nested))
            cursor = nested
        other = V2MainWindow(project=project)
        other.resize(660, 460)  # Force a real horizontal overflow at safe nesting depth.
        other.show()
        self.pump()
        try:
            canvas = other.branch
            horizontal = canvas.horizontalScrollBar()
            self.assertGreater(horizontal.maximum(), 0)
            saved = min(48, horizontal.maximum())
            horizontal.setValue(saved)
            self.assertTrue(canvas.focus_module(module.id))
            horizontal.setValue(0)
            self.assertTrue(canvas.exit_focus())
            self.pump()
            self.assertEqual(horizontal.value(), saved)
            self.assertEqual(other.session.report_snapshot(), project.report)
        finally:
            other._confirm_transition = lambda: False
            other.close()
            self.pump()

    def test_zoom_and_fit_are_presentation_only_and_preserve_no_scrollbar(self):
        from PySide6.QtCore import Qt
        canvas = self.win.branch
        from reportmaker.v2.projections import NodeAddress
        parent = self.original.modules[0]
        child = parent.blocks[1].module
        paragraph = child.blocks[0]
        addr = NodeAddress(self.original.id, child.id, paragraph.id, "text")
        self.assertIn("font-size: 14px", canvas.editor_for(addr).styleSheet())
        self.assertTrue(canvas.set_zoom(130))
        self.assertEqual(canvas.zoom_percent, 130)
        self.assertIn("font-size: 18px", canvas.editor_for(addr).styleSheet())
        from PySide6.QtGui import QImage
        from reportmaker.v2.branch.canvas import ConnectorGutter, PhotoThumbnail
        image = QImage(400, 200, QImage.Format.Format_RGB32)
        original = PhotoThumbnail(image, 100, "center", zoom_pct=100)
        enlarged = PhotoThumbnail(image, 100, "center", zoom_pct=130)
        self.assertGreater(enlarged.heightForWidth(800), original.heightForWidth(800))
        base_connector = ConnectorGutter(4, (), False, zoom_pct=100)
        zoom_connector = ConnectorGutter(4, (), False, zoom_pct=130)
        self.assertGreater(zoom_connector.width(), base_connector.width())
        self.assertTrue(canvas.fit_to_screen())
        self.assertTrue(55 <= canvas.zoom_percent <= 160)
        self.assertEqual(canvas.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(canvas.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(self.win.session.report_snapshot(), self.original)

    def test_pending_caption_draft_blocks_focus_and_zoom_without_losing_text(self):
        from reportmaker.v2.projections import NodeAddress
        canvas = self.win.branch
        parent = self.original.modules[0]
        photo = parent.blocks[2]
        address = NodeAddress(self.original.id, parent.id, photo.id, "caption")
        editor = canvas.editor_for(address)
        editor.setPlainText("Unapplied M5 draft")
        self.pump()
        self.assertTrue(canvas.drafts.pending)
        self.assertFalse(canvas.focus_module(parent.id))
        self.assertFalse(canvas.set_zoom(130))
        # A visible TOC selection that does not rebuild an editor stays safe.
        self.assertTrue(canvas.reveal_node(self.original.conclusion.id))
        self.assertIs(canvas.editor_for(address), editor)
        self.assertEqual(canvas.editor_for(address).toPlainText(), "Unapplied M5 draft")
        self.assertEqual(self.win.session.report_snapshot(), self.original)


if __name__ == "__main__":
    unittest.main()
