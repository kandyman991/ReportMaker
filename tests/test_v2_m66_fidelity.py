"""M6.6 initial Word/table/paper fidelity gates; synthetic data only."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm
from pypdf import PdfReader

from reportmaker.export import ExportStyle, export_project
from reportmaker.engine import module_outline
from reportmaker.model import LocalizedText, TableBlock
from test_m4_export import synthetic_project


class WordPrintGeometryTests(unittest.TestCase):
    def setUp(self):
        self.project = synthetic_project()
        self.original = deepcopy(self.project)
        self.style = ExportStyle(
            page_width_cm=18, page_height_cm=25,
            left_margin_cm=1.8, right_margin_cm=2.2,
            top_margin_cm=2.1, bottom_margin_cm=1.8,
            normal_font="Calibri", normal_size_pt=12,
            heading_font="Calibri", heading_size_pt=19,
        )

    def test_word_info_and_content_tables_have_fixed_printable_grid(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "word.docx"
            export_project(self.project, target, format="docx", style=self.style)
            doc = Document(target)
            self.assertAlmostEqual(doc.sections[0].page_width / Cm(1), 18, places=2)
            self.assertAlmostEqual(doc.sections[0].left_margin / Cm(1), 1.8, places=2)
            self.assertEqual(doc.styles["Normal"].font.size.pt, 12)
            self.assertEqual(doc.styles["Heading 1"].font.size.pt, 19)
            expected = Cm(14).twips
            self.assertGreaterEqual(len(doc.tables), 2)
            for table in doc.tables:
                with self.subTest(columns=len(table.columns)):
                    self.assertFalse(table.autofit)
                    width = table._tbl.tblPr.xpath("./w:tblW")
                    self.assertEqual(len(width), 1)
                    self.assertEqual(width[0].get(qn("w:type")), "dxa")
                    self.assertLessEqual(abs(int(width[0].get(qn("w:w"))) - expected), 2)
                    columns = sum(col.width.twips for col in table.columns)
                    self.assertLessEqual(abs(columns - expected), len(table.columns)+1)
        self.assertEqual(self.project, self.original)

    def test_wide_and_long_tables_remain_editable_and_pdf_flows_on_real_pages(self):
        # The first row is DATA, not an invented repeating header.
        words = [[LocalizedText("it", "R%02d" % i) for i in range(9)]
                 for _ in range(75)]
        self.project.report.modules[0].blocks.append(TableBlock(words))
        with TemporaryDirectory() as directory:
            word = Path(directory) / "many.docx"
            pdf = Path(directory) / "many.pdf"
            export_project(self.project, word, format="docx", style=self.style)
            export_project(self.project, pdf, format="pdf", style=self.style)
            doc = Document(word)
            table = doc.tables[-1]
            self.assertEqual(len(table.columns), 9)
            self.assertEqual(len(table.rows), 75)
            self.assertFalse(table.autofit)
            self.assertEqual(table.cell(0, 0).text, "R00")
            pages = PdfReader(pdf).pages
            self.assertGreaterEqual(len(pages), 2)
            self.assertAlmostEqual(float(pages[0].mediabox.width), Cm(18).pt, delta=1)
            self.assertAlmostEqual(float(pages[0].mediabox.height), Cm(25).pt, delta=1)


class RichWordFidelityTests(unittest.TestCase):
    def test_alpha_decimal_bullets_continue_and_restart_in_editable_word_numbering(self):
        from docx.oxml.ns import qn
        from reportmaker.model import ParagraphBlock, LocalizedText
        from reportmaker.rich_text import RichFormatting, ParagraphStyle

        project = synthetic_project()
        sequence = [
            ("Decimal one", "decimal"),
            ("Decimal two", "decimal"),
            ("Plain separator", "none"),
            ("Restart decimal", "decimal"),
            ("Lower one", "lower-alpha"),
            ("Lower two", "lower-alpha"),
            ("Upper one", "upper-alpha"),
            ("Upper two", "upper-alpha"),
            ("Bullet one", "bullet"),
            ("Bullet two", "bullet"),
        ]
        text = "\n".join(label for label, _ in sequence)
        specs = []
        index = 0
        for label, kind in sequence:
            if kind != "none":
                specs.append(ParagraphStyle(index, list_kind=kind))
            index += len(label) + 1
        module = project.report.modules[0]
        module.blocks[0] = ParagraphBlock(
            LocalizedText("it", text), rich=RichFormatting(paragraphs=specs))
        module.blocks.insert(1, ParagraphBlock(
            LocalizedText("it", "Bullet three\nOrdinary ending"),
            rich=RichFormatting(paragraphs=[ParagraphStyle(0, list_kind="bullet")])))
        original = deepcopy(project)
        with TemporaryDirectory() as directory:
            dest = Path(directory) / "lists.docx"
            export_project(project, dest, format="docx")
            doc = Document(dest)
            expected = sequence + [("Bullet three", "bullet"),
                                   ("Ordinary ending", "none")]
            found = {paragraph.text: paragraph for paragraph in doc.paragraphs
                     if paragraph.text in dict(expected)}
            self.assertEqual(set(found), {text for text, _ in expected})
            root = doc.part.numbering_part.element
            numbering = {int(num.get(qn("w:numId"))):
                         int(num.xpath("./w:abstractNumId")[0].get(qn("w:val")))
                         for num in root.xpath("./w:num")}
            formats = {int(abst.get(qn("w:abstractNumId"))):
                       abst.find(qn("w:lvl")).find(qn("w:numFmt")).get(qn("w:val"))
                       for abst in root.xpath("./w:abstractNum")}
            groups = []
            for label, kind in expected:
                numpr = found[label]._p.pPr.numPr
                if kind == "none":
                    self.assertIsNone(numpr, label)
                    groups.append(None)
                    continue
                self.assertIsNotNone(numpr, label)
                number = int(numpr.numId.val)
                self.assertEqual(formats[numbering[number]], {
                    "decimal": "decimal", "lower-alpha": "lowerLetter",
                    "upper-alpha": "upperLetter", "bullet": "bullet"}[kind])
                groups.append(number)
            self.assertEqual(groups[0], groups[1])
            self.assertNotEqual(groups[0], groups[3])  # reset after plain
            self.assertNotEqual(groups[3], groups[4])  # kind change
            self.assertEqual(groups[4], groups[5])
            self.assertNotEqual(groups[5], groups[6])
            self.assertEqual(groups[6], groups[7])
            self.assertEqual(groups[8], groups[9])
            self.assertEqual(groups[9], groups[10])  # next canonical block
            self.assertIsNone(groups[-1])
        self.assertEqual(project, original)

    def test_run_size_line_pitch_heading_flow_and_manual_page_break(self):
        from docx.shared import Pt
        from reportmaker.model import ParagraphBlock, HeadingBlock, LocalizedText
        from reportmaker.rich_text import RichFormatting, TextRun, ParagraphStyle
        project = synthetic_project()
        module = project.report.modules[0]
        module.blocks[0] = ParagraphBlock(
            LocalizedText("it", "Large text normal text"),
            rich=RichFormatting(
                runs=[TextRun(0, 10, size=28, bold=True, color="#336699")],
                paragraphs=[ParagraphStyle(0, align="justify", line_height=1.5)]))
        child = module.blocks[1].module
        child.blocks[-1] = HeadingBlock(
            LocalizedText("it", "Rich heading"), level=2,
            rich=RichFormatting(paragraphs=[ParagraphStyle(0, line_height=1.25)]))
        style = ExportStyle(heading_font="Cambria", heading_size_pt=24,
                            normal_font="Calibri", normal_size_pt=12)
        before = deepcopy(project)
        with TemporaryDirectory() as directory:
            word = Path(directory) / "rich.docx"
            pdf = Path(directory) / "rich.pdf"
            export_project(project, word, format="docx", style=style)
            export_project(project, pdf, format="pdf", style=style)
            doc = Document(word)
            large = next(p for p in doc.paragraphs
                         if p.text == "Large text normal text")
            self.assertAlmostEqual(large.paragraph_format.line_spacing.pt,
                                   28 * 1.4 * 1.5, delta=.1)
            self.assertEqual(large.paragraph_format.alignment, 3)  # JUSTIFY
            self.assertEqual(large.runs[0].font.size.pt, 28)
            rich = next(p for p in doc.paragraphs if p.text == "Rich heading")
            self.assertTrue(rich.paragraph_format.keep_with_next)
            self.assertEqual(rich.runs[0].font.size.pt, 24 - 2)
            self.assertEqual(rich.runs[0].font.name, "Cambria")
            self.assertEqual(doc.styles["Heading 1"].font.size.pt, 24)
            self.assertEqual(doc.styles["Heading 2"].font.size.pt, 23)
            self.assertEqual(doc.styles["Heading 3"].font.size.pt, 22)
            self.assertEqual(doc.styles["Heading 3"].font.name, "Cambria")
            self.assertAlmostEqual(rich.paragraph_format.line_spacing.pt,
                                   22 * 1.4 * 1.25, delta=.1)
            module_heading = next(p for p in doc.paragraphs
                                  if p.text == "1 Verifica linea")
            self.assertTrue(module_heading.paragraph_format.keep_with_next)
            self.assertEqual(len(PdfReader(pdf).pages) >= 3, True)
            self.assertIn("Rich heading", "\n".join(
                page.extract_text() for page in PdfReader(pdf).pages))
        self.assertEqual(project, before)

    def test_word_page_fields_and_bookmarks_are_ready_for_native_repagination(self):
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        from docx.oxml.ns import qn
        project = synthetic_project()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "fields.docx"
            export_project(project, target, format="docx")
            with ZipFile(target) as archive:
                settings = ET.fromstring(archive.read("word/settings.xml"))
                body = ET.fromstring(archive.read("word/document.xml"))
                footer_names = [name for name in archive.namelist()
                                if name.startswith("word/footer") and
                                name.endswith(".xml")]
                self.assertTrue(footer_names)
                footers = [ET.fromstring(archive.read(name)) for name in footer_names]
            update_fields = settings.find(".//" + qn("w:updateFields"))
            self.assertIsNotNone(update_fields)
            self.assertEqual(update_fields.get(qn("w:val")), "true")
            refs = [node.text or "" for node in body.iter(qn("w:instrText"))
                    if "PAGEREF" in (node.text or "")]
            self.assertEqual(len(refs), len(module_outline(project.report)))
            bookmarks = {element.get(qn("w:name"))
                         for element in body.iter(qn("w:bookmarkStart"))}
            self.assertTrue(bookmarks)
            for instruction in refs:
                bookmark = instruction.split("PAGEREF", 1)[1].strip().split()[0]
                self.assertIn(bookmark, bookmarks)
            footer_fields = [node.text or "" for footer in footers
                             for node in footer.iter(qn("w:instrText"))]
            self.assertTrue(any(text.strip() == "PAGE" for text in footer_fields))
            # A "?": Word's PAGEREF placeholder before Word paginates, not
            # a fabricated page number or evidence of Word page rendering.

    def test_explicit_word_fonts_cover_east_asian_and_complex_script_runs(self):
        from reportmaker.model import ParagraphBlock, LocalizedText
        from reportmaker.rich_text import RichFormatting, TextRun
        from docx.oxml.ns import qn

        project = synthetic_project()
        source = "日本語測定 — valve"
        project.report.modules[0].blocks[0] = ParagraphBlock(
            LocalizedText("it", source), rich=RichFormatting(
                runs=[TextRun(0, 5, family="Cambria", bold=True)]))
        before = deepcopy(project)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "fonts.docx"
            export_project(project, target, format="docx",
                           style=ExportStyle(normal_font="DejaVu Sans",
                                             heading_font="Cambria"))
            word = Document(target)
            normal_fonts = word.styles["Normal"]._element.rPr.rFonts
            for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                self.assertEqual(normal_fonts.get(qn("w:" + attr)),
                                 "DejaVu Sans")
            text = next(p for p in word.paragraphs if p.text == source)
            runfonts = text.runs[0]._r.rPr.rFonts
            for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                self.assertEqual(runfonts.get(qn("w:" + attr)), "Cambria")
            self.assertEqual(text.text, source)
        self.assertEqual(project, before)

    def test_annotated_photo_and_page_break_are_retained_in_both_outputs(self):
        from reportmaker.model import PhotoMark, PhotoVisual
        from reportmaker.v2.visual_export import annotated_png
        project = synthetic_project()
        child = project.report.modules[0].blocks[1].module
        photo = child.blocks[1]
        photo.visual = PhotoVisual(
            width_pct=80, alignment="center",
            marks=[PhotoMark("arrow", .1, .2, .8, .75, color="#dd2233")])
        before = deepcopy(project)
        style = ExportStyle(page_width_cm=17, page_height_cm=24,
                            left_margin_cm=1.6, right_margin_cm=1.6,
                            top_margin_cm=2, bottom_margin_cm=1.8)
        with TemporaryDirectory() as directory:
            word = Path(directory) / "annotated.docx"
            pdf = Path(directory) / "annotated.pdf"
            for fmt, target in (("docx", word), ("pdf", pdf)):
                export_project(project, target, format=fmt, style=style,
                               visual_renderer=annotated_png)
            doc = Document(word)
            self.assertEqual(len(doc.inline_shapes), 1)
            self.assertTrue(any("w:type=\"page\"" in p._p.xml or
                                "<w:br w:type=\"page\"" in p._p.xml
                                for p in doc.paragraphs))
            text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
            self.assertIn("Dettagli", text)
            self.assertIn("Foto dimostrativa", text)
        self.assertEqual(project, before)


class DeepReportFidelityTests(unittest.TestCase):
    def test_deep_ordered_modules_and_multiline_tables_export_without_mutation(self):
        from reportmaker.model import Module, NestedModuleBlock, ParagraphBlock
        project = synthetic_project()
        parent = project.report.modules[-1]
        for level in range(18):
            child = Module(
                LocalizedText("it", "Nested fidelity level " + str(level)),
                [ParagraphBlock(LocalizedText(
                    "it", ("Unicode inspection café 日本語 " * 5) + str(level)))])
            if level % 4 == 0:
                child.blocks.append(TableBlock([[
                    LocalizedText("it", f"Value {level}"),
                    LocalizedText("it", "Multiple readings\nVerified status"),
                ]]))
            parent.blocks.append(NestedModuleBlock(child))
            parent = child
        original = deepcopy(project)
        with TemporaryDirectory() as directory:
            docx = Path(directory) / "nested.docx"
            pdf = Path(directory) / "nested.pdf"
            for fmt, dest in (("docx", docx), ("pdf", pdf)):
                export_project(project, dest, format=fmt)
            headings = [p.text for p in Document(docx).paragraphs]
            body = "\n".join(p.extract_text() for p in PdfReader(pdf).pages)
            for level in range(18):
                title = "Nested fidelity level " + str(level)
                self.assertTrue(any(title in h for h in headings), title)
                self.assertIn(title, body)
            body_start = headings.index("2 Prova")
            first_child = next(i for i, heading in enumerate(headings)
                               if i > body_start and "Nested fidelity level 0" in heading)
            last_child = next(i for i, heading in enumerate(headings)
                              if i > body_start and "Nested fidelity level 17" in heading)
            self.assertLess(body_start, first_child)
            self.assertLess(first_child, last_child)
            self.assertLess(last_child, headings.index("Conclusioni"))
        self.assertEqual(project, original)

    def test_tight_template_pdf_overflow_preserves_existing_customer_file(self):
        from reportmaker.export import ExportError
        project = synthetic_project()
        project.report.modules[0].blocks.append(TableBlock([[
            LocalizedText("it", "Synthetic oversized row\n" * 340)]]))
        style = ExportStyle(page_width_cm=15, page_height_cm=20,
                            left_margin_cm=2, right_margin_cm=2,
                            top_margin_cm=2.5, bottom_margin_cm=1.8)
        with TemporaryDirectory() as directory:
            pdf = Path(directory) / "user-existing.pdf"
            pdf.write_bytes(b"EXISTING CUSTOMER FILE")
            with self.assertRaisesRegex(ExportError, "does not fit"):
                export_project(project, pdf, format="pdf", style=style)
            self.assertEqual(pdf.read_bytes(), b"EXISTING CUSTOMER FILE")
            self.assertFalse(list(Path(directory).glob(".reportmaker-export-*")))


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Offscreen Qt geometry; real Windows DPI acceptance separate")
class NaturalPageFidelityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_paper_width_and_margins_scale_together_without_fixed_500px_minimum(self):
        from reportmaker.v2.editor_tab import NaturalPagePaper
        style = ExportStyle(page_width_cm=18, left_margin_cm=2.5,
                            top_margin_cm=3, right_margin_cm=1.5,
                            bottom_margin_cm=2)
        paper = NaturalPagePaper(style)
        try:
            # No Python attribute may mask QWidget.style() / native theming.
            self.assertIsNotNone(paper.style())
            for width in (650, 310):
                paper.resize(width, 250)
                paper.show()
                self.app.processEvents()
                self.assertEqual(paper.width(), width)
                left, top, right, bottom = paper.flow.getContentsMargins()
                self.assertAlmostEqual(left, width * 2.5/18, delta=2)
                self.assertAlmostEqual(top, width * 3/18, delta=2)
                self.assertAlmostEqual(right, width * 1.5/18, delta=2)
                self.assertAlmostEqual(bottom, width * 2/18, delta=2)
                self.assertLess(left + right, width)
            self.assertEqual(paper.maximumWidth(), 720)
        finally:
            paper.close()

    def test_page_editor_applies_template_font_without_mutating_canonical_rich_text(self):
        from reportmaker.v2.app import V2MainWindow
        from reportmaker.v2.projections import NodeAddress
        project = synthetic_project()
        original = deepcopy(project.report)
        style = ExportStyle(normal_font="DejaVu Sans", normal_size_pt=13,
                            heading_font="DejaVu Sans", heading_size_pt=21)
        window = V2MainWindow(project=project, load_website=False,
                              ephemeral_browser=True)
        try:
            window.editor_tab.set_style(style)
            for _ in range(6):
                self.app.processEvents()
            child = original.modules[0].blocks[1].module
            paragraph = child.blocks[0]
            heading = child.blocks[-1]
            para_addr = NodeAddress(original.id, child.id, paragraph.id, "text")
            head_addr = NodeAddress(original.id, child.id, heading.id, "text")
            self.assertEqual(
                window.editor_tab._editors[para_addr].font().pointSizeF(), 13)
            self.assertEqual(
                window.editor_tab._editors[head_addr].font().pointSizeF(), 21)
            self.assertTrue(window.editor_tab._editors[head_addr].font().bold())
            self.assertEqual(window.session.report_snapshot(), original)
            self.assertFalse(window.session._editor.can_undo)
        finally:
            window._confirm_transition = lambda: False
            window.close()
            self.app.processEvents()

    def test_table_grows_on_live_cell_edit_with_inner_scrollbars_disabled(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTableWidgetItem
        from reportmaker.v2.editor_tab import NaturalPageTable
        table = NaturalPageTable(1, 1)
        try:
            table.resize(310, 90)
            table.setItem(0, 0, QTableWidgetItem("short"))
            table.show()
            self.app.processEvents()
            before = table.sizeHint().height()
            table.item(0, 0).setText("Long synthetic table cell text " * 60)
            self.app.processEvents()
            self.assertGreater(table.sizeHint().height(), before)
            self.assertEqual(table.verticalScrollBarPolicy(),
                             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(table.horizontalScrollBarPolicy(),
                             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        finally:
            table.close()


if __name__ == "__main__":
    unittest.main()
