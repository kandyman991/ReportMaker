"""Two-pane workspace: split view, tabs per pane, and a tool picker per tab.

Offscreen Qt only; says nothing about native Windows behaviour.
"""
from __future__ import annotations

import json
import os
import unittest

from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node
from reportmaker.v2.workspace import PAGE_TOOL, TOOLS, default_state

TOOL_IDS = [spec.id for spec in TOOLS]


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offline Qt CI")
class _WorkspaceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def pump(self, rounds=6):
        for _ in range(rounds):
            self.app.processEvents()

    def make(self, state=None, *, width=1366, saver=None):
        from reportmaker.v2.app import V2MainWindow
        win = V2MainWindow(load_website=False, ephemeral_browser=True,
                           workspace_state=state, workspace_saver=saver)
        win.resize(width, 800)
        win.show()
        self.pump()
        self.addCleanup(self.close, win)
        return win

    def close(self, win):
        win._confirm_transition = lambda: False
        win.close()
        self.pump()

    @staticmethod
    def layout_of(win):
        """{'left': [tool or '' per tab], 'right': [...]} in tab order."""
        return {pane.side: [pane.tool_at(i) for i in range(pane.count())]
                for pane in (win.tabs.left, win.tabs.right)}

    def tool_widgets(self, win):
        return [win.branch, win.editor_tab, win.gallery_tab, win.chat_tab, win.preview_tab]


class DefaultArrangementTests(_WorkspaceCase):
    def test_without_a_saved_layout_there_is_one_pane_showing_modules(self):
        win = self.make()
        self.assertFalse(win.tabs.is_split)
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": []})
        self.assertTrue(win.tabs.right.isHidden())
        self.assertIs(win.tabs.currentWidget(), win.branch)
        self.assertIs(win.centralWidget(), win.tabs)
        self.assertEqual(win.minimumWidth(), 660)

    def test_the_first_run_layout_is_two_panes_modules_and_preview(self):
        win = self.make(default_state(split=True))
        self.assertTrue(win.tabs.is_split)
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["preview"]})
        self.assertFalse(win.tabs.right.isHidden())
        self.assertTrue(win.branch.isVisible() and win.preview_tab.isVisible())
        self.assertGreaterEqual(win.minimumWidth(), 960)

    def test_both_panes_get_a_usable_share_of_the_window(self):
        win = self.make(default_state(split=True), width=1100)
        left, right = win.tabs.left.width(), win.tabs.right.width()
        self.assertGreaterEqual(min(left, right), 400)
        self.assertLess(abs(left - right), 40, "starts as an even split")

    def test_every_tool_is_the_same_widget_wherever_it_is_shown(self):
        win = self.make(default_state(split=True))
        for tool_id, widget in zip(TOOL_IDS, self.tool_widgets(win), strict=True):
            self.assertIs(win.tabs.tool_widget(tool_id), widget)
            self.assertEqual(widget.property(PAGE_TOOL), tool_id)
        self.assertEqual(len({id(w) for w in self.tool_widgets(win)}), 5)


class PickingToolsTests(_WorkspaceCase):
    def test_a_new_tab_offers_every_tool_and_the_choice_fills_that_tab(self):
        from reportmaker.v2.workspace import ToolPicker
        win = self.make(default_state(split=True))
        picker = win.tabs.new_tab(win.tabs.right)
        self.assertIsInstance(picker, ToolPicker)
        self.assertEqual(list(picker.tiles), TOOL_IDS)
        self.assertEqual(self.layout_of(win)["right"], ["preview", ""])
        picker.tiles["photos"].click()
        self.pump()
        self.assertEqual(self.layout_of(win)["right"], ["preview", "photos"])
        self.assertIs(win.tabs.right.currentWidget(), win.gallery_tab)
        self.assertTrue(win.gallery_tab.isVisible())

    def test_each_tab_menu_lists_the_tools_and_switches_that_tab_in_place(self):
        from PySide6.QtWidgets import QMenu
        win = self.make(default_state(split=True))
        pane = win.tabs.right
        menu = pane.fill_menu(QMenu(pane), pane.widget(0))
        names = [a.objectName() for a in menu.actions() if a.objectName()]
        self.assertEqual(names, ["tabTool_" + t for t in TOOL_IDS] + ["tabMoveToOther", "tabClose"])
        checked = [a.objectName() for a in menu.actions() if a.isChecked()]
        self.assertEqual(checked, ["tabTool_preview"])
        next(a for a in menu.actions() if a.objectName() == "tabTool_editor").trigger()
        self.pump()
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["editor"]})
        self.assertTrue(win.editor_tab.isVisible())
        self.assertFalse(win.preview_tab.isVisible(), "Preview is parked, not shown twice")

    def test_every_tab_has_its_own_menu_button(self):
        from PySide6.QtWidgets import QTabBar
        win = self.make(default_state(split=True))
        for pane in (win.tabs.left, win.tabs.right):
            bar = pane.tabBar()
            for index in range(pane.count()):
                button = bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
                self.assertIsNotNone(button)
                self.assertEqual(button.objectName(), "v2TabMenu")
                self.assertIsNotNone(button.menu())

    def test_choosing_a_tool_open_elsewhere_moves_it(self):
        win = self.make(default_state(split=True))
        win.tabs.assign(win.tabs.right, 0, "modules")  # Modules was alone on the left
        self.pump()
        self.assertEqual(self.layout_of(win)["right"], ["modules"])
        self.assertEqual(self.layout_of(win)["left"], [""], "the emptied tab offers a new choice")
        self.assertTrue(win.branch.isVisible())
        self.assertFalse(win.preview_tab.isVisible())
        self.assertEqual(win.tabs.describe_location("preview"), None)

    def test_moving_within_a_pane_keeps_the_tab_count_right(self):
        win = self.make()
        win.tabs.show_tool("editor")
        win.tabs.show_tool("preview")
        self.assertEqual(self.layout_of(win)["left"], ["modules", "editor", "preview"])
        win.tabs.assign(win.tabs.left, 0, "preview")  # Preview replaces Modules' tab
        self.assertEqual(self.layout_of(win)["left"], ["preview", "editor"])

    def test_the_rail_opens_a_tool_in_a_new_tab_or_selects_the_tab_that_has_it(self):
        win = self.make()
        win.findChild(type(win.split_action), "rail_editor").trigger()
        self.pump()
        self.assertEqual(self.layout_of(win)["left"], ["modules", "editor"])
        self.assertIs(win.tabs.currentWidget(), win.editor_tab)
        win.findChild(type(win.split_action), "rail_modules").trigger()
        self.pump()
        self.assertEqual(self.layout_of(win)["left"], ["modules", "editor"], "no duplicate tab")
        self.assertIs(win.tabs.currentWidget(), win.branch)

    def test_the_rail_fills_an_empty_tab_instead_of_adding_another(self):
        win = self.make()
        win.tabs.new_tab()
        win.tabs.show_tool("photos")
        self.assertEqual(self.layout_of(win)["left"], ["modules", "photos"])

    def test_the_rail_highlights_the_tool_of_the_active_pane(self):
        win = self.make(default_state(split=True))
        checked = lambda: [a.objectName() for a in win.rail.actions()
                           if a.isCheckable() and a.isChecked() and a.objectName() != "rail_split"]
        self.assertEqual(checked(), ["rail_modules"])
        win.tabs.set_active(win.tabs.right)
        self.pump()
        self.assertEqual(checked(), ["rail_preview"])

    def test_window_wide_tab_api_still_works_for_existing_callers(self):
        win = self.make()
        tabs = win.tabs
        self.assertEqual(tabs.count(), 5)
        self.assertEqual([tabs.widget(i) for i in range(5)], self.tool_widgets(win))
        self.assertEqual([tabs.tabText(i) for i in range(5)],
                         ["Modules", "Editor", "Photo Gallery", "ChatGPT", "Preview"])
        tabs.setCurrentWidget(win.preview_tab)
        self.assertIs(tabs.currentWidget(), win.preview_tab)
        self.assertEqual(tabs.currentIndex(), 4)
        tabs.setCurrentIndex(1)
        self.assertIs(tabs.currentWidget(), win.editor_tab)
        with self.assertRaises(ValueError):
            tabs.setCurrentWidget(win.statusBar())


class ClosingAndMovingTests(_WorkspaceCase):
    def test_closing_the_last_tab_leaves_a_tool_picker_and_the_tool_stays_alive(self):
        win = self.make()
        win.tabs.close_tab(win.tabs.left, win.branch)
        self.assertEqual(self.layout_of(win)["left"], [""])
        self.assertFalse(win.branch.isVisible())
        self.assertIsNotNone(win.branch.parent(), "parked, not orphaned")
        win.tabs.show_tool("modules")
        self.assertEqual(self.layout_of(win)["left"], ["modules"])

    def test_closing_a_tab_that_is_not_the_last_just_removes_it(self):
        win = self.make()
        win.tabs.show_tool("editor")
        win.tabs.close_tab(win.tabs.left, win.editor_tab)
        self.assertEqual(self.layout_of(win)["left"], ["modules"])

    def test_closing_an_already_empty_last_tab_changes_nothing(self):
        win = self.make()
        win.tabs.close_tab(win.tabs.left, win.branch)
        picker = win.tabs.left.widget(0)
        win.tabs.close_tab(win.tabs.left, picker)
        self.assertEqual(self.layout_of(win)["left"], [""])

    def test_a_tab_moves_to_the_other_pane(self):
        win = self.make(default_state(split=True))
        win.tabs.show_tool("editor")  # joins the active (left) pane
        win.tabs.move_to_other(win.tabs.left, win.editor_tab)
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["preview", "editor"]})
        self.assertIs(win.tabs.right.currentWidget(), win.editor_tab)

    def test_moving_a_tab_with_the_split_off_turns_the_split_on(self):
        win = self.make()
        win.tabs.move_to_other(win.tabs.left, win.branch)
        self.assertTrue(win.tabs.is_split)
        self.assertIn("modules", self.layout_of(win)["right"])
        self.assertEqual(self.layout_of(win)["left"], [""])

    def test_unsplitting_brings_every_tool_back_to_the_single_pane(self):
        win = self.make(default_state(split=True))
        win.tabs.show_tool("editor")
        win.split_action.setChecked(False)
        self.pump()
        self.assertFalse(win.tabs.is_split)
        self.assertEqual(self.layout_of(win)["right"], [])
        self.assertEqual(sorted(self.layout_of(win)["left"]), ["editor", "modules", "preview"])
        self.assertTrue(win.tabs.right.isHidden())
        self.assertEqual(win.minimumWidth(), 660)
        self.assertEqual([t for t in self.layout_of(win)["left"] if not t], [])

    def test_splitting_again_seeds_the_second_pane_with_preview_or_a_picker(self):
        win = self.make()
        win.split_action.setChecked(True)
        self.pump()
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["preview"]})
        win.split_action.setChecked(False)
        win.tabs.show_tool("editor")
        win.split_action.setChecked(True)
        self.pump()
        # Preview came back into the left pane when it was unsplit, so the right pane has a picker.
        self.assertEqual(self.layout_of(win)["right"], [""])

    def test_the_split_shortcut_is_ctrl_backslash(self):
        win = self.make()
        self.assertEqual(win.split_action.shortcut().toString(), "Ctrl+\\")
        self.assertFalse(win.split_action.objectName().startswith("v2"))


class StateTests(_WorkspaceCase):
    def test_the_arrangement_round_trips_through_json(self):
        saved = []
        win = self.make(default_state(split=True), saver=saved.append)
        win.tabs.show_tool("editor")
        win.tabs.assign(win.tabs.right, 0, "photos")
        self.pump()
        state = json.loads(json.dumps(win.tabs.state()))
        self.assertEqual(state["left"], ["modules", "editor"])
        self.assertEqual(state["right"], ["photos"])
        other = self.make(state)
        self.assertEqual(self.layout_of(other), self.layout_of(win))
        self.assertTrue(other.tabs.is_split)
        self.assertTrue(saved, "the window reports layout changes so they can be remembered")
        self.assertEqual(saved[-1]["right"], ["photos"])

    def test_a_damaged_saved_layout_falls_back_instead_of_failing(self):
        bad_states = [
            {}, {"split": "yes", "left": "modules"}, {"split": True, "left": [], "right": []},
            {"left": ["nope", 7, None, "editor", "editor"], "right": ["preview", "editor"], "split": True},
            {"split": True, "left": ["modules"], "right": ["preview"], "sizes": [0, -5], "left_current": 99},
            {"split": True, "left": ["modules"], "sizes": "wide", "active": 3},
        ]
        for state in bad_states:
            with self.subTest(state=state):
                win = self.make(state)
                layout = self.layout_of(win)
                tools = [t for t in layout["left"] + layout["right"] if t]
                self.assertEqual(len(tools), len(set(tools)), "no tool twice")
                self.assertTrue(layout["left"], "the left pane is never empty")
                self.assertIsNotNone(win.tabs.currentWidget())

    def test_an_empty_saved_layout_opens_modules(self):
        for state in ({}, {"split": True, "left": [], "right": []}, {"left": ["nope"]}):
            with self.subTest(state=state):
                self.assertEqual(self.layout_of(self.make(state))["left"], ["modules"])

    def test_with_the_split_off_tools_saved_for_the_right_pane_land_on_the_left(self):
        win = self.make({"split": False, "left": ["modules"], "right": ["preview"]})
        self.assertEqual(self.layout_of(win), {"left": ["modules", "preview"], "right": []})

    def test_the_saved_state_holds_only_tool_ids_and_sizes(self):
        win = self.make(default_state(split=True))
        state = win.tabs.state()
        self.assertEqual(set(state), {"split", "left", "left_current", "right", "right_current",
                                      "sizes", "active"})
        self.assertTrue(set(state["left"] + state["right"]) <= set(TOOL_IDS))

    def test_settings_round_trip_and_ignore_garbage(self):
        import tempfile

        from PySide6.QtCore import QSettings

        from reportmaker.v2.workspace import restore_state, store_state
        with tempfile.TemporaryDirectory() as folder:
            settings = QSettings(os.path.join(folder, "layout.ini"), QSettings.Format.IniFormat)
            self.assertIsNone(restore_state(settings))
            store_state(default_state(split=True), settings)
            self.assertEqual(restore_state(settings), default_state(split=True))
            settings.setValue("v2/workspace", "{not json")
            self.assertIsNone(restore_state(settings))
            settings.setValue("v2/workspace", "[1, 2]")
            self.assertIsNone(restore_state(settings))


class SharedStateTests(_WorkspaceCase):
    """The tools are single widgets, so moving them can never fork the report."""

    def test_moving_modules_keeps_its_unapplied_edit(self):
        from PySide6.QtTest import QTest
        win = self.make(default_state(split=True))
        report = win.session.report_snapshot()
        module = report.modules[0]
        address = NodeAddress(report.id, module.blocks[0].module.id,
                              module.blocks[0].module.blocks[0].id, "text")
        editor = win.branch.editor_for(address)
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, " moved edit")
        self.assertEqual(win.branch.drafts.draft_owner(address), "branch")
        win.tabs.move_to_other(win.tabs.left, win.branch)
        self.pump()
        self.assertEqual(win.branch.drafts.draft_owner(address), "branch")
        self.assertIn("moved edit", win.branch.drafts.text(address))
        self.assertEqual(find_node(win.session.report_snapshot(), address).text.original,
                         "Example inspection note. Edit me directly in the branch.")

    def test_preview_beside_modules_follows_an_applied_edit_without_switching_tabs(self):
        from PySide6.QtTest import QTest
        win = self.make(default_state(split=True))
        report = win.session.report_snapshot()
        inner = report.modules[0].blocks[0].module
        address = NodeAddress(report.id, inner.id, inner.blocks[0].id, "text")
        editor = win.branch.editor_for(address)
        editor.setPlainText("Pump bearing replaced")
        self.assertTrue(win.branch.apply_draft(address))
        QTest.qWait(60)
        from PySide6.QtWidgets import QLabel
        shown = " ".join(label.text() for label in win.preview_tab.findChildren(QLabel))
        self.assertIn("Pump bearing replaced", shown)
        self.assertIs(win.tabs.left.currentWidget(), win.branch, "no tab switch was needed")

    def test_a_tool_is_activated_when_it_becomes_visible_not_before(self):
        win = self.make(default_state(split=True))
        calls = []
        win.chat_tab.activate = lambda: calls.append("assistant")
        self.pump()
        win.tabs.show_tool("photos")
        self.assertEqual(calls, [])
        win.tabs.show_tool("assistant")
        self.assertEqual(calls, ["assistant"])
        win.tabs.show_tool("modules")
        win.tabs.show_tool("assistant")
        self.assertEqual(calls, ["assistant", "assistant"])

    def test_clicking_in_a_pane_makes_it_the_active_one(self):
        win = self.make(default_state(split=True))
        self.assertIs(win.tabs.active_pane, win.tabs.left)
        win.preview_tab.setFocus()
        self.pump()
        win.tabs.right.currentWidget().setFocus()
        win.tabs.set_active(win.tabs.right)
        self.assertIs(win.tabs.active_pane, win.tabs.right)
        self.assertEqual(win.tabs.left.property("active"), False)
        self.assertEqual(win.tabs.right.property("active"), True)

    def test_inserting_a_photo_returns_to_modules_wherever_it_is(self):
        win = self.make(default_state(split=True))
        win.tabs.assign(win.tabs.right, 0, "photos")
        win.gallery_tab.on_inserted()
        self.assertIs(win.tabs.left.currentWidget(), win.branch)


@unittest.skipUnless(hasattr(DraftCoordinator, "subscribe_changes"),
                     "needs the Editor/Modules draft sync from PR #114")
class SideBySideInterferenceTests(_WorkspaceCase):
    """Modules and Editor visible at once: neither may let you type over the other's draft."""

    def setUp(self):
        self.win = self.make({"split": True, "left": ["modules"], "right": ["editor"]})
        report = self.win.session.report_snapshot()
        inner = report.modules[0].blocks[0].module
        self.address = NodeAddress(report.id, inner.id, inner.blocks[0].id, "text")

    def type_into(self, editor, text):
        from PySide6.QtTest import QTest
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, text)

    def test_editor_beside_modules_locks_the_field_being_edited_in_modules(self):
        from PySide6.QtTest import QTest
        self.assertTrue(self.win.branch.isVisible() and self.win.editor_tab.isVisible())
        self.type_into(self.win.branch.editor_for(self.address), " LEFT-EDIT")
        QTest.qWait(60)
        page = self.win.editor_tab._editors[self.address]
        self.assertTrue(page.isReadOnly())
        self.assertIn("LEFT-EDIT", page.toPlainText())

    def test_modules_beside_editor_locks_the_field_being_edited_in_the_editor(self):
        from PySide6.QtTest import QTest
        self.type_into(self.win.editor_tab._editors[self.address], " RIGHT-EDIT")
        self.assertEqual(self.win.branch.drafts.draft_owner(self.address), "page-editor")
        QTest.qWait(450)  # Modules redraws once typing pauses
        field = self.win.branch.editor_for(self.address)
        self.assertTrue(field.isReadOnly())
        self.assertIn("RIGHT-EDIT", field.toPlainText())

    def test_modules_fits_its_half_of_the_window(self):
        for width in (960, 1100, 1366):
            win = self.make({"split": True, "left": ["modules"], "right": ["preview"]}, width=width)
            self.pump(10)
            with self.subTest(width=width):
                self.assertEqual(win.branch.horizontalScrollBar().maximum(), 0)
                self.assertGreaterEqual(win.branch.viewport().width(), 400)


class EditorPageWidthTests(_WorkspaceCase):
    def test_the_editor_page_uses_the_printable_width_and_does_not_clip_text(self):
        from PySide6.QtWidgets import QFrame, QPlainTextEdit
        for width in (1366, 960):
            win = self.make(default_state(split=True), width=width)
            win.tabs.assign(win.tabs.right, 0, "editor")
            self.pump(20)
            paper = win.editor_tab.findChild(QFrame, "v2DocumentPaper")
            viewport = win.editor_tab.scroll.viewport().width()
            with self.subTest(width=width):
                self.assertGreater(paper.width(), 0.9 * min(paper.maximumWidth(), viewport))
                for field in win.editor_tab.findChildren(QPlainTextEdit):
                    if field.isVisible():
                        self.assertGreaterEqual(field.height(), field.sizeHint().height() - 1)


if __name__ == "__main__":
    unittest.main()
