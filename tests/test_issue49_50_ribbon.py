"""Issues #49/#50: font-entry focus and read-only formatting-state regressions.

Qt GUI tests run in Windows CI; all text and documents are synthetic.
"""
from __future__ import annotations

import unittest


class FontAndFormattingRibbonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 desktop not available")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        from reportmaker.rich_editor import SafeRichTextEdit, RichTextRibbon
        self.root = QWidget()
        layout = QVBoxLayout(self.root)
        self.editor = SafeRichTextEdit()
        self.ribbon = RichTextRibbon(self.editor)
        layout.addWidget(self.ribbon)
        layout.addWidget(self.editor)
        self.root.resize(1050, 430)
        self.root.show()
        self.app.processEvents()

    def tearDown(self):
        self.root.close()
        self.app.processEvents()

    def select(self, start, end):
        from PySide6.QtGui import QTextCursor
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()

    def button(self, name):
        from PySide6.QtWidgets import QPushButton
        return self.ribbon.findChild(QPushButton, name)

    def test_deleting_font_name_does_not_apply_partial_font_or_move_focus(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        self.editor.setPlainText("Synthetic valve report")
        self.select(0, 9)
        before = self.editor.toPlainText()
        before_fmt = self.editor.textCursor().charFormat()
        edit = self.ribbon.family.lineEdit()
        edit.setFocus()
        self.app.processEvents()
        edit.setText("Cambr")
        for _ in range(3):
            QTest.keyClick(edit, Qt.Key.Key_Backspace)
            self.app.processEvents()
            self.assertIs(QApplication.focusWidget(), edit)
            self.assertTrue(self.editor.textCursor().hasSelection())
            self.assertEqual(self.editor.toPlainText(), before)
        self.assertEqual(self.editor.textCursor().charFormat().fontFamilies(),
                         before_fmt.fontFamilies())
        edit.setText("UnknownFontDefinitelyNotInstalled")
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.editor.toPlainText(), before)
        self.assertTrue(self.editor.textCursor().hasSelection())
        self.assertNotEqual(self.ribbon.family.currentText(),
                            "UnknownFontDefinitelyNotInstalled")
        edit.setFocus()
        edit.setText("NotAnInstalledFont")
        QTest.keyClick(edit, Qt.Key.Key_Escape)
        self.assertNotEqual(edit.text(), "NotAnInstalledFont")
        self.assertTrue(self.editor.textCursor().hasSelection())

    def test_valid_enter_commit_keeps_selection_and_original_text(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtTest import QTest
        from reportmaker.rich_editor import capture_rich

        self.editor.setPlainText("Valve inspection")
        self.select(0, 5)
        valid = QFontDatabase.families()[0]
        edit = self.ribbon.family.lineEdit()
        edit.setFocus()
        edit.setText(valid)
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.editor.toPlainText(), "Valve inspection")
        self.assertEqual(self.editor.textCursor().selectedText(), "Valve")
        self.assertEqual(self.ribbon.family.currentText().casefold(), valid.casefold())
        text, rich = capture_rich(self.editor)
        self.assertEqual(text, "Valve inspection")
        if valid.casefold() != "cambria":
            self.assertTrue(any(run.family.casefold() == valid.casefold()
                                for run in rich.runs))

    def test_size_entry_and_tab_navigation_do_not_steal_focus(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        self.editor.setPlainText("Valve inspection")
        self.select(0, 5)
        edit = self.ribbon.size.lineEdit()
        edit.setFocus()
        edit.setText("13")
        QTest.keyClick(edit, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), edit)
        self.assertEqual(edit.text(), "1")
        self.assertEqual(self.editor.toPlainText(), "Valve inspection")
        edit.setText("15")
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.editor.textCursor().selectedText(), "Valve")
        self.assertEqual(self.editor.textCursor().charFormat().fontPointSize(), 15)

    def test_icons_and_checked_styles_follow_selection_and_mixed_runs(self):
        from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor

        self.editor.setPlainText("Bold plain")
        self.select(0, 4)
        bold = self.button("richBold")
        italic = self.button("richItalic")
        self.assertNotEqual(bold.text(), "Bold")
        for name in ("richBold", "richItalic", "richUnderline", "richStrike",
                     "richSubscript", "richSuperscript", "richAlignLeft",
                     "richAlignRight", "richBullets", "richNumbering"):
            button = self.button(name)
            self.assertTrue(button.isCheckable())
            self.assertTrue(button.accessibleName())
            self.assertTrue(button.toolTip())
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        cursor = self.editor.textCursor()
        cursor.mergeCharFormat(fmt)
        self.ribbon.sync()
        self.assertTrue(bold.isChecked())
        self.select(5, 10)
        self.assertFalse(bold.isChecked())
        self.select(0, 10)
        self.assertFalse(bold.isChecked())
        self.assertTrue(bold.property("richMixed"))
        self.assertIn("mixed", bold.toolTip())
        bold.click()  # mixed becomes uniformly bold
        self.assertTrue(bold.isChecked())
        self.assertFalse(bold.property("richMixed"))
        self.select(0, 4)
        italic.click()
        self.assertTrue(italic.isChecked())
        self.select(5, 10)
        self.assertFalse(italic.isChecked())
        self.assertEqual(self.editor.toPlainText(), "Bold plain")

    def test_paragraph_alignment_tracks_caret_and_selected_paragraphs(self):
        from PySide6.QtCore import Qt
        self.editor.setPlainText("First\nSecond")
        self.select(0, 0)
        self.button("richAlignRight").click()
        self.assertTrue(self.button("richAlignRight").isChecked())
        self.select(6, 6)
        self.assertTrue(self.button("richAlignLeft").isChecked())
        self.select(0, 12)
        self.assertTrue(self.button("richAlignLeft").property("richMixed"))
        self.assertTrue(self.button("richAlignRight").property("richMixed"))
        self.button("richAlignCenter").click()
        self.assertTrue(self.button("richAlignCenter").isChecked())
        self.assertEqual(self.editor.toPlainText(), "First\nSecond")


if __name__ == "__main__":
    unittest.main()
