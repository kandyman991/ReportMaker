"""M7.3 issue #99: native-theme contrast, without customer images or V1 changes."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from reportmaker.model import PhotoVisual
from reportmaker.v2.app import V2MainWindow, blank_report
from reportmaker.v2.branch.photo_tools import V2PictureEditorDialog


def synthetic_png() -> bytes:
    data = BytesIO()
    Image.new("RGB", (48, 28), (130, 160, 190)).save(data, "PNG")
    return data.getvalue()


def _contrast(a, b) -> float:
    def lum(c):
        rgb = (c.redF(), c.greenF(), c.blueF())
        val = [x / 12.92 if x <= 0.04045 else ((x + .055) / 1.055) ** 2.4
               for x in rgb]
        return .2126 * val[0] + .7152 * val[1] + .0722 * val[2]
    x, y = sorted((lum(a), lum(b)))
    return (y + .05) / (x + .05)


@unittest.skipUnless(__import__("os").environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "offline Qt, not physical Windows acceptance")
class V2ControlContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtGui import QPalette
        self.baseline_palette = QPalette(self.app.palette())
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def tearDown(self):
        self.app.setPalette(self.baseline_palette)
        self.app.processEvents()

    def _theme(self, dark):
        from PySide6.QtGui import QPalette, QColor
        pal = QPalette(self.baseline_palette)
        bg, fg = (("#181d26", "#ffffff") if dark else ("#f0f3f8", "#182d42"))
        for role, color in ((QPalette.ColorRole.Window, bg),
                            (QPalette.ColorRole.Base, bg),
                            (QPalette.ColorRole.Button, bg),
                            (QPalette.ColorRole.WindowText, fg),
                            (QPalette.ColorRole.Text, fg),
                            (QPalette.ColorRole.ButtonText, fg)):
            pal.setColor(role, QColor(color))
        self.app.setPalette(pal)

    def _assert_button_contrast(self, button, label):
        from PySide6.QtGui import QPalette
        button.ensurePolished()
        palette = button.palette()
        fg = palette.color(QPalette.ColorRole.ButtonText)
        bg = palette.color(QPalette.ColorRole.Button)
        self.assertGreaterEqual(_contrast(fg, bg), 4.5, (label, fg.name(), bg.name()))

    def _assert_field_contrast(self, widget, label):
        from PySide6.QtGui import QPalette
        widget.ensurePolished()
        palette = widget.palette()
        self.assertGreaterEqual(_contrast(
            palette.color(QPalette.ColorRole.Text), palette.color(QPalette.ColorRole.Base)),
            4.5, label)

    def test_all_10_annotation_glyphs_are_legible_and_selected_state_is_distinct(self):
        from PySide6.QtWidgets import QToolButton
        from reportmaker.photo_editor import TOOLS
        for dark in (False, True):
            with self.subTest(dark=dark):
                self._theme(dark)
                dlg = V2PictureEditorDialog(None, synthetic_png(), PhotoVisual(), "en")
                dlg.show()
                self.app.processEvents()
                try:
                    self.assertEqual(len(TOOLS), 10)
                    self.assertEqual(len(dlg.tool_buttons.buttons()), 10)
                    self.assertTrue(dlg.tool_choice.isHidden())
                    self.assertIn("QToolButton:checked", dlg.tool_buttons.button(0).styleSheet())
                    self.assertIn("color: #ffffff", dlg.tool_buttons.button(0).styleSheet())
                    self.assertIn("color: #1b3550", dlg.tool_buttons.button(0).styleSheet())
                    self.assertIn("QToolButton:hover", dlg.tool_buttons.button(0).styleSheet())
                    self.assertIn("QToolButton:disabled", dlg.tool_buttons.button(0).styleSheet())
                    self.assertIn("QToolButton:focus", dlg.tool_buttons.button(0).styleSheet())
                    for index, kind in enumerate(TOOLS):
                        btn = dlg.tool_buttons.button(index)
                        self.assertIsInstance(btn, QToolButton)
                        self.assertTrue(btn.isVisible())
                        self.assertGreaterEqual(btn.width(), 34)
                        self.assertTrue(btn.accessibleName())
                        self._assert_button_contrast(btn, kind)
                        btn.click()
                        self.assertTrue(btn.isChecked())
                        self.assertEqual(dlg.canvas.tool, kind)
                        self.assertEqual(sum(b.isChecked() for b in dlg.tool_buttons.buttons()), 1)
                finally:
                    dlg.close()
                    self.app.processEvents()

    def test_disabled_photo_tools_remain_distinguishable(self):
        from PySide6.QtGui import QPalette
        for dark in (False, True):
            with self.subTest(dark=dark):
                self._theme(dark)
                dlg = V2PictureEditorDialog(None, synthetic_png(), PhotoVisual(), "en")
                dlg.show()
                self.app.processEvents()
                try:
                    button = dlg.tool_buttons.button(2)
                    button.setEnabled(False)
                    self.app.processEvents()
                    palette = button.palette()
                    fg = palette.color(QPalette.ColorGroup.Disabled,
                                       QPalette.ColorRole.ButtonText)
                    bg = palette.color(QPalette.ColorGroup.Disabled,
                                       QPalette.ColorRole.Button)
                    self.assertGreaterEqual(_contrast(fg, bg), 4.5)
                finally:
                    dlg.close()
                    self.app.processEvents()

    def test_dialog_action_buttons_fields_and_two_rows_readable_in_both_themes(self):
        from PySide6.QtWidgets import QPushButton, QSpinBox, QComboBox, QLabel, QDialogButtonBox
        for dark in (False, True):
            with self.subTest(dark=dark):
                self._theme(dark)
                dlg = V2PictureEditorDialog(None, synthetic_png(), PhotoVisual(), "en")
                dlg.show()
                self.app.processEvents()
                try:
                    # Tools and actions are on separate rows, not one clipped toolbar.
                    self.assertEqual(dlg.layout().itemAt(0).layout().count(), 11)
                    action_row = dlg.layout().itemAt(1).layout()
                    self.assertGreaterEqual(action_row.count(), 7)
                    self.assertEqual(dlg.layout().itemAt(3).layout().count(), 4)
                    self.assertEqual(dlg.layout().itemAt(4).layout().count(), 4)
                    # All three shorter rows must fit the native 950px dialog
                    # even when Windows fonts are wider than Linux fonts.
                    self.assertLessEqual(dlg.geometry().width(), 950)
                    buttons = dlg.findChildren(QPushButton)
                    self.assertTrue(any(b.text() == "Color" for b in buttons))
                    self.assertTrue(any(b.text() == "Rotate 90°" for b in buttons))
                    self.assertTrue(any(b.text() == "Delete mark" for b in buttons))
                    self.assertIsNotNone(dlg.findChild(QDialogButtonBox))
                    for b in buttons:
                        self._assert_button_contrast(b, b.text())
                    for typ in (QSpinBox, QComboBox):
                        for field in dlg.findChildren(typ):
                            if field is dlg.tool_choice:
                                continue
                            self._assert_field_contrast(field, typ.__name__)
                    for label in dlg.findChildren(QLabel):
                        label.ensurePolished()
                        from PySide6.QtGui import QPalette
                        self.assertGreaterEqual(
                            _contrast(label.palette().color(QPalette.ColorRole.WindowText),
                                      label.palette().color(QPalette.ColorRole.Window)),
                            4.5, label.text())
                finally:
                    dlg.close()
                    self.app.processEvents()

    def test_branch_photo_actions_caption_gallery_and_editor_controls_readable(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QPushButton, QPlainTextEdit
        for dark in (False, True):
            with self.subTest(dark=dark):
                self._theme(dark)
                win = V2MainWindow(blank_report("Synthetic contrast tester"),
                                   load_website=False)
                win.show()
                self.app.processEvents()
                try:
                    photo = Path(self.folder.name) / "test-photo.png"
                    photo.write_bytes(synthetic_png())
                    self.assertTrue(win.branch.import_photo_paths([str(photo)]))
                    self.app.processEvents()
                    for name in ("v2PhotoEdit", "v2PhotoReplace", "v2PhotoReplaceFile"):
                        button = win.branch.findChild(QPushButton, name)
                        self.assertIsNotNone(button, name)
                        self._assert_button_contrast(button, name)
                    caption = win.branch.findChild(QPlainTextEdit, "v2PhotoCaption")
                    self.assertIsNotNone(caption)
                    self._assert_field_contrast(caption, "Photo caption")
                    color = caption.palette().color(QPalette.ColorRole.PlaceholderText)
                    background = caption.palette().color(QPalette.ColorRole.Base)
                    self.assertGreaterEqual(_contrast(color, background), 4.5)
                    for name in ("v2GalleryImport", "v2GalleryPaste", "v2GalleryInsert",
                                 "v2EditorApply", "v2EditorRevert"):
                        button = win.findChild(QPushButton, name)
                        self.assertIsNotNone(button, name)
                        self._assert_button_contrast(button, name)
                finally:
                    win._confirm_transition = lambda: False
                    win.close()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
