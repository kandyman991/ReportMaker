"""Issue #38: real Qt ribbon visibility and page-to-ribbon focus regressions.

Synthetic GUI fixtures only; installed Windows/DPI acceptance remains separate.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from reportmaker.model import HeadingBlock, LocalizedText, PhotoBlock
from reportmaker.project_io import load_project
from reportmaker.reference import manual_snapshot
from reportmaker.visual_editor import VisualReportEditor


class RibbonVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 desktop not available")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
        self.working = TemporaryDirectory()
        self.owner = QMainWindow()
        self.owner.settings = QSettings(
            str(Path(self.working.name) / "local.ini"), QSettings.Format.IniFormat)
        root = QWidget()
        self.owner.setCentralWidget(root)
        row = QHBoxLayout(root)
        left = QVBoxLayout()
        center = QVBoxLayout()
        row.addLayout(left, 1)
        row.addLayout(center, 2)
        self.controller = VisualReportEditor(self.owner, left, center)
        self.owner.resize(1100, 840)
        self.owner.show()
        self.app.processEvents()

    def tearDown(self):
        self.owner.close()
        self.app.processEvents()
        self.working.cleanup()

    def assert_ribbon_onscreen(self):
        from PySide6.QtWidgets import QPushButton
        ribbon = self.controller.rich_ribbon
        scroll = ribbon.scroller
        self.app.processEvents()
        self.assertTrue(ribbon.isVisibleTo(self.owner))
        self.assertFalse(ribbon.isHidden())
        self.assertGreater(ribbon.height(), 55)
        self.assertGreater(scroll.viewport().height(), 45)
        for control in (ribbon.family, ribbon.size,
                        ribbon.findChild(QPushButton, "richBold")):
            self.assertTrue(control.isVisibleTo(self.owner), control.objectName())
            self.assertGreater(control.visibleRegion().boundingRect().height(), 0,
                               control.objectName())

    def test_ribbon_remains_visible_when_editor_splitter_is_collapsed_and_resized(self):
        self.assert_ribbon_onscreen()
        for width, height in ((1100, 840), (900, 660), (1160, 900)):
            with self.subTest(width=width, height=height):
                self.owner.resize(width, height)
                self.controller.content_splitter.setSizes([0, 900])
                self.assert_ribbon_onscreen()

    def test_heading_photo_and_paragraph_restore_ribbon(self):
        report = self.controller.report
        module = report.modules[0]
        buf = BytesIO()
        Image.new("RGB", (16, 12), (0, 100, 140)).save(buf, "PNG")
        self.controller.assets["synthetic"] = buf.getvalue()
        self.controller.editor.apply(lambda candidate: candidate.modules[0].blocks.extend([
            HeadingBlock(LocalizedText("en", "Synthetic heading")),
            PhotoBlock("synthetic", LocalizedText("en", "Synthetic caption")),
        ]))
        self.controller.refresh()
        self.assert_ribbon_onscreen()
        self.controller.blocks.setCurrentRow(1)
        self.assert_ribbon_onscreen()
        self.controller.blocks.setCurrentRow(2)
        self.app.processEvents()
        self.assertFalse(self.controller.rich_ribbon.isVisibleTo(self.owner))
        self.controller.blocks.setCurrentRow(0)
        self.assert_ribbon_onscreen()

    def test_page_style_preserves_emoji_selection_and_canonical_formatting(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import QPushButton
        controller = self.controller
        controller.editor.apply(lambda report: setattr(
            report, "customer_snapshot", manual_snapshot("Synthetic customer")))
        controller.refresh()
        module = controller.report.modules[0]
        block_id = module.blocks[0].id
        field = controller.page.fields[(module.id, block_id, "text")]
        field.setPlainText("Valve 😀 test")
        cursor = field.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(8, QTextCursor.MoveMode.KeepAnchor)
        field.setTextCursor(cursor)
        style = controller.page.findChild(QPushButton, "pageStyle_" + block_id)
        style.click()
        self.assert_ribbon_onscreen()
        self.assertEqual(controller._edit_block_id, block_id)
        self.assertEqual(controller.text_edit.textCursor().selectedText(), "😀")
        controller.rich_ribbon.findChild(QPushButton, "richBold").click()
        self.assertTrue(controller.apply_block())
        block = controller.report.modules[0].blocks[0]
        self.assertEqual(block.text.original, "Valve 😀 test")
        self.assertTrue(any(run.bold and run.start == 6 and run.end == 7
                            for run in block.rich.runs))
        controller.undo()
        self.assertFalse(controller.report.modules[0].blocks[0].rich.runs)
        controller.redo()
        self.assertTrue(any(run.bold for run in
                            controller.report.modules[0].blocks[0].rich.runs))
        target = Path(self.working.name) / "style.rmproj"
        self.assertTrue(controller.save_to_path(target))
        loaded = load_project(target)
        self.assertEqual(loaded.report.modules[0].blocks[0].text.original,
                         "Valve 😀 test")
        self.assertTrue(any(run.bold for run in loaded.report.modules[0].blocks[0].rich.runs))

    def test_horizontal_navigation_reaches_hidden_tools(self):
        from PySide6.QtWidgets import QToolButton
        ribbon = self.controller.rich_ribbon
        self.controller.tabs.resize(430, self.controller.tabs.height())
        self.app.processEvents()
        bar = ribbon.scroller.horizontalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        ribbon.findChild(QToolButton, "richRibbonScrollRight").click()
        self.assertGreater(bar.value(), 0)
        after = bar.value()
        ribbon.findChild(QToolButton, "richRibbonScrollLeft").click()
        self.assertLess(bar.value(), after)


if __name__ == "__main__":
    unittest.main()
