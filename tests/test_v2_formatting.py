"""M3.2 contextual rich ribbon and canonical, Unicode-safe formatting regressions.

Synthetic text only. Installed Windows DPI/keyboard/screen-reader acceptance is
a separate manual gate from the offscreen Qt tests here.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportmaker.rich_text import ParagraphStyle, RichFormatting, TextRun
from reportmaker.v2.adapters.formatting import (
    format_chars, format_paragraphs, paragraph_uniform, paragraph_value,
    selection_uniform,
    to_codepoint, to_utf16,
)
from reportmaker.v2.commands import CommandGateway
from reportmaker.v2.drafts import DraftCoordinator
from reportmaker.v2.projections import NodeAddress, find_node
from reportmaker.v2.session import PendingDraftError, ReportSession, StaleIntentError
from reportmaker.project_io import ReportProject, load_project
from test_v2_inline import sample


class PureFormattingTests(unittest.TestCase):
    def test_unicode_selection_uses_codepoints_not_qt_utf16_offsets(self):
        text = "A👷🏽B\n東京"
        self.assertEqual(to_utf16(text, 3), 5)
        self.assertEqual(to_codepoint(text, 5), 3)
        with self.assertRaisesRegex(ValueError, "surrogate"):
            to_codepoint(text, 2)
        for bad in (-1, 999, True):
            with self.subTest(offset=bad), self.assertRaises(ValueError):
                to_codepoint(text, bad)
        for bad in (-1, len(text) + 1, True):
            with self.subTest(index=bad), self.assertRaises(ValueError):
                to_utf16(text, bad)

    def test_character_selection_preserves_unselected_styles_and_normalizes(self):
        text = "Café 👷 notes"
        rich = RichFormatting([TextRun(0, 4, bold=True, italic=True)])
        first = format_chars(text, rich, 2, 7, "underline", True)
        self.assertEqual(first.runs, [
            TextRun(0, 2, bold=True, italic=True),
            TextRun(2, 4, bold=True, italic=True, underline=True),
            TextRun(4, 7, underline=True),
        ])
        self.assertFalse(selection_uniform(text, first, 0, 7, "underline"))
        self.assertTrue(selection_uniform(text, first, 2, 7, "underline"))
        second = format_chars(text, first, 2, 7, "underline", False)
        self.assertEqual(second.runs, rich.runs)
        self.assertEqual(format_chars(text, rich, 0, 4, "bold", True), rich)

    def test_size_preserves_other_attributes_and_fails_atomically(self):
        text = "abc"
        original = RichFormatting([TextRun(0, 3, bold=True, color="#0000ff")])
        new = format_chars(text, original, 1, 3, "size", 18)
        self.assertEqual(new.runs[1], TextRun(
            1, 3, size=18, bold=True, color="#0000ff"))
        for args in ((0, 0, "bold", True), (0, 4, "bold", True),
                     (0, 2, "bold", "yes"), (0, 2, "size", 2),
                     (0, 2, "color", "#123456")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                format_chars(text, original, *args)
        self.assertEqual(original.runs, [TextRun(0, 3, bold=True, color="#0000ff")])

    def test_multiline_paragraph_selection_excludes_next_start(self):
        text = "one\ntwo\nthree"
        baseline = RichFormatting([TextRun(0, 3, bold=True)])
        listed = format_paragraphs(text, baseline, 0, 8, "list_kind", "decimal")
        self.assertEqual([p.start for p in listed.paragraphs], [0, 4])
        self.assertEqual([p.list_kind for p in listed.paragraphs], ["decimal"] * 2)
        aligned = format_paragraphs(text, listed, 5, 5, "align", "center")
        self.assertEqual(paragraph_value(text, aligned, 5, "align"), "center")
        self.assertEqual(paragraph_value(text, aligned, 10, "list_kind"), "none")
        self.assertFalse(paragraph_uniform(text, listed, 0, len(text),
                                           "list_kind", "decimal"))
        self.assertTrue(paragraph_uniform(text, listed, 0, 8,
                                          "list_kind", "decimal"))
        removed = format_paragraphs(text, aligned, 0, 4, "list_kind", "none")
        self.assertEqual(paragraph_value(text, removed, 0, "list_kind"), "none")
        self.assertEqual(paragraph_value(text, removed, 5, "list_kind"), "decimal")
        self.assertEqual(removed.runs, baseline.runs)
        with self.assertRaises(ValueError):
            format_paragraphs(text, baseline, 0, 1, "align", "random")


class FormattingDraftTests(unittest.TestCase):
    def setUp(self):
        report, _, self.address = sample()
        self.session = ReportSession(ReportProject(report))
        self.gateway = CommandGateway(self.session)
        self.drafts = DraftCoordinator(self.session, self.gateway)

    def test_format_only_draft_is_atomic_undoable_and_translation_stays_fresh(self):
        before = find_node(self.session.report_snapshot(), self.address)
        self.assertTrue(self.drafts.format(self.address, 0, 10, "bold", True))
        self.assertTrue(self.drafts.is_dirty(self.address))
        self.assertEqual(self.session.revision, 0)
        self.assertEqual(find_node(self.session.report_snapshot(), self.address), before)
        with self.assertRaises(PendingDraftError):
            self.session.require_clean_drafts()
        self.assertTrue(self.drafts.commit(self.address))
        new = find_node(self.session.report_snapshot(), self.address)
        self.assertEqual(new.rich.runs, [TextRun(0, 10, bold=True)])
        self.assertEqual(new.text.translations, before.text.translations)
        self.assertFalse(new.text.stale_languages)
        self.assertTrue(self.gateway.undo(self.session.generation, self.session.revision))
        self.assertEqual(find_node(self.session.report_snapshot(), self.address), before)
        self.assertTrue(self.gateway.redo(self.session.generation, self.session.revision))
        self.assertEqual(find_node(self.session.report_snapshot(), self.address), new)

    def test_format_then_type_rebases_unmodified_runs_no_shadow_copy(self):
        self.drafts.format(self.address, 0, 10, "bold", True)
        self.drafts.update(self.address, "Inspection 👷 note")
        draft_rich = self.drafts.rich(self.address)
        self.assertEqual(draft_rich.runs, [TextRun(0, 10, bold=True)])
        self.assertTrue(self.drafts.commit(self.address))
        stored = find_node(self.session.report_snapshot(), self.address)
        self.assertEqual(stored.text.original, "Inspection 👷 note")
        self.assertEqual(stored.rich.runs, [TextRun(0, 10, bold=True)])
        self.assertIn("it", stored.text.stale_languages)

    def test_revert_and_toggle_back_do_not_modify_canonical_history(self):
        self.drafts.format(self.address, 0, 4, "italic", True)
        self.assertTrue(self.drafts.pending)
        self.drafts.format(self.address, 0, 4, "italic", False)
        self.assertFalse(self.drafts.pending)
        self.assertEqual(self.session.revision, 0)
        self.drafts.format(self.address, 0, 4, "bold", True)
        self.assertTrue(self.drafts.pending)
        self.drafts.discard(self.address)
        self.assertFalse(self.drafts.pending)
        self.assertEqual(find_node(self.session.report_snapshot(), self.address).rich.runs, [])

    def test_stale_source_rejected_and_uncommitted_format_preserved(self):
        self.drafts.format(self.address, 0, 4, "bold", True)
        self.drafts._committing = True
        try:
            from reportmaker.v2.commands import CommandIntent
            self.gateway.execute(CommandIntent(
                "set_paragraph_rich", self.address,
                {"text": "external", "rich": RichFormatting()},
                self.session.revision, self.session.generation))
        finally:
            self.drafts._committing = False
        with self.assertRaises(StaleIntentError):
            self.drafts.commit(self.address)
        self.assertTrue(self.drafts.pending)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Qt offscreen required")
class ContextualRibbonQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from reportmaker.v2.app import V2MainWindow
        report, self.title, self.address = sample()
        self.win = V2MainWindow(report)
        self.win.show()
        for _ in range(4):
            self.app.processEvents()

    def tearDown(self):
        self.win._confirm_transition = lambda: False
        self.win.close()
        self.app.processEvents()

    def focused(self, address=None):
        from PySide6.QtWidgets import QWidget
        address = address or self.address
        editor = self.win.branch.editor_for(address)
        editor.setFocus()
        for _ in range(4):
            self.app.processEvents()
        ribbon = self.win.branch._ribbons.get(address, (None,))[0]
        self.assertIsNotNone(ribbon)
        self.assertTrue(ribbon.isVisible())
        return editor, ribbon

    def action(self, object_name):
        from PySide6.QtWidgets import QToolButton
        item = self.win.branch.findChild(QToolButton, object_name)
        self.assertIsNotNone(item, object_name)
        return item

    def test_contextual_visibility_focus_and_selected_style_state(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import QWidget
        # Initial focus can vary by platform/window manager. Force the
        # non-rich title active and require any ribbons to be inactive.
        self.win.branch.editor_for(self.title).setFocus()
        for _ in range(4):
            self.app.processEvents()
        self.assertFalse(any(item.isVisible() for item, _ in
                             self.win.branch._ribbons.values()))
        editor, ribbon = self.focused()
        bold = self.action("v2RichBold")
        self.assertFalse(bold.isEnabled())
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self.app.processEvents()
        self.assertTrue(bold.isEnabled())
        bold.click()
        self.assertTrue(editor.hasFocus(), "toolbar stole editor focus")
        self.assertEqual(editor.textCursor().selectedText(), "Inspection")
        self.assertTrue(bold.isChecked())
        self.assertFalse(self.win.branch.verticalScrollBar().isVisible())
        self.win.branch.editor_for(self.title).setFocus()
        for _ in range(4):
            self.app.processEvents()
        self.assertFalse(ribbon.isVisible())

    def test_keyboard_shortcuts_combined_styles_and_format_only_save_gate(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        editor, _ = self.focused()
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        QTest.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(editor, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.action("v2RichBold").isChecked())
        self.assertTrue(self.action("v2RichItalic").isChecked())
        self.action("v2RichLarger").click()
        self.assertTrue(self.win.branch.drafts.pending)
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-saved.rmproj"
            with self.assertRaises(PendingDraftError):
                self.win.session.require_clean_drafts()
            self.assertFalse(target.exists())
            self.assertTrue(self.win.branch.apply_draft(self.address))
            for _ in range(5):
                self.app.processEvents()
            self.assertTrue(self.win.save_project(target))
            reopened = load_project(target)
            block = find_node(reopened.report, self.address)
            self.assertEqual(block.rich.runs, [
                TextRun(0, len(block.text.original), size=16, bold=True, italic=True)])
        self.assertTrue(self.win.branch.undo())
        self.assertEqual(find_node(self.win.session.report_snapshot(), self.address).rich.runs, [])
        self.assertTrue(self.win.branch.redo())

    def test_multiline_numbered_list_is_one_qt_list_and_model_roundtrips(self):
        from PySide6.QtGui import QTextCursor
        editor, _ = self.focused()
        editor.setPlainText("one\ntwo\nthree")
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        self.action("v2RichNumbers").click()
        blocks = [editor.document().findBlockByNumber(i) for i in range(3)]
        qt_lists = [block.textList() for block in blocks]
        self.assertTrue(all(item is not None for item in qt_lists))
        self.assertEqual([qt_lists[0].itemNumber(block) for block in blocks],
                         [0, 1, 2])
        self.assertTrue(self.win.branch.apply_draft(self.address))
        stored = find_node(self.win.session.report_snapshot(), self.address)
        self.assertEqual([p.list_kind for p in stored.rich.paragraphs],
                         ["decimal", "decimal", "decimal"])
        self.assertEqual([p.start for p in stored.rich.paragraphs], [0, 4, 8])

    def test_mixed_list_group_button_applies_consistently(self):
        from PySide6.QtGui import QTextCursor
        editor, _ = self.focused()
        editor.setPlainText("first\nsecond")
        # First paragraph numbered; second still ordinary.
        first = editor.textCursor()
        first.setPosition(0)
        editor.setTextCursor(first)
        self.action("v2RichNumbers").click()
        all_text = editor.textCursor()
        all_text.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(all_text)
        self.assertFalse(self.action("v2RichNumbers").isChecked())
        self.action("v2RichNumbers").click()
        self.assertTrue(self.action("v2RichNumbers").isChecked())
        self.assertEqual([p.list_kind for p in self.win.branch.drafts.rich(
            self.address).paragraphs], ["decimal", "decimal"])

    def test_invalid_styled_boundary_keeps_draft_visible_after_refresh(self):
        from reportmaker.rich_text import ParagraphStyle
        report = self.win.session.report_snapshot()
        block = find_node(report, self.address)
        block.text.update_original("First\nSecond")
        block.rich.paragraphs = [ParagraphStyle(6, align="right")]
        self.win.session.replace_project(ReportProject(report), discard_unsaved=True)
        self.win.branch._refresh()
        self.app.processEvents()
        editor = self.win.branch.editor_for(self.address)
        editor.setPlainText("First Second")
        self.assertTrue(self.win.branch.drafts.pending)
        # The preview must fail soft even when the rich rebase is impossible.
        self.win.branch._refresh()
        self.app.processEvents()
        self.assertEqual(self.win.branch.editor_for(self.address).toPlainText(),
                         "First Second")
        self.assertFalse(self.win.branch.apply_draft(self.address))
        self.assertTrue(self.win.branch.drafts.pending)
        self.win.branch.revert_draft(self.address)
        self.assertFalse(self.win.branch.drafts.pending)

    def test_rich_highlighter_tracks_typed_text_without_polluting_native_undo(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        editor, _ = self.focused()
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self.action("v2RichBold").click()
        self.assertFalse(editor.document().isUndoAvailable(),
                         "Formatting projection must not create a native undo command")
        cursor = editor.textCursor()
        cursor.clearSelection()
        cursor.setPosition(3)
        editor.setTextCursor(cursor)
        QTest.keyClicks(editor, "X")
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), "InsXpection note")
        self.assertEqual([(r.start, r.end) for r in
                          self.win.branch.drafts.rich(self.address).runs],
                         [(0, 3), (4, 6)])
        # Character highlighting must follow the rebased canonical ranges;
        # Qt must not show inherited bold on the unstyled inserted character.
        bold_offsets = {i for entry in editor.document().firstBlock().layout().formats()
                        if entry.format.fontWeight() >= 700
                        for i in range(entry.start, entry.start + entry.length)}
        self.assertEqual(bold_offsets, {0, 1, 2, 4, 5})
        self.assertTrue(editor.document().isUndoAvailable())
        editor.undo()
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), "Inspection note")
        self.assertEqual([(r.start, r.end) for r in
                          self.win.branch.drafts.rich(self.address).runs],
                         [(0, 5)])

    def test_underline_highlighter_does_not_override_heading_base_weight(self):
        from PySide6.QtGui import QTextCursor, QTextFormat
        self.win.branch._selected_module_id = self.address.module_id
        self.assertTrue(self.win.branch.add_heading(level=2))
        for _ in range(5):
            self.app.processEvents()
        report = self.win.session.report_snapshot()
        heading_id = report.modules[0].blocks[0].module.blocks[-1].id
        address = NodeAddress(report.id, self.address.module_id, heading_id, "text")
        editor, _ = self.focused(address)
        editor.setPlainText("Headline")
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        self.action("v2RichUnderline").click()
        formats = editor.document().firstBlock().layout().formats()
        underlines = [entry for entry in formats if entry.format.fontUnderline()]
        self.assertTrue(underlines)
        self.assertFalse(any(entry.format.hasProperty(QTextFormat.Property.FontWeight)
                             for entry in underlines),
                         "Underline alone must not suppress the heading's base bold")

    def test_heading_formatting_selection_preserves_level_and_unicode(self):
        from PySide6.QtGui import QTextCursor
        self.win.branch._selected_module_id = self.address.module_id
        self.assertTrue(self.win.branch.add_heading(level=4))
        for _ in range(5):
            self.app.processEvents()
        report = self.win.session.report_snapshot()
        heading = find_node(report, NodeAddress(
            report.id, self.address.module_id,
            report.modules[0].blocks[0].module.blocks[-1].id, "text"))
        address = NodeAddress(report.id, self.address.module_id, heading.id, "text")
        editor, _ = self.focused(address)
        editor.setPlainText("👷 café")
        c = editor.textCursor()
        c.setPosition(0)
        c.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(c)
        self.action("v2RichUnderline").click()
        self.assertEqual(editor.textCursor().selectedText(), "👷")
        self.assertTrue(self.win.branch.apply_draft(address))
        for _ in range(5):
            self.app.processEvents()
        stored = find_node(self.win.session.report_snapshot(), address)
        self.assertEqual(stored.level, 4)
        self.assertEqual(stored.text.original, "👷 café")
        self.assertEqual(stored.rich.runs, [TextRun(0, 1, underline=True)])
        self.assertEqual(self.win.branch.editor_for(address).textCursor().selectedText(),
                         "👷")


if __name__ == "__main__":
    unittest.main()
