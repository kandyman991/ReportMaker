"""V2 design tokens, chrome stylesheet and workspace rail (offscreen Qt; no native-Windows claim)."""
from __future__ import annotations

import os
import unittest

from reportmaker.v2.theme import (
    APPLIED_SCHEMES, DARK, LIGHT, SCHEMES, TEXT_PAIRS, UI_PAIRS, contrast_ratio, stylesheet,
)


class TokenContrastTests(unittest.TestCase):
    def test_every_text_pair_meets_wcag_aa_in_both_schemes(self):
        for scheme, tokens in SCHEMES.items():
            for foreground, background in TEXT_PAIRS:
                with self.subTest(scheme=scheme, pair=(foreground, background)):
                    self.assertGreaterEqual(
                        contrast_ratio(tokens[foreground], tokens[background]), 4.5)

    def test_control_borders_and_focus_rings_meet_3_to_1(self):
        for scheme, tokens in SCHEMES.items():
            for foreground, background in UI_PAIRS:
                with self.subTest(scheme=scheme, pair=(foreground, background)):
                    self.assertGreaterEqual(
                        contrast_ratio(tokens[foreground], tokens[background]), 3.0)

    def test_schemes_define_the_same_tokens(self):
        self.assertEqual(LIGHT.keys(), DARK.keys())
        for tokens in SCHEMES.values():
            for name, value in tokens.items():
                self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$", name)

    def test_only_light_is_applied_until_the_canvas_is_tokenised(self):
        self.assertEqual(APPLIED_SCHEMES, ("light",))

    def test_known_ratios(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(contrast_ratio("#777777", "#777777"), 1.0, places=2)

    def test_stylesheet_uses_every_core_token_and_leaves_no_placeholder(self):
        for tokens in (LIGHT, DARK):
            sheet = stylesheet(tokens)
            for name in ("bg", "surface", "line", "text", "accent", "accent-soft"):
                self.assertIn(tokens[name], sheet, name)
            self.assertEqual(sheet.count("{"), sheet.count("}"))
            self.assertNotIn("['", sheet)
            self.assertNotIn("{t[", sheet)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class ChromeQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_stylesheet_parses_without_qt_warnings(self):
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
        from PySide6.QtWidgets import QWidget
        seen: list[str] = []
        previous = qInstallMessageHandler(lambda kind, context, message: seen.append(message))
        try:
            for tokens in (LIGHT, DARK):
                widget = QWidget()
                widget.setStyleSheet(stylesheet(tokens))
                widget.ensurePolished()
        finally:
            qInstallMessageHandler(previous)
        bad = [m for m in seen if "stylesheet" in m.lower() or "parse" in m.lower()]
        self.assertEqual(bad, [])
        self.assertIsNotNone(QtMsgType)

    def test_icons_render_for_every_state_and_unknown_names_fail(self):
        from PySide6.QtGui import QIcon
        from reportmaker.v2.icons import PATHS, icon
        for name in PATHS:
            made = icon(name, normal="#3D4B5A", checked="#0A4CA8", disabled="#52606F")
            with self.subTest(icon=name):
                self.assertFalse(made.isNull())
                for mode, state in ((QIcon.Mode.Normal, QIcon.State.Off),
                                    (QIcon.Mode.Normal, QIcon.State.On),
                                    (QIcon.Mode.Disabled, QIcon.State.Off)):
                    self.assertFalse(made.pixmap(22, 22, mode, state).isNull())
        with self.assertRaises(KeyError):
            icon("does-not-exist", normal="#000000", checked="#000000", disabled="#000000")


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class WorkspaceRailQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        self.win = V2MainWindow(load_website=False, ephemeral_browser=True)
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def rail_actions(self):
        from PySide6.QtGui import QAction
        return [a for a in self.win.rail.actions() if isinstance(a, QAction)]

    def test_rail_sits_on_the_left_and_replaces_the_tab_bar(self):
        from PySide6.QtCore import Qt
        self.assertEqual(self.win.toolBarArea(self.win.rail), Qt.ToolBarArea.LeftToolBarArea)
        self.assertEqual(self.win.rail.objectName(), "workspaceRail")
        self.assertTrue(self.win.tabs.tabBar().isHidden())
        # The tabs remain the single source of truth for the central widget.
        self.assertIs(self.win.centralWidget(), self.win.tabs)

    def test_rail_has_one_checkable_icon_action_per_workspace_in_tab_order(self):
        actions = self.rail_actions()
        self.assertEqual([a.text() for a in actions],
                         ["Modules", "Editor", "Photos", "Assistant", "Preview"])
        self.assertEqual(len(actions), self.win.tabs.count())
        for action in actions:
            self.assertTrue(action.isCheckable())
            self.assertFalse(action.icon().isNull())
            self.assertTrue(action.toolTip())
            self.assertFalse(action.objectName().startswith("v2"),
                             "rail actions must not look like V2 commands")
        self.assertEqual([self.win.tabs.widget(i) for i in range(self.win.tabs.count())],
                         [self.win.branch, self.win.editor_tab, self.win.gallery_tab,
                          self.win.chat_tab, self.win.preview_tab])

    def test_triggering_a_rail_action_switches_the_workspace(self):
        panes = [self.win.branch, self.win.editor_tab, self.win.gallery_tab,
                 self.win.chat_tab, self.win.preview_tab]
        for action, pane in zip(self.rail_actions(), panes, strict=True):
            with self.subTest(action=action.text()):
                action.trigger()
                self.app.processEvents()
                self.assertIs(self.win.tabs.currentWidget(), pane)
                self.assertTrue(action.isChecked())

    def test_changing_tab_elsewhere_moves_the_rail_highlight(self):
        self.win.tabs.setCurrentWidget(self.win.preview_tab)
        self.app.processEvents()
        checked = [a.text() for a in self.rail_actions() if a.isChecked()]
        self.assertEqual(checked, ["Preview"])
        self.win.gallery_tab.on_inserted()  # inserting a photo returns to Modules
        self.app.processEvents()
        self.assertEqual([a.text() for a in self.rail_actions() if a.isChecked()], ["Modules"])

    def test_tab_text_is_unchanged_for_existing_callers(self):
        tabs = self.win.tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Modules", "Editor", "Photo Gallery", "ChatGPT", "Preview"])

    def test_window_carries_the_light_chrome_stylesheet(self):
        self.assertEqual(self.win.styleSheet(), stylesheet(LIGHT))


if __name__ == "__main__":
    unittest.main()
