"""Synthetic Word-template import regression: no real customer samples or internet."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
import unittest

from docx import Document
from docx.shared import Cm, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image
from pypdf import PdfReader

from reportmaker.export import ExportStyle, export_project
from reportmaker.template_import import (
    DocumentTemplate, TemplateError, import_word_template, load_template,
    save_template, validate_template, MAX_HEADER_FOOTER_CHARS,
)
from test_m4_export import synthetic_project


def create_sample(filename: Path):
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(18)
    section.page_height = Cm(25)
    section.left_margin = Cm(1.7)
    section.right_margin = Cm(1.9)
    section.top_margin = Cm(2.7)
    section.bottom_margin = Cm(2.2)
    section.header_distance = Cm(.8)
    section.footer_distance = Cm(.7)
    doc.styles["Normal"].font.name = "Cambria"
    doc.styles["Normal"].font.size = Pt(12)
    doc.styles["Heading 1"].font.name = "Cambria"
    doc.styles["Heading 1"].font.size = Pt(17)
    header = section.header.paragraphs[0]
    header.add_run("SYNTHETIC COMPANY")
    stream = BytesIO()
    Image.new("RGB", (40, 20), (120, 50, 20)).save(stream, "PNG")
    header.add_run().add_picture(BytesIO(stream.getvalue()), width=Cm(.9))
    section.footer.paragraphs[0].text = "Lab use only"
    doc.add_paragraph("Untrusted source document body; must not enter report")
    doc.save(filename)


def mutate_package(path, edit):
    with ZipFile(path) as z:
        parts = [(x.filename, z.read(x.filename)) for x in z.infolist()]
    rebuilt = edit(parts)
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        for name, data in rebuilt:
            z.writestr(name, data)


class TemplateImportTests(unittest.TestCase):
    def test_supported_layout_roundtrip_and_export_parity(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "sample.docx"
            create_sample(source)
            original = source.read_bytes()
            converted = import_word_template(source)
            template = converted.template
            self.assertEqual(template.page_width_cm, 18)
            self.assertEqual(template.page_height_cm, 25)
            self.assertAlmostEqual(template.left_margin_cm, 1.7, places=2)
            self.assertIn("SYNTHETIC COMPANY", template.header_text)
            self.assertEqual(template.footer_text, "Lab use only")
            self.assertEqual(template.normal_font, "Cambria")
            self.assertEqual(template.normal_size_pt, 12)
            self.assertEqual(template.heading_font, "Cambria")
            self.assertEqual(template.heading_size_pt, 17)
            self.assertTrue(template.logo)
            self.assertTrue(any("body" in w.lower() for w in converted.warnings))
            stored = root / "layout.rmtemplate"
            save_template(template, stored)
            self.assertEqual(template, load_template(stored))
            profile = ExportStyle(
                template.header_text, template.footer_text, template.logo,
                template.page_width_cm, template.page_height_cm,
                template.left_margin_cm, template.right_margin_cm,
                template.top_margin_cm, template.bottom_margin_cm,
                template.header_distance_cm, template.footer_distance_cm,
                template.normal_font, template.normal_size_pt,
                template.heading_font, template.heading_size_pt)
            project = synthetic_project()
            word, pdf = root / "output.docx", root / "output.pdf"
            export_project(project, word, format="docx", style=profile)
            export_project(project, pdf, format="pdf", style=profile)
            self.assertEqual(source.read_bytes(), original)
            generated = Document(word)
            sec = generated.sections[0]
            self.assertAlmostEqual(sec.page_width / Cm(1), 18, places=2)
            self.assertAlmostEqual(sec.page_height / Cm(1), 25, places=2)
            self.assertAlmostEqual(sec.left_margin / Cm(1), 1.7, places=2)
            self.assertEqual(generated.styles["Normal"].font.name, "Cambria")
            self.assertEqual(generated.styles["Normal"].font.size.pt, 12)
            self.assertEqual(generated.styles["Heading 1"].font.size.pt, 17)
            self.assertIn("SYNTHETIC COMPANY", sec.header.paragraphs[0].text)
            self.assertIn("Lab use only", sec.footer.paragraphs[0].text)
            self.assertNotIn("Untrusted source document body", "\n".join(p.text for p in generated.paragraphs))
            pdf_pages = PdfReader(pdf).pages
            self.assertGreaterEqual(len(pdf_pages), 1)
            self.assertAlmostEqual(float(pdf_pages[0].mediabox.width), 18*72/2.54, delta=2)
            self.assertAlmostEqual(float(pdf_pages[0].mediabox.height), 25*72/2.54, delta=2)
            self.assertIn("Lab use only", pdf_pages[0].extract_text())

    def test_long_multiline_letterhead_fields_and_export_roundtrip(self):
        """Both >120-char fields and a cached Word PAGE value survive safely."""
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "synthetic-letterhead.docx"
            doc = Document()
            sec = doc.sections[0]
            sec.top_margin = Cm(3.5)
            sec.bottom_margin = Cm(3.0)
            sec.footer_distance = Cm(.7)
            header_line = "SYNTHETIC SERVICE LAB | " + "Regional Office " * 8
            footer_line = "Example Street 12, Fictional City | " + "Support Desk " * 9
            self.assertGreater(len(header_line), 120)
            self.assertGreater(len(footer_line), 120)
            sec.header.paragraphs[0].text = header_line
            sec.header.add_paragraph("Synthetic engineering department")
            footer = sec.footer.paragraphs[0]
            footer.add_run(footer_line)
            footer.add_run().add_break()
            footer.add_run("Phone: 000 000 000")
            sec.footer.add_paragraph("Test contact only")
            # Word PAGE field cached display value must never become static 9999.
            def field_run(kind):
                run = sec.footer.paragraphs[-1].add_run()
                char = OxmlElement("w:fldChar")
                char.set(qn("w:fldCharType"), kind)
                run._r.append(char)
            sec.footer.paragraphs[-1].add_run(" | Page ")
            field_run("begin")
            instruction = sec.footer.paragraphs[-1].add_run()
            field = OxmlElement("w:instrText")
            field.text = " PAGE "
            instruction._r.append(field)
            field_run("separate")
            sec.footer.paragraphs[-1].add_run("9999")
            field_run("end")
            doc.save(source)
            original = source.read_bytes()

            result = import_word_template(source)
            layout = result.template
            self.assertEqual(layout.header_text, header_line + "\nSynthetic engineering department")
            self.assertEqual(layout.footer_text, footer_line +
                             "\nPhone: 000 000 000\nTest contact only | Page ")
            self.assertNotIn("9999", layout.footer_text)
            self.assertTrue(any("Dynamic" in w for w in result.warnings))
            saved = root / "roundtrip.rmtemplate"
            save_template(layout, saved)
            self.assertEqual(load_template(saved), layout)
            style = ExportStyle(
                layout.header_text, layout.footer_text, layout.logo,
                layout.page_width_cm, layout.page_height_cm,
                layout.left_margin_cm, layout.right_margin_cm,
                layout.top_margin_cm, layout.bottom_margin_cm,
                layout.header_distance_cm, layout.footer_distance_cm,
                layout.normal_font, layout.normal_size_pt,
                layout.heading_font, layout.heading_size_pt)
            word, pdf = root / "report.docx", root / "report.pdf"
            for kind, destination in (("docx", word), ("pdf", pdf)):
                export_project(synthetic_project(), destination, format=kind, style=style)
            self.assertEqual(source.read_bytes(), original)
            dotx = root / "synthetic-letterhead.dotx"
            dotx.write_bytes(original)
            mutate_package(dotx, lambda parts: [
                (name, payload.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
                ) if name == "[Content_Types].xml" else payload)
                for name, payload in parts])
            self.assertEqual(import_word_template(dotx).template, layout)
            generated = Document(word).sections[0]
            self.assertEqual(generated.header.paragraphs[0].text, layout.header_text)
            self.assertTrue(generated.footer.paragraphs[0].text.startswith(layout.footer_text))
            text = PdfReader(pdf).pages[0].extract_text()
            self.assertIn("SYNTHETIC SERVICE LAB", text)
            self.assertIn("Support Desk", text)
            self.assertIn("Phone: 000 000 000", text)
            self.assertIn("Page 1", text)

    def test_field_limits_and_control_characters_are_explicit(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "bounded.rmtemplate"
            safe = DocumentTemplate(
                header_text="H" * MAX_HEADER_FOOTER_CHARS,
                footer_text="F" * MAX_HEADER_FOOTER_CHARS)
            save_template(safe, target)
            self.assertEqual(load_template(target), safe)
            for field in ("header_text", "footer_text"):
                bad = replace(safe, **{field: "Z" * (MAX_HEADER_FOOTER_CHARS + 1)})
                with self.subTest(field=field):
                    with self.assertRaisesRegex(TemplateError,
                                                f"{field.split('_')[0].title()} text exceeds "
                                                f"the {MAX_HEADER_FOOTER_CHARS}-character limit"):
                        validate_template(bad)
                    with self.assertRaises(TemplateError):
                        save_template(bad, target)
                    self.assertEqual(load_template(target), safe)
            too_long_doc = root / "too-long.docx"
            excessive = Document()
            excessive.sections[0].footer.paragraphs[0].text = (
                "Synthetic " * (MAX_HEADER_FOOTER_CHARS // 10 + 1))
            excessive.save(too_long_doc)
            with self.assertRaisesRegex(TemplateError,
                                        f"Footer text exceeds the {MAX_HEADER_FOOTER_CHARS}-character limit"):
                import_word_template(too_long_doc)
            for invalid in ("\x00", "\r", "\x1b"):
                with self.assertRaisesRegex(TemplateError, "Header text contains unsupported"):
                    validate_template(replace(safe, header_text=invalid))
            self.assertEqual(validate_template(
                replace(DocumentTemplate(), footer_text="first\nsecond\tthird")
            ).footer_text, "first\nsecond\tthird")

    def test_layout_dialog_edits_multiline_text_without_truncating(self):
        try:
            from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPlainTextEdit
            from reportmaker.template_dialog import edit_template_layout
        except ImportError:
            self.skipTest("Qt desktop dependencies absent")
        app = QApplication.instance() or QApplication([])
        original = DocumentTemplate(
            header_text="Regional Office " * 9,
            footer_text="Synthetic Support Office " * 8)
        def accept_with_change(dialog):
            header = dialog.findChild(QPlainTextEdit, "template_header_text")
            footer = dialog.findChild(QPlainTextEdit, "template_footer_text")
            self.assertEqual(header.toPlainText(), original.header_text)
            self.assertEqual(footer.toPlainText(), original.footer_text)
            header.setPlainText(original.header_text + "\nSecond line")
            actions = dialog.findChild(QDialogButtonBox)
            actions.accepted.emit()
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, "exec", accept_with_change):
            edited = edit_template_layout(None, original)
        self.assertEqual(edited.header_text, original.header_text + "\nSecond line")
        self.assertEqual(edited.footer_text, original.footer_text)

    def test_dotx_main_type_is_normalized_only_in_memory(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "sample.dotx"
            create_sample(path)
            def make_dotx(parts):
                return [(name, data.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
                ) if name == "[Content_Types].xml" else data)
                        for name, data in parts]
            mutate_package(path, make_dotx)
            original = path.read_bytes()
            loaded = import_word_template(path)
            self.assertEqual(loaded.template.page_height_cm, 25)
            self.assertEqual(path.read_bytes(), original)

    def test_external_relationship_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "bad.docx"
            create_sample(path)
            def link(parts):
                return [(name, payload.replace(
                    b"</Relationships>",
                    b'<Relationship Id="external" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.invalid/track" TargetMode="External"/></Relationships>'
                ) if name == "word/_rels/document.xml.rels" else payload)
                        for name, payload in parts]
            mutate_package(path, link)
            with self.assertRaisesRegex(TemplateError, "External"):
                import_word_template(path)

    def test_absolute_relationship_targets_rejected_even_without_external_mode(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "spoofed.docx"
            for mode in ('', ' TargetMode="Internal"', ' TargetMode="Bogus"'):
                create_sample(path)
                def link(parts):
                    return [(name, payload.replace(
                        b"</Relationships>",
                        ('<Relationship Id="spoof" '
                         'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                         'Target="https://example.invalid/private"' + mode +
                         '/></Relationships>').encode("utf-8")
                    ) if name == "word/_rels/document.xml.rels" else payload)
                            for name, payload in parts]
                mutate_package(path, link)
                with self.assertRaisesRegex(TemplateError, "External"):
                    import_word_template(path)

    def test_header_image_private_metadata_is_not_saved_in_profile(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new("RGB", (48, 24), "green")
            exif = image.getexif()
            exif[270] = "PRIVATE_CUSTOMER_SITE"
            raw = BytesIO()
            image.save(raw, "JPEG", exif=exif)
            self.assertIn(b"PRIVATE_CUSTOMER_SITE", raw.getvalue())
            source = root / "private.docx"
            doc = Document()
            doc.sections[0].header.paragraphs[0].add_run().add_picture(BytesIO(raw.getvalue()))
            doc.save(source)
            imported = import_word_template(source)
            self.assertNotIn(b"PRIVATE_CUSTOMER_SITE", imported.template.logo)
            output = root / "clean.rmtemplate"
            save_template(DocumentTemplate(logo=raw.getvalue()), output)
            clean = load_template(output)
            self.assertTrue(clean.logo)
            self.assertNotIn(b"PRIVATE_CUSTOMER_SITE", clean.logo)
            self.assertNotIn(b"PRIVATE_CUSTOMER_SITE", output.read_bytes())

    def test_macro_part_zip_traversal_and_xml_dtd_rejected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "bad.docx"
            create_sample(path)
            mutate_package(path, lambda parts: parts + [
                ("word/vbaProject.bin", b"not a real macro")])
            with self.assertRaisesRegex(TemplateError, "Active"):
                import_word_template(path)
            create_sample(path)
            mutate_package(path, lambda parts: parts + [("../escape", b"no")])
            with self.assertRaisesRegex(TemplateError, "path"):
                import_word_template(path)
            create_sample(path)
            mutate_package(path, lambda parts: [
                (name, b'<!DOCTYPE doc [<!ENTITY leak SYSTEM "file:///etc/passwd">]>' + data
                 if name == "word/document.xml" else data)
                for name, data in parts])
            with self.assertRaisesRegex(TemplateError, "DTD"):
                import_word_template(path)

    def test_utf16_encoded_dtd_cannot_bypass_entity_guard(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "utf16-dtd.docx"
            create_sample(path)
            evil = ('<?xml version="1.0" encoding="UTF-16"?>'
                    '<!DOCTYPE w:document [<!ENTITY sensitive "synthetic-private">]>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    'wordprocessingml/2006/main">&sensitive;</w:document>').encode("utf-16")
            mutate_package(path, lambda parts: [
                (name, evil if name == "word/document.xml" else payload)
                for name, payload in parts])
            with self.assertRaisesRegex(TemplateError, "DTD/entities"):
                import_word_template(path)

    def test_benign_zip_directories_and_corruption_handling(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "word.docx"
            create_sample(path)
            mutate_package(path, lambda parts: parts + [("additional/", b"")])
            self.assertEqual(import_word_template(path).template.page_width_cm, 18)
            path.write_bytes(b"PK" + b"broken" * 10)
            with self.assertRaises(TemplateError):
                import_word_template(path)

    def test_corrupt_profile_and_geometry_rejected_without_overwriting(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "layout.rmtemplate"
            base = DocumentTemplate()
            save_template(base, target)
            good = target.read_bytes()
            for update in (
                {"page_width_cm": 0},
                {"left_margin_cm": 7, "right_margin_cm": 7, "page_width_cm": 15},
                {"header_text": "\x00HTML injection"},
                {"normal_size_pt": float("nan")},
                {"heading_size_pt": 120},
                {"logo": b"not an image"},
            ):
                with self.assertRaises((ValueError, TypeError)):
                    save_template(replace(base, **update), target)
                self.assertEqual(target.read_bytes(), good)
            target.write_text('{"format":"unknown","layout":{},"version":1}')
            with self.assertRaises(TemplateError):
                load_template(target)
            target.write_bytes(good + b"extra")
            with self.assertRaises(TemplateError):
                load_template(target)

    def test_qt_import_selection_and_clear_is_local_and_non_destructive(self):
        try:
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import (
                QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                QMessageBox, QVBoxLayout, QWidget,
            )
            from reportmaker.visual_editor import VisualReportEditor
        except ImportError:
            self.skipTest("Qt desktop dependencies absent")
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "template.docx"
            out = root / "kept.rmtemplate"
            create_sample(source)
            window = QMainWindow()
            window.settings = QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat)
            host = QWidget()
            window.setCentralWidget(host)
            columns = QHBoxLayout(host)
            a, b = QVBoxLayout(), QVBoxLayout()
            columns.addLayout(a)
            columns.addLayout(b)
            editor = VisualReportEditor(window, a, b)
            with (patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")),
                  patch.object(QFileDialog, "getSaveFileName", return_value=(str(out), "")),
                  patch("reportmaker.visual_editor.edit_template_layout",
                        side_effect=lambda owner, template, warnings=(): template),
                  patch.object(QMessageBox, "warning",
                               side_effect=AssertionError("Unexpected template modal warning"))):
                self.assertTrue(editor.import_document_template())
            active = editor._export_style()
            self.assertEqual(active.page_width_cm, 18)
            self.assertEqual(active.heading_size_pt, 17)
            self.assertEqual(editor.page.layout_template.page_width_cm, 18)
            self.assertIn("SYNTHETIC", active.company_name)
            self.assertIsNotNone(editor.page.findChild(QLabel, "pageTemplateLogo"))
            self.assertTrue(any("SYNTHETIC COMPANY" in label.text()
                                for label in editor.page.findChildren(QLabel)))
            self.assertEqual(load_template(out).page_width_cm, 18)
            self.assertTrue(editor.clear_document_template())
            self.assertEqual(editor._export_style().page_width_cm, 21)
            self.assertTrue(out.exists())
            window.close()


if __name__ == "__main__":
    unittest.main()
