"""Regression gates for #54/#56: safe module movement and expansion state.

Synthetic projects only. Qt UI tests exercise actual widgets offscreen on CI.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from reportmaker.engine import ProjectEditor, module_outline
from reportmaker.model import (
    LocalizedText, Module, NestedModuleBlock, ParagraphBlock, PhotoBlock,
    TableBlock,
)
from reportmaker.project_io import ReportProject, load_project, save_project


def txt(value):
    return LocalizedText("en", value)


def sample_project():
    from reportmaker.reference import manual_snapshot
    from reportmaker.model import Report
    from datetime import date

    d = Module(txt("D"), [TableBlock([[txt("Bearing"), txt("OK")]])])
    f = Module(txt("F"), [ParagraphBlock(txt("Deep note"))])
    a = Module(txt("A"), [
        ParagraphBlock(txt("Before nested")),
        NestedModuleBlock(d),
        ParagraphBlock(txt("After nested")),
    ])
    b = Module(txt("B"), [
        PhotoBlock("synthetic-photo", txt("Synthetic photo")),
        NestedModuleBlock(f),
    ])
    c = Module(txt("C"), [NestedModuleBlock(Module(txt("C.1")))])
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot("Synthetic client"),
        created_date=date(2026, 10, 28),
        start_date=date(2026, 10, 27), end_date=date(2026, 10, 28),
        primary_language="en", output_languages=["en"],
        modules=[a, b, c], conclusion=Module(txt("Conclusions")),
    )
    image = BytesIO()
    Image.new("RGB", (12, 10), (20, 70, 110)).save(image, format="PNG")
    return ReportProject(report, {"synthetic-photo": image.getvalue()})


def root_titles(report):
    return [module.title.original for module in report.modules]


class ModelMovementTests(unittest.TestCase):
    def test_moved_subtree_is_not_flattened_and_roundtrips(self):
        project = sample_project()
        editor = ProjectEditor(project.report)
        a, b, c = editor.report.modules
        original_b = deepcopy(b)
        editor.move_module(b.id, parent_id=a.id, index=1)
        nested = editor.report.modules[0].blocks[1].module
        self.assertEqual(nested, original_b)
        self.assertEqual([e.title for e in module_outline(editor.report)],
                         ["A", "B", "F", "D", "C", "C.1", "Conclusions"])
        with self.assertRaises(ValueError):
            editor.move_module(a.id, parent_id=b.id)  # cannot move under descendant
        self.assertEqual(editor.report.modules[0].blocks[1].module, original_b)
        editor.move_module(b.id, index=1)
        self.assertEqual(root_titles(editor.report), ["A", "B", "C"])
        self.assertEqual(editor.report.modules[1], original_b)
        self.assertEqual(editor.report.ordered_sections()[-1].title.original, "Conclusions")
        self.assertTrue(editor.undo())
        self.assertEqual(editor.report.modules[0].blocks[1].module, original_b)
        self.assertTrue(editor.redo())
        with TemporaryDirectory() as directory:
            file = Path(directory) / "modules.rmproj"
            save_project(ReportProject(editor.report, project.assets), file)
            loaded = load_project(file)
        self.assertEqual(root_titles(loaded.report), ["A", "B", "C"])
        self.assertEqual(loaded.report.modules[1], original_b)
        self.assertEqual(loaded.assets, project.assets)


class SyntheticDragEvent:
    def __init__(self, tree, point, modifiers):
        from PySide6.QtCore import QPointF
        self.tree, self.point, self.keys = tree, QPointF(point), modifiers
        self.accepted = False
        self.ignored = False

    def source(self):
        return self.tree

    def position(self):
        return self.point

    def modifiers(self):
        return self.keys

    def acceptProposedAction(self):
        self.accepted = True

    def setDropAction(self, action):
        self.drop_action = action

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class ModuleTreeQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 desktop dependencies absent")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
        from reportmaker.visual_editor import VisualReportEditor
        self.tmp = TemporaryDirectory()
        self.owner = QMainWindow()
        self.owner.settings = QSettings(
            str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        widget = QWidget()
        self.owner.setCentralWidget(widget)
        layout = QHBoxLayout(widget)
        left, center = QVBoxLayout(), QVBoxLayout()
        layout.addLayout(left)
        layout.addLayout(center)
        self.editor = VisualReportEditor(self.owner, left, center)
        self.editor._replace(sample_project(), None)
        self.owner.resize(1400, 920)
        self.owner.show()
        self.app.processEvents()

    def tearDown(self):
        self.owner.close()
        self.app.processEvents()
        self.tmp.cleanup()

    def select(self, title):
        from PySide6.QtCore import Qt
        item = next(item for item in self.items()
                    if item.text(0) == title)
        self.editor.tree.setCurrentItem(item)
        self.app.processEvents()
        return item

    def items(self):
        tree = self.editor.tree
        result = []
        stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            result.append(item)
            stack.extend(item.child(i) for i in range(item.childCount()))
        return result

    def drop(self, source, target, *, after=False, inside=False):
        from PySide6.QtCore import QPoint, Qt
        tree = self.editor.tree
        source_item = self.select(source)
        target_item = next(item for item in self.items()
                           if item.text(0) == target)
        rect = tree.visualItemRect(target_item)
        self.assertTrue(rect.isValid())
        point = QPoint(rect.center().x(), rect.center().y() if inside else
                       (rect.bottom() - 1 if after else rect.top() + 1))
        keys = (Qt.KeyboardModifier.ControlModifier if inside
                else Qt.KeyboardModifier.NoModifier)
        tree._drag_item = source_item
        try:
            event = SyntheticDragEvent(tree, point, keys)
            tree.dragMoveEvent(event)
            if event.accepted:
                tree.dropEvent(event)
            return event
        finally:
            tree._drag_item = None
            tree._clear_drop_visual()
            self.app.processEvents()

    def test_up_down_indent_unmerge_and_boundaries(self):
        from PySide6.QtWidgets import QPushButton
        controls = self.editor.module_move_buttons
        self.select("B")
        self.assertTrue(controls["moduleMoveUp"].isEnabled())
        self.assertTrue(self.editor.move_module_up())
        self.assertEqual(root_titles(self.editor.report), ["B", "A", "C"])
        self.assertFalse(controls["moduleMoveUp"].isEnabled())
        self.assertTrue(self.editor.move_module_down())
        self.assertEqual(root_titles(self.editor.report), ["A", "B", "C"])
        self.assertTrue(self.editor.move_module_in())
        self.assertEqual(root_titles(self.editor.report), ["A", "C"])
        a = self.editor.report.modules[0]
        b = [block.module for block in a.blocks
             if isinstance(block, NestedModuleBlock)][-1]
        self.assertEqual(b.title.original, "B")
        self.assertEqual(b.blocks[0].asset_id, "synthetic-photo")
        self.assertEqual(b.blocks[1].module.title.original, "F")
        self.assertTrue(controls["moduleMoveOut"].isEnabled())
        self.assertTrue(self.editor.move_module_out())
        self.assertEqual(root_titles(self.editor.report), ["A", "B", "C"])
        self.assertFalse(controls["moduleMoveOut"].isEnabled())
        self.select("Conclusions")
        self.assertTrue(all(not button.isEnabled() for button in controls.values()))
        for name in controls:
            btn = self.owner.findChild(QPushButton, name)
            self.assertIsNotNone(btn)
            self.assertTrue(btn.accessibleName())
            self.assertTrue(btn.toolTip())

    def test_nested_move_uses_mixed_block_indices(self):
        a = self.editor.report.modules[0]
        e = Module(txt("E"), [ParagraphBlock(txt("E note"))])
        self.assertTrue(self.editor._change(
            lambda: self.editor.editor.add_module(e, parent_id=a.id)))
        self.select("E")
        self.assertTrue(self.editor.move_module_up())
        blocks = self.editor.report.modules[0].blocks
        self.assertEqual([type(block).__name__ for block in blocks],
                         ["ParagraphBlock", "NestedModuleBlock", "NestedModuleBlock", "ParagraphBlock"])
        self.assertEqual([block.module.title.original for block in blocks
                          if isinstance(block, NestedModuleBlock)], ["E", "D"])
        self.assertTrue(self.editor.move_module_down())
        self.assertEqual([block.module.title.original for block in
                          self.editor.report.modules[0].blocks
                          if isinstance(block, NestedModuleBlock)], ["D", "E"])

    def test_drag_reorders_without_nesting_ctrl_explicitly_nests(self):
        self.assertTrue(self.drop("B", "A").accepted)
        self.assertEqual(root_titles(self.editor.report), ["B", "A", "C"])
        self.assertTrue(self.drop("B", "A", after=True).accepted)
        self.assertEqual(root_titles(self.editor.report), ["A", "B", "C"])
        # Dropping on the middle of a row is still reorder, not OnItem nesting.
        tree = self.editor.tree
        self.select("B")
        a = next(i for i in self.items() if i.text(0) == "A")
        from PySide6.QtCore import Qt
        center_plan = tree._drop_plan(
            tree.visualItemRect(a).center(), Qt.KeyboardModifier.NoModifier)
        self.assertIsNotNone(center_plan)
        self.assertIsNotNone(center_plan[2])
        self.assertTrue(self.drop("B", "A", inside=True).accepted)
        self.assertEqual(root_titles(self.editor.report), ["A", "C"])
        self.assertEqual([e.title for e in module_outline(self.editor.report)],
                         ["A", "D", "B", "F", "C", "C.1", "Conclusions"])
        # Cross-parent plain dragging must never silently unmerge.
        self.assertTrue(self.drop("B", "C").ignored)
        self.assertEqual(root_titles(self.editor.report), ["A", "C"])
        self.assertTrue(self.drop("A", "B", inside=True).ignored)  # cycle
        self.assertTrue(self.editor.move_module_out())
        self.assertEqual(root_titles(self.editor.report), ["A", "B", "C"])
        self.assertTrue(self.drop("B", "Conclusions").accepted)
        self.assertEqual(root_titles(self.editor.report), ["A", "C", "B"])
        self.assertEqual(self.editor.report.conclusion.title.original, "Conclusions")

    def test_collapse_retained_through_edits_and_selected_reveal(self):
        tree = self.editor.tree
        a = self.select("A")
        c = next(i for i in self.items() if i.text(0) == "C")
        a.setExpanded(False)
        c.setExpanded(False)
        a_id = self.editor.report.modules[0].id
        self.assertTrue(self.editor._change(
            lambda: self.editor.editor.add_block(
                a_id, ParagraphBlock(txt("New text")))))
        self.assertFalse(self.editor._item_for_id(a_id).isExpanded())
        c_id = self.editor.report.modules[2].id
        self.assertFalse(self.editor._item_for_id(c_id).isExpanded())
        self.assertTrue(self.editor._change(
            lambda: self.editor.editor.rename_module(a_id, "A renamed")))
        self.assertFalse(self.editor._item_for_id(a_id).isExpanded())
        self.editor.undo()
        self.editor.redo()
        self.assertFalse(self.editor._item_for_id(a_id).isExpanded())
        # Explicit selection of moved descendant expands only its own ancestors.
        self.editor._module_id = self.editor.report.modules[0].blocks[1].module.id
        self.editor.refresh(reveal_selected=True)
        self.assertTrue(self.editor._item_for_id(a_id).isExpanded())
        self.assertFalse(self.editor._item_for_id(c_id).isExpanded())
        # Saving does not reset expansion; Open starts with sensible defaults.
        self.editor._item_for_id(a_id).setExpanded(False)
        path = Path(self.tmp.name) / "state.rmproj"
        self.assertTrue(self.editor.save_to_path(path))
        self.assertFalse(self.editor._item_for_id(a_id).isExpanded())
        self.assertTrue(self.editor.open_from_path(path))
        self.assertTrue(self.editor._item_for_id(a_id).isExpanded())
        self.assertTrue(self.editor._item_for_id(c_id).isExpanded())


if __name__ == "__main__":
    unittest.main()
