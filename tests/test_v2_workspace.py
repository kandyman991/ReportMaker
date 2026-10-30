"""Two-pane workspace: split view, tabs per pane, and a tool picker per tab.

Offscreen Qt only; says nothing about native Windows behaviour.
"""
from __future__ import annotations

import json
import os
import unittest

from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node
from reportmaker.v2.workspace import (
    MAX_INSTANCES,
    MAX_TABS_PER_PANE,
    PAGE_TOOL,
    TOOLS,
    default_state,
)

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

    def test_the_window_attributes_are_the_first_copy_of_each_tool(self):
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

    def test_the_same_tool_can_be_open_in_both_panes(self):
        win = self.make(default_state(split=True))
        win.tabs.assign(win.tabs.right, 0, "modules")
        self.pump()
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["modules"]})
        left, right = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        self.assertIs(left, win.branch)
        self.assertIsNot(right, left, "each tab has its own copy")
        self.assertTrue(left.isVisible() and right.isVisible())
        self.assertNotEqual(left.owner, right.owner, "and its own draft owner")
        self.assertEqual(len(win.tabs.copies("modules")), 2)
        self.assertFalse(win.preview_tab.isVisible(), "Preview was replaced in its tab and is parked")

    def test_picking_a_tool_for_a_tab_never_takes_it_from_another_tab(self):
        win = self.make()
        win.tabs.show_tool("editor")
        win.tabs.show_tool("preview")
        self.assertEqual(self.layout_of(win)["left"], ["modules", "editor", "preview"])
        win.tabs.assign(win.tabs.left, 0, "preview")  # the Modules tab now shows a second Preview
        self.assertEqual(self.layout_of(win)["left"], ["preview", "editor", "preview"])
        first, third = win.tabs.left.widget(0), win.tabs.left.widget(2)
        self.assertIsNot(first, third)

    def test_a_tool_that_is_open_somewhere_is_selected_not_duplicated_by_the_rail(self):
        win = self.make(default_state(split=True))
        win.findChild(type(win.split_action), "rail_preview").trigger()
        self.pump()
        self.assertEqual(self.layout_of(win), {"left": ["modules"], "right": ["preview"]})
        self.assertIs(win.tabs.active_pane, win.tabs.right)

    def test_the_picker_says_where_a_tool_is_already_open(self):
        win = self.make(default_state(split=True))
        picker = win.tabs.new_tab(win.tabs.right)
        note = picker.tiles["modules"].note.text()
        self.assertIn("left pane", note)
        self.assertIn("another copy", note)
        self.assertNotIn("left pane", picker.tiles["photos"].note.text())

    def test_there_is_a_limit_to_how_many_copies_one_tool_gets(self):
        win = self.make()
        for _ in range(MAX_INSTANCES - 1):
            win.tabs.new_tab()
            win.tabs.assign(win.tabs.left, win.tabs.left.currentIndex(), "modules")
        self.assertEqual(len(win.tabs.copies("modules")), MAX_INSTANCES)
        win.tabs.new_tab()
        spare = win.tabs.left.currentIndex()
        win.tabs.assign(win.tabs.left, spare, "modules")
        self.assertEqual(len(win.tabs.copies("modules")), MAX_INSTANCES)
        self.assertEqual(win.tabs.left.tool_at(spare), "", "the tab still offers a choice")
        self.assertIn("already open", win.statusBar().currentMessage())

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
            {"split": True, "left": ["preview"] * 30, "right": ["modules"] * 30},
        ]
        for state in bad_states:
            with self.subTest(state=state):
                win = self.make(state)
                layout = self.layout_of(win)
                tools = [t for t in layout["left"] + layout["right"] if t]
                self.assertLessEqual(max((tools.count(t) for t in set(tools)), default=0),
                                     MAX_INSTANCES)
                self.assertLessEqual(len(layout["left"]), MAX_TABS_PER_PANE)
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
    """Moving a tab moves the very same copy, so it never forks the report or loses its state."""

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

    def test_split_rail_compacts_at_minimum_width_and_restores_when_wide(self):
        from PySide6.QtCore import Qt
        win = self.make({"split": True, "left": ["modules"],
                         "right": ["preview"]}, width=960)
        self.pump(10)
        self.assertEqual(win.rail.toolButtonStyle(),
                         Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.assertLessEqual(win.rail.width(), 65)
        self.assertGreaterEqual(win.branch.viewport().width(), 400)
        win.resize(1366, 800)
        self.pump(10)
        self.assertEqual(win.rail.toolButtonStyle(),
                         Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        win.resize(960, 800)
        self.pump(10)
        self.assertEqual(win.rail.toolButtonStyle(),
                         Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.assertLessEqual(win.rail.width(), 65)

    def test_modules_fits_its_half_of_the_window(self):
        for width in (960, 1100, 1366):
            win = self.make({"split": True, "left": ["modules"], "right": ["preview"]}, width=width)
            self.pump(10)
            with self.subTest(width=width):
                branch = win.branch
                self.assertEqual(branch.horizontalScrollBar().maximum(), 0,
                                 f"window={win.width()} rail={win.rail.width()} "
                                 f"viewport={branch.viewport().width()} "
                                 f"host={branch._host.width()} "
                                 f"card_min={branch._card_min_width} "
                                 f"indent={branch._gutters[-1].step} "
                                 f"depth={max(g.depth for g in branch._gutters)} "
                                 f"split={win.tabs._splitter.sizes()}")
                self.assertGreaterEqual(win.branch.viewport().width(), 400)


class SameToolInBothPanesTests(_WorkspaceCase):
    """Each tab has its own copy of a tool; copies never overwrite each other."""

    def modules_pair(self):
        win = self.make({"split": True, "left": ["modules"], "right": ["modules"]})
        report = win.session.report_snapshot()
        inner = report.modules[0].blocks[0].module
        address = NodeAddress(report.id, inner.id, inner.blocks[0].id, "text")
        return win, win.tabs.left.currentWidget(), win.tabs.right.currentWidget(), address

    @staticmethod
    def type_into(editor, text):
        from PySide6.QtTest import QTest
        editor.setFocus()
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClicks(editor, text)

    def test_two_modules_show_the_same_report_and_stage_under_different_owners(self):
        win, left, right, address = self.modules_pair()
        self.assertEqual(left.visible_nodes, right.visible_nodes)
        self.assertEqual({left.owner, right.owner}, {"branch", "branch-2"})
        self.assertIs(left.drafts, right.drafts, "one coordinator, one draft guard per session")
        self.type_into(left.editor_for(address), " LEFT")
        self.assertEqual(win.branch.drafts.draft_owner(address), left.owner)

    def test_second_modules_copy_locks_immediately_before_any_timer(self):
        win, left, right, address = self.modules_pair()
        other = right.editor_for(address)
        self.assertFalse(other.isReadOnly())
        self.type_into(left.editor_for(address), " LEFT-IMMEDIATE")
        # No qWait/processEvents: ownership notification must guard the other
        # active pane synchronously, even when layout redraws are delayed.
        self.assertEqual(win.branch.drafts.draft_owner(address), left.owner)
        self.assertTrue(other.isReadOnly())
        self.assertIn("LEFT-IMMEDIATE", other.toPlainText(),
                      "The locked copy must display the owner's draft immediately")
        before = left.drafts.text(address)
        self.type_into(other, " RIGHT-NOT-ALLOWED")
        self.assertNotIn("RIGHT-NOT-ALLOWED", other.toPlainText())
        self.assertEqual(left.drafts.text(address), before)

    def test_a_field_edited_in_one_modules_locks_in_the_other(self):
        from PySide6.QtTest import QTest
        _win, left, right, address = self.modules_pair()
        self.type_into(left.editor_for(address), " LEFT-EDIT")
        QTest.qWait(450)  # the other copy redraws once typing pauses
        other = right.editor_for(address)
        self.assertTrue(other.isReadOnly())
        self.assertIn("LEFT-EDIT", other.toPlainText())
        before = left.drafts.text(address)
        self.type_into(other, " RIGHT-EDIT")
        self.assertNotIn("RIGHT-EDIT", other.toPlainText())
        self.assertEqual(left.drafts.text(address), before)
        self.assertEqual(left.drafts.draft_owner(address), left.owner)

    def test_applying_in_one_modules_updates_the_other_and_unlocks_it(self):
        from PySide6.QtTest import QTest
        _win, left, right, address = self.modules_pair()
        self.type_into(left.editor_for(address), " LEFT-EDIT")
        QTest.qWait(450)
        self.assertTrue(left.apply_draft(address))
        QTest.qWait(450)
        other = right.editor_for(address)
        self.assertFalse(other.isReadOnly())
        self.assertIn("LEFT-EDIT", other.toPlainText())
        self.assertFalse(left.drafts.pending)

    def test_two_editors_lock_each_other_the_same_way(self):
        from PySide6.QtTest import QTest
        win = self.make({"split": True, "left": ["editor"], "right": ["editor"]})
        first, second = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        self.assertEqual({first.owner, second.owner}, {"page-editor", "page-editor-2"})
        address = next(iter(first._editors))
        self.type_into(first._editors[address], " FIRST")
        QTest.qWait(80)
        locked = second._editors[address]
        self.assertTrue(locked.isReadOnly())
        self.assertIn("FIRST", locked.toPlainText())
        self.type_into(locked, " SECOND")
        self.assertNotIn("SECOND", win.branch.drafts.text(address))

    def test_both_previews_follow_an_applied_edit(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLabel
        win = self.make({"split": True, "left": ["modules"], "right": ["preview"]})
        win.tabs.new_tab(win.tabs.left)
        win.tabs.assign(win.tabs.left, 1, "preview")
        self.assertEqual(len(win.tabs.copies("preview")), 2)
        report = win.session.report_snapshot()
        inner = report.modules[0].blocks[0].module
        address = NodeAddress(report.id, inner.id, inner.blocks[0].id, "text")
        win.branch.editor_for(address).setPlainText("Seal replaced twice")
        win.branch.apply_draft(address)
        QTest.qWait(80)
        for preview in win.tabs.copies("preview"):
            shown = " ".join(label.text() for label in preview.findChildren(QLabel))
            self.assertIn("Seal replaced twice", shown)

    def test_a_new_copy_starts_with_the_current_page_style(self):
        from dataclasses import replace

        from reportmaker.export import ExportStyle
        win = self.make()
        style = replace(ExportStyle(), footer_note="Footer for this layout")
        win._set_page_style(style)
        win.tabs.show_tool("editor")
        win.tabs.new_tab()
        win.tabs.assign(win.tabs.left, win.tabs.left.currentIndex(), "editor")
        copies = win.tabs.copies("editor")
        self.assertEqual(len(copies), 2)
        self.assertTrue(all(c.style.footer_note == "Footer for this layout" for c in copies))

    def test_all_assistant_copies_share_one_browser_profile(self):
        win = self.make({"split": True, "left": ["assistant"], "right": ["assistant"]})
        first, second = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        self.assertIsNot(first, second)
        self.assertIs(first.shared_profile, second.shared_profile)
        from unittest import mock

        from reportmaker.v2 import chat_tab
        sentinel = object()  # a real QWebEngineProfile needs Chromium, which CI avoids
        with mock.patch.object(chat_tab, "_make_profile", return_value=sentinel) as make:
            self.assertIs(first.shared_profile.get(), sentinel)
            self.assertIs(second.shared_profile.get(), sentinel)
        make.assert_called_once()

    def test_closing_an_extra_copy_deletes_it_and_stops_it_listening(self):
        win, _left, right, address = self.modules_pair()
        win.tabs.close_tab(win.tabs.right, right)
        self.pump()
        self.assertEqual(win.tabs.copies("modules"), [win.branch])
        self.assertEqual(self.layout_of(win)["right"], [""])
        # The report keeps changing without the deleted copy being told.
        win.branch.editor_for(address).setPlainText("after closing")
        self.assertTrue(win.branch.apply_draft(address))
        self.pump()

    def test_closing_the_first_copy_parks_it_and_keeps_its_state(self):
        win, _left, right, _address = self.modules_pair()
        win.branch.set_zoom(130)
        win.tabs.close_tab(win.tabs.left, win.branch)
        self.assertIn(win.branch, win.tabs.copies("modules"))
        self.assertEqual(win.branch._zoom_pct, 130)
        win.tabs.show_tool("modules")  # select the copy that is open on the right
        self.assertIs(win.tabs.currentWidget(), right)

    def test_a_closed_copy_with_unapplied_edits_is_kept_so_they_are_not_orphaned(self):
        win, _left, right, address = self.modules_pair()
        self.type_into(right.editor_for(address), " KEEP-ME")
        win.tabs.close_tab(win.tabs.right, right)
        self.pump()
        self.assertIn(right, win.tabs.copies("modules"))
        self.assertEqual(win.branch.drafts.draft_owner(address), right.owner)
        self.assertTrue(win.branch.drafts.pending)
        # Reopening Modules in an empty tab brings that same copy back with its edit.
        win.tabs.assign(win.tabs.right, 0, "modules")
        self.assertIs(win.tabs.right.currentWidget(), right)
        self.assertIn("KEEP-ME", right.editor_for(address).toPlainText())

    def test_moving_a_second_copy_to_the_other_pane_keeps_that_copy(self):
        win, _left, right, _address = self.modules_pair()
        right.set_zoom(70)
        win.tabs.move_to_other(win.tabs.right, right)
        self.assertIs(win.tabs.left.widget(1), right)
        self.assertEqual(right._zoom_pct, 70)

    def test_the_saved_layout_restores_both_copies(self):
        win, *_ = self.modules_pair()
        other = self.make(win.tabs.state())
        self.assertEqual(self.layout_of(other), {"left": ["modules"], "right": ["modules"]})
        self.assertEqual(len(other.tabs.copies("modules")), 2)


class ToolbarScopeTests(_WorkspaceCase):
    """The Module and navigation toolbars act only on a Modules tab the user can see."""

    def module_actions(self, win):
        from PySide6.QtGui import QAction
        return [a for a in (win.findChild(QAction, n) for n in win._module_action_names)
                if a is not None]

    def action(self, win, name):
        from PySide6.QtGui import QAction
        return win.findChild(QAction, name)

    def test_with_modules_visible_the_commands_are_available(self):
        win = self.make()
        self.assertIs(win.modules_target(), win.branch)
        for name in ("v2AddModule", "v2AddParagraph", "v2ZoomIn", "v2Search", "v2UndoChange"):
            self.assertTrue(self.action(win, name).isEnabled(), name)

    def test_the_toolbar_groups_are_exactly_the_modules_commands(self):
        win = self.make()
        names = set(win._module_action_names)
        self.assertEqual(
            names & {"v2NewProject", "v2OpenProject", "v2SaveProject", "v2SaveProjectAs",
                     "v2ReportInfo", "v2Translations", "v2ImportTemplate"}, set())
        for expected in ("v2AddModule", "v2Indent", "v2PastePhoto", "v2ZoomIn", "v2PanLeft",
                         "v2Contents", "v2Search", "v2RedoChange"):
            self.assertIn(expected, names)

    def test_with_another_tool_alone_on_screen_every_modules_command_is_off(self):
        win = self.make()
        win.tabs.show_tool("preview")
        self.pump()
        self.assertIsNone(win.modules_target())
        for action in self.module_actions(win):
            self.assertFalse(action.isEnabled(), action.objectName())
            self.assertIn("needs a visible Modules tab", action.toolTip())
        for name in ("v2NewProject", "v2OpenProject", "v2SaveProject", "v2ReportInfo"):
            self.assertTrue(self.action(win, name).isEnabled(), name + " belongs to the project")

    def test_the_modules_only_drop_downs_switch_off_with_their_commands(self):
        from PySide6.QtWidgets import QToolButton
        win = self.make()
        menus = ("v2InsertMenu", "v2ArrangeMenu", "v2NavigateMenu", "v2ViewMenu")
        self.assertTrue(all(win.findChild(QToolButton, n).isEnabled() for n in menus))
        win.tabs.show_tool("editor")
        self.pump()
        self.assertFalse(any(win.findChild(QToolButton, n).isEnabled() for n in menus))
        for name in ("v2ProjectMenu", "v2LanguagesMenu"):
            self.assertTrue(win.findChild(QToolButton, name).isEnabled(), name)

    def test_the_commands_come_back_when_modules_is_shown_again(self):
        win = self.make()
        win.tabs.show_tool("preview")
        win.tabs.show_tool("modules")
        self.pump()
        self.assertTrue(self.action(win, "v2AddParagraph").isEnabled())
        self.assertNotIn("needs a visible", self.action(win, "v2AddParagraph").toolTip())

    def test_a_hidden_modules_is_never_changed_even_if_a_command_is_forced(self):
        win = self.make()
        win.tabs.show_tool("preview")
        before_zoom = win.branch._zoom_pct
        before_nodes = win.branch.visible_nodes
        for name in ("v2ZoomIn", "v2AddParagraph", "v2AddModule", "v2UndoChange", "v2PanRight"):
            self.action(win, name).trigger()  # disabled: Qt does not even emit it
        self.assertEqual(win.branch._zoom_pct, before_zoom)
        # And if a callback were reached some other way it still refuses.
        self.assertIsNone(win._cmd("zoom_by", 10)())
        self.assertIsNone(win._cmd("add_paragraph")())
        self.pump()
        self.assertEqual(win.branch._zoom_pct, before_zoom)
        self.assertEqual(win.branch.visible_nodes, before_nodes)
        self.assertIn("Show Modules", win.statusBar().currentMessage())

    def test_the_command_reaches_the_visible_modules_in_the_other_pane(self):
        win = self.make(default_state(split=True))  # Modules left, Preview right
        win.tabs.set_active(win.tabs.right)
        self.pump()
        self.assertIs(win.modules_target(), win.branch)
        self.assertTrue(self.action(win, "v2ZoomIn").isEnabled())
        self.action(win, "v2ZoomIn").trigger()
        self.assertEqual(win.branch._zoom_pct, 110)

    def test_with_two_modules_visible_the_active_pane_decides(self):
        win = self.make({"split": True, "left": ["modules"], "right": ["modules"]})
        left, right = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        win.tabs.set_active(win.tabs.right)
        self.pump()
        self.assertIs(win.modules_target(), right)
        self.action(win, "v2ZoomIn").trigger()
        self.assertEqual((left._zoom_pct, right._zoom_pct), (100, 110))
        win.tabs.set_active(win.tabs.left)
        self.pump()
        self.assertIs(win.modules_target(), left)
        self.action(win, "v2ZoomOut").trigger()
        self.assertEqual((left._zoom_pct, right._zoom_pct), (90, 110))

    def test_a_modules_in_a_background_tab_is_not_a_target(self):
        win = self.make({"split": True, "left": ["modules", "preview"], "right": ["editor"]})
        win.tabs.left.setCurrentIndex(1)  # Preview on top, Modules behind it
        self.pump()
        self.assertIsNone(win.modules_target())
        self.assertFalse(self.action(win, "v2AddParagraph").isEnabled())

    def test_a_structural_command_adds_to_the_visible_copy_and_both_copies_update(self):
        win = self.make({"split": True, "left": ["modules"], "right": ["modules"]})
        left, right = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        win.tabs.set_active(win.tabs.right)
        before = len(win.session.report_snapshot().modules)
        self.action(win, "v2AddModule").trigger()
        self.pump(20)
        self.assertEqual(len(win.session.report_snapshot().modules), before + 1)
        self.assertEqual(left.visible_nodes, right.visible_nodes)

    def test_the_photos_tool_inserts_only_into_a_visible_modules(self):
        win = self.make()
        self.assertFalse(win._modules_commands.add_photo(asset_id="missing"))
        win.tabs.show_tool("photos")
        self.pump()
        self.assertIsNone(win.modules_target())
        calls = []
        win.branch.add_photo = lambda **kw: calls.append(kw) or True
        self.assertFalse(win._modules_commands.add_photo(asset_id="x"))
        self.assertEqual(calls, [], "Modules is hidden behind Photos")
        win.tabs.show_tool("modules")
        self.assertTrue(win._modules_commands.add_photo(asset_id="x"))
        self.assertEqual(calls, [{"asset_id": "x"}])

    def test_find_and_contents_need_a_visible_modules_too(self):
        win = self.make(default_state(split=True))
        win.tabs.assign(win.tabs.left, 0, "editor")  # Modules is no longer on screen
        self.pump()
        self.assertFalse(self.action(win, "v2Search").isEnabled())
        self.assertFalse(self.action(win, "v2Contents").isEnabled())
        win.search_branches()  # forced: reports instead of searching a hidden canvas
        self.assertIn("Show Modules", win.statusBar().currentMessage())

    def test_move_and_indent_follow_the_selection_of_the_visible_copy(self):
        win = self.make({"split": True, "left": ["modules"], "right": ["modules"]})
        left, right = win.tabs.left.currentWidget(), win.tabs.right.currentWidget()
        report = win.session.report_snapshot()
        first = report.modules[0].id
        left._selected_module_id = first
        right._selected_module_id = None
        left.selectionChanged.emit()
        win.tabs.set_active(win.tabs.left)
        self.pump()
        with_selection = self.action(win, "v2Focus").isEnabled()
        win.tabs.set_active(win.tabs.right)
        self.pump()
        self.assertTrue(with_selection)
        self.assertFalse(self.action(win, "v2Focus").isEnabled(),
                         "Focus follows the copy that is active, which has no selection")


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
