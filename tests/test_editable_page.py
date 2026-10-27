"""Step 2 synthetic editable-page regression (no private files or browser access)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from reportmaker.engine import ProjectEditor, module_outline
from reportmaker.export import export_project
from reportmaker.model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, TableBlock,
)
from reportmaker.page_editor import EditableDocumentPage, locate_block
from reportmaker.project_io import ReportProject, load_project, save_project
from reportmaker.rich_text import RichFormatting, TextRun
from reportmaker.visual_editor import new_report


def make_sample():
    report = new_report().report
    report.title.update_original("Synthetic inspection")
    paragraph = report.modules[0].blocks[0]
    paragraph.text.update_original("Valve 😀 test")
    paragraph.text.set_translation("de", "Ventiltest")
    paragraph.rich = RichFormatting(runs=[TextRun(0, 5, bold=True)])
    heading = HeadingBlock(LocalizedText("en", "Inspection notes"))
    table = TableBlock([[LocalizedText("en", "Old cell")]])
    table.rows[0][0].set_translation("fr", "Ancienne cellule")
    photo = PhotoBlock("synthphoto", LocalizedText("en", "Old caption"))
    photo.caption.set_translation("es", "Pie anterior")
    nested = Module(LocalizedText("en", "Subassembly"), [
        ParagraphBlock(LocalizedText("en", "Nested text"))])
    report.modules[0].blocks += [
        heading, table, photo, PageBreakBlock(), NestedModuleBlock(nested)]
    buf = BytesIO()
    Image.new("RGB", (35, 25), (40, 100, 160)).save(buf, format="PNG")
    return report, (paragraph.id, heading.id, table.id, photo.id, nested.id), {
        "synthphoto": buf.getvalue()}


class EditablePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 desktop not available")
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_edits_one_undo_and_translation_staleness(self):
        report, ids, assets = make_sample()
        editor = ProjectEditor(report)
        page = EditableDocumentPage()
        page.rebuild(editor.report, assets)
        module_id = editor.report.modules[0].id
        paragraph, heading, table, photo, nested = ids
        self.assertEqual(len(module_outline(editor.report)), 3)
        self.assertEqual(page.fields[(module_id, paragraph, "text")].toPlainText(),
                         "Valve 😀 test")
        self.assertFalse(any("summary" in key for key in page.fields))
        self.assertFalse(any("module" in key for key in page.fields))

        text = page.fields[(module_id, paragraph, "text")]
        text.moveCursor(text.textCursor().MoveOperation.End)
        text.insertPlainText(" updated")
        page.fields[(module_id, heading, "text")].insertPlainText("EDIT ")
        page.fields[(module_id, table, "table")].item(0, 0).setText("New cell")
        page.fields[(module_id, photo, "caption")].setPlainText("New caption")
        self.assertEqual(len(page.pending), 4)
        with self.assertRaisesRegex(RuntimeError, "unsaved"):
            page.rebuild(editor.report, assets)
        self.assertTrue(page.commit(editor))
        self.assertFalse(page.pending)

        changed = editor.report.modules[0].blocks
        self.assertEqual(changed[0].text.original, "Valve 😀 test updated")
        self.assertIn("de", changed[0].text.stale_languages)
        self.assertTrue(any(run.bold for run in changed[0].rich.runs))
        self.assertEqual(changed[1].text.original, "EDIT Inspection notes")
        self.assertEqual(changed[2].rows[0][0].original, "New cell")
        self.assertIn("fr", changed[2].rows[0][0].stale_languages)
        self.assertEqual(changed[3].caption.original, "New caption")
        self.assertIn("es", changed[3].caption.stale_languages)
        self.assertEqual(changed[4].id, report.modules[0].blocks[4].id)
        self.assertEqual(changed[5].module.title.original, "Subassembly")
        self.assertEqual(len(module_outline(editor.report)), 3)
        self.assertTrue(editor.undo())   # single atomic history operation
        self.assertEqual(editor.report.modules[0].blocks[0].text.original,
                         "Valve 😀 test")
        self.assertFalse(editor.report.modules[0].blocks[0].text.stale_languages)
        self.assertTrue(editor.redo())
        self.assertEqual(editor.report.modules[0].blocks[3].caption.original,
                         "New caption")

        with TemporaryDirectory() as folder:
            target = Path(folder) / "page-edit.rmproj"
            save_project(ReportProject(editor.report, assets), target)
            restored = load_project(target)
            self.assertEqual(restored.report.modules[0].blocks[0].text.original,
                             "Valve 😀 test updated")
            self.assertEqual(restored.report.modules[0].blocks[2].rows[0][0].original,
                             "New cell")
            self.assertEqual(restored.report.modules[0].blocks[3].caption.original,
                             "New caption")
            from docx import Document
            from pypdf import PdfReader
            word = Path(folder) / "page-edit.docx"
            pdf = Path(folder) / "page-edit.pdf"
            export_project(restored, word, format="docx")
            export_project(restored, pdf, format="pdf")
            word_body = " ".join(p.text for p in Document(word).paragraphs)
            pdf_body = " ".join(p.extract_text() for p in PdfReader(pdf).pages)
            self.assertIn("Valve 😀 test updated", word_body)
            self.assertIn("New cell", pdf_body)

    def test_no_imported_html_or_independent_outline(self):
        from PySide6.QtCore import QMimeData
        report, ids, assets = make_sample()
        page = EditableDocumentPage()
        page.rebuild(report, assets)
        field = page.fields[(report.modules[0].id, ids[0], "text")]
        paste = QMimeData()
        paste.setHtml('<img src="https://example.com/track"><b>unsafe</b>')
        field.insertFromMimeData(paste)
        self.assertNotIn("unsafe", field.toPlainText())
        paste.setText("safe plain text")
        paste.setHtml("<b>FORGED HTML</b>")
        field.insertFromMimeData(paste)
        self.assertIn("safe plain text", field.toPlainText())
        self.assertNotIn("FORGED HTML", field.toPlainText())
        self.assertFalse(page.fields[(report.modules[0].id, ids[0], "text")].acceptDrops())
        self.assertEqual(locate_block(report, report.modules[0].id, ids[1]).text.original,
                         "Inspection notes")

    def test_visual_controller_save_and_style_selected_from_page(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import (
            QHBoxLayout, QMainWindow, QPushButton, QVBoxLayout, QWidget,
        )
        from reportmaker.reference import manual_snapshot
        from reportmaker.visual_editor import VisualReportEditor
        with TemporaryDirectory() as folder:
            owner = QMainWindow()
            owner.settings = QSettings(str(Path(folder) / "local.ini"),
                                       QSettings.Format.IniFormat)
            root = QWidget()
            owner.setCentralWidget(root)
            row = QHBoxLayout(root)
            left = QVBoxLayout()
            center = QVBoxLayout()
            row.addLayout(left)
            row.addLayout(center)
            controller = VisualReportEditor(owner, left, center)
            controller.editor.apply(lambda report: setattr(
                report, "customer_snapshot", manual_snapshot("Synthetic customer")))
            controller.refresh()
            module = controller.report.modules[0]
            key = (module.id, module.blocks[0].id, "text")
            field = controller.page.fields[key]
            field.insertPlainText("Visible page insertion")
            self.assertTrue(controller.page.pending)
            path = Path(folder) / "direct.rmproj"
            self.assertTrue(controller.save_to_path(path))
            self.assertFalse(controller.page.pending)
            self.assertEqual(load_project(path).report.modules[0].blocks[0].text.original,
                             "Visible page insertion")
            self.assertTrue(controller.page.fields[key].toPlainText().startswith(
                "Visible page insertion"))
            # Style jumps to the same canonical block and never edits the TOC.
            controller.page.findChild(
                QPushButton, "pageStyle_" + module.blocks[0].id).click()
            self.assertEqual(controller.text_edit.toPlainText(),
                             "Visible page insertion")
            self.assertEqual(module_outline(controller.report)[0].title,
                             "Intervention")
            owner.close()

    def test_invalid_edit_rolls_back_atomically(self):
        report, ids, assets = make_sample()
        editor = ProjectEditor(report)
        page = EditableDocumentPage()
        page.rebuild(editor.report, assets)
        key = (report.modules[0].id, ids[0], "text")
        field = page.fields[key]
        field.setPlainText("new wording")
        prior = editor.report
        with patch("reportmaker.page_editor.capture_rich", return_value=(
            "new wording", RichFormatting(runs=[TextRun(0, 200, bold=True)])
        )):
            with self.assertRaises(ValueError):
                page.commit(editor)
        self.assertIs(editor.report, prior)
        self.assertTrue(page.pending)
        self.assertFalse(editor.can_undo)


if __name__ == "__main__":
    unittest.main()
