"""Linux audit regression: every V2 toolbar command remains discoverable.

These are Qt widget tests, not a substitute for physical Windows acceptance.
"""
from __future__ import annotations

import os
import unittest

from reportmaker.v2.app import V2MainWindow, blank_report


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offscreen Qt")
class ResponsiveCommandToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = V2MainWindow(blank_report("SYNTHETIC TOOLBAR QA"), load_website=False)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._confirm_transition = lambda: True
        self.window.close()
        self.app.processEvents()

    def test_every_command_available_without_toolbar_overflow_at_minimum_width(self):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QToolBar, QToolButton, QMenu
        win = self.window
        bars = [win.findChild(QToolBar, name) for name in (
            "v2BranchActions", "v2BranchEditing", "v2BranchNavigation")]
        self.assertTrue(all(bars))
        menu_buttons = [b for name in (
            "v2ProjectMenu", "v2LanguagesMenu", "v2InsertMenu",
            "v2ArrangeMenu", "v2NavigateMenu", "v2ViewMenu")
            if (b := win.findChild(QToolButton, name)) is not None]
        self.assertEqual(len(menu_buttons), 6)

        all_names = {a.objectName() for a in win.findChildren(QAction)
                     if a.objectName().startswith("v2")}
        accessible = set()
        for bar in bars:
            accessible.update(a.objectName() for a in bar.actions()
                              if a.objectName().startswith("v2"))
        for button in menu_buttons:
            self.assertIsInstance(button.menu(), QMenu)
            accessible.update(a.objectName() for a in button.menu().actions())
        self.assertEqual(all_names, accessible)
        self.assertEqual(len(all_names), 42)

        for width in (660, 800, 1024, 1280, 1600):
            with self.subTest(width=width):
                win.resize(width, 820)
                self.app.processEvents()
                for bar in bars:
                    self.assertTrue(bar.isVisible())
                    # Only explicit application commands count; Qt's hidden
                    # overflow extension button is not an action.
                    for action in bar.actions():
                        widget = bar.widgetForAction(action)
                        self.assertIsNotNone(widget, action.objectName())
                        self.assertTrue(widget.isVisible(),
                                        (width, bar.objectName(), action.objectName()))
                for button in menu_buttons:
                    self.assertTrue(button.isVisible(), (width, button.objectName()))
                    self.assertLessEqual(
                        button.mapTo(win, button.rect().topRight()).x(), win.width(),
                        (width, button.objectName()))

    def test_clicking_a_real_insert_menu_item_updates_canonical_report(self):
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtGui import QAction
        win = self.window
        win.resize(800, 820)
        self.app.processEvents()
        before = win.session.report_snapshot()
        button = win.findChild(QToolButton, "v2InsertMenu")
        menu = button.menu()
        heading = win.findChild(QAction, "v2AddHeading")
        self.assertIn(heading, menu.actions())
        self.assertTrue(heading.isEnabled())

        # A mouse event on the actual popup, not just QAction.trigger().
        QTimer.singleShot(40, lambda: QTest.mouseClick(
            menu, Qt.MouseButton.LeftButton,
            pos=menu.actionGeometry(heading).center()))
        button.showMenu()
        self.app.processEvents()
        after = win.session.report_snapshot()
        self.assertEqual(len(after.modules[0].blocks),
                         len(before.modules[0].blocks) + 1)
        self.assertEqual(type(after.modules[0].blocks[-1]).__name__,
                         "HeadingBlock")
        self.assertEqual(win.findChild(QAction, "v2UndoChange").shortcut().toString(),
                         "Ctrl+Alt+Z")
        self.assertTrue(win.branch.undo())
        self.assertEqual(win.session.report_snapshot().modules, before.modules)


    def test_shortcut_still_dispatches_menu_only_action_with_menu_closed(self):
        from unittest import mock
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtTest import QSignalSpy
        win = self.window
        import_action = win.findChild(QAction, "v2ImportPhoto")
        insert_menu = win.findChild(QToolButton, "v2InsertMenu").menu()
        self.assertIn(import_action, insert_menu.actions())
        self.assertFalse(insert_menu.isVisible())
        self.assertEqual(import_action.shortcut().toString(), "Ctrl+Shift+I")
        spy = QSignalSpy(import_action.triggered)
        with mock.patch("reportmaker.v2.branch.canvas.QFileDialog.getOpenFileNames",
                        return_value=("", "")) as chooser:
            QTest.keyClick(win, Qt.Key.Key_I,
                           Qt.KeyboardModifier.ControlModifier
                           | Qt.KeyboardModifier.ShiftModifier)
            self.app.processEvents()
            self.assertEqual(spy.count(), 1)
            chooser.assert_called_once()
        self.assertEqual(len(win.session.assets), 0)


if __name__ == "__main__":
    unittest.main()
